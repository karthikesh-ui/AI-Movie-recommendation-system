"""
Natural-language recommendation pipeline.

Combines:
1. candidate retrieval
2. deterministic ranking

This module does NOT:
- call Gemini
- call OMDb
- modify the existing ML recommendation system
"""

from nl_recommender import retrieve_candidates
from nl_ranking import rank_candidates


def recommend_from_intent(movies, intent, limit=10):
    """
    Retrieve and deterministically rank movies
    using a validated natural-language intent.
    """

    candidates = retrieve_candidates(
        movies,
        intent,
    )

    if candidates is None or candidates.empty:
        return candidates.copy()

    ranking = intent.get(
        "ranking",
        "general",
    )

    return rank_candidates(
        candidates,
        ranking=ranking,
        limit=limit,
    )