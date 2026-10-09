import json
import unittest
from types import SimpleNamespace
from urllib.parse import urlencode
from unittest.mock import Mock, patch

import pandas as pd
import requests

import app as movie_app
from nl_pipeline import recommend_from_intent
from nl_recommender import retrieve_candidates


class ModelBApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = movie_app.app.test_client()

    def request_recommendations(self, text):
        with patch.object(movie_app, "GEMINI_API_KEY", ""), patch.object(
            movie_app, "OMDB_API_KEY", ""
        ), patch.object(
            movie_app, "RECOMMENDATION_SOURCE", "local"
        ):
            response = self.client.get(
                "/api/recommend-text?" + urlencode({"text": text})
            )
        return response, response.get_json()

    def test_phase_a_natural_language_cases(self):
        cases = [
            (
                "I want a feel-good movie to watch alone tonight",
                {"mood": "feel_good", "audience": "solo"},
            ),
            (
                "Suggest a family-friendly Indian comedy",
                {"audience": "family", "genres": {"comedy", "family"}},
            ),
            ("I want a suspense thriller", {"genres": {"thriller"}}),
            (
                "Recommend a short movie for tonight",
                {"duration_preference": "short"},
            ),
            ("I want an emotional romantic movie", {"mood": "romantic"}),
            (
                "Suggest a science-fiction adventure",
                {"genres": {"adventure"}},
            ),
            (
                "Recommend a Telugu action movie",
                {"genres": {"action"}, "languages": {"telugu"}},
            ),
            (
                "Suggest a Hindi romantic movie",
                {"mood": "romantic", "languages": {"hindi"}},
            ),
            (
                "Recommend a movie released between 2010 and 2020",
                {"year_from": 2010, "year_to": 2020},
            ),
            (
                "Suggest a Hindi action movie released between 2010 and 2020 under 2 hours",
                {
                    "genres": {"action"},
                    "languages": {"hindi"},
                    "year_from": 2010,
                    "year_to": 2020,
                    "duration_preference": "short",
                },
            ),
        ]

        for text, expected in cases:
            with self.subTest(text=text):
                response, payload = self.request_recommendations(text)
                self.assertEqual(response.status_code, 200)
                intent = payload["intent"]
                results = payload["results"]
                self.assertTrue(results)
                self.assertEqual(
                    len({item["title"].casefold() for item in results}),
                    len(results),
                )
                self.assertFalse(
                    any(key.startswith("_") for item in results for key in item)
                )

                for key, value in expected.items():
                    if key in {"genres", "languages"}:
                        self.assertTrue(value.issubset(set(intent[key])))
                    else:
                        self.assertEqual(intent[key], value)

                if expected.get("genres"):
                    requested_genres = set(intent["genres"])
                    self.assertTrue(
                        all(
                            requested_genres.intersection(
                                genre.strip().casefold()
                                for genre in item["genre"].split(",")
                            )
                            for item in results
                        )
                    )
                if "telugu" in expected.get("languages", set()):
                    self.assertTrue(
                        all("telugu" in item["language"].casefold() for item in results)
                    )
                if "hindi" in expected.get("languages", set()):
                    self.assertTrue(
                        all("hindi" in item["language"].casefold() for item in results)
                    )
                if expected.get("year_from"):
                    self.assertTrue(
                        all(
                            expected["year_from"] <= int(item["year"])
                            <= expected["year_to"]
                            for item in results
                        )
                    )
                if expected.get("duration_preference") == "short":
                    self.assertTrue(
                        all(int(item["runtime"].split()[0]) < 120 for item in results)
                    )

    def test_fallback_results_are_deterministic(self):
        text = "Suggest a Hindi romantic movie"
        first_response, first = self.request_recommendations(text)
        second_response, second = self.request_recommendations(text)
        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(first["intent"], second["intent"])
        self.assertEqual(first["results"], second["results"])

    def test_short_hindi_comedy_enforces_duration_language_and_genre(self):
        response, payload = self.request_recommendations("Suggest a short Hindi comedy")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["intent"]["duration_preference"], "short")
        self.assertIn("hindi", payload["intent"]["languages"])
        self.assertIn("comedy", payload["intent"]["genres"])
        self.assertTrue(payload["results"])
        for result in payload["results"]:
            self.assertIn("hindi", result["language"].casefold())
            self.assertIn("comedy", result["genre"].casefold())
            self.assertLess(int(result["runtime"].split()[0]), 120)

    def test_science_fiction_spelling_variants_map_to_available_genre_hints(self):
        expected_genres = {
            genre
            for genre in ("adventure", "fantasy", "action")
            if genre in movie_app.DATASET_VOCABULARY["genres"]
        }
        for phrase in ("science fiction", "science-fiction", "sci-fi", "scifi"):
            with self.subTest(phrase=phrase):
                intent, _ = movie_app._rule_based_intent_parse(
                    f"Suggest a {phrase} adventure",
                    movie_app.DATASET_VOCABULARY,
                )
                self.assertTrue(expected_genres.issubset(set(intent["genres"])))

    def test_after_year_is_exclusive_and_merged_from_partial_gemini(self):
        partial_intent = json.dumps(
            {
                "genres": [],
                "languages": [],
                "year_from": None,
                "year_to": None,
                "duration_preference": None,
                "mood": None,
                "audience": None,
                "ranking": "general",
            }
        )
        with patch.object(movie_app, "GEMINI_API_KEY", "configured"), patch.object(
            movie_app, "_create_gemini_client", return_value=object()
        ), patch.object(
            movie_app, "_generate_with_gemini", return_value=partial_intent
        ):
            intent, _ = movie_app.parse_recommendation_intent(
                "Recommend a feel-good movie released after 2015",
                movie_app.DATASET_VOCABULARY,
            )

        self.assertEqual(intent["year_from"], 2016)
        self.assertEqual(intent["mood"], "feel_good")

        response, payload = self.request_recommendations(
            "Recommend a feel-good movie released after 2015"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["intent"]["year_from"], 2016)
        self.assertTrue(all(int(item["year"]) >= 2016 for item in payload["results"]))

    def test_title_recommendations_are_local_in_model_b_phase_two(self):
        tmdb = Mock()
        with patch.object(movie_app, "OMDB_API_KEY", ""), patch.object(movie_app, "TMDB_CLIENT", tmdb):
            response = self.client.get(
                "/api/recommend?" + urlencode({"title": "RRR", "limit": 6})
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["source"], "local")
        self.assertEqual(tmdb.mock_calls, [])

    def test_omdb_runtime_cannot_override_duration_constraint_metadata(self):
        def conflicting_enrichment(title, dataset_index=None):
            return {
                "title": title,
                "year": 2099,
                "rating": 10,
                "genre": "Unrelated",
                "runtime": "999 min",
                "language": "unrelated",
                "poster": "",
                "plot": "",
                "source": "Indian Dataset + OMDb",
            }

        with patch.object(movie_app, "GEMINI_API_KEY", ""), patch.object(
            movie_app, "OMDB_API_KEY", ""
        ), patch.object(movie_app, "get_movie_details", side_effect=conflicting_enrichment):
            response, payload = self.request_recommendations(
                "Recommend a short movie for tonight"
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["results"])
        for result in payload["results"]:
            self.assertNotEqual(result["runtime"], "999 min")
            self.assertTrue(
                result["runtime"] == "N/A"
                or int(result["runtime"].split()[0]) < 120
            )

    def test_search_places_exact_title_before_substring_matches(self):
        with patch.object(movie_app, "OMDB_API_KEY", ""):
            response = self.client.get("/api/search?q=RRR")

        self.assertEqual(response.status_code, 200)
        results = response.get_json()["results"]
        self.assertEqual(results[0]["title"].casefold(), "rrr")


