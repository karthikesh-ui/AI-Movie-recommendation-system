import unittest

import pandas as pd

from nl_intent import build_dataset_vocabulary, find_catalog_terms, GENRE_ALIASES, validate_intent
from nl_pipeline import recommend_from_intent
from nl_recommender import retrieve_candidates


class NaturalLanguageIntentTests(unittest.TestCase):
    def setUp(self):
        self.movies = pd.DataFrame([
            {"title": "Action One", "genre": "Action, Thriller", "language": "Telugu", "year": 2022, "duration_min": 140, "rating": 8.0, "votes": 500},
            {"title": "Family One", "genre": "Family, Animation", "language": "Tamil", "year": 1995, "duration_min": 95, "rating": 7.8, "votes": 120},
            {"title": "Horror One", "genre": "Horror, Thriller", "language": "Telugu", "year": 2023, "duration_min": 110, "rating": 8.8, "votes": 900},
            {"title": "Space One", "genre": "Sci-Fi", "language": "Telugu", "year": 2020, "duration_min": 125, "rating": 7.0, "votes": 50},
        ])
        self.vocabulary = build_dataset_vocabulary(self.movies)

    def test_aliases_and_plural_catalog_terms_are_resolved(self):
        self.assertEqual(
            find_catalog_terms("uplifting sci fi thrillers", self.vocabulary["genres"], GENRE_ALIASES),
            ["sci-fi", "thriller"],
        )
        self.assertIn(
            "thriller",
            find_catalog_terms("thrillers", self.vocabulary["genres"], GENRE_ALIASES),
        )
        self.assertEqual(
            find_catalog_terms("latest Telugu comedies", {"comedy"}, GENRE_ALIASES),
            ["comedy"],
        )
        self.assertEqual(
            find_catalog_terms("recent romantic comedies", {"romance", "comedy"}, GENRE_ALIASES),
            ["romance", "comedy"],
        )

    def test_validation_resolves_aliases_and_keeps_exclusions_separate(self):
        intent = validate_intent(
            {"genres": ["action"], "exclude_genres": ["scary"], "languages": ["telugu"]},
            self.vocabulary,
        )
        self.assertEqual(intent["genres"], ["action"])
        self.assertEqual(intent["exclude_genres"], ["horror"])
        self.assertEqual(intent["languages"], ["telugu"])

    def test_excluded_genres_never_return_from_local_retrieval(self):
        intent = validate_intent(
            {"genres": ["thriller"], "exclude_genres": ["horror"], "languages": ["telugu"]},
            self.vocabulary,
        )
        results = recommend_from_intent(self.movies, intent, limit=10)
        self.assertEqual(results["title"].tolist(), ["Action One"])

    def test_explicit_genres_are_strict_and_not_replaced_by_adjacent_genres(self):
        intent = validate_intent(
            {"genres": ["sci-fi"], "languages": ["telugu"], "mood": "emotional"},
            self.vocabulary,
        )
        results = retrieve_candidates(self.movies, intent)
        self.assertEqual(results["title"].tolist(), ["Space One"])

    def test_multiple_explicit_genres_require_every_requested_genre(self):
        intent = validate_intent(
            {"genres": ["action", "thriller"], "languages": ["telugu"]},
            self.vocabulary,
        )
        results = retrieve_candidates(self.movies, intent)
        self.assertEqual(results["title"].tolist(), ["Action One"])


if __name__ == "__main__":
    unittest.main()
