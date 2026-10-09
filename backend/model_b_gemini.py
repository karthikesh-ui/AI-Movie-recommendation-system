"""Free-tier Gemini adapter used only by the Model-B movie-search flow."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable


@dataclass(frozen=True)
class GeminiMovieResponse:
    ok: bool
    data: dict[str, Any] | None = None
    error: str | None = None


def _text(value: Any) -> str | None:
    value = str(value).strip() if value is not None else ""
    return value or None


def _year(value: Any) -> int | None:
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if 1888 <= value <= date.today().year + 2 else None


def _strings(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return [text for item in values if (text := _text(item))]


class ModelBGeminiClient:
    """Ask Gemini for structured suggestions; OMDb verifies them downstream."""

    def __init__(self, api_key: str | None = None, *, client_factory: Callable[[], Any] | None = None) -> None:
        self.api_key = (api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")).strip()
        self.client_factory = client_factory

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _client(self):
        if self.client_factory:
            return self.client_factory()
        from google import genai
        from google.genai import types
        return genai.Client(api_key=self.api_key, http_options=types.HttpOptions(timeout=10_000))

    def identify_and_discover(self, title: str, *, year: int | None = None, language: str | None = None) -> GeminiMovieResponse:
        title = _text(title)
        if not title:
            return GeminiMovieResponse(False, error="invalid_request")
        if not self.configured:
            return GeminiMovieResponse(False, error="missing_configuration")

        from google.genai import types
        prompt = f'''Identify this film and, only if you are confident it is a real movie, return similar real movies.
Return JSON only, with this exact shape:
{{"selected_movie":{{"title":"", "year":null, "language":"", "country":"", "type":"movie", "genres":[], "overview":"", "confidence":0}}, "candidates":[{{"title":"", "year":null, "language":"", "genres":[], "overview":"", "reason":"", "confidence":0}}]}}
Do not invent ratings, IDs, poster URLs, OTT providers, release dates, or candidates. Return an empty candidates list if uncertain. The backend will verify every result with OMDb.
Requested title: {title}
Requested year: {year or "unknown"}
Requested language: {language or "unknown"}'''
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0,
        )
        try:
            response = self._client().models.generate_content(
                model=os.getenv("GEMINI_MODEL", "").strip() or "gemini-3.8-flash",
                contents=prompt,
                config=config,
            )
        except Exception as error:
            status = getattr(error, "code", None) or getattr(error, "status_code", None)
            if status == 429:
                failure = "rate_limited"
            elif status in {401, 403}:
                failure = "unauthorized"
            elif "timeout" in type(error).__name__.casefold():
                failure = "timeout"
            else:
                failure = "provider_unavailable"
            return GeminiMovieResponse(False, error=failure)
        try:
            payload = json.loads(getattr(response, "text", ""))
        except (TypeError, ValueError):
            return GeminiMovieResponse(False, error="malformed_response")
        return self._validated(payload)

    def _validated(self, payload: Any) -> GeminiMovieResponse:
        if not isinstance(payload, dict) or not isinstance(payload.get("selected_movie"), dict):
            return GeminiMovieResponse(False, error="malformed_response")
        selected = payload["selected_movie"]
        title = _text(selected.get("title"))
        confidence = selected.get("confidence")
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0
        if not title or selected.get("type") not in (None, "movie") or confidence < 0.6:
            return GeminiMovieResponse(False, error="ambiguous")
        selected_data = {
            "title": title, "year": _year(selected.get("year")),
            "language": _text(selected.get("language")), "country": _text(selected.get("country")),
            "genres": _strings(selected.get("genres")), "overview": _text(selected.get("overview")),
            "confidence": confidence,
        }
        valid_candidates = []
        for candidate in payload.get("candidates", []):
            if not isinstance(candidate, dict):
                continue
            candidate_title, candidate_year = _text(candidate.get("title")), _year(candidate.get("year"))
            try:
                candidate_confidence = float(candidate.get("confidence"))
            except (TypeError, ValueError):
                candidate_confidence = 0
            if not candidate_title or candidate_year is None or candidate_confidence < 0.6:
                continue
            valid_candidates.append({
                "title": candidate_title, "year": candidate_year,
                "language": _text(candidate.get("language")),
                "genres": _strings(candidate.get("genres")), "overview": _text(candidate.get("overview")),
                "reason": _text(candidate.get("reason")), "confidence": candidate_confidence,
            })
        return GeminiMovieResponse(True, {"selected_movie": selected_data, "candidates": valid_candidates})