class ModelBRetrievalTests(unittest.TestCase):
    def test_missing_metadata_does_not_crash_retrieval(self):
        movies = pd.DataFrame(
            [
                {"title": "Known genre", "genre": "romance", "year": None, "duration_min": None},
                {"title": "Missing genre", "genre": None, "year": None, "duration_min": None},
            ]
        )
        intent = {
            "genres": [],
            "languages": [],
            "year_from": None,
            "year_to": None,
            "duration_preference": None,
            "mood": "romantic",
            "audience": None,
        }
        candidates = retrieve_candidates(movies, intent)
        self.assertEqual(len(candidates), 2)

    def test_mood_match_outranks_conflicting_audience_match(self):
        movies = pd.DataFrame(
            [
                {"title": "Feel-good comedy", "genre": "comedy", "rating": 5.0, "votes": 50},
                {"title": "Solo thriller", "genre": "thriller", "rating": 9.0, "votes": 10000},
            ]
        )
        intent = {
            "genres": [],
            "languages": [],
            "year_from": None,
            "year_to": None,
            "duration_preference": None,
            "mood": "feel_good",
            "audience": "solo",
            "ranking": "general",
        }
        results = recommend_from_intent(movies, intent, limit=2)
        self.assertEqual(results.iloc[0]["title"], "Feel-good comedy")
        self.assertFalse(any(column.startswith("_") for column in results.columns))

    def test_mood_ranking_uses_ascending_title_for_ties(self):
        movies = pd.DataFrame(
            [
                {"title": "Zulu romance", "genre": "romance", "rating": 7.0, "votes": 100},
                {"title": "Alpha romance", "genre": "romance", "rating": 7.0, "votes": 100},
            ]
        )
        intent = {
            "genres": [],
            "languages": [],
            "year_from": None,
            "year_to": None,
            "duration_preference": None,
            "mood": "romantic",
            "audience": None,
            "ranking": "general",
        }
        results = recommend_from_intent(movies, intent, limit=2)
        self.assertEqual(results["title"].tolist(), ["Alpha romance", "Zulu romance"])


