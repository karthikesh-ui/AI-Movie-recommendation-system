import unittest
from unittest.mock import Mock, patch

import pandas as pd

import app as movie_app
from hybrid_retrieval import deduplicate, normalize_recommendation_source, retrieve_hybrid
from discovery_provider import WatchmodeDiscoveryProvider, TMDBDiscoveryProvider, WatchmodeOTTEnricher, DiscoveryOutcome
from movie_candidate import MovieCandidate, local_candidate, watchmode_search_candidate
from watchmode_client import WatchmodeResponse


class CandidateTests(unittest.TestCase):
    def test_normalization_preserves_missing_values(self):
        candidate = local_candidate(pd.Series({"title": "Example", "year": None, "genre": None, "language": None}))
        payload = candidate.public_dict()
        self.assertIsNone(payload["year"])
        self.assertEqual(payload["genres"], [])
        self.assertEqual(payload["language"], [])
        self.assertEqual(payload["freshness_status"], "release_date_missing")

    def test_watchmode_mapping_ignores_malformed_and_preserves_id(self):
        self.assertIsNone(watchmode_search_candidate("not a mapping"))
        candidate = watchmode_search_candidate({"id": "1569154", "name": "RRR", "year": "2022"})
        self.assertEqual(candidate.watchmode_id, 1569154)
        self.assertEqual(candidate.title, "RRR")
        self.assertEqual(candidate.year, 2022)

    def test_deduplication_uses_ids_then_title_and_year(self):
        first = MovieCandidate(title="RRR", year=2022, imdb_id="tt8178634", provider=["local_dataset"])
        same = MovieCandidate(title="Different label", year=2022, imdb_id="tt8178634", provider=["watchmode"])
        remake = MovieCandidate(title="RRR", year=1956, provider=["watchmode"])
        unknown_year = MovieCandidate(title="RRR", provider=["watchmode"])
        merged = deduplicate([first, same, remake, unknown_year])
        self.assertEqual(len(merged), 3)
        self.assertEqual(set(merged[0].provider), {"local_dataset", "watchmode"})


class RecommendationSourceTests(unittest.TestCase):
    @staticmethod
    def _intent():
        return {"genres": ["action"], "languages": ["telugu"], "ranking": "general"}

    def test_configuration_defaults_to_tmdb_and_normalizes_supported_values(self):
        self.assertEqual(normalize_recommendation_source(None), "tmdb")
        self.assertEqual(normalize_recommendation_source(" LOCAL "), "local")
        self.assertEqual(normalize_recommendation_source("hybrid"), "hybrid")
        self.assertEqual(normalize_recommendation_source("unsupported"), "tmdb")

    def test_tmdb_source_uses_discovery_without_local_retrieval(self):
        tmdb = Mock()
        tmdb.discover.return_value = DiscoveryOutcome(
            [MovieCandidate(title="Fresh", year=2026, tmdb_id=99, release_date="2026-10-01", provider=["tmdb"], freshness_status="verified_release_date")],
            "available", query_supported=True,
        )
        with patch("hybrid_retrieval._local_general") as local_general, patch("hybrid_retrieval._local_similarity") as local_similarity:
            result = retrieve_hybrid(
                text="latest Telugu action movies", title=None, region="IN", limit=5,
                intent=self._intent(), movies=Mock(), tfidf_matrix=Mock(), neighbors=Mock(),
                find_movie_index=Mock(), watchmode_client=Mock(), tmdb_discovery_provider=tmdb,
                recommendation_source="tmdb",
            )
        self.assertEqual(result["recommendation_source"], "tmdb")
        self.assertFalse(result["local_fallback_used"])
        self.assertEqual(result["results"][0]["tmdb_id"], 99)
        local_general.assert_not_called()
        local_similarity.assert_not_called()

    def test_tmdb_failure_is_not_silently_replaced_with_local_results(self):
        tmdb = Mock()
        tmdb.discover.return_value = DiscoveryOutcome([], "unavailable", "TMDB unavailable")
        with patch("hybrid_retrieval._local_general") as local_general:
            result = retrieve_hybrid(
                text="latest Telugu action movies", title=None, region="IN", limit=5,
                intent=self._intent(), movies=Mock(), tfidf_matrix=Mock(), neighbors=Mock(),
                find_movie_index=Mock(), watchmode_client=Mock(), tmdb_discovery_provider=tmdb,
                recommendation_source="tmdb",
            )
        self.assertEqual(result["results"], [])
        self.assertFalse(result["local_fallback_used"])
        local_general.assert_not_called()

    def test_local_source_still_uses_local_retrieval(self):
        candidate = MovieCandidate(title="Local", year=2020, provider=["local_dataset"])
        with patch("hybrid_retrieval._local_general", return_value=[candidate]) as local_general:
            result = retrieve_hybrid(
                text="Suggest a Telugu action movie", title=None, region="IN", limit=5,
                intent=self._intent(), movies=Mock(), tfidf_matrix=Mock(), neighbors=Mock(),
                find_movie_index=Mock(), watchmode_client=Mock(), recommendation_source="local",
            )
        self.assertEqual(result["recommendation_source"], "local")
        self.assertTrue(result["local_fallback_used"])
        local_general.assert_called_once()


class HybridApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = movie_app.app.test_client()

    def setUp(self):
        self.source_patch = patch.object(movie_app, "RECOMMENDATION_SOURCE", "hybrid")
        self.source_patch.start()

    def tearDown(self):
        self.source_patch.stop()

    def _provider(self, search=None, sources=None):
        fake = Mock()
        fake.search_by_title.return_value = search or WatchmodeResponse(True, 200, {"title_results": []})
        fake.streaming_sources.return_value = sources or WatchmodeResponse(True, 200, [])
        return fake

    def _request(self, url, provider=None):
        provider = provider or self._provider()
        with patch.object(movie_app, "GEMINI_API_KEY", ""), patch.object(movie_app, "WATCHMODE_CLIENT", provider), patch.object(
            movie_app, "WATCHMODE_DISCOVERY", WatchmodeDiscoveryProvider(provider, enabled=False)
        ), patch.object(
            movie_app, "TMDB_DISCOVERY", TMDBDiscoveryProvider(Mock(configured=False))
        ):
            response = self.client.get(url)
        return response, response.get_json(), provider

    def test_general_request_uses_local_candidates_without_watchmode_discovery(self):
        response, payload, provider = self._request("/api/recommend-hybrid?text=Suggest%20a%20Telugu%20action%20movie")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["mode"], "GENERAL")
        self.assertTrue(payload["results"])
        provider.search_by_title.assert_not_called()

    def test_latest_request_is_explicitly_local_catalog_fallback(self):
        response, payload, provider = self._request("/api/recommend-hybrid?text=I%20want%20the%20latest%20Telugu%20action%20movie")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["mode"], "LATEST")
        self.assertEqual(payload["verification"]["freshness"], "local_catalog_only")
        self.assertIn("fallback", payload["limitation"].casefold())
        self.assertTrue(all(item["freshness_status"] == "local_catalog_no_verified_release_date" for item in payload["results"]))
        provider.search_by_title.assert_not_called()

    def test_ott_exact_title_maps_india_sources(self):
        provider = self._provider(
            search=WatchmodeResponse(True, 200, {"title_results": [{"id": 1569154, "name": "RRR", "year": 2022}]}),
            sources=WatchmodeResponse(True, 200, [{"name": "Netflix", "type": "sub", "region": "IN"}]),
        )
        response, payload, fake = self._request("/api/recommend-hybrid?text=Where%20can%20I%20watch%20RRR%3F&title=RRR&region=IN", provider)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["mode"], "OTT_AVAILABILITY")
        self.assertEqual(payload["verification"]["availability"], "verified")
        self.assertTrue(any(item["streaming_sources"] for item in payload["results"]))
        fake.streaming_sources.assert_called_once_with(1569154, regions="IN")

    def test_ott_timeout_returns_local_candidate_as_unverified(self):
        provider = self._provider(search=WatchmodeResponse(False, None, error="timeout"))
        response, payload, _ = self._request("/api/recommend-hybrid?text=Where%20can%20I%20watch%20RRR%3F&title=RRR", provider)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["verification"]["availability"], "not_verified")
        self.assertEqual(payload["provider_status"]["state"], "timeout")
        self.assertTrue(payload["results"])

    def test_ott_provider_failures_and_malformed_data_are_safe(self):
        for outcome in (
            WatchmodeResponse(False, 401, error="unauthorized"),
            WatchmodeResponse(False, 429, error="rate_limited"),
            WatchmodeResponse(False, 500, error="http_error"),
            WatchmodeResponse(True, 200, {"title_results": "invalid"}),
        ):
            with self.subTest(outcome=outcome.error or "malformed"):
                provider = self._provider(search=outcome)
                response, payload, _ = self._request("/api/recommend-hybrid?text=Where%20can%20I%20watch%20RRR%3F&title=RRR", provider)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(payload["verification"]["availability"], "not_verified")
                self.assertIn(payload["provider_status"]["state"], {"unauthorized", "rate_limited", "http_error", "malformed_response"})

    def test_local_dataset_unavailable_does_not_crash(self):
        with patch.object(movie_app, "movies", None), patch.object(movie_app, "GEMINI_API_KEY", ""):
            response = self.client.get("/api/recommend-hybrid?text=Suggest%20a%20Telugu%20action%20movie")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["results"], [])

    def test_similarity_order_uses_existing_artifacts_and_skips_watchmode(self):
        response, payload, provider = self._request("/api/recommend-hybrid?title=RRR&limit=3")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["mode"], "SIMILARITY")
        self.assertEqual(len(payload["results"]), 3)
        self.assertNotIn("rrr", [item["title"].casefold() for item in payload["results"]])
        provider.search_by_title.assert_not_called()

    def test_invalid_request_contract(self):
        self.assertEqual(self.client.get("/api/recommend-hybrid").status_code, 400)
        self.assertEqual(self.client.get("/api/recommend-hybrid?text=x&region=India").status_code, 400)
        self.assertEqual(self.client.get("/api/recommend-hybrid?text=x&limit=21").status_code, 400)

    def test_tmdb_latest_result_precedes_local_fallback_and_skips_watchmode(self):
        tmdb = Mock()
        tmdb.discover.return_value = DiscoveryOutcome(
            [MovieCandidate(title="Fresh Telugu Action", year=2026, tmdb_id=99, release_date="2026-09-20", language=["te"], genres=["Action"], provider=["tmdb"], data_source=["tmdb_discovery"], freshness_status="verified_release_date")],
            "available", query_supported=True,
        )
        watchmode = self._provider()
        with patch.object(movie_app, "GEMINI_API_KEY", ""), patch.object(movie_app, "WATCHMODE_CLIENT", watchmode), patch.object(movie_app, "TMDB_DISCOVERY", tmdb):
            response = self.client.get("/api/recommend-hybrid?text=Show%20me%20the%20latest%20Telugu%20action%20movies&region=IN")
        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["discovery"]["provider"], "tmdb")
        self.assertFalse(payload["local_fallback_used"])
        self.assertEqual(payload["results"][0]["tmdb_id"], 99)
        watchmode.genres.assert_not_called()

    def test_recommend_text_uses_tmdb_source_for_latest_natural_language(self):
        tmdb = Mock()
        tmdb.discover.return_value = DiscoveryOutcome(
            [MovieCandidate(title="TMDB Fresh", year=2026, tmdb_id=101, release_date="2026-09-20",
                            language=["te"], genres=["Action"], provider=["tmdb"],
                            freshness_status="verified_release_date")],
            "available", query_supported=True,
        )
        with patch.object(movie_app, "RECOMMENDATION_SOURCE", "tmdb"), patch.object(
            movie_app, "GEMINI_API_KEY", ""
        ), patch.object(movie_app, "TMDB_DISCOVERY", tmdb), patch(
            "hybrid_retrieval._local_general"
        ) as local_general:
            response = self.client.get("/api/recommend-text?text=latest%20Telugu%20action%20movies")
        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["recommendation_source"], "tmdb")
        self.assertEqual(payload["results"][0]["tmdb_id"], 101)
        local_general.assert_not_called()

    def test_latest_ott_enriches_tmdb_candidates_and_filters_verified_india_sources(self):
        tmdb = Mock()
        tmdb.discover.return_value = DiscoveryOutcome(
            [MovieCandidate(title="Fresh Telugu Action", original_title="Fresh Telugu Action", year=2026, tmdb_id=99,
                            release_date="2026-09-20", language=["te"], genres=["Action"], provider=["tmdb"],
                            data_source=["tmdb_discovery"], freshness_status="verified_release_date")],
            "available", query_supported=True,
        )
        watchmode = self._provider(
            search=WatchmodeResponse(True, 200, {"title_results": [{"id": 44, "name": "Fresh Telugu Action", "year": 2026}]}),
            sources=WatchmodeResponse(True, 200, [{"name": "Netflix", "type": "sub", "region": "IN"}]),
        )
        with patch.object(movie_app, "GEMINI_API_KEY", ""), patch.object(movie_app, "WATCHMODE_CLIENT", watchmode), patch.object(movie_app, "TMDB_DISCOVERY", tmdb), patch.object(movie_app, "WATCHMODE_OTT_ENRICHER", WatchmodeOTTEnricher(watchmode)):
            response = self.client.get("/api/recommend-hybrid?text=Show%20me%20the%20latest%20Telugu%20action%20movies%20available%20on%20OTT%20in%20India&region=IN")
        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["mode"], "LATEST_OTT")
        self.assertEqual(payload["verification"]["freshness"], "verified_release_date")
        self.assertEqual(payload["availability_filter"]["requested"], True)
        self.assertEqual(payload["results"][0]["availability_status"], "verified_available")
        self.assertEqual(payload["results"][0]["watchmode_id"], 44)
        self.assertEqual(payload["results"][0]["streaming_sources"][0]["name"], "Netflix")
        watchmode.streaming_sources.assert_called_once_with(44, regions="IN")


if __name__ == "__main__":
    unittest.main()
