"""Provider-neutral movie candidate representation for hybrid retrieval.

The existing API presentation objects intentionally remain unchanged.  This
module is used only by the additive hybrid endpoint and keeps absent provider
values as ``None`` (or empty lists where an empty collection is meaningful).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
import math
import re
from typing import Any, Mapping


def normalize_title(value: Any) -> str | None:
    """Return a conservative title key without treating punctuation as identity."""
    if value is None:
        return None
    text = str(value).strip().casefold()
    return re.sub(r"\s+", " ", text) or None


def _text(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    value = str(value).strip()
    return value or None


def _number(value: Any, number_type=float):
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = number_type(value)
    except (TypeError, ValueError):
        return None
    return None if isinstance(parsed, float) and math.isnan(parsed) else parsed


def _year(value: Any) -> int | None:
    parsed = _number(value, int)
    return parsed if parsed is not None and 1800 <= parsed <= 2100 else None


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple, set)) else str(value).split(",")
    return [text for item in values if (text := _text(item))]


def _first_present(*values: Any) -> Any:
    for value in values:
        if _text(value) is not None:
            return value
    return None


def _release_date(value: Any) -> str | None:
    text = _text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


@dataclass
class MovieCandidate:
    title: str
    original_title: str | None = None
    year: int | None = None
    overview: str | None = None
    genres: list[str] = field(default_factory=list)
    language: list[str] = field(default_factory=list)
    poster_url: str | None = None
    imdb_id: str | None = None
    tmdb_id: int | None = None
    watchmode_id: int | None = None
    release_date: str | None = None
    runtime: int | None = None
    rating: float | None = None
    rating_source: str | None = None
    streaming_sources: list[dict[str, Any]] = field(default_factory=list)
    availability_region: str | None = None
    availability_checked_at: str | None = None
    provider: list[str] = field(default_factory=list)
    data_source: list[str] = field(default_factory=list)
    freshness_status: str = "unknown"
    availability_status: str = "not_checked"

    @property
    def normalized_title(self) -> str | None:
        return normalize_title(self.title)

    def public_dict(self) -> dict[str, Any]:
        """Return the additive endpoint representation without ranking internals."""
        payload = asdict(self)
        payload["normalized_title"] = self.normalized_title
        return payload


def local_candidate(row: Mapping[str, Any]) -> MovieCandidate | None:
    """Map an existing cleaned local-dataset row without enrichment calls."""
    title = _text(row.get("title"))
    if not title:
        return None
    return MovieCandidate(
        title=title,
        original_title=_text(row.get("title_original")),
        year=_year(row.get("year")),
        genres=_list(_first_present(row.get("genre_original"), row.get("genre"))),
        language=_list(_first_present(row.get("language_original"), row.get("language"))),
        imdb_id=_text(row.get("id")),
        runtime=_number(row.get("duration_min"), int),
        rating=_number(row.get("rating"), float),
        rating_source="local_dataset" if _number(row.get("rating"), float) is not None else None,
        provider=["local_dataset"],
        data_source=["local_dataset"],
        freshness_status="release_date_missing",
    )


def watchmode_search_candidate(item: Any) -> MovieCandidate | None:
    """Safely map only documented/observed title-search values from Watchmode."""
    if not isinstance(item, Mapping):
        return None
    title = _text(item.get("name") or item.get("title"))
    if not title:
        return None
    return MovieCandidate(
        title=title,
        original_title=_text(item.get("original_title")),
        year=_year(item.get("year")),
        imdb_id=_text(item.get("imdb_id")),
        tmdb_id=_number(item.get("tmdb_id"), int),
        watchmode_id=_number(item.get("id"), int),
        release_date=_release_date(item.get("release_date")),
        provider=["watchmode"],
        data_source=["watchmode_title_search"],
        freshness_status=("release_date_verified" if _release_date(item.get("release_date")) else "release_date_missing"),
    )


def watchmode_sources(items: Any, region: str) -> list[dict[str, Any]]:
    """Map source facts conservatively; unknown source fields stay absent."""
    if not isinstance(items, list):
        return []
    result = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        name = _text(item.get("name"))
        if not name:
            continue
        source = {"name": name}
        for field in ("type", "region", "web_url", "ios_url", "android_url"):
            value = _text(item.get(field))
            if value:
                source[field] = value
        source.setdefault("region", region)
        result.append(source)
    return result


def checked_at() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
