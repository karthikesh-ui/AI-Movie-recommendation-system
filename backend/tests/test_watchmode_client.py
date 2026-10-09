import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests

from watchmode_client import WatchmodeClient


def response(status_code, payload=None, json_error=None, headers=None):
    item = SimpleNamespace(status_code=status_code, headers=headers or {})
    item.json = Mock(side_effect=json_error) if json_error else Mock(return_value=payload)
    return item


class WatchmodeClientTests(unittest.TestCase):
    def client(self, get):
        return WatchmodeClient(api_key="test-key", session=SimpleNamespace(get=get))

    def test_successful_search_uses_header_and_validates_results(self):
        get = Mock(return_value=response(200, {"title_results": [{"id": 1}]}))
        result = self.client(get).search_by_title("RRR")
        self.assertTrue(result.ok)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(get.call_args.kwargs["headers"]["X-API-Key"], "test-key")
        self.assertNotIn("apiKey", get.call_args.kwargs["params"])

    def test_invalid_key_is_reported_without_provider_message(self):
        result = self.client(Mock(return_value=response(401, {"message": "secret detail"}))).status()
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "authentication_failed")

    def test_timeout_is_safe(self):
        result = self.client(Mock(side_effect=requests.Timeout)).status()
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "timeout")

    def test_rate_limit_preserves_only_retry_after(self):
        get = Mock(return_value=response(429, {}, headers={"Retry-After": "60"}))
        client = self.client(get)
        result = client.status()
        self.assertEqual(result.error, "rate_limited")
        self.assertEqual(result.retry_after, "60")
        self.assertEqual(client.status().error, "rate_limited")
        get.assert_called_once()

    def test_server_error_is_safe(self):
        result = self.client(Mock(return_value=response(500, {"error": "internal"}))).status()
        self.assertEqual(result.error, "http_error")
        self.assertEqual(result.status_code, 500)

    def test_empty_results_are_valid(self):
        result = self.client(Mock(return_value=response(200, {"title_results": []}))).search_by_title("Unknown")
        self.assertTrue(result.ok)
        self.assertEqual(result.data["title_results"], [])

    def test_malformed_json_is_rejected(self):
        result = self.client(Mock(return_value=response(200, json_error=ValueError("bad json")))).status()
        self.assertEqual(result.error, "malformed_response")

    def test_missing_configuration_skips_network(self):
        get = Mock()
        with patch.dict(os.environ, {"WATCHMODE_API_KEY": ""}, clear=False):
            result = WatchmodeClient(session=SimpleNamespace(get=get)).status()
        self.assertEqual(result.error, "missing_configuration")
        get.assert_not_called()

    def test_india_sources_and_paid_release_response_are_normalized(self):
        sources = self.client(Mock(return_value=response(200, []))).streaming_sources(123, regions="IN")
        restricted = self.client(Mock(return_value=response(401, {}))).release_discovery(
            regions="IN", advanced=True
        )
        self.assertTrue(sources.ok)
        self.assertEqual(restricted.error, "unauthorized")

    def test_authenticated_status_does_not_mislabel_paid_india_restriction(self):
        get = Mock(side_effect=[response(200, {"account": "active"}), response(401, {})])
        report = self.client(get).connectivity_status(verify_india_release_access=True)
        self.assertTrue(report["authenticated"])
        self.assertFalse(report["operation_supported"])
        self.assertEqual(report["quota_or_plan_restriction"], "paid_plan_or_region_not_enabled")

    def test_list_titles_uses_documented_discovery_parameters(self):
        get = Mock(return_value=response(200, {"titles": []}))
        result = self.client(get).list_titles(
            regions="IN", genres="4", languages="te",
            release_date_start="20260101", release_date_end="20261001",
            sort_by="release_date_desc", page=1, limit=10,
        )
        self.assertTrue(result.ok)
        params = get.call_args.kwargs["params"]
        self.assertEqual(params["regions"], "IN")
        self.assertEqual(params["genres"], "4")
        self.assertEqual(params["languages"], "te")
        self.assertEqual(params["sort_by"], "release_date_desc")

    def test_list_titles_rejects_malformed_title_payload(self):
        result = self.client(Mock(return_value=response(200, {"titles": "invalid"}))).list_titles()
        self.assertEqual(result.error, "malformed_response")


if __name__ == "__main__":
    unittest.main()
