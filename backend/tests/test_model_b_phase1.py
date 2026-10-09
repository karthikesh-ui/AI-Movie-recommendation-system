import unittest
from unittest.mock import Mock, patch

import pandas as pd

import app as movie_app


class ModelBPhaseOneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = movie_app.app.test_client()

    def setUp(self):
        self.gemini = Mock()
        self.omdb_movie = {
            "title": "The Paradise", "year": "2026", "rating": "N/A", "genre": "Action",
            "genres": ["Action"], "runtime": "N/A", "plot": "OMDb verified.",
            "overview": "OMDb verified.", "poster": "", "poster_url": "", "language": "Telugu",
            "source": "omdb", "local_match": False, "availability_status": "unknown",
        }
        self.gemini_patch = patch.object(movie_app, "MODEL_B_GEMINI", self.gemini)
        self.omdb_lookup = Mock(return_value=self.omdb_movie)
        self.omdb_patch = patch.object(movie_app, "_model_b_omdb_movie", self.omdb_lookup)
        self.gemini_patch.start()
        self.omdb_patch.start()

    def tearDown(self):
        self.omdb_patch.stop()
        self.gemini_patch.stop()

    def test_search_and_details_use_omdb_without_gemini(self):
        search = self.client.get("/api/search?q=The%20Paradise")
        details = self.client.get("/api/movie?title=The%20Paradise")

        self.assertEqual(search.status_code, 200)
        self.assertEqual(search.get_json()["source"], "omdb")
        self.assertEqual(details.status_code, 200)
        self.assertEqual(details.get_json()["source"], "omdb")
        self.assertEqual(self.gemini.mock_calls, [])

    def test_autocomplete_is_local_and_does_not_call_providers(self):
        tmdb = Mock()
        with patch.object(movie_app, "TMDB_CLIENT", tmdb):
            response = self.client.get("/api/autocomplete?q=RR")

        self.assertEqual(response.status_code, 200)
        self.assertIn("RRR", response.get_json())
        self.assertEqual(self.omdb_lookup.mock_calls, [])
        self.assertEqual(self.gemini.mock_calls, [])
        self.assertEqual(tmdb.mock_calls, [])

    def test_recommendations_use_at_most_six_omdb_poster_enrichments(self):
        response = self.client.get("/api/recommend?title=The%20Paradise")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["source"], "local")
        self.assertLessEqual(self.omdb_lookup.call_count, 6)
        self.assertEqual(self.gemini.mock_calls, [])

    def test_local_recommendations_exclude_seed_without_gemini(self):
        response = self.client.get("/api/recommend?title=RRR&year=2022&genre=Action,Drama&language=Telugu")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["source"], "local")
        self.assertEqual(payload["recommendation_source"], "tfidf_nn")
        self.assertLessEqual(payload["count"], 6)
        self.assertTrue(all(item["title"].casefold() != "rrr" for item in payload["results"]))
        self.assertTrue(all("telugu" in str(item["language"]).casefold() for item in payload["results"]))
        self.assertLessEqual(self.omdb_lookup.call_count, 6)
        self.assertEqual(self.gemini.mock_calls, [])

    def test_local_recommendations_keep_selected_language_and_exclude_title_duplicates(self):
        catalog = pd.DataFrame([
            {"id": "tt001", "title": "RRR", "year": 2022, "duration_min": 180, "rating": 8.0, "votes": 1000,
             "genre": "Action, Drama", "genre_original": "Action, Drama", "language": "telugu", "language_original": "Telugu"},
            {"id": "tt002", "title": "RRR", "year": 1999, "duration_min": 120, "rating": 7.5, "votes": 500,
             "genre": "Action", "genre_original": "Action", "language": "telugu", "language_original": "Telugu"},
            {"id": "tt003", "title": "Telugu Action", "year": 2021, "duration_min": 130, "rating": 7.0, "votes": 400,
             "genre": "Action", "genre_original": "Action", "language": "telugu", "language_original": "Telugu"},
            {"id": "tt004", "title": "Tamil Action", "year": 2022, "duration_min": 130, "rating": 9.0, "votes": 900,
             "genre": "Action, Drama", "genre_original": "Action, Drama", "language": "tamil", "language_original": "Tamil"},
        ])
        keys = catalog["title"].str.casefold().str.replace(r"[^\w]+", " ", regex=True).str.strip()
        with patch.object(movie_app, "movies", catalog), patch.object(movie_app, "MODEL_B_TITLE_KEYS", keys), \
             patch.object(movie_app, "tfidf_matrix", None), patch.object(movie_app, "neighbors", None):
            results, strategy = movie_app._model_b_local_recommendations(
                "RRR", 2022, ["Action", "Drama"], "tt001", 6, "Telugu"
            )

        self.assertEqual(strategy, "genre_fallback")
        self.assertEqual([item["title"] for item in results], ["Telugu Action"])

    def test_optional_director_and_cast_matches_boost_local_candidates(self):
        catalog = pd.DataFrame([
            {"id": "tt001", "title": "Seed", "year": 2022, "duration_min": 120, "rating": 8.0, "votes": 1000,
             "genre": "Action", "genre_original": "Action", "language": "telugu", "language_original": "Telugu", "director": "A Director", "cast": "Actor One, Actor Two"},
            {"id": "tt002", "title": "Shared Team", "year": 2020, "duration_min": 120, "rating": 6.0, "votes": 100,
             "genre": "Action", "genre_original": "Action", "language": "telugu", "language_original": "Telugu", "director": "A Director", "cast": "Actor One, Another Actor"},
            {"id": "tt003", "title": "Unrelated Team", "year": 2022, "duration_min": 120, "rating": 9.5, "votes": 9000,
             "genre": "Action", "genre_original": "Action", "language": "telugu", "language_original": "Telugu", "director": "Other Director", "cast": "Other Actor"},
        ])
        keys = catalog["title"].str.casefold().str.replace(r"[^\w]+", " ", regex=True).str.strip()
        with patch.object(movie_app, "movies", catalog), patch.object(movie_app, "MODEL_B_TITLE_KEYS", keys), \
             patch.object(movie_app, "tfidf_matrix", None), patch.object(movie_app, "neighbors", None):
            results, _ = movie_app._model_b_local_recommendations(
                "Seed", 2022, ["Action"], "tt001", 6, "Telugu", "A Director", "Actor One, Actor Two"
            )

        self.assertEqual(results[0]["title"], "Shared Team")

    def test_omdb_poster_enrichment_preserves_local_source(self):
        self.omdb_movie.update({"poster": "https://poster.test/final.jpg", "poster_url": "https://poster.test/final.jpg", "imdb_id": "tt1234567"})
        response = self.client.get("/api/recommend?title=RRR&year=2022&genre=Action,Drama")

        item = response.get_json()["results"][0]
        self.assertEqual(item["source"], "local")
        self.assertEqual(item["poster"], "https://poster.test/final.jpg")
        self.assertLessEqual(self.omdb_lookup.call_count, 6)

    def test_na_omdb_poster_is_normalized_to_null(self):
        self.omdb_movie.update({"poster": "N/A", "poster_url": "N/A"})
        response = self.client.get("/api/recommend?title=RRR&year=2022&genre=Action,Drama")

        self.assertIsNone(response.get_json()["results"][0]["poster"])

    def test_omdb_missing_movie_returns_empty_search_results(self):
        self.omdb_lookup.return_value = None
        with patch.object(movie_app, "OMDB_API_KEY", "configured"):
            response = self.client.get("/api/search?q=The%20Paradise")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["results"], [])


if __name__ == "__main__":
    unittest.main()
