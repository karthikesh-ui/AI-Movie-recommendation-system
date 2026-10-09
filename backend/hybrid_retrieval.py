"""Failure-isolated retrieval for the additive hybrid recommendation endpoint."""

from __future__ import annotations

import copy
import re
from typing import Any

import pandas as pd

from movie_candidate import (
    MovieCandidate,
    checked_at,
    local_candidate,
    normalize_title,
    watchmode_search_candidate,
    watchmode_sources,
)
from nl_pipeline import recommend_from_intent


LATEST_WORDS = re.compile(r"\b(latest|recent|recently released|new|upcoming)\b", re.I)
OTT_WORDS = re.compile(r"\b(where can i watch|where.*watch|stream(?:ing)?|ott|available to watch)\b", re.I)
SIMILARITY_WORDS = re.compile(r"\b(like|similar to|movies? like)\b", re.I)


RECOMMENDATION_SOURCES = frozenset({"tmdb", "local", "hybrid"})


def normalize_recommendation_source(value: str | None) -> str:
    """Return a safe, explicit source choice; TMDB is the A9 default."""
    source = str(value or "tmdb").strip().casefold()
    return source if source in RECOMMENDATION_SOURCES else "tmdb"


def detect_mode(text: str, title: str | None = None) -> str:
    if OTT_WORDS.search(text) and LATEST_WORDS.search(text):
        return "LATEST_OTT"
    if OTT_WORDS.search(text):
        return "OTT_AVAILABILITY"
    if LATEST_WORDS.search(text):
        return "LATEST"
    if title or SIMILARITY_WORDS.search(text):
        return "SIMILARITY"
    return "GENERAL"


def _candidate_key(candidate: MovieCandidate) -> tuple[str, str]:
    for field, value in (("imdb", candidate.imdb_id), ("tmdb", candidate.tmdb_id), ("watchmode", candidate.watchmode_id)):
        if value is not None:
            return field, str(value)
    # Unknown years deliberately do not merge by title: it protects remakes.
    if candidate.normalized_title and candidate.year is not None:
        return "title_year", f"{candidate.normalized_title}|{candidate.year}"
    return "unique", str(id(candidate))


def _merge(primary: MovieCandidate, secondary: MovieCandidate) -> MovieCandidate:
    """Combine only complementary data after a conservative identity decision."""
    for field in ("original_title", "year", "overview", "poster_url", "imdb_id", "tmdb_id", "watchmode_id", "release_date", "runtime", "rating", "rating_source", "availability_region", "availability_checked_at"):
        if getattr(primary, field) is None:
            setattr(primary, field, getattr(secondary, field))
    for field in ("genres", "language", "provider", "data_source"):
        setattr(primary, field, list(dict.fromkeys(getattr(primary, field) + getattr(secondary, field))))
    for source in secondary.streaming_sources:
        if source not in primary.streaming_sources:
            primary.streaming_sources.append(source)
    if secondary.availability_status != "not_checked":
        primary.availability_status = secondary.availability_status
    if primary.freshness_status == "release_date_missing":
        primary.freshness_status = secondary.freshness_status
    return primary


def deduplicate(candidates: list[MovieCandidate]) -> list[MovieCandidate]:
    merged: dict[tuple[str, str], MovieCandidate] = {}
    for candidate in candidates:
        key = _candidate_key(candidate)
        if key in merged:
            _merge(merged[key], candidate)
        else:
            merged[key] = candidate
    return list(merged.values())


def _local_general(movies, intent: dict[str, Any], limit: int) -> list[MovieCandidate]:
    if movies is None:
        return []
    rows = recommend_from_intent(movies, intent, limit=limit)
    if rows is None or rows.empty:
        return []
    return [candidate for _, row in rows.iterrows() if (candidate := local_candidate(row))]


def _local_similarity(movies, tfidf_matrix, neighbors, find_movie_index, seed_title: str, limit: int) -> list[MovieCandidate]:
    if movies is None or tfidf_matrix is None or neighbors is None:
        return []
    index = find_movie_index(seed_title)
    if index is None:
        return []
    # The saved estimator may be configured for all CPUs.  A shallow copy keeps
    # the trained index/artifacts intact while allowing this request to avoid
    # mutating global estimator state (and works in restricted worker hosts).
    query_neighbors = copy.copy(neighbors)
    query_neighbors.n_jobs = 1
    distances, indices = query_neighbors.kneighbors(
        tfidf_matrix[index], n_neighbors=min(max(limit + 1, neighbors.n_neighbors), len(movies))
    )
    selected_title = normalize_title(movies.iloc[index].get("title"))
    result, seen = [], {selected_title}
    for _, candidate_index in zip(distances[0], indices[0]):
        if candidate_index == index:
            continue
        candidate = local_candidate(movies.iloc[candidate_index])
        if candidate is None or candidate.normalized_title in seen:
            continue
        seen.add(candidate.normalized_title)
        result.append(candidate)
        if len(result) >= limit:
            break
    return result


