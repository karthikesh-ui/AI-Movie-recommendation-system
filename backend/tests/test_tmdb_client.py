import unittest
import os
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests

from tmdb_client import TMDBClient


def response(status_code, payload=None, json_error=None, headers=None):
    item = SimpleNamespace(status_code=status_code, headers=headers or {})
    item.json = Mock(side_effect=json_error) if json_error else Mock(return_value=payload)
    return item


class TMDBClientTests(unittest.TestCase):
    def client(self, get, token="eyJmock-read-access-token"):
        return TMDBClient(read_access_token=token, session=SimpleNamespace(get=get))

    def test_bearer_authentication_and_discovery_request(self):
        get = Mock(return_value=response(200, {"page": 1, "results": []}))
        result = self.client(get).discover_movies(
            genre_id=28, original_language="te", region="IN",
            release_date_start="2026-07-01", release_date_end="2026-10-01", page=1, limit=10,
        )
        self.assertTrue(result.ok)
        params = get.call_args.kwargs["params"]
        self.assertNotIn("api_key", params)
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer eyJmock-read-access-token")
        self.assertEqual(get.call_args.kwargs["headers"]["accept"], "application/json")
        self.assertEqual(params["with_genres"], "28")
        self.assertEqual(params["with_original_language"], "te")
        self.assertEqual(params["region"], "IN")
        self.assertEqual(params["sort_by"], "primary_release_date.desc")

    def test_environment_token_is_loaded_without_legacy_key_fallback(self):
        get = Mock(return_value=response(200, {"genres": []}))
        with patch.dict(os.environ, {"TMDB_API_READ_ACCESS_TOKEN": "eyJenv-token", "TMDB_API_KEY": "legacy-key"}, clear=False):
            TMDBClient(session=SimpleNamespace(get=get)).movie_genres()
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer eyJenv-token")
        self.assertNotIn("api_key", get.call_args.kwargs["params"])

    def test_missing_key_skips_network(self):
        get = Mock()
        result = TMDBClient(read_access_token="", session=SimpleNamespace(get=get)).movie_genres()
        self.assertEqual(result.error, "missing_configuration")
        get.assert_not_called()

    def test_unauthorized_rate_limit_and_server_error_are_safe(self):
        for status, expected in ((401, "authentication_failed"), (403, "unauthorized"), (429, "rate_limited"), (500, "http_error")):
            with self.subTest(status=status):
                result = self.client(Mock(return_value=response(status, {}, headers={"Retry-After": "30"}))).movie_genres()
                self.assertEqual(result.error, expected)

    def test_timeout_malformed_empty_and_pagination(self):
        self.assertEqual(self.client(Mock(side_effect=requests.Timeout)).movie_genres().error, "timeout")
        malformed = self.client(Mock(return_value=response(200, {"page": 1, "results": "bad"}))).discover_movies(
            genre_id=28, original_language="te", region="IN", release_date_start="2026-01-01", release_date_end="2026-10-01"
        )
        self.assertEqual(malformed.error, "malformed_response")
        empty = self.client(Mock(return_value=response(200, {"page": 2, "results": []}))).discover_movies(
            genre_id=28, original_language="te", region="IN", release_date_start="2026-01-01", release_date_end="2026-10-01", page=2
        )
        self.assertTrue(empty.ok)
        self.assertEqual(empty.data["page"], 2)

    def test_transient_timeout_is_retried_once(self):
        get = Mock(side_effect=[requests.Timeout, response(200, {"page": 1, "results": []})])
        result = self.client(get).discover_movies(
            genre_id=28, original_language="te", region="IN",
            release_date_start="2026-07-01", release_date_end="2026-10-01",
        )
        self.assertTrue(result.ok)
        self.assertEqual(get.call_count, 2)

    def test_movie_search_and_details_use_bearer_only(self):
        get = Mock(side_effect=[
            response(200, {"page": 1, "results": [{"id": 1, "title": "RRR"}]}),
            response(200, {"id": 1, "title": "RRR"}),
        ])
        client = self.client(get)
        self.assertTrue(client.search_movies("RRR").ok)
        self.assertTrue(client.movie_details(1).ok)
        self.assertTrue(get.call_args_list[0].args[0].endswith("/search/movie"))
        self.assertTrue(get.call_args_list[1].args[0].endswith("/movie/1"))
        for call in get.call_args_list:
            self.assertNotIn("api_key", call.kwargs["params"])
            self.assertTrue(call.kwargs["headers"]["Authorization"].startswith("Bearer "))

    def test_related_movie_requests_use_bearer_only(self):
        get = Mock(return_value=response(200, {"page": 1, "results": []}))
        client = self.client(get)
        self.assertTrue(client.similar_movies(1).ok)
        self.assertTrue(client.recommended_movies(1).ok)
        self.assertTrue(get.call_args_list[0].args[0].endswith("/movie/1/similar"))
        self.assertTrue(get.call_args_list[1].args[0].endswith("/movie/1/recommendations"))
