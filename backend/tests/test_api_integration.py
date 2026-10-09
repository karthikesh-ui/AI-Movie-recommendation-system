import os
import unittest
from urllib.parse import urlencode
from unittest.mock import Mock, patch

import app as movie_app
from model_b_gemini import GeminiMovieResponse


class ApiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = movie_app.app.test_client()

    def setUp(self):
        self.gemini_patch = patch.object(movie_app, "GEMINI_API_KEY", "")
        self.omdb_patch = patch.object(movie_app, "OMDB_API_KEY", "")
        self.gemini_patch.start()
        self.omdb_patch.start()
        self.model_b_gemini = Mock()
        self.model_b_gemini.identify_and_discover.return_value = GeminiMovieResponse(False, error="missing_configuration")
        self.model_b_gemini_patch = patch.object(movie_app, "MODEL_B_GEMINI", self.model_b_gemini)
        self.model_b_gemini_patch.start()
        movie_app._model_b_gemini.cache_clear()

    def tearDown(self):
        movie_app._omdb.cache_clear()
        movie_app.movie_details.cache_clear()
        self.omdb_patch.stop()
        self.gemini_patch.stop()
        self.model_b_gemini_patch.stop()

    def test_health_reports_model_state_without_secrets(self):
        response = self.client.get("/api/health")
        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["model_loaded"])
        self.assertEqual(payload["movies_loaded"], len(movie_app.movies))
        self.assertIsInstance(payload["gemini_configured"], bool)
        self.assertIsInstance(payload["omdb_configured"], bool)
        self.assertIsInstance(payload["watchmode_configured"], bool)
        self.assertNotIn("GEMINI_API_KEY", payload)
        self.assertNotIn("OMDB_API_KEY", payload)
        self.assertNotIn("WATCHMODE_API_KEY", payload)

    def test_live_server_origin_passes_cors_preflight(self):
        response = self.client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:5500",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("Access-Control-Allow-Origin"),
            "http://localhost:5500",
        )

    def test_cors_rejects_wildcard_and_unconfigured_origins(self):
        with patch.dict(os.environ, {"FRONTEND_ORIGIN": "*"}):
            self.assertEqual(
                movie_app._configured_frontend_origins(),
                ["http://localhost:5500"],
            )

        with patch.dict(
            os.environ,
            {"FRONTEND_ORIGIN": "https://frontend.example, http://localhost:5500"},
        ):
            self.assertEqual(
                movie_app._configured_frontend_origins(),
                ["https://frontend.example", "http://localhost:5500"],
            )

        response = self.client.options(
            "/api/health",
            headers={
                "Origin": "https://unconfigured.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))

    def test_autocomplete_returns_titles_and_handles_short_query(self):
        empty = self.client.get("/api/autocomplete?q=R")
        response = self.client.get("/api/autocomplete?q=RR")
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.get_json(), [])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()[0], "RRR")
        self.assertLessEqual(len(response.get_json()), 8)

    def test_search_returns_exact_title_first(self):
        with patch.object(movie_app, "OMDB_API_KEY", ""):
            response = self.client.get("/api/search?q=RRR")
        self.assertEqual(response.status_code, 200)
        results = response.get_json()["results"]
        self.assertEqual(results[0]["title"], "RRR")
        self.assertLessEqual(len(results), 10)

    def test_movie_details_use_local_catalog_without_omdb(self):
        with patch.object(movie_app, "OMDB_API_KEY", ""):
            response = self.client.get(
                "/api/movie?" + urlencode({"title": "RRR"})
            )
        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["title"], "RRR")
        self.assertEqual(payload["source"], "local")
        self.assertTrue(payload["local_match"])

    def test_model_b_recommendations_are_local(self):
        with patch.object(movie_app, "OMDB_API_KEY", ""):
            response = self.client.get(
                "/api/recommend?" + urlencode({"title": "RRR", "limit": 6})
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["source"], "local")

    def test_invalid_and_empty_inputs_have_controlled_errors(self):
        self.assertEqual(self.client.get("/api/movie").status_code, 400)
        self.assertEqual(self.client.get("/api/recommend").status_code, 400)
        self.assertEqual(self.client.get("/api/recommend-text").status_code, 400)
        self.assertEqual(
            self.client.get("/api/recommend?title=RRR&limit=nope").status_code,
            400,
        )
        self.assertEqual(
            self.client.get("/api/movie?title=__unknown_movie__").status_code,
            503,
        )

    def test_oversized_inputs_and_result_limits_are_rejected(self):
        long_value = "x" * 501
        self.assertEqual(
            self.client.get("/api/recommend-text?" + urlencode({"text": long_value})).status_code,
            400,
        )
        self.assertEqual(
            self.client.get("/api/movie?" + urlencode({"title": "x" * 151})).status_code,
            400,
        )
        self.assertEqual(
            self.client.get("/api/recommend?title=RRR&limit=21").status_code,
            400,
        )
        self.assertEqual(
            self.client.get("/api/search?q=" + "x" * 151).status_code,
            400,
        )
        self.assertEqual(
            self.client.get("/api/autocomplete?q=" + "x" * 151).status_code,
            400,
        )

    def test_flask_serves_existing_frontend_pages_and_scripts(self):
        for path in (
            "/",
            "/recommendation.html",
            "/movie-search.html",
            "/theme.js",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                try:
                    self.assertEqual(response.status_code, 200)
                finally:
                    response.close()


if __name__ == "__main__":
    unittest.main()
