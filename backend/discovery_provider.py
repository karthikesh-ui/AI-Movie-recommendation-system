"""Capability-gated Watchmode live discovery adapter.

It uses only documented Watchmode catalog calls and is disabled by default so
ordinary hybrid requests never consume discovery credits accidentally.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import time
from typing import Any, Mapping

from movie_candidate import MovieCandidate, _number, _text, _year, checked_at


LANGUAGE_CODES = {
    "telugu": "te", "hindi": "hi", "tamil": "ta", "malayalam": "ml",
    "kannada": "kn", "bengali": "bn", "marathi": "mr", "punjabi": "pa",
    "gujarati": "gu", "english": "en",
}

# Stable TMDB movie genre IDs for the project's supported intent vocabulary.
# Known genres must not depend on a separate, optional reference-data request.
TMDB_MOVIE_GENRES = {
    "action": (28, "Action"), "adventure": (12, "Adventure"),
    "animation": (16, "Animation"), "comedy": (35, "Comedy"),
    "crime": (80, "Crime"), "documentary": (99, "Documentary"),
    "drama": (18, "Drama"), "family": (10751, "Family"),
    "fantasy": (14, "Fantasy"), "history": (36, "History"),
    "horror": (27, "Horror"), "music": (10402, "Music"),
    "mystery": (9648, "Mystery"), "romance": (10749, "Romance"),
    "science fiction": (878, "Science Fiction"), "tv movie": (10770, "TV Movie"),
    "thriller": (53, "Thriller"), "war": (10752, "War"), "western": (37, "Western"),
}
TMDB_MOVIE_GENRE_IDS = {name: value[0] for name, value in TMDB_MOVIE_GENRES.items()}
TMDB_MOVIE_GENRE_NAMES = {value[0]: value[1] for value in TMDB_MOVIE_GENRES.values()}


@dataclass(frozen=True)
class DiscoveryOutcome:
    candidates: list[MovieCandidate]
    status: str
    limitation: str | None = None
    provider_status: dict[str, Any] | None = None
    query_supported: bool = False
    credits_note: str | None = None


@dataclass(frozen=True)
class AvailabilityEnrichmentOutcome:
    """Safe result of resolving TMDB candidates against Watchmode sources."""

    candidates: list[MovieCandidate]
    attempted: int
    verified_available: int
    unknown: int
    provider_status: dict[str, Any] | None = None


def normalized_discovery_error(response, operation: str) -> dict[str, str | int | None]:
    """Expose a stable, non-sensitive discovery failure category.

    Watchmode intentionally returns a generic safe ``unauthorized`` from the
    client for HTTP 401.  For advanced release discovery, a prior successful
    authenticated catalog operation proves the key is valid, so that 401 is a
    plan/operation entitlement restriction rather than an invalid key.
    """
    error = response.error or "provider_unavailable"
    if error == "missing_configuration":
        state = "missing_configuration"
    elif error == "authentication_failed":
        state = "invalid_api_key"
    elif error == "unauthorized":
        state = "unauthorized_or_plan_restricted" if operation == "title-release-dates" else "invalid_api_key"
    elif error == "rate_limited":
        state = "rate_limited"
    elif error == "malformed_response":
        state = "malformed_response"
    else:
        state = "provider_unavailable"
    return {"operation": operation, "http_status": response.status_code, "state": state}


class WatchmodeDiscoveryProvider:
    """Combines title filtering with exact regional release-date rows.

    ``list-titles`` supplies genre/language/region filtering.  Advanced
    ``title-release-dates`` supplies the actual release type/date.  A title is
    emitted only when both sources agree on its Watchmode ID; this prevents a
    list filter alone from being presented as verified per-title freshness.
    """

    def __init__(self, client, *, enabled: bool = False, window_days: int = 90):
        self.client = client
        self.enabled = enabled
        self.window_days = max(1, int(window_days))
        self._genre_ids: dict[str, int] | None = None

    def _genres(self) -> tuple[dict[str, int] | None, Any | None]:
        if self._genre_ids is not None:
            return self._genre_ids, None
        response = self.client.genres()
        if not response.ok or not isinstance(response.data, list):
            return None, response
        values: dict[str, int] = {}
        for item in response.data:
            if not isinstance(item, Mapping):
                continue
            name, identifier = _text(item.get("name")), _number(item.get("id"), int)
            if name and identifier is not None:
                values[name.casefold()] = identifier
        self._genre_ids = values
        return values, None

    @staticmethod
    def _language(intent: Mapping[str, Any]) -> str | None:
        values = intent.get("languages", [])
        if not isinstance(values, list) or len(values) != 1:
            return None
        return LANGUAGE_CODES.get(str(values[0]).casefold())

    def discover(self, *, intent: Mapping[str, Any], region: str, limit: int, release_kind: str, as_of: date | None = None) -> DiscoveryOutcome:
        if not self.enabled:
            return DiscoveryOutcome([], "disabled", "Verified latest discovery is unsupported while live discovery is disabled; using the local catalog fallback.")
        if not self.client.configured:
            return DiscoveryOutcome([], "unavailable", "Watchmode is not configured; using the local catalog fallback.", {"state": "missing_configuration"})
        language = self._language(intent)
        if not language:
            return DiscoveryOutcome([], "unsupported", "Live discovery requires exactly one supported requested language.")
        requested_genres = intent.get("genres", [])
        if not isinstance(requested_genres, list) or len(requested_genres) != 1:
            return DiscoveryOutcome([], "unsupported", "Live discovery requires exactly one requested genre.")
        genres, genre_response = self._genres()
        if genre_response:
            return DiscoveryOutcome([], "unavailable", "Watchmode genre reference data is unavailable; using the local catalog fallback.", normalized_discovery_error(genre_response, "genres"))
        genre_id = genres.get(str(requested_genres[0]).casefold())
        if genre_id is None:
            return DiscoveryOutcome([], "unsupported", "The requested genre is not available from Watchmode discovery.")

        today = as_of or date.today()
        start = today - timedelta(days=self.window_days)
        start_param, end_param = start.strftime("%Y%m%d"), today.strftime("%Y%m%d")
        titles = self.client.list_titles(
            types="movie", regions=region, genres=str(genre_id), languages=language,
            release_date_start=start_param, release_date_end=end_param,
            source_types="sub" if release_kind == "streaming" else None,
            sort_by="release_date_desc", page=1, limit=limit,
        )
        if not titles.ok:
            return DiscoveryOutcome([], "unavailable", "Watchmode title discovery is unavailable; using the local catalog fallback.", normalized_discovery_error(titles, "list-titles"))
        if not isinstance(titles.data, Mapping) or not isinstance(titles.data.get("titles"), list):
            return DiscoveryOutcome([], "unavailable", "Watchmode title discovery returned malformed data; using the local catalog fallback.", {"operation": "list-titles", "http_status": titles.status_code, "state": "malformed_response"})

        # Paid-plan advanced rows establish exact calendar dates and release
        # semantics.  Do not emit list-only candidates as date-verified.
        releases = self.client.release_discovery(start_date=start_param, end_date=end_param, regions=region, advanced=True)
        if not releases.ok:
            limitation = "Watchmode release-date verification is unavailable; using the local catalog fallback."
            if releases.status_code == 401:
                limitation = "Watchmode advanced release discovery requires account entitlement; using the local catalog fallback."
            return DiscoveryOutcome([], "unavailable", limitation, normalized_discovery_error(releases, "title-release-dates"))
        if not isinstance(releases.data, list):
            return DiscoveryOutcome([], "unavailable", "Watchmode release-date verification returned malformed data; using the local catalog fallback.", {"operation": "title-release-dates", "http_status": releases.status_code, "state": "malformed_response"})

        wanted_type = "streaming" if release_kind == "streaming" else "theatrical"
        release_by_id: dict[int, Mapping[str, Any]] = {}
        for item in releases.data:
            if not isinstance(item, Mapping) or str(item.get("region", "")).upper() != region:
                continue
            item_type = _text(item.get("type")) or ""
            if wanted_type == "streaming" and not item_type.startswith("streaming_"):
                continue
            if wanted_type == "theatrical" and item_type != "theatrical_release":
                continue
            identifier = _number(item.get("id"), int)
            release_date = _text(item.get("release_date"))
            if identifier is not None and release_date:
                old = release_by_id.get(identifier)
                if old is None or str(old.get("release_date")) < release_date:
                    release_by_id[identifier] = item

        candidates = []
        for item in titles.data["titles"]:
            if not isinstance(item, Mapping):
                continue
            identifier = _number(item.get("id"), int)
            release = release_by_id.get(identifier) if identifier is not None else None
            if release is None:
                continue
            title = _text(item.get("title"))
            if not title:
                continue
            is_streaming = wanted_type == "streaming"
            verification_status = _text(release.get("verification_status"))
            candidates.append(MovieCandidate(
                title=title,
                year=_year(item.get("year")),
                imdb_id=_text(item.get("imdb_id")),
                tmdb_id=_number(item.get("tmdb_id"), int),
                watchmode_id=identifier,
                release_date=_text(release.get("release_date")),
                language=[_text(release.get("original_language"))] if _text(release.get("original_language")) else [],
                provider=["watchmode"],
                data_source=["watchmode_list_titles", "watchmode_title_release_dates"],
                freshness_status="verified_ott_premiere_date" if is_streaming else "verified_release_date",
                availability_region=region if is_streaming else None,
                availability_status=("verified_streaming_availability" if verification_status == "confirmed_available" else "unknown") if is_streaming else "not_checked",
            ))
        candidates.sort(key=lambda candidate: candidate.release_date or "", reverse=True)
        return DiscoveryOutcome(
            candidates[:limit], "verified",
            query_supported=True,
            credits_note="One genre reference call (cached), one list-titles page, and one advanced release-date page each cost one Watchmode catalog credit on success.",
        )


class TMDBDiscoveryProvider:
    """TMDB movie discovery normalized into the existing candidate schema."""

    def __init__(self, client, *, window_days: int = 90):
        self.client = client
        self.window_days = max(1, int(window_days))
        self._genre_names: dict[int, str] | None = None
        self._genre_ids: dict[str, int] | None = None

    def _genres(self):
        if self._genre_ids is not None:
            return self._genre_ids, self._genre_names, None
        response = self.client.movie_genres()
        if not response.ok or not isinstance(response.data, Mapping) or not isinstance(response.data.get("genres"), list):
            return None, None, response
        ids, names = {}, {}
        for item in response.data["genres"]:
            if not isinstance(item, Mapping):
                continue
            identifier, name = _number(item.get("id"), int), _text(item.get("name"))
            if identifier is not None and name:
                ids[name.casefold()] = identifier
                names[identifier] = name
        self._genre_ids, self._genre_names = ids, names
        return ids, names, None

    def discover(self, *, intent: Mapping[str, Any], region: str, limit: int, release_kind: str, as_of: date | None = None) -> DiscoveryOutcome:
        if not self.client.configured:
            return DiscoveryOutcome([], "unavailable", "TMDB is not configured; using the local catalog fallback.", {"operation": "discover/movie", "state": "missing_configuration"})
        # TMDB discovery establishes movie release metadata only. It cannot
        # establish a regional OTT premiere or current streaming availability.
        if release_kind == "streaming":
            return DiscoveryOutcome([], "unsupported", "TMDB discovery does not verify OTT premieres or streaming availability.", {"operation": "discover/movie", "state": "unsupported_release_type"})
        languages = intent.get("languages", [])
        language = WatchmodeDiscoveryProvider._language(intent)
        genres = intent.get("genres", [])
        if (not isinstance(languages, list) or (not language and languages)
                or not isinstance(genres, list) or len(genres) != 1):
            return DiscoveryOutcome([], "unsupported", "TMDB live discovery requires one supported genre and, when specified, one supported language.")
        requested_genre = str(genres[0]).casefold()
        genre_id = TMDB_MOVIE_GENRE_IDS.get(requested_genre)
        genre_names = TMDB_MOVIE_GENRE_NAMES
        if genre_id is None:
            genre_ids, genre_names, genre_response = self._genres()
            if genre_response:
                return DiscoveryOutcome([], "unavailable", "TMDB genre metadata is unavailable; using the local catalog fallback.", _tmdb_status(genre_response, "genre/movie/list"))
            genre_id = genre_ids.get(requested_genre)
        if genre_id is None:
            return DiscoveryOutcome([], "unsupported", "The requested genre is not available from TMDB discovery.")
        today = as_of or date.today()
        start = today - timedelta(days=self.window_days)
        response = self.client.discover_movies(
            genre_id=genre_id, original_language=language, region=region,
            release_date_start=start.isoformat(), release_date_end=today.isoformat(), page=1, limit=limit,
        )
        if not response.ok:
            return DiscoveryOutcome([], "unavailable", "TMDB movie discovery is unavailable; using the local catalog fallback.", _tmdb_status(response, "discover/movie"))
        if not isinstance(response.data, Mapping) or not isinstance(response.data.get("results"), list):
            return DiscoveryOutcome([], "unavailable", "TMDB movie discovery returned malformed data; using the local catalog fallback.", {"operation": "discover/movie", "http_status": response.status_code, "state": "malformed_response"})
        candidates = []
        for item in response.data["results"][:limit]:
            if not isinstance(item, Mapping):
                continue
            identifier, title, release_date = _number(item.get("id"), int), _text(item.get("title")), _text(item.get("release_date"))
            original_language = _text(item.get("original_language"))
            # The provider query filters language; retaining the returned value
            # lets clients distinguish verified `te` from absent/other values.
            if identifier is None or not title or not release_date or (language and original_language != language):
                continue
            genre_values = [genre_names[genre] for genre in item.get("genre_ids", []) if genre in genre_names]
            poster_path = _text(item.get("poster_path"))
            candidates.append(MovieCandidate(
                title=title,
                original_title=_text(item.get("original_title")),
                year=_year(release_date[:4]),
                overview=_text(item.get("overview")),
                genres=genre_values,
                language=[original_language],
                poster_url=f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None,
                tmdb_id=identifier,
                release_date=release_date,
                rating=_number(item.get("vote_average"), float),
                rating_source="tmdb" if _number(item.get("vote_average"), float) is not None else None,
                provider=["tmdb"],
                data_source=["tmdb_discovery"],
                freshness_status="verified_release_date",
            ))
        candidates.sort(key=lambda candidate: candidate.release_date or "", reverse=True)
        return DiscoveryOutcome(candidates, "available" if candidates else "empty", query_supported=True)


class WatchmodeOTTEnricher:
    """Bounded, conservative TMDB-to-Watchmode availability enrichment.

    The adapter uses title search and title sources only. It never calls
    Watchmode's restricted release-date endpoint, so OTT availability cannot
    be confused with TMDB's theatrical freshness evidence.
    """

    def __init__(self, client, *, cache_ttl_seconds: int = 900, max_candidates: int = 10):
        self.client = client
        self.cache_ttl_seconds = max(1, int(cache_ttl_seconds))
        self.max_candidates = max(1, int(max_candidates))
        self._identity_cache: dict[tuple[str | None, int | None, str | None], tuple[float, MovieCandidate | None]] = {}
        self._sources_cache: dict[tuple[int, str], tuple[float, list[dict[str, Any]]]] = {}

    @staticmethod
    def _status(response, operation: str) -> dict[str, Any]:
        error = getattr(response, "error", None) or "provider_unavailable"
        state = {
            "missing_configuration": "missing_configuration", "unauthorized": "unauthorized",
            "authentication_failed": "unauthorized", "rate_limited": "rate_limited",
            "malformed_response": "malformed_response", "timeout": "timeout",
        }.get(error, "provider_unavailable")
        return {"operation": operation, "http_status": getattr(response, "status_code", None), "state": state}

    @staticmethod
    def _identity_key(candidate: MovieCandidate) -> tuple[str | None, int | None, str | None]:
        from movie_candidate import normalize_title
        return (candidate.normalized_title, candidate.year, normalize_title(candidate.original_title))

    def _resolve(self, candidate: MovieCandidate) -> tuple[MovieCandidate | None, dict[str, Any] | None]:
        if candidate.watchmode_id is not None:
            return candidate, None
        key = self._identity_key(candidate)
        now = time.monotonic()
        cached = self._identity_cache.get(key)
        if cached and cached[0] > now:
            return cached[1], None
        response = self.client.search_by_title(candidate.title)
        if not response.ok:
            return None, self._status(response, "search")
        if not isinstance(response.data, Mapping) or not isinstance(response.data.get("title_results"), list):
            return None, {"operation": "search", "http_status": response.status_code, "state": "malformed_response"}
        from movie_candidate import normalize_title, watchmode_search_candidate
        matches = [watchmode_search_candidate(item) for item in response.data["title_results"]]
        names = {name for name in (candidate.normalized_title, normalize_title(candidate.original_title)) if name}
        exact = [
            item for item in matches if item
            and (item.normalized_title in names or normalize_title(item.original_title) in names)
            and (candidate.year is None or item.year == candidate.year)
        ]
        # Multiple same-name/year candidates remain unresolved, rather than
        # guessing based on provider result order.
        match = exact[0] if len(exact) == 1 else None
        self._identity_cache[key] = (now + self.cache_ttl_seconds, match)
        return match, None

    def _sources(self, watchmode_id: int, region: str) -> tuple[list[dict[str, Any]] | None, dict[str, Any] | None]:
        key, now = (watchmode_id, region), time.monotonic()
        cached = self._sources_cache.get(key)
        if cached and cached[0] > now:
            return cached[1], None
        response = self.client.streaming_sources(watchmode_id, regions=region)
        if not response.ok:
            return None, self._status(response, "sources")
        if not isinstance(response.data, list):
            return None, {"operation": "sources", "http_status": response.status_code, "state": "malformed_response"}
        from movie_candidate import watchmode_sources
        sources = watchmode_sources(response.data, region)
        self._sources_cache[key] = (now + self.cache_ttl_seconds, sources)
        return sources, None

    def enrich(self, candidates: list[MovieCandidate], *, region: str, limit: int) -> AvailabilityEnrichmentOutcome:
        """Attach only verified source facts; any ambiguity/failure is unknown."""
        attempted = verified = unknown = 0
        first_status = None
        checked_count = min(len(candidates), limit, self.max_candidates)
        for candidate in candidates[:checked_count]:
            attempted += 1
            match, status = self._resolve(candidate)
            if match is None:
                candidate.availability_status = "unknown"
                unknown += 1
                first_status = first_status or status
                continue
            candidate.watchmode_id = match.watchmode_id
            candidate.imdb_id = candidate.imdb_id or match.imdb_id
            candidate.provider = list(dict.fromkeys(candidate.provider + ["watchmode"]))
            candidate.data_source = list(dict.fromkeys(candidate.data_source + ["watchmode_title_search"]))
            sources, status = self._sources(match.watchmode_id, region)
            candidate.availability_checked_at = checked_at()
            candidate.availability_region = region
            if sources:
                candidate.streaming_sources = sources
                candidate.availability_status = "verified_available"
                candidate.data_source = list(dict.fromkeys(candidate.data_source + ["watchmode_sources"]))
                verified += 1
            else:
                # Empty source data can mean incomplete coverage. Never turn
                # it into a false "unavailable" assertion.
                candidate.availability_status = "unknown"
                unknown += 1
                first_status = first_status or status
        for candidate in candidates[checked_count:]:
            candidate.availability_status = "unknown"
            unknown += 1
        return AvailabilityEnrichmentOutcome(candidates, attempted, verified, unknown, first_status)


def _tmdb_status(response, operation: str) -> dict[str, str | int | None]:
    error = response.error or "provider_unavailable"
    state = {
        "missing_configuration": "missing_configuration",
        "authentication_failed": "authentication_failed",
        "unauthorized": "unauthorized",
        "rate_limited": "rate_limited",
        "malformed_response": "malformed_response",
    }.get(error, "provider_unavailable")
    return {"operation": operation, "http_status": response.status_code, "state": state}
