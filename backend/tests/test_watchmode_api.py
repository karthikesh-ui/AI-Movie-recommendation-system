import unittest
from unittest.mock import Mock, patch

import app as movie_app
from watchmode_client import WatchmodeResponse


class WatchmodeApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = movie_app.app.test_client()

    def provider(self, **methods):
        fake = Mock()
        fake.configured = True
        for name, result in methods.items():
            setattr(fake, name, Mock(return_value=result))
        return fake

    def request_with(self, provider, path):
        with patch.object(movie_app, "WATCHMODE_CLIENT", provider):
            return self.client.get(path)

    def test_successful_status(self):
        response = self.request_with(
            self.provider(status=WatchmodeResponse(True, 200, {"unused": "value"})),
            "/api/watchmode/status",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["provider"], "watchmode")
        self.assertTrue(response.get_json()["authenticated"])
        self.assertNotIn("unused", response.get_json())

    def test_missing_api_key(self):
        response = self.request_with(
            self.provider(status=WatchmodeResponse(False, None, error="missing_configuration")),
            "/api/watchmode/status",
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["provider"], "watchmode")

    def test_successful_search_and_empty_search(self):
        success = self.request_with(
            self.provider(search_by_title=WatchmodeResponse(
                True, 200, {"title_results": [{"id": 12, "name": "RRR", "year": 2022}]}
            )),
            "/api/watchmode/search?q=RRR",
        )
        empty = self.request_with(
            self.provider(search_by_title=WatchmodeResponse(True, 200, {"title_results": []})),
            "/api/watchmode/search?q=Unknown",
        )
        self.assertEqual(success.status_code, 200)
        self.assertEqual(success.get_json()["count"], 1)
        self.assertEqual(empty.get_json()["results"], [])

    def test_invalid_query_and_title_id(self):
        self.assertEqual(self.client.get("/api/watchmode/search?q=").status_code, 400)
        self.assertEqual(self.client.get("/api/watchmode/title/not-a-number").status_code, 400)

    def test_successful_title_details(self):
        response = self.request_with(
            self.provider(movie_details=WatchmodeResponse(True, 200, {"id": 12, "title": "RRR"})),
            "/api/watchmode/title/12",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["result"]["title"], "RRR")

    def test_successful_regional_sources(self):
        provider = self.provider(streaming_sources=WatchmodeResponse(True, 200, [{"name": "Netflix"}]))
        response = self.request_with(provider, "/api/watchmode/sources/12?region=IN")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["region"], "IN")
        provider.streaming_sources.assert_called_once_with("12", regions="IN")

    def test_unsupported_region_or_plan_restriction(self):
        restricted = self.request_with(
            self.provider(streaming_sources=WatchmodeResponse(False, 401, error="unauthorized")),
            "/api/watchmode/sources/12?region=IN",
        )
        invalid_region = self.client.get("/api/watchmode/sources/12?region=India")
        self.assertEqual(restricted.status_code, 502)
        self.assertEqual(invalid_region.status_code, 400)

    def test_timeout_rate_limit_and_provider_error(self):
        timeout = self.request_with(
            self.provider(search_by_title=WatchmodeResponse(False, None, error="timeout")),
            "/api/watchmode/search?q=RRR",
        )
        limited = self.request_with(
            self.provider(search_by_title=WatchmodeResponse(False, 429, error="rate_limited", retry_after="60")),
            "/api/watchmode/search?q=RRR",
        )
        provider_error = self.request_with(
            self.provider(search_by_title=WatchmodeResponse(False, 500, error="http_error")),
            "/api/watchmode/search?q=RRR",
        )
        self.assertEqual(timeout.status_code, 504)
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited.get_json()["retry_after"], "60")
        self.assertEqual(provider_error.status_code, 502)


if __name__ == "__main__":
    unittest.main()
