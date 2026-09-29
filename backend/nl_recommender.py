"""
Natural-language movie recommendation retrieval.

This module retrieves candidate movies from the existing
Indian movie dataset.

It does NOT:
- call Gemini
- rank movies
- call OMDb
- modify the existing ML recommendation system
"""


import pandas as pd


def _contains_any(value, requested_values):
    """
    Check whether a comma-separated dataset field contains
    at least one requested normalized value.
    """

    if pd.isna(value):
        return False

    available = {
        item.strip().casefold()
        for item in str(value).split(",")
        if item.strip()
    }

    return bool(
        available.intersection(
            requested_values
        )
    )


def retrieve_candidates(
    movies,
    intent,
):
    """
    Retrieve candidate movies from the existing dataset
    using explicit structured intent filters.

    This function performs candidate retrieval only.
    Ranking will be implemented separately.
    """

    if movies is None or movies.empty:
        return movies

    if not isinstance(intent, dict):
        return movies.iloc[0:0].copy()

    candidates = movies.copy()

    # --------------------------------------------------------
    # Genre filter
    # --------------------------------------------------------

    genres = {
        str(value).strip().casefold()
        for value in intent.get("genres", [])
        if str(value).strip()
    }

    if genres and "genre" in candidates.columns:

        candidates = candidates[
            candidates["genre"].apply(
                lambda value: _contains_any(
                    value,
                    genres
                )
            )
        ]

    # --------------------------------------------------------
    # Language filter
    # --------------------------------------------------------

    languages = {
        str(value).strip().casefold()
        for value in intent.get("languages", [])
        if str(value).strip()
    }

    if languages and "language" in candidates.columns:

        candidates = candidates[
            candidates["language"].apply(
                lambda value: _contains_any(
                    value,
                    languages
                )
            )
        ]

    # --------------------------------------------------------
    # Year range
    # --------------------------------------------------------

    if "year" in candidates.columns:

        year_values = pd.to_numeric(
            candidates["year"],
            errors="coerce"
        )

        year_from = intent.get("year_from")

        year_to = intent.get("year_to")

        if year_from is not None:

            candidates = candidates[
                year_values >= int(year_from)
            ]

            year_values = pd.to_numeric(
                candidates["year"],
                errors="coerce"
            )

        if year_to is not None:

            candidates = candidates[
                year_values <= int(year_to)
            ]
        # --------------------------------------------------------
    # Duration preference
    # --------------------------------------------------------

    duration_preference = intent.get(
        "duration_preference"
    )

    if (
        duration_preference
        and "duration_min" in candidates.columns
    ):

        duration_values = pd.to_numeric(
            candidates["duration_min"],
            errors="coerce"
        )

        if duration_preference == "short":

            candidates = candidates[
                duration_values < 112
            ]

        elif duration_preference == "medium":

            candidates = candidates[
                (duration_values >= 112)
                & (duration_values <= 145)
            ]

        elif duration_preference == "long":

            candidates = candidates[
                duration_values > 145
            ]
    # --------------------------------------------------------
    # Limit candidate count
    # --------------------------------------------------------

    return candidates.copy()