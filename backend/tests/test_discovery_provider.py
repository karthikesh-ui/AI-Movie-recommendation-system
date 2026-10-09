import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

from discovery_provider import WatchmodeDiscoveryProvider, TMDBDiscoveryProvider, WatchmodeOTTEnricher, normalized_discovery_error
from discovery_provider import DiscoveryOutcome
from hybrid_retrieval import retrieve_hybrid
from movie_candidate import MovieCandidate
from watchmode_client import WatchmodeResponse


class WatchmodeDiscoveryProviderTests(unittest.TestCase):
    def client(self, *, genres=None, titles=None, releases=None):
        return SimpleNamespace(
            configured=True,
            genres=Mock(return_value=genres or WatchmodeResponse(True, 200, [{"id": 4, "name": "Action"}])),
            list_titles=Mock(return_value=titles or WatchmodeResponse(True, 200, {"titles": [{"id": 7, "title": "Recent Telugu Film", "year": 2026, "imdb_id": "tt7"}]})),
            release_discovery=Mock(return_value=releases or WatchmodeResponse(True, 200, [{"id": 7, "region": "IN", "type": "theatrical_release", "release_date": "2026-09-20", "original_language": "te"}])),
        )

    def test_supported_theatrical_discovery_requires_matching_verified_release_row(self):
        client = self.client()
        provider = WatchmodeDiscoveryProvider(client, enabled=True, window_days=90)
        outcome = provider.discover(
            intent={"genres": ["action"], "languages": ["telugu"]},
            region="IN", limit=10, release_kind="theatrical", as_of=date(2026, 10, 4),
        )
        self.assertEqual(outcome.status, "verified")
        self.assertEqual(outcome.candidates[0].release_date, "2026-09-20")
        self.assertEqual(outcome.candidates[0].freshness_status, "verified_release_date")
        self.assertEqual(outcome.candidates[0].language, ["te"])
        self.assertEqual(client.list_titles.call_args.kwargs["languages"], "te")
        self.assertEqual(client.list_titles.call_args.kwargs["genres"], "4")

    def test_streaming_premiere_is_not_labelled_as_theatrical(self):
        client = self.client(releases=WatchmodeResponse(True, 200, [{
            "id": 7, "region": "IN", "type": "streaming_movie_release",
            "release_date": "2026-09-20", "original_language": "te",
            "verification_status": "confirmed_available",
        }]))
        provider = WatchmodeDiscoveryProvider(client, enabled=True)
        outcome = provider.discover(
            intent={"genres": ["action"], "languages": ["telugu"]},
            region="IN", limit=10, release_kind="streaming", as_of=date(2026, 10, 4),
        )
        candidate = outcome.candidates[0]
        self.assertEqual(candidate.freshness_status, "verified_ott_premiere_date")
        self.assertEqual(candidate.availability_status, "verified_streaming_availability")
        self.assertEqual(client.list_titles.call_args.kwargs["source_types"], "sub")

    def test_missing_date_is_not_emitted_as_fresh(self):
        client = self.client(releases=WatchmodeResponse(True, 200, [{
            "id": 7, "region": "IN", "type": "theatrical_release", "release_date": None,
        }]))
        outcome = WatchmodeDiscoveryProvider(client, enabled=True).discover(
            intent={"genres": ["action"], "languages": ["telugu"]},
            region="IN", limit=10, release_kind="theatrical", as_of=date(2026, 10, 4),
        )
        self.assertEqual(outcome.status, "verified")
        self.assertEqual(outcome.candidates, [])

    def test_disabled_and_paid_restriction_fall_back_safely(self):
        disabled = WatchmodeDiscoveryProvider(self.client(), enabled=False).discover(
            intent={"genres": ["action"], "languages": ["telugu"]}, region="IN", limit=10, release_kind="theatrical"
        )
        self.assertEqual(disabled.status, "disabled")
        client = self.client(releases=WatchmodeResponse(False, 401, error="unauthorized"))
        restricted = WatchmodeDiscoveryProvider(client, enabled=True).discover(
            intent={"genres": ["action"], "languages": ["telugu"]}, region="IN", limit=10, release_kind="theatrical"
        )
        self.assertEqual(restricted.provider_status["state"], "unauthorized_or_plan_restricted")
        self.assertEqual(restricted.provider_status["operation"], "title-release-dates")
        self.assertIn("entitlement", restricted.limitation)

    def test_unsupported_language_does_not_call_provider(self):
        client = self.client()
        outcome = WatchmodeDiscoveryProvider(client, enabled=True).discover(
            intent={"genres": ["action"], "languages": ["telugu", "hindi"]}, region="IN", limit=10, release_kind="theatrical"
        )
        self.assertEqual(outcome.status, "unsupported")
        client.genres.assert_not_called()

    def test_normalized_error_states_are_safe_and_operation_specific(self):
        cases = [
            (WatchmodeResponse(False, None, error="missing_configuration"), "genres", "missing_configuration"),
            (WatchmodeResponse(False, 401, error="authentication_failed"), "genres", "invalid_api_key"),
            (WatchmodeResponse(False, 401, error="unauthorized"), "title-release-dates", "unauthorized_or_plan_restricted"),
            (WatchmodeResponse(False, 429, error="rate_limited"), "list-titles", "rate_limited"),
            (WatchmodeResponse(False, 502, error="http_error"), "list-titles", "provider_unavailable"),
            (WatchmodeResponse(False, 200, error="malformed_response"), "genres", "malformed_response"),
        ]
        for response, operation, expected in cases:
            with self.subTest(expected=expected):
                status = normalized_discovery_error(response, operation)
                self.assertEqual(status["state"], expected)
                self.assertEqual(status["operation"], operation)
                self.assertEqual(status["http_status"], response.status_code)


