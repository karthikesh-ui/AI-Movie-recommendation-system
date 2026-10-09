"""
Deterministic ranking for natural-language movie recommendations.

This module:
- ranks movies using dataset fields only
- does not call Gemini
- does not call OMDb
- does not modify the existing ML recommendation system
"""
import numpy as np
import pandas as pd
DATASET_MEAN_RATING = 6.22427
MIN_VOTE_CONFIDENCE = 100
def _numeric_series(df, column, default=0.0):
    if column not in df.columns:
        return pd.Series(default, index=df.index, dtype=float)

    return pd.to_numeric(df[column], errors="coerce").fillna(default)

def add_ranking_scores(candidates):
    """Add deterministic ranking scores without changing movie selection."""

    if candidates is None or candidates.empty:
        return candidates.copy()

    result = candidates.copy()

    rating = _numeric_series(result, "rating")
    votes = _numeric_series(result, "votes")

    # Bayesian-style quality score.
    confidence = votes / (votes + MIN_VOTE_CONFIDENCE)

    result["_quality_score"] = (
        confidence * rating
        + (1 - confidence) * DATASET_MEAN_RATING
    )

    # Log scaling prevents extremely popular movies from dominating.
    result["_popularity_score"] = np.log1p(votes)

    # Underrated score:
    # retain quality while giving preference to lower exposure.
    vote_support = np.log1p(votes)

    result["_underrated_score"] = (
        result["_quality_score"]
        * (vote_support / (1 + vote_support))
        / (1 + 0.15 * vote_support)
    )
    # General score balances quality and popularity.
    result["_general_score"] = (
        0.70 * result["_quality_score"]
        + 0.30 * (
            result["_popularity_score"]
            / max(result["_popularity_score"].max(), 1.0)
        )
    )

    return result


def rank_candidates(candidates, ranking="general", limit=10):
    """
    Rank candidates deterministically according to the requested mode.
    """

    if candidates is None or candidates.empty:
        return candidates.copy()

    result = add_ranking_scores(candidates)

    ranking = str(ranking or "general").strip().casefold()

    if ranking == "best":
        sort_columns = ["_quality_score", "votes", "title"]

    elif ranking == "highly_rated":
        sort_columns = ["_quality_score", "rating", "votes", "title"]

    elif ranking == "popular":
        sort_columns = [
            "_popularity_score",
            "_quality_score",
            "rating",
            "title",
        ]

    elif ranking == "underrated":
        sort_columns = [
            "_underrated_score",
            "_quality_score",
            "rating",
            "title",
        ]

    else:
        sort_columns = [
            "_general_score",
            "_quality_score",
            "votes",
            "title",
        ]

    if "_intent_genre_score" in result.columns:
        sort_columns.insert(0, "_intent_genre_score")
        ascending = [False] * (len(sort_columns) - 1) + [True]
    else:
        ascending = [False] * (len(sort_columns) - 1) + [True]

    result = result.sort_values(
        by=sort_columns,
        ascending=ascending,
        kind="mergesort",
        na_position="last",
    )

    # Remove internal scoring columns from the public result.
    score_columns = [
        "_quality_score",
        "_popularity_score",
        "_underrated_score",
        "_general_score",
        "_intent_genre_score",
    ]

    result = result.drop(
        columns=[column for column in score_columns if column in result.columns]
    )

    return result.head(limit).copy()