"""Small, independent client for the Watchmode catalog API.

This module deliberately does not import Flask or recommendation code.  Its
methods return ``WatchmodeResponse`` objects instead of raising provider
details into application responses, so callers can make their own fallback
decision without exposing credentials or upstream internals.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Mapping, Optional

import requests


WATCHMODE_BASE_URL = "https://api.watchmode.com/v1"
DEFAULT_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class WatchmodeResponse:
    """A safe, normalized result from Watchmode.

    ``error`` is an application-safe category, not an upstream error message.
    API keys and response bodies are intentionally never retained in errors.
    """

    ok: bool
    status_code: Optional[int]
    data: Optional[Any] = None
    error: Optional[str] = None
    retry_after: Optional[str] = None


class WatchmodeClient:
    """Watchmode API client using the documented ``X-API-Key`` header."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        session: Any = requests,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        base_url: str = WATCHMODE_BASE_URL,
    ) -> None:
        self.api_key = (api_key if api_key is not None else os.getenv("WATCHMODE_API_KEY", "")).strip()
        self.session = session
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")
        self._retry_after_monotonic = 0.0

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _request(
        self,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        expected_type: type | tuple[type, ...] = dict,
    ) -> WatchmodeResponse:
        if not self.configured:
            return WatchmodeResponse(False, None, error="missing_configuration")
        if time.monotonic() < self._retry_after_monotonic:
            return WatchmodeResponse(False, 429, error="rate_limited")

        try:
            response = self.session.get(
                f"{self.base_url}/{path.lstrip('/')}",
                headers={"X-API-Key": self.api_key, "Accept": "application/json"},
                params=params,
                timeout=self.timeout,
            )
        except requests.Timeout:
            return WatchmodeResponse(False, None, error="timeout")
        except requests.RequestException:
            return WatchmodeResponse(False, None, error="network_error")

        status_code = getattr(response, "status_code", None)
        if status_code == 401:
            return WatchmodeResponse(False, status_code, error="unauthorized")
        if status_code == 429:
            retry_after = response.headers.get("Retry-After")
            try:
                self._retry_after_monotonic = time.monotonic() + max(0, int(retry_after))
            except (TypeError, ValueError):
                # A date-form Retry-After is still surfaced to callers, but is
                # not parsed here so a bad provider header cannot block calls.
                pass
            return WatchmodeResponse(
                False,
                status_code,
                error="rate_limited",
                retry_after=retry_after,
            )
        if not isinstance(status_code, int) or not 200 <= status_code < 300:
            return WatchmodeResponse(False, status_code, error="http_error")

        try:
            data = response.json()
        except (ValueError, requests.JSONDecodeError):
            return WatchmodeResponse(False, status_code, error="malformed_response")

        if not isinstance(data, expected_type):
            return WatchmodeResponse(False, status_code, error="malformed_response")
        return WatchmodeResponse(True, status_code, data=data)

    def status(self) -> WatchmodeResponse:
        """Call Watchmode's zero-credit status endpoint."""
        response = self._request("status/", expected_type=dict)
        if response.error == "unauthorized":
            return WatchmodeResponse(False, response.status_code, error="authentication_failed")
        return response

    def search_by_title(self, title: str) -> WatchmodeResponse:
        """Search titles only; one Watchmode catalog credit on success."""
        value = title.strip() if isinstance(title, str) else ""
        if not value:
            return WatchmodeResponse(False, None, error="invalid_request")
        response = self._request(
            "search/",
            params={"search_field": "name", "search_value": value},
            expected_type=dict,
        )
        if response.ok and not isinstance(response.data.get("title_results"), list):
            return WatchmodeResponse(False, response.status_code, error="malformed_response")
        return response

    def movie_details(self, watchmode_id: str | int) -> WatchmodeResponse:
        """Fetch details using a Watchmode ID (avoids external-ID lookup cost)."""
        if not str(watchmode_id).strip():
            return WatchmodeResponse(False, None, error="invalid_request")
        return self._request(f"title/{watchmode_id}/details/", expected_type=dict)

    def streaming_sources(
        self, watchmode_id: str | int, *, regions: Optional[str] = None
    ) -> WatchmodeResponse:
        """Fetch sources, optionally for account-enabled comma-separated regions."""
        if not str(watchmode_id).strip():
            return WatchmodeResponse(False, None, error="invalid_request")
        params = {"regions": regions} if regions else None
        return self._request(f"title/{watchmode_id}/sources/", params=params, expected_type=list)

    def genres(self) -> WatchmodeResponse:
        """Return Watchmode's genre reference list (one catalog credit)."""
        return self._request("genres/", expected_type=list)

    def list_titles(
        self,
        *,
        types: str = "movie",
        regions: Optional[str] = None,
        source_types: Optional[str] = None,
        genres: Optional[str] = None,
        languages: Optional[str] = None,
        release_date_start: Optional[str] = None,
        release_date_end: Optional[str] = None,
        sort_by: str = "release_date_desc",
        page: int = 1,
        limit: int = 20,
    ) -> WatchmodeResponse:
        """List/filter titles using the documented paid catalog operation.

        This method intentionally accepts only the dimensions used by the
        discovery adapter.  It does not assert that a caller's account has
        access to a requested region or that list-title dates have theatrical
        versus streaming semantics.
        """
        if not 1 <= int(page) or not 1 <= int(limit) <= 250:
            return WatchmodeResponse(False, None, error="invalid_request")
        params = {
            key: value for key, value in {
                "types": types,
                "regions": regions,
                "source_types": source_types,
                "genres": genres,
                "languages": languages,
                "release_date_start": release_date_start,
                "release_date_end": release_date_end,
                "sort_by": sort_by,
                "page": page,
                "limit": limit,
            }.items() if value is not None
        }
        response = self._request("list-titles/", params=params, expected_type=dict)
        if response.ok and not isinstance(response.data.get("titles"), list):
            return WatchmodeResponse(False, response.status_code, error="malformed_response")
        return response

    def release_discovery(
        self,
        *,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        regions: Optional[str] = None,
        advanced: bool = False,
    ) -> WatchmodeResponse:
        """Return release discovery data only when the caller explicitly requests it.

        ``advanced=True`` calls the paid ``title-release-dates`` endpoint, which
        supports a regional filter such as ``IN``.  The basic releases endpoint
        is primarily US-oriented and does not claim India-specific coverage.
        """
        params = {k: v for k, v in {
            "start_date": start_date, "end_date": end_date,
            "regions": regions if advanced else None,
        }.items() if v is not None}
        endpoint = "title-release-dates/" if advanced else "releases/"
        expected = list if advanced else dict
        return self._request(endpoint, params=params or None, expected_type=expected)

    def connectivity_status(self, *, verify_india_release_access: bool = False) -> dict[str, Any]:
        """Report zero-credit connectivity facts without making discovery calls.

        Region availability and paid-operation access are intentionally left
        unverified by default: checking them requires an account-specific paid
        call. Set ``verify_india_release_access`` only when spending one
        catalog credit is acceptable.
        """
        status = self.status()
        report = {
            "http_status": status.status_code,
            "authenticated": status.ok,
            "endpoint_accessible": status.ok,
            "operation_supported": None,
            "india_region_available": None,
            "quota_or_plan_restriction": None,
            "error": status.error,
        }
        if not status.ok or not verify_india_release_access:
            return report

        india_release = self.release_discovery(regions="IN", advanced=True)
        report["operation_supported"] = india_release.ok
        if india_release.ok:
            report["india_region_available"] = any(
                item.get("region") == "IN"
                for item in india_release.data
                if isinstance(item, dict)
            )
            report["quota_or_plan_restriction"] = None
        elif india_release.status_code == 401:
            # The status call already authenticated this key. Official docs
            # document 401 here for free-plan access, so do not call it a key
            # failure. Region enablement can also be account-specific.
            report["quota_or_plan_restriction"] = "paid_plan_or_region_not_enabled"
            report["error"] = "paid_plan_or_region_not_enabled"
        else:
            report["error"] = india_release.error
        return report


def api_connectivity_status(*, verify_india_release_access: bool = False) -> dict[str, Any]:
    return WatchmodeClient().connectivity_status(
        verify_india_release_access=verify_india_release_access
    )


def search_by_movie_title(title: str) -> WatchmodeResponse:
    return WatchmodeClient().search_by_title(title)


def fetch_movie_details(watchmode_id: str | int) -> WatchmodeResponse:
    return WatchmodeClient().movie_details(watchmode_id)


def fetch_streaming_sources(
    watchmode_id: str | int, *, regions: Optional[str] = None
) -> WatchmodeResponse:
    return WatchmodeClient().streaming_sources(watchmode_id, regions=regions)


def fetch_release_discovery(**kwargs: Any) -> WatchmodeResponse:
    return WatchmodeClient().release_discovery(**kwargs)