class TMDBDiscoveryProviderTests(unittest.TestCase):
    def client(self, *, genres=None, movies=None):
        return SimpleNamespace(
            configured=True,
            movie_genres=Mock(return_value=genres or WatchmodeResponse(True, 200, {"genres": [{"id": 28, "name": "Action"}]})),
            discover_movies=Mock(return_value=movies or WatchmodeResponse(True, 200, {"page": 1, "results": [{
                "id": 99, "title": "Fresh Telugu Action", "original_title": "Fresh Telugu Action",
                "original_language": "te", "release_date": "2026-09-20", "genre_ids": [28],
                "overview": "Verified provider data.", "poster_path": "/poster.jpg", "vote_average": 7.2,
            }]})),
        )

    def test_tmdb_discovery_normalizes_live_candidate(self):
        client = self.client()
        outcome = TMDBDiscoveryProvider(client, window_days=90).discover(
            intent={"genres": ["action"], "languages": ["telugu"]}, region="IN", limit=10, release_kind="theatrical", as_of=date(2026, 10, 5),
        )
        self.assertEqual(outcome.status, "available")
        candidate = outcome.candidates[0]
        self.assertEqual(candidate.tmdb_id, 99)
        self.assertEqual(candidate.release_date, "2026-09-20")
        self.assertEqual(candidate.language, ["te"])
        self.assertIn("Action", candidate.genres)
        self.assertEqual(candidate.freshness_status, "verified_release_date")
        self.assertEqual(client.discover_movies.call_args.kwargs["genre_id"], 28)
        client.movie_genres.assert_not_called()

    def test_known_genre_skips_failed_reference_metadata(self):
        client = self.client(genres=WatchmodeResponse(False, None, error="network_error"))
        outcome = TMDBDiscoveryProvider(client).discover(
            intent={"genres": ["action"], "languages": ["telugu"]},
            region="IN", limit=10, release_kind="theatrical",
        )
        self.assertEqual(outcome.status, "available")
        self.assertEqual(client.discover_movies.call_args.kwargs["genre_id"], 28)
        client.movie_genres.assert_not_called()

    def test_unknown_genre_uses_reference_metadata_only_as_safe_fallback(self):
        client = self.client(genres=WatchmodeResponse(False, None, error="network_error"))
        outcome = TMDBDiscoveryProvider(client).discover(
            intent={"genres": ["unknown"], "languages": ["telugu"]},
            region="IN", limit=10, release_kind="theatrical",
        )
        self.assertEqual(outcome.status, "unavailable")
        self.assertEqual(outcome.provider_status["operation"], "genre/movie/list")
        client.discover_movies.assert_not_called()

    def test_tmdb_failure_empty_and_ott_are_safe(self):
        client = self.client(movies=WatchmodeResponse(False, 429, error="rate_limited"))
        limited = TMDBDiscoveryProvider(client).discover(
            intent={"genres": ["action"], "languages": ["telugu"]}, region="IN", limit=10, release_kind="theatrical"
        )
        self.assertEqual(limited.provider_status["state"], "rate_limited")
        client.movie_genres.assert_not_called()
        empty = TMDBDiscoveryProvider(self.client(movies=WatchmodeResponse(True, 200, {"page": 1, "results": []}))).discover(
            intent={"genres": ["action"], "languages": ["telugu"]}, region="IN", limit=10, release_kind="theatrical"
        )
        self.assertEqual(empty.status, "empty")
        ott = TMDBDiscoveryProvider(self.client()).discover(
            intent={"genres": ["action"], "languages": ["telugu"]}, region="IN", limit=10, release_kind="streaming"
        )
        self.assertEqual(ott.status, "unsupported")

    def test_tmdb_india_region_discovery_allows_no_language_filter(self):
        client = self.client()
        outcome = TMDBDiscoveryProvider(client).discover(
            intent={"genres": ["thriller"], "languages": []}, region="IN", limit=10,
            release_kind="theatrical",
        )
        self.assertEqual(outcome.status, "available")
        self.assertIsNone(client.discover_movies.call_args.kwargs["original_language"])


