"""
Natural-language recommendation intent schema and validation.

This module does NOT recommend movies.
It only validates and normalizes structured intent
produced by the natural-language understanding layer.
"""

from __future__ import annotations

from typing import Any


# ============================================================
# Controlled Intent Values
# ============================================================

ALLOWED_DURATION_PREFERENCES = {
    "short",
    "medium",
    "long",
}

ALLOWED_MOODS = {
    "feel_good",
    "emotional",
    "intense",
    "light",
    "romantic",
}

ALLOWED_AUDIENCES = {
    "solo",
    "partner",
    "friends",
    "family",
}

ALLOWED_RANKINGS = {
    "general",
    "best",
    "highly_rated",
    "popular",
    "underrated",
}


# ============================================================
# Empty Intent
# ============================================================

def empty_intent() -> dict[str, Any]:
    """
    Return the canonical empty natural-language intent.
    """

    return {
        "genres": [],
        "languages": [],
        "year_from": None,
        "year_to": None,
        "duration_preference": None,
        "mood": None,
        "audience": None,
        "ranking": "general",
    }


# ============================================================
# Normalization Helpers
# ============================================================

def _normalize_string(value: Any) -> str:
    """
    Normalize a string for comparison.
    """

    return str(value).strip().casefold()


def _normalize_list(value: Any) -> list[str]:
    """
    Convert a value into a clean list of normalized strings.
    """

    if value is None:
        return []

    if isinstance(value, str):
        value = [value]

    if not isinstance(value, list):
        return []

    result = []

    for item in value:

        if not isinstance(item, str):
            continue

        normalized = _normalize_string(item)

        if normalized and normalized not in result:
            result.append(normalized)

    return result


def _normalize_year(value: Any) -> int | None:
    """
    Convert a valid year value into an integer.
    """

    if value is None or value == "":
        return None

    try:

        year = int(value)

    except (TypeError, ValueError):

        return None

    if year < 1800 or year > 2100:
        return None

    return year


# ============================================================
# Dataset Vocabulary
# ============================================================

def build_dataset_vocabulary(movies) -> dict[str, set[str]]:
    """
    Build normalized genre and language vocabularies
    from the actual Indian movie dataset.

    The dataset remains the source of truth.
    """

    genres: set[str] = set()
    languages: set[str] = set()

    if movies is None:
        return {
            "genres": genres,
            "languages": languages,
        }

    if "genre" in movies.columns:

        for value in movies["genre"].dropna():

            for item in str(value).split(","):

                normalized = _normalize_string(item)

                if normalized:
                    genres.add(normalized)

    if "language" in movies.columns:

        for value in movies["language"].dropna():

            for item in str(value).split(","):

                normalized = _normalize_string(item)

                if normalized:
                    languages.add(normalized)

    return {
        "genres": genres,
        "languages": languages,
    }


# ============================================================
# Intent Validation
# ============================================================

def validate_intent(
    raw_intent: Any,
    dataset_vocabulary: dict[str, set[str]] | None = None,
) -> dict[str, Any]:
    """
    Validate and normalize a structured natural-language intent.

    Unknown fields are ignored.

    Unsupported dataset genres/languages are removed.

    Invalid controlled values are converted to None/defaults.

    The function always returns the canonical intent structure.
    """

    intent = empty_intent()

    if not isinstance(raw_intent, dict):
        return intent

    vocabulary = dataset_vocabulary or {
        "genres": set(),
        "languages": set(),
    }

    valid_genres = vocabulary.get(
        "genres",
        set(),
    )

    valid_languages = vocabulary.get(
        "languages",
        set(),
    )

    # --------------------------------------------------------
    # Genres
    # --------------------------------------------------------

    requested_genres = _normalize_list(
        raw_intent.get("genres")
    )

    if valid_genres:

        intent["genres"] = [
            genre
            for genre in requested_genres
            if genre in valid_genres
        ]

    # --------------------------------------------------------
    # Languages
    # --------------------------------------------------------

    requested_languages = _normalize_list(
        raw_intent.get("languages")
    )

    if valid_languages:

        intent["languages"] = [
            language
            for language in requested_languages
            if language in valid_languages
        ]

    # --------------------------------------------------------
    # Years
    # --------------------------------------------------------

    year_from = _normalize_year(
        raw_intent.get("year_from")
    )

    year_to = _normalize_year(
        raw_intent.get("year_to")
    )

    # Correct an inverted range safely.
    if (
        year_from is not None
        and year_to is not None
        and year_from > year_to
    ):
        year_from, year_to = year_to, year_from

    intent["year_from"] = year_from
    intent["year_to"] = year_to

    # --------------------------------------------------------
    # Duration
    # --------------------------------------------------------

    duration = raw_intent.get(
        "duration_preference"
    )

    if isinstance(duration, str):

        duration = _normalize_string(duration)

        if duration in ALLOWED_DURATION_PREFERENCES:
            intent["duration_preference"] = duration

    # --------------------------------------------------------
    # Mood
    # --------------------------------------------------------

    mood = raw_intent.get("mood")

    if isinstance(mood, str):

        mood = _normalize_string(mood)

        if mood in ALLOWED_MOODS:
            intent["mood"] = mood

    # --------------------------------------------------------
    # Audience
    # --------------------------------------------------------

    audience = raw_intent.get("audience")

    if isinstance(audience, str):

        audience = _normalize_string(audience)

        if audience in ALLOWED_AUDIENCES:
            intent["audience"] = audience

    # --------------------------------------------------------
    # Ranking
    # --------------------------------------------------------

    ranking = raw_intent.get(
        "ranking",
        "general",
    )

    if isinstance(ranking, str):

        ranking = _normalize_string(ranking)

        if ranking in ALLOWED_RANKINGS:
            intent["ranking"] = ranking

    return intent