class ExternalServiceTests(unittest.TestCase):
    def tearDown(self):
        movie_app._omdb.cache_clear()
        movie_app.movie_details.cache_clear()
        movie_app.nl_ai_explanation.cache_clear()
        movie_app._gemini_relevant_explanation_fields.cache_clear()
        movie_app.GEMINI_RETRY_AFTER = 0.0
        movie_app.OMDB_RETRY_AFTER = 0.0

    def test_gemini_malformed_json_uses_rule_fallback(self):
        with patch.object(movie_app, "GEMINI_API_KEY", "configured"), patch.object(
            movie_app, "_create_gemini_client", return_value=object()
        ), patch.object(movie_app, "_generate_with_gemini", return_value="{invalid"):
            intent, unsupported = movie_app.parse_recommendation_intent(
                "I want a feel-good movie to watch alone",
                movie_app.DATASET_VOCABULARY,
            )

        self.assertEqual(intent["mood"], "feel_good")
        self.assertEqual(intent["audience"], "solo")
        self.assertEqual(unsupported, {"genres": [], "languages": []})

    def test_gemini_timeout_returns_no_generated_content(self):
        generate = Mock(side_effect=TimeoutError("private request detail"))
        client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
        self.assertIsNone(movie_app._generate_with_gemini(client, "prompt"))
        self.assertIsNone(movie_app._generate_with_gemini(client, "another prompt"))
        self.assertEqual(generate.call_count, 1)

    def test_unsupported_gemini_intent_is_safely_normalized(self):
        generated = json.dumps(
            {
                "genres": ["not-a-dataset-genre"],
                "languages": ["klingon"],
                "mood": "cosmic",
                "audience": "alien",
                "ranking": "unbounded",
            }
        )
        with patch.object(movie_app, "GEMINI_API_KEY", "configured"), patch.object(
            movie_app, "_create_gemini_client", return_value=object()
        ), patch.object(movie_app, "_generate_with_gemini", return_value=generated):
            intent, unsupported = movie_app.parse_recommendation_intent(
                "Recommend a movie",
                movie_app.DATASET_VOCABULARY,
            )

        self.assertEqual(intent["genres"], [])
        self.assertEqual(intent["languages"], [])
        self.assertIsNone(intent["mood"])
        self.assertIsNone(intent["audience"])
        self.assertEqual(intent["ranking"], "general")
        self.assertEqual(unsupported["genres"], ["not-a-dataset-genre"])
        self.assertEqual(unsupported["languages"], ["klingon"])

    def test_gemini_explanation_uses_only_supplied_metadata(self):
        generated = json.dumps(
            {"relevant_fields": ["genre", "year", "cast"]}
        )
        movie_app.nl_ai_explanation.cache_clear()
        with patch.object(movie_app, "GEMINI_API_KEY", "configured"), patch.object(
            movie_app, "_create_gemini_client", return_value=object()
        ), patch.object(movie_app, "_generate_with_gemini", return_value=generated):
            explanation = movie_app.nl_ai_explanation(
                "Hindi action movie",
                "Example Film",
                2018,
                7.2,
                "Action",
                "Hindi",
            )

        self.assertIn("genre: Action", explanation)
        self.assertIn("year: 2018", explanation)
        self.assertNotIn("cast", explanation.casefold())
        self.assertNotIn("7.2", explanation)

    def test_gemini_relevant_field_selection_is_shared_per_request(self):
        generated = json.dumps({"relevant_fields": ["genre", "language"]})
        generate = Mock(return_value=generated)
        with patch.object(movie_app, "GEMINI_API_KEY", "configured"), patch.object(
            movie_app, "_create_gemini_client", return_value=object()
        ), patch.object(movie_app, "_generate_with_gemini", generate):
            first = movie_app.nl_ai_explanation(
                "Hindi romantic movie", "Film One", 2018, 7.1, "Romance", "Hindi"
            )
            second = movie_app.nl_ai_explanation(
                "Hindi romantic movie", "Film Two", 2020, 8.0, "Drama", "Hindi"
            )

        self.assertIn("genre: Romance", first)
        self.assertIn("genre: Drama", second)
        self.assertEqual(generate.call_count, 1)

    def test_movie_details_explanation_is_grounded_without_gemini(self):
        explanation = movie_app.ai_explanation("Base Film", "Candidate Film")
        self.assertIn("recommendation model", explanation)
        self.assertIn("Base Film", explanation)
        self.assertNotIn("shares themes", explanation)

    def test_omdb_missing_key_skips_network(self):
        movie_app._omdb.cache_clear()
        with patch.object(movie_app, "OMDB_API_KEY", ""), patch.object(
            movie_app.requests, "get"
        ) as get:
            self.assertIsNone(movie_app._omdb("No Key Film"))
        get.assert_not_called()

    def test_omdb_timeout_uses_dataset_fallback_path(self):
        movie_app._omdb.cache_clear()
        with patch.object(movie_app, "OMDB_API_KEY", "test-key"), patch.object(
            movie_app.requests, "get", side_effect=requests.Timeout
        ) as get:
            self.assertIsNone(movie_app._omdb("Timeout Film"))
            self.assertIsNone(movie_app._omdb("Another Timeout Film"))
        get.assert_called_once()

    def test_omdb_non_object_json_is_rejected(self):
        movie_app._omdb.cache_clear()
        response = SimpleNamespace(
            raise_for_status=Mock(),
            json=Mock(return_value=[]),
        )
        with patch.object(movie_app, "OMDB_API_KEY", "test-key"), patch.object(
            movie_app.requests, "get", return_value=response
        ):
            self.assertIsNone(movie_app._omdb("Malformed Film"))

    def test_omdb_missing_fields_are_defaulted_and_cached(self):
        movie_app._omdb.cache_clear()
        movie_app.movie_details.cache_clear()
        response = SimpleNamespace(
            raise_for_status=Mock(),
            json=Mock(return_value={"Response": "True"}),
        )
        with patch.object(movie_app, "OMDB_API_KEY", "test-key"), patch.object(
            movie_app.requests, "get", return_value=response
        ) as get:
            details = movie_app.movie_details("Sparse Film")
            movie_app.movie_details("Sparse Film")

        self.assertEqual(details["title"], "Sparse Film")
        self.assertEqual(details["genre"], "N/A")
        self.assertEqual(details["language"], "N/A")
        self.assertEqual(details["poster"], "")
        self.assertEqual(details["country"], "N/A")
        self.assertEqual(details["released"], "N/A")
        self.assertEqual(details["awards"], "N/A")
        self.assertEqual(details["metascore"], "N/A")
        get.assert_called_once()


if __name__ == "__main__":
    unittest.main()
