"""Small, safe TMDB v3 client for server-side movie discovery."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Mapping, Optional

import requests


TMDB_BASE_URL = "https://api.themoviedb.org/3"
DEFAULT_TIMEOUT_SECONDS = 10
TRANSIENT_REQUEST_ATTEMPTS = 2


@dataclass(frozen=True)
class TMDBResponse:
    ok: bool
    status_code: Optional[int]
    data: Optional[Any] = None
    error: Optional[str] = None
    retry_after: Optional[str] = None


class TMDBClient:
    """TMDB Read Access Token client without credential leakage."""

    def __init__(self, read_access_token: Optional[str] = None, *, session: Any = requests, timeout: int = DEFAULT_TIMEOUT_SECONDS, base_url: str = TMDB_BASE_URL) -> None:
        self.read_access_token = (read_access_token if read_access_token is not None else os.getenv("TMDB_API_READ_ACCESS_TOKEN", "")).strip()
        self.session = session
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")
        self._retry_after_monotonic = 0.0

    @property
    def configured(self) -> bool:
        return bool(self.read_access_token)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.read_access_token}", "accept": "application/json"}

    def _request(self, path: str, *, params: Optional[Mapping[str, Any]] = None, expected_type: type | tuple[type, ...] = dict) -> TMDBResponse:
        if not self.configured:
            return TMDBResponse(False, None, error="missing_configuration")
        if time.monotonic() < self._retry_after_monotonic:
            return TMDBResponse(False, 429, error="rate_limited")
        response = None
        last_error = None
        for _ in range(TRANSIENT_REQUEST_ATTEMPTS):
            try:
                response = self.session.get(
                    f"{self.base_url}/{path.lstrip('/')}",
                    params=dict(params or {}), headers=self._headers(), timeout=self.timeout,
                )
                break
            except requests.Timeout:
                last_error = "timeout"
            except requests.RequestException:
                last_error = "network_error"
        if response is None:
            return TMDBResponse(False, None, error=last_error or "network_error")
        status_code = getattr(response, "status_code", None)
        if status_code == 401:
            return TMDBResponse(False, status_code, error="authentication_failed")
        if status_code == 403:
            return TMDBResponse(False, status_code, error="unauthorized")
        if status_code == 429:
            retry_after = response.headers.get("Retry-After")
            try:
                self._retry_after_monotonic = time.monotonic() + max(0, int(retry_after))
            except (TypeError, ValueError):
                pass
            return TMDBResponse(False, status_code, error="rate_limited", retry_after=retry_after)
        if not isinstance(status_code, int) or not 200 <= status_code < 300:
            return TMDBResponse(False, status_code, error="http_error")
        try:
            data = response.json()
        except (ValueError, requests.JSONDecodeError):
            return TMDBResponse(False, status_code, error="malformed_response")
        if not isinstance(data, expected_type):
            return TMDBResponse(False, status_code, error="malformed_response")
        return TMDBResponse(True, status_code, data=data)

    def movie_genres(self) -> TMDBResponse:
        response = self._request("genre/movie/list")
        if response.ok and not isinstance(response.data.get("genres"), list):
            return TMDBResponse(False, response.status_code, error="malformed_response")
        return response

    def search_movies(self, query: str, *, page: int = 1, language: str = "en-US") -> TMDBResponse:
        if not isinstance(query, str) or not query.strip() or not 1 <= int(page) <= 500:
            return TMDBResponse(False, None, error="invalid_request")
        response = self._request("search/movie", params={"query": query.strip(), "page": page, "language": language})
        if response.ok and (not isinstance(response.data.get("results"), list) or not isinstance(response.data.get("page"), int)):
            return TMDBResponse(False, response.status_code, error="malformed_response")
        return response

    def movie_details(self, movie_id: int | str, *, language: str = "en-US") -> TMDBResponse:
        if not str(movie_id).isdigit() or int(movie_id) < 1:
            return TMDBResponse(False, None, error="invalid_request")
        return self._request(f"movie/{movie_id}", params={"language": language})

    def similar_movies(self, movie_id: int | str, *, page: int = 1, language: str = "en-US") -> TMDBResponse:
        return self._related_movies(movie_id, "similar", page=page, language=language)

    def recommended_movies(self, movie_id: int | str, *, page: int = 1, language: str = "en-US") -> TMDBResponse:
        return self._related_movies(movie_id, "recommendations", page=page, language=language)

    def _related_movies(self, movie_id: int | str, operation: str, *, page: int, language: str) -> TMDBResponse:
        if not str(movie_id).isdigit() or int(movie_id) < 1 or not 1 <= int(page) <= 500:
            return TMDBResponse(False, None, error="invalid_request")
        response = self._request(f"movie/{movie_id}/{operation}", params={"page": page, "language": language})
        if response.ok and (not isinstance(response.data.get("results"), list) or not isinstance(response.data.get("page"), int)):
            return TMDBResponse(False, response.status_code, error="malformed_response")
        return response

    def discover_movies(self, *, genre_id: int, original_language: str | None, region: str, release_date_start: str, release_date_end: str, page: int = 1, limit: int = 20) -> TMDBResponse:
        if not 1 <= int(page) <= 500 or not 1 <= int(limit) <= 20:
            return TMDBResponse(False, None, error="invalid_request")
        params = {
            "include_adult": "false",
            "include_video": "false",
            "language": "en-US",
            "with_genres": str(genre_id),
            "region": region,
            "release_date.gte": release_date_start,
            "release_date.lte": release_date_end,
            "sort_by": "primary_release_date.desc",
            "page": page,
        }
        if original_language:
            params["with_original_language"] = original_language
        response = self._request("discover/movie", params=params)
        if response.ok and (not isinstance(response.data.get("results"), list) or not isinstance(response.data.get("page"), int)):
            return TMDBResponse(False, response.status_code, error="malformed_response")
        return response