class WatchmodeOTTEnricherTests(unittest.TestCase):
    def client(self, *, search=None, sources=None):
        return SimpleNamespace(
            search_by_title=Mock(return_value=search or WatchmodeResponse(True, 200, {"title_results": [{"id": 44, "name": "Fresh Telugu Action", "year": 2026}]})),
            streaming_sources=Mock(return_value=sources or WatchmodeResponse(True, 200, [{"name": "Netflix", "type": "sub", "region": "IN"}])),
        )

    @staticmethod
    def candidate():
        return MovieCandidate(title="Fresh Telugu Action", original_title="Fresh Telugu Action", year=2026, tmdb_id=99,
                              release_date="2026-09-20", freshness_status="verified_release_date", provider=["tmdb"], data_source=["tmdb_discovery"])

    def test_exact_title_year_match_preserves_tmdb_freshness(self):
        client = self.client()
        candidate = self.candidate()
        outcome = WatchmodeOTTEnricher(client).enrich([candidate], region="IN", limit=10)
        self.assertEqual(outcome.verified_available, 1)
        self.assertEqual(candidate.watchmode_id, 44)
        self.assertEqual(candidate.availability_status, "verified_available")
        self.assertEqual(candidate.availability_region, "IN")
        self.assertEqual(candidate.freshness_status, "verified_release_date")
        self.assertIn("watchmode_sources", candidate.data_source)

    def test_ambiguous_or_missing_match_stays_unknown_without_source_lookup(self):
        ambiguous = self.client(search=WatchmodeResponse(True, 200, {"title_results": [
            {"id": 44, "name": "Fresh Telugu Action", "year": 2026},
            {"id": 45, "name": "Fresh Telugu Action", "year": 2026},
        ]}))
        candidate = self.candidate()
        WatchmodeOTTEnricher(ambiguous).enrich([candidate], region="IN", limit=10)
        self.assertEqual(candidate.availability_status, "unknown")
        ambiguous.streaming_sources.assert_not_called()
        missing = self.client(search=WatchmodeResponse(True, 200, {"title_results": []}))
        candidate = self.candidate()
        WatchmodeOTTEnricher(missing).enrich([candidate], region="IN", limit=10)
        self.assertEqual(candidate.availability_status, "unknown")
        missing.streaming_sources.assert_not_called()

    def test_source_failures_empty_and_cache_are_safe(self):
        for source in (
            WatchmodeResponse(False, 401, error="unauthorized"), WatchmodeResponse(False, None, error="timeout"),
            WatchmodeResponse(False, 429, error="rate_limited"), WatchmodeResponse(False, 500, error="http_error"),
            WatchmodeResponse(True, 200, []),
        ):
            with self.subTest(error=source.error or "empty"):
                client = self.client(sources=source)
                candidate = self.candidate()
                outcome = WatchmodeOTTEnricher(client).enrich([candidate], region="IN", limit=10)
                self.assertEqual(candidate.availability_status, "unknown")
                self.assertEqual(outcome.verified_available, 0)
        client = self.client()
        enricher = WatchmodeOTTEnricher(client)
        enricher.enrich([self.candidate()], region="IN", limit=10)
        enricher.enrich([self.candidate()], region="IN", limit=10)
        client.search_by_title.assert_called_once()
        client.streaming_sources.assert_called_once()