def _exact_watchmode_match(candidates: list[MovieCandidate], seed_title: str, seed_year: int | None = None) -> MovieCandidate | None:
    wanted = normalize_title(seed_title)
    exact = [item for item in candidates if item.normalized_title == wanted]
    if len(exact) > 1 and seed_year is not None:
        exact = [item for item in exact if item.year == seed_year]
    return exact[0] if len(exact) == 1 else None


def _local_seed(movies, find_movie_index, seed_title: str) -> MovieCandidate | None:
    if movies is None or not seed_title:
        return None
    index = find_movie_index(seed_title)
    return local_candidate(movies.iloc[index]) if index is not None else None


def _availability(seed_title: str, region: str, watchmode_client, local_seed: MovieCandidate | None) -> tuple[list[MovieCandidate], str, dict[str, Any] | None]:
    """Return candidate(s), verification state, and a safe provider status."""
    if not seed_title:
        return ([local_seed] if local_seed else []), "not_verified", {"state": "missing_title"}
    response = watchmode_client.search_by_title(seed_title)
    if not response.ok:
        return ([local_seed] if local_seed else []), "not_verified", {"state": response.error or "unavailable"}
    if not isinstance(response.data, dict) or not isinstance(response.data.get("title_results"), list):
        return ([local_seed] if local_seed else []), "not_verified", {"state": "malformed_response"}
    external = [watchmode_search_candidate(item) for item in response.data["title_results"]]
    external = [item for item in external if item]
    match = _exact_watchmode_match(external, seed_title, local_seed.year if local_seed else None)
    if match is None:
        state = "ambiguous" if any(item.normalized_title == normalize_title(seed_title) for item in external) else "not_found"
        return ([local_seed] if local_seed else external), "not_verified", {"state": state}
    sources_response = watchmode_client.streaming_sources(match.watchmode_id, regions=region)
    if not sources_response.ok:
        return deduplicate(([local_seed] if local_seed else []) + [match]), "not_verified", {"state": sources_response.error or "unavailable"}
    if not isinstance(sources_response.data, list):
        return deduplicate(([local_seed] if local_seed else []) + [match]), "not_verified", {"state": "malformed_response"}
    match.streaming_sources = watchmode_sources(sources_response.data, region)
    match.availability_region = region
    match.availability_checked_at = checked_at()
    match.availability_status = "verified_available" if match.streaming_sources else "verified_no_sources_returned"
    return deduplicate(([local_seed] if local_seed else []) + [match]), "verified", None


