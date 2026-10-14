"""
Natural-language recommendation intent schema and validation.

This module does NOT recommend movies.
It only validates and normalizes structured intent
produced by the natural-language understanding layer.
"""

from __future__ import annotations

from typing import Any
import re


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

# These are language conveniences, not a second taxonomy.  Values are still
# accepted only when they exist in the loaded catalog vocabulary.
GENRE_ALIASES = {
    "science fiction": ("sci-fi",),
    "science-fiction": ("sci-fi",),
    "sci fi": ("sci-fi",),
    "scifi": ("sci-fi",),
    "rom com": ("romance", "comedy"),
    "romcom": ("romance", "comedy"),
    "romantic": ("romance",),
    "kids": ("family", "animation"),
    "children": ("family", "animation"),
    "scary": ("horror",),
    "detective": ("mystery", "crime"),
}

LANGUAGE_ALIASES = {
    "odia": ("oriya",),
    "malayali": ("malayalam",),
    "rajasthani": ("rajastani",),
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
        "exclude_genres": [],
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


def normalize_query_text(value: Any) -> str:
    """Normalize user prose without changing the original request payload."""

    return re.sub(r"\s+", " ", _normalize_string(value)).strip()


def canonicalize_terms(
    values: Any,
    vocabulary: set[str],
    aliases: dict[str, tuple[str, ...]],
) -> list[str]:
    """Resolve a small set of user-facing aliases against catalog vocabulary."""

    result: list[str] = []
    for value in _normalize_list(values):
        candidates = aliases.get(value, (value,))
        for candidate in candidates:
            if candidate in vocabulary and candidate not in result:
                result.append(candidate)
    return result


def find_catalog_terms(
    text: Any,
    vocabulary: set[str],
    aliases: dict[str, tuple[str, ...]],
) -> list[str]:
    """Find catalog terms and safe aliases in free-form user text."""

    normalized = normalize_query_text(text)
    result: list[str] = []

    for phrase, replacements in aliases.items():
        if re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", normalized):
            for replacement in replacements:
                if replacement in vocabulary and replacement not in result:
                    result.append(replacement)

    for term in sorted(vocabulary, key=len, reverse=True):
        pattern = re.escape(term).replace(r"\-", r"[-\s]?")
        if term.endswith("y") and len(term) > 1 and term[-2] not in "aeiou":
            # comedy -> comedies, fantasy -> fantasies, mystery -> mysteries
            singular_or_plural = re.escape(term[:-1]) + r"(?:y|ies)"
        elif term.endswith("s"):
            singular_or_plural = pattern
        else:
            singular_or_plural = pattern + r"(?:s|es)?"
        if re.search(r"(?<!\w)" + singular_or_plural + r"(?!\w)", normalized):
            if term not in result:
                result.append(term)

    return result


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

    requested_genres = canonicalize_terms(raw_intent.get("genres"), valid_genres, GENRE_ALIASES)

    if valid_genres:

        intent["genres"] = [
            genre
            for genre in requested_genres
            if genre in valid_genres
        ]

    excluded_genres = canonicalize_terms(raw_intent.get("exclude_genres"), valid_genres, GENRE_ALIASES)
    if valid_genres:
        intent["exclude_genres"] = [
            genre for genre in excluded_genres if genre not in intent["genres"]
        ]

    # --------------------------------------------------------
    # Languages
    # --------------------------------------------------------

    requested_languages = canonicalize_terms(raw_intent.get("languages"), valid_languages, LANGUAGE_ALIASES)

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