class DiscoveryIntegrationTests(unittest.TestCase):
    def test_non_latest_requests_do_not_call_discovery(self):
        discovery = Mock()
        result = retrieve_hybrid(
            text="Suggest an action movie", title=None, region="IN", limit=5,
            intent={"genres": [], "languages": [], "ranking": "general"},
            movies=None, tfidf_matrix=None, neighbors=None, find_movie_index=lambda _: None,
            watchmode_client=Mock(), discovery_provider=discovery, recommendation_source="hybrid",
        )
        self.assertEqual(result["mode"], "GENERAL")
        discovery.discover.assert_not_called()

    def test_verified_discovery_response_keeps_release_and_ott_semantics_distinct(self):
        discovery = Mock()
        discovery.discover.return_value = DiscoveryOutcome(
            [MovieCandidate(title="Recent Telugu Film", year=2026, release_date="2026-09-20", freshness_status="verified_release_date", provider=["watchmode"])],
            "verified", query_supported=True, credits_note="test",
        )
        result = retrieve_hybrid(
            text="latest Telugu action movies", title=None, region="IN", limit=5,
            intent={"genres": ["action"], "languages": ["telugu"], "ranking": "general"},
            movies=None, tfidf_matrix=None, neighbors=None, find_movie_index=lambda _: None,
            watchmode_client=Mock(), discovery_provider=discovery, recommendation_source="hybrid",
        )
        self.assertEqual(result["verification"]["freshness"], "verified_release_date")
        self.assertEqual(result["verification"]["availability"], "unknown")
        self.assertFalse(result["local_fallback_used"])

    def test_tmdb_discover_failure_keeps_normal_local_fallback(self):
        client = TMDBDiscoveryProviderTests().client(
            movies=WatchmodeResponse(False, 500, error="http_error")
        )
        result = retrieve_hybrid(
            text="latest Telugu action movies", title=None, region="IN", limit=5,
            intent={"genres": ["action"], "languages": ["telugu"], "ranking": "general"},
            movies=None, tfidf_matrix=None, neighbors=None, find_movie_index=lambda _: None,
            watchmode_client=Mock(), tmdb_discovery_provider=TMDBDiscoveryProvider(client), recommendation_source="hybrid",
        )
        self.assertTrue(result["local_fallback_used"])
        self.assertEqual(result["discovery"]["provider"], "tmdb")
        self.assertEqual(result["discovery"]["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