def retrieve_hybrid(*, text: str, title: str | None, region: str, limit: int, intent: dict[str, Any], movies, tfidf_matrix, neighbors, find_movie_index, watchmode_client, discovery_provider=None, tmdb_discovery_provider=None, watchmode_ott_enricher=None, recommendation_source: str | None = "tmdb") -> dict[str, Any]:
    """Retrieve from the configured source without changing endpoint names."""
    source = normalize_recommendation_source(recommendation_source)
    mode = detect_mode(text, title)
    seed_title = title.strip() if title else None

    # A9 boundary: this branch deliberately does not touch any local artifact
    # or local retrieval helper. TMDB failures stay visible to the caller.
    if source == "tmdb":
        if mode in {"LATEST", "LATEST_OTT"}:
            if tmdb_discovery_provider is None:
                return _response(mode, text, intent, [], local_fallback_used=False,
                                 recommendation_source=source, freshness="not_verified",
                                 limitation="TMDB discovery is not configured.",
                                 discovery={"provider": "tmdb", "status": "not_configured", "query_supported": False})
            outcome = tmdb_discovery_provider.discover(
                intent=intent, region=region, limit=limit, release_kind="theatrical",
            )
            discovery = {"provider": "tmdb", "status": outcome.status, "query_supported": outcome.query_supported}
            if outcome.status != "available":
                limitation = outcome.limitation
                if limitation and "local catalog fallback" in limitation.casefold():
                    limitation = "TMDB discovery is unavailable; no local catalog fallback is used in TMDB mode."
                return _response(mode, text, intent, [], local_fallback_used=False,
                                 recommendation_source=source, freshness="not_verified",
                                 limitation=limitation, provider_status=outcome.provider_status,
                                 discovery=discovery)
            if mode == "LATEST_OTT":
                if watchmode_ott_enricher is None:
                    return _response(mode, text, intent, [], local_fallback_used=False,
                                     recommendation_source=source, availability="unknown",
                                     freshness="verified_release_date", discovery=discovery,
                                     availability_filter={"requested": True, "region": region, "verified_only": True, "matched": 0, "checked": 0})
                enrichment = watchmode_ott_enricher.enrich(outcome.candidates, region=region, limit=limit)
                verified = deduplicate([item for item in enrichment.candidates if item.availability_status == "verified_available"])
                return _response(mode, text, intent, verified[:limit], local_fallback_used=False,
                                 recommendation_source=source,
                                 availability="verified" if verified else "unknown",
                                 freshness="verified_release_date", provider_status=enrichment.provider_status,
                                 discovery=discovery,
                                 availability_filter={"requested": True, "region": region, "verified_only": True,
                                                      "matched": len(verified), "checked": enrichment.attempted})
            return _response(mode, text, intent, outcome.candidates[:limit], local_fallback_used=False,
                             recommendation_source=source, availability="unknown",
                             freshness="verified_release_date", discovery=discovery)
        return _response(mode, text, intent, [], local_fallback_used=False,
                         recommendation_source=source, freshness="not_verified",
                         limitation="TMDB live discovery currently requires an explicit latest or recent request with one supported language and genre.",
                         discovery={"provider": "tmdb", "status": "unsupported", "query_supported": False})

    if mode == "SIMILARITY":
        candidates = _local_similarity(movies, tfidf_matrix, neighbors, find_movie_index, seed_title or "", limit)
        return _response(mode, text, intent, candidates, local_fallback_used=True, recommendation_source=source)
    if mode == "OTT_AVAILABILITY":
        candidates, availability, provider_status = _availability(seed_title or "", region, watchmode_client, _local_seed(movies, find_movie_index, seed_title or ""))
        return _response(mode, text, intent, candidates[:limit], local_fallback_used=bool(candidates and availability != "verified"), availability=availability, provider_status=provider_status, recommendation_source=source)

    candidates = _local_general(movies, intent, limit)
    if source == "local":
        if mode in {"LATEST", "LATEST_OTT"}:
            for candidate in candidates:
                candidate.freshness_status = "local_catalog_no_verified_release_date"
            return _response(mode, text, intent, candidates, local_fallback_used=True,
                             recommendation_source=source, freshness="local_catalog_only",
                             limitation="Live TMDB discovery is disabled while the local recommendation source is selected.")
        return _response(mode, text, intent, candidates, local_fallback_used=True, recommendation_source=source)

    if mode in {"LATEST", "LATEST_OTT"}:
        # TMDB establishes current movie release facts for both latest modes.
        # It must not be asked to prove an OTT premiere/availability fact.
        release_kind = "theatrical"
        if tmdb_discovery_provider is not None:
            tmdb_outcome = tmdb_discovery_provider.discover(
                intent=intent, region=region, limit=limit, release_kind=release_kind,
            )
            if tmdb_outcome.status == "available":
                merged = deduplicate(tmdb_outcome.candidates + candidates)
                merged.sort(key=lambda candidate: (candidate.release_date is not None, candidate.release_date or ""), reverse=True)
                if mode == "LATEST_OTT":
                    if watchmode_ott_enricher is not None:
                        enrichment = watchmode_ott_enricher.enrich(tmdb_outcome.candidates, region=region, limit=limit)
                        verified = deduplicate([item for item in enrichment.candidates if item.availability_status == "verified_available"])
                        return _response(
                            mode, text, intent, verified[:limit], local_fallback_used=False,
                            availability="verified" if verified else "unknown",
                            freshness="verified_release_date",
                            provider_status=enrichment.provider_status,
                            discovery={"provider": "tmdb", "status": "available", "query_supported": True},
                            recommendation_source=source, availability_filter={"requested": True, "region": region, "verified_only": True,
                                                 "matched": len(verified), "checked": enrichment.attempted},
                        )
                    # The endpoint remains truthful if an application has not
                    # configured the optional enricher.
                    return _response(
                        mode, text, intent, [], local_fallback_used=False,
                        availability="unknown", freshness="verified_release_date",
                        discovery={"provider": "tmdb", "status": "available", "query_supported": True},
                        recommendation_source=source, availability_filter={"requested": True, "region": region, "verified_only": True,
                                             "matched": 0, "checked": 0},
                    )
                return _response(
                    mode, text, intent, merged[:limit], local_fallback_used=False,
                    availability="unknown", freshness="verified_release_date",
                    recommendation_source=source, discovery={"provider": "tmdb", "status": "available", "query_supported": True},
                )
            # The current Watchmode account is known to lack advanced access;
            # do not spend additional Watchmode credits after a TMDB failure.
            # Local fallback remains truthful and preserves the A7 provider for
            # future explicit capability-gated use.
            for candidate in candidates:
                candidate.freshness_status = "local_catalog_no_verified_release_date"
            return _response(
                mode, text, intent, candidates, local_fallback_used=True,
                freshness="local_catalog_only", limitation=tmdb_outcome.limitation or "TMDB returned no verified recent candidates; using the local catalog fallback.",
                recommendation_source=source, provider_status=tmdb_outcome.provider_status,
                discovery={"provider": "tmdb", "status": tmdb_outcome.status, "query_supported": tmdb_outcome.query_supported},
            )
        if discovery_provider is not None:
            outcome = discovery_provider.discover(
                intent=intent,
                region=region,
                limit=limit,
                release_kind=release_kind,
            )
            if outcome.status == "verified":
                # Both pools already meet explicit local/provider constraints.
                # Verified, dated provider candidates lead; local candidates are
                # retained as non-fresh fallback context after them.
                merged = deduplicate(outcome.candidates + candidates)
                merged.sort(key=lambda candidate: (candidate.release_date is not None, candidate.release_date or ""), reverse=True)
                availability = "verified_streaming_availability" if mode == "LATEST_OTT" and any(item.availability_status == "verified_streaming_availability" for item in outcome.candidates) else "unknown"
                freshness = "verified_ott_premiere_date" if mode == "LATEST_OTT" else "verified_release_date"
                return _response(
                    mode, text, intent, merged[:limit], local_fallback_used=False,
                    availability=availability, freshness=freshness, recommendation_source=source,
                    discovery={"provider": "watchmode", "status": "verified", "query_supported": True, "credits_note": outcome.credits_note},
                )
        for candidate in candidates:
            candidate.freshness_status = "local_catalog_no_verified_release_date"
        limitation = outcome.limitation if discovery_provider is not None else "Verified latest discovery is unsupported by the current Watchmode integration."
        provider_status = outcome.provider_status if discovery_provider is not None else None
        discovery = {"provider": "watchmode", "status": outcome.status, "query_supported": outcome.query_supported} if discovery_provider is not None else {"provider": "watchmode", "status": "not_configured", "query_supported": False}
        return _response(mode, text, intent, candidates, local_fallback_used=True, recommendation_source=source, freshness="local_catalog_only", limitation=limitation, provider_status=provider_status, discovery=discovery)
    return _response(mode, text, intent, candidates, local_fallback_used=True, recommendation_source=source)


def _response(mode: str, text: str, intent: dict[str, Any], candidates: list[MovieCandidate], *, local_fallback_used: bool, availability: str = "not_requested", freshness: str = "not_requested", limitation: str | None = None, provider_status: dict[str, Any] | None = None, discovery: dict[str, Any] | None = None, availability_filter: dict[str, Any] | None = None, recommendation_source: str = "tmdb") -> dict[str, Any]:
    payload = {
        "mode": mode,
        "query": text,
        "intent": intent,
        "results": [candidate.public_dict() for candidate in deduplicate(candidates)],
        "local_fallback_used": local_fallback_used,
        "recommendation_source": recommendation_source,
        "verification": {"availability": availability, "freshness": freshness},
    }
    if limitation:
        payload["limitation"] = limitation
    if provider_status:
        payload["provider_status"] = provider_status
    if discovery:
        payload["discovery"] = discovery
    if availability_filter:
        payload["availability_filter"] = availability_filter
    if limitation:
        payload["limitations"] = [limitation]
    return payload
