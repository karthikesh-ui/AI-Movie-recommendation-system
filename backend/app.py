import os
import sys
import pickle
import re
import time
import copy
import math
from functools import lru_cache

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import pandas as pd
import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from nl_intent import (
    build_dataset_vocabulary,
    validate_intent,
)
from nl_pipeline import recommend_from_intent
from watchmode_client import WatchmodeClient, WatchmodeResponse
from hybrid_retrieval import retrieve_hybrid, normalize_recommendation_source
from discovery_provider import WatchmodeDiscoveryProvider, TMDBDiscoveryProvider, WatchmodeOTTEnricher
from tmdb_client import TMDBClient
from model_b_gemini import ModelBGeminiClient
from movie_candidate import MovieCandidate
# ============================================================
# Environment Configuration
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

FRONTEND_DIR = os.path.join(
    BASE_DIR,
    "..",
    "frontend"
)

ENV_FILE = os.path.join(
    BASE_DIR,
    ".env"
)

load_dotenv(ENV_FILE)


# ============================================================
# Flask Application
# ============================================================

app = Flask(
    __name__,
    static_folder=FRONTEND_DIR,
    static_url_path=""
)


def _configured_frontend_origins():
    configured_origins = os.getenv(
        "FRONTEND_ORIGIN",
        "http://localhost:5500",
    )
    origins = [
        origin.strip()
        for origin in configured_origins.split(",")
        if origin.strip() and origin.strip() != "*"
    ]
    return origins or ["http://localhost:5500"]


# ============================================================
# CORS Configuration
# ============================================================

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": _configured_frontend_origins()
        }
    }
)


# ============================================================
# API Keys
# ============================================================

OMDB_API_KEY = os.getenv(
    "OMDB_API_KEY",
    ""
)

GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY",
    "")

PROVIDER_BACKOFF_SECONDS = 30
GEMINI_RETRY_AFTER = 0.0
OMDB_RETRY_AFTER = 0.0
WATCHMODE_CLIENT = WatchmodeClient()
WATCHMODE_DISCOVERY_ENABLED = os.getenv("WATCHMODE_DISCOVERY_ENABLED", "false").strip().casefold() in {"1", "true", "yes", "on"}
try:
    WATCHMODE_DISCOVERY_WINDOW_DAYS = max(1, int(os.getenv("WATCHMODE_DISCOVERY_WINDOW_DAYS", "90")))
except ValueError:
    WATCHMODE_DISCOVERY_WINDOW_DAYS = 90
WATCHMODE_DISCOVERY = WatchmodeDiscoveryProvider(
    WATCHMODE_CLIENT,
    enabled=WATCHMODE_DISCOVERY_ENABLED,
    window_days=WATCHMODE_DISCOVERY_WINDOW_DAYS,
)
TMDB_CLIENT = TMDBClient()
RECOMMENDATION_SOURCE = normalize_recommendation_source(
    os.getenv("RECOMMENDATION_SOURCE", "tmdb")
)
TMDB_DISCOVERY = TMDBDiscoveryProvider(
    TMDB_CLIENT,
    window_days=WATCHMODE_DISCOVERY_WINDOW_DAYS,
)
WATCHMODE_OTT_ENRICHER = WatchmodeOTTEnricher(WATCHMODE_CLIENT)
MODEL_B_GEMINI = ModelBGeminiClient(GEMINI_API_KEY)

INDIAN_LANGUAGE_HINTS = {
    "hindi", "tamil", "telugu", "malayalam", "kannada",
    "bengali", "marathi", "gujarati", "punjabi", "oriya",
    "assamese", "nepali", "bhojpuri", "kashmiri",
    "kannada", "konkani", "rajasthani", "sanskrit"
}
# ============================================================
# Gemini Natural-Language Intent Parser
# ============================================================

def _rule_based_intent_parse(user_text, dataset_vocabulary):
    text_lower = user_text.lower()
    valid_genres = dataset_vocabulary.get("genres", set()) if dataset_vocabulary else set()
    valid_languages = dataset_vocabulary.get("languages", set()) if dataset_vocabulary else set()

    non_genre_terms = {"short", "medium", "long"}
    matched_genres = [
        genre
        for genre in valid_genres
        if genre not in non_genre_terms and genre in text_lower
    ]
    matched_languages = [l for l in valid_languages if l in text_lower]

    # “Indian” is a region cue, not one original-language filter.  Keeping it
    # unfiltered lets TMDB use its India region query without claiming a title
    # has every language in the local catalog.

    if re.search(r"\bscience[\s-]+fiction\b|\bsci[\s-]*fi\b|\bscifi\b", text_lower):
        for genre in ["adventure", "fantasy", "action"]:
            if genre in valid_genres and genre not in matched_genres:
                matched_genres.append(genre)

    mood = None
    if any(k in text_lower for k in ["feel-good", "feel good", "happy", "fun", "joy"]):
        mood = "feel_good"
    elif any(k in text_lower for k in ["romantic", "romance", "love", "date"]):
        mood = "romantic"
    elif any(k in text_lower for k in ["emotional", "touching", "heartfelt", "sad"]):
        mood = "emotional"
    elif any(k in text_lower for k in ["intense", "thrilling", "action", "suspense", "mystery"]):
        mood = "intense"
    elif any(k in text_lower for k in ["light", "casual", "easygoing", "funny"]):
        mood = "light"

    audience = None
    if any(k in text_lower for k in ["alone", "solo", "watch alone", "by myself"]):
        audience = "solo"
    elif any(k in text_lower for k in ["with family", "family-friendly", "family friendly", "for family"]):
        audience = "family"
    elif any(k in text_lower for k in ["with friends", "friends", "group", "hangout"]):
        audience = "friends"
    elif any(k in text_lower for k in ["with partner", "date night", "couple", "romantic night"]):
        audience = "partner"
    elif "family" in text_lower:
        audience = "family"
    elif "friend" in text_lower:
        audience = "friends"
    elif any(k in text_lower for k in ["partner", "couple"]):
        audience = "partner"

    ranking = "general"
    if any(k in text_lower for k in ["best", "top", "highest rated", "greatest"]):
        ranking = "best"
    elif any(k in text_lower for k in ["popular", "blockbuster", "hit"]):
        ranking = "popular"
    elif "underrated" in text_lower:
        ranking = "underrated"

    duration_preference = None
    if any(term in text_lower for term in ["short movie", "short film", "under 2 hours", "less than 2 hours"]):
        duration_preference = "short"
    elif re.search(r"\bshort\b", text_lower) and (matched_genres or matched_languages):
        duration_preference = "short"
    elif any(term in text_lower for term in ["long movie", "long film", "over 2 hours", "more than 2 hours"]):
        duration_preference = "long"
    elif any(term in text_lower for term in ["medium-length", "average length"]):
        duration_preference = "medium"

    year_from = None
    year_to = None
    year_range = re.search(
        r"\b(?:between|from)\s+(18\d{2}|19\d{2}|20\d{2}|2100)\s+(?:and|to|through|until)\s+(18\d{2}|19\d{2}|20\d{2}|2100)\b",
        text_lower,
    )
    if year_range:
        year_from, year_to = map(int, year_range.groups())
    else:
        start_year = re.search(
            r"\b(after|since)\s+(18\d{2}|19\d{2}|20\d{2}|2100)\b",
            text_lower,
        )
        end_year = re.search(
            r"\b(?:before|until)\s+(18\d{2}|19\d{2}|20\d{2}|2100)\b",
            text_lower,
        )
        if start_year:
            year_from = int(start_year.group(2))
            if start_year.group(1) == "after":
                year_from += 1
        if end_year:
            year_to = int(end_year.group(1))

    raw_intent = {
        "genres": matched_genres,
        "languages": matched_languages,
        "year_from": year_from,
        "year_to": year_to,
        "duration_preference": duration_preference,
        "mood": mood,
        "audience": audience,
        "ranking": ranking
    }

    validated_intent = validate_intent(raw_intent, dataset_vocabulary)
    unsupported_terms = {"genres": [], "languages": []}
    return validated_intent, unsupported_terms


def _generate_with_gemini(client, prompt):
    global GEMINI_RETRY_AFTER

    if time.monotonic() < GEMINI_RETRY_AFTER:
        return None

    candidates = [
        os.getenv("GEMINI_MODEL", ""),
        "gemini-2.5-flash",
        "gemini-1.5-flash",
        "gemini-2.0-flash",
        "gemini-3.8-flash"
    ]
    models_to_try = []
    for m in candidates:
        if m and m not in models_to_try:
            models_to_try.append(m)

    for model_name in models_to_try:
        try:
            res = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            if res and res.text:
                return res.text.strip()
        except Exception as error:
            if "timeout" in type(error).__name__.casefold():
                GEMINI_RETRY_AFTER = time.monotonic() + PROVIDER_BACKOFF_SECONDS
                break
            continue
    return None


def _create_gemini_client():
    from google import genai
    from google.genai import types

    return genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=types.HttpOptions(timeout=10_000),
    )


def parse_recommendation_intent(user_text, dataset_vocabulary):
    """
    Convert a natural-language movie request into
    validated structured intent.

    Uses Gemini API if available with fallback to rule-based parsing.
    """
    if not isinstance(user_text, str):
        return None, None

    user_text = user_text.strip()
    if not user_text:
        return None, None

    if GEMINI_API_KEY:
        try:
            client = _create_gemini_client()

            prompt = f"""
You convert a user's movie request into structured intent.

Return ONLY valid JSON.
Do not use Markdown.
Do not recommend or select any movie.
Do not invent movie titles.
Do not rank movies.

Use exactly these fields:

{{
  "genres": [],
  "languages": [],
  "year_from": null,
  "year_to": null,
  "duration_preference": null,
  "mood": null,
  "audience": null,
  "ranking": "general"
}}

Allowed duration_preference values:
short, medium, long, null

Allowed mood values:
feel_good, emotional, intense, light, romantic, null

Allowed audience values:
solo, partner, friends, family, null

Allowed ranking values:
general, best, highly_rated, popular, underrated

Genres and languages must be expressed using the user's meaning.
The backend will validate them against the actual dataset.

If the user does not specify something, use:
- empty array for genres/languages
- null for year_from/year_to
- null for duration_preference
- null for mood
- null for audience
- "general" for ranking

User request:
{user_text}
"""
            text = _generate_with_gemini(client, prompt)

            if text:
                if text.startswith("```"):
                    lines = text.splitlines()
                    if lines and lines[0].strip().startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    text = "\n".join(lines).strip()

                import json
                raw_intent = json.loads(text)
                valid_genres = dataset_vocabulary.get("genres", set()) if dataset_vocabulary else set()
                valid_languages = dataset_vocabulary.get("languages", set()) if dataset_vocabulary else set()

                requested_genres = raw_intent.get("genres", [])
                requested_languages = raw_intent.get("languages", [])

                if isinstance(requested_genres, str):
                    requested_genres = [requested_genres]
                if isinstance(requested_languages, str):
                    requested_languages = [requested_languages]

                requested_genres = [
                    str(value).strip().casefold()
                    for value in requested_genres
                    if str(value).strip()
                ]

                if any(
                    phrase in user_text.casefold()
                    for phrase in ("short movie", "short film")
                ):
                    requested_genres = [
                        genre for genre in requested_genres
                        if genre != "short"
                    ]
                    raw_intent["genres"] = requested_genres

                requested_languages = [
                    str(value).strip().casefold()
                    for value in requested_languages
                    if str(value).strip()
                ]

                unsupported_terms = {
                    "genres": [
                        genre
                        for genre in requested_genres
                        if genre not in valid_genres
                    ],
                    "languages": [
                        language
                        for language in requested_languages
                        if language not in valid_languages
                    ]
                }

                validated_intent = validate_intent(
                    raw_intent,
                    dataset_vocabulary
                )

                fallback_intent, _ = _rule_based_intent_parse(
                    user_text,
                    dataset_vocabulary
                )
                for field in (
                    "year_from",
                    "year_to",
                    "mood",
                    "audience",
                    "duration_preference",
                ):
                    if fallback_intent[field] is not None:
                        validated_intent[field] = fallback_intent[field]

                return validated_intent, unsupported_terms

        except Exception:
            print(
                "Gemini intent request failed. Falling back to rule-based parser."
            )

    return _rule_based_intent_parse(user_text, dataset_vocabulary)

# ============================================================
# Load Indian Movie Recommendation Model
# ============================================================

MODEL_DIR = os.path.join(
    BASE_DIR,
    "models"
)

MOVIES_MODEL_FILE = os.path.join(
    MODEL_DIR,
    "movies.pkl"
)

VECTORIZER_MODEL_FILE = os.path.join(
    MODEL_DIR,
    "vectorizer.pkl"
)

TFIDF_MATRIX_MODEL_FILE = os.path.join(
    MODEL_DIR,
    "tfidf_matrix.pkl"
)

NEIGHBORS_MODEL_FILE = os.path.join(
    MODEL_DIR,
    "neighbors.pkl"
)


try:

    print("=" * 65)
    print("LOADING INDIAN MOVIE RECOMMENDATION MODEL")
    print("=" * 65)

    with open(
        MOVIES_MODEL_FILE,
        "rb"
    ) as f:

        movies = pickle.load(f)

    with open(
        VECTORIZER_MODEL_FILE,
        "rb"
    ) as f:

        vectorizer = pickle.load(f)

    with open(
        TFIDF_MATRIX_MODEL_FILE,
        "rb"
    ) as f:

        tfidf_matrix = pickle.load(f)

    with open(
        NEIGHBORS_MODEL_FILE,
        "rb"
    ) as f:

        neighbors = pickle.load(f)

    MODEL_LOADED = True

    print(
        f"Movies loaded: {len(movies):,}"
    )

    print(
        f"TF-IDF matrix: {tfidf_matrix.shape}"
    )

    print(
        f"TF-IDF features: {tfidf_matrix.shape[1]:,}"
    )

    print(
        f"Nearest neighbors: {neighbors.n_neighbors}"
    )

    print("Recommendation model loaded successfully.")

    DATASET_VOCABULARY = build_dataset_vocabulary(movies)
    MODEL_B_TITLE_KEYS = (
        movies["title"].astype(str).str.casefold()
        .str.replace(r"[^\w]+", " ", regex=True).str.strip()
    )

    print(
        f"Dataset vocabulary: "
        f"{len(DATASET_VOCABULARY['genres'])} genres, "
        f"{len(DATASET_VOCABULARY['languages'])} languages"
    )
except Exception as error:

    print(
        f"Recommendation model loading error: {error}"
    )

    movies = None
    vectorizer = None
    tfidf_matrix = None
    neighbors = None
    DATASET_VOCABULARY = {
        "genres": set(),
        "languages": set(),
    }
    MODEL_B_TITLE_KEYS = pd.Series(dtype="object")
    MODEL_LOADED = False


# ============================================================
# OMDb Helper
# ============================================================

def _poster(value):
    """
    Return a valid poster URL.

    OMDb returns 'N/A' when no poster exists.
    """

    if value and value != "N/A":
        return value

    return ""


@lru_cache(maxsize=256)
def _omdb(title=None, plot="full", imdb_id=None):
    """
    Get movie information from OMDb.

    Results are cached to reduce unnecessary API calls.
    """

    global OMDB_RETRY_AFTER

    if not OMDB_API_KEY or time.monotonic() < OMDB_RETRY_AFTER:
        return None

    try:

        response = requests.get(
            "https://www.omdbapi.com/",
            params={
                **({"i": imdb_id} if imdb_id else {"t": title} if title else {}),
                "plot": plot,
                "apikey": OMDB_API_KEY
            },
            timeout=8
        )

        response.raise_for_status()

        data = response.json()

        if not isinstance(data, dict):
            return None

        if data.get("Response") == "False":
            return None

        return data

    except requests.RequestException:
        OMDB_RETRY_AFTER = time.monotonic() + PROVIDER_BACKOFF_SECONDS

        print(
            "OMDb request failed. Using dataset metadata when available."
        )

        return None


# ============================================================
# Movie Details
# ============================================================

@lru_cache(maxsize=256)
def movie_details(title, imdb_id=None):
    """
    Get movie details using OMDb.

    OMDb is used for enrichment.
    The Indian dataset remains the source for
    movie discovery and recommendation.
    """

    data = _omdb(title, imdb_id=imdb_id)

    if not data:
        return None

    return {
        "title": data.get(
            "Title",
            title
        ),

        "year": data.get(
            "Year",
            "N/A"
        ),

        "rating": data.get(
            "imdbRating",
            "N/A"
        ),

        "genre": data.get(
            "Genre",
            "N/A"
        ),

        "runtime": data.get(
            "Runtime",
            "N/A"
        ),

        "director": data.get(
            "Director",
            "N/A"
        ),

        "writer": data.get(
            "Writer",
            "N/A"
        ),

        "cast": data.get(
            "Actors",
            "N/A"
        ),

        "plot": data.get(
            "Plot",
            "No plot available."
        ),

        "poster": _poster(
            data.get("Poster")
        ),

        "language": data.get(
            "Language",
            "N/A"
        ),

        "country": data.get("Country", "N/A"),
        "released": data.get("Released", "N/A"),
        "awards": data.get("Awards", "N/A"),
        "metascore": data.get("Metascore", "N/A"),

        "source": "OMDb",

        "imdb_id": data.get(
            "imdbID"
        ),
        "imdb_votes": data.get("imdbVotes", "N/A"),
        "imdb_rating": data.get("imdbRating", "N/A")
    }


# ============================================================
# Dataset Movie Details
# ============================================================
def dataset_movie_details(index):
    """
    Build movie details directly from the Indian dataset.

    Used when OMDb cannot provide information.
    """

    row = movies.iloc[index]

    year = (
        int(row["year"])
        if pd.notna(row["year"])
        else "N/A"
    )

    rating = (
        float(row["rating"])
        if pd.notna(row["rating"])
        else "N/A"
    )

    runtime = "N/A"

    if pd.notna(row["duration_min"]):
        runtime = f"{int(row['duration_min'])} min"

    # Genre
    genre = row.get("genre_original", "")

    if pd.isna(genre) or not str(genre).strip():
        genre = "N/A"
    else:
        genre = str(genre).strip()

    # Language
    language = row.get("language_original", "")

    if pd.isna(language) or not str(language).strip():
        language = "N/A"
    else:
        language = str(language).strip()

    # IMDb ID
    imdb_id = row.get("id", "")

    if pd.isna(imdb_id) or not str(imdb_id).strip():
        imdb_id = None
    else:
        imdb_id = str(imdb_id).strip()

    return {
        "title": str(row["title"]),
        "year": year,
        "rating": rating,
        "genre": genre,
        "runtime": runtime,
        "director": "N/A",
        "writer": "N/A",
        "cast": "N/A",
        "plot": "Details unavailable.",
        "poster": "",
        "language": language,
        "source": "ML Dataset",
        "imdb_id": imdb_id,
        "imdb_votes": int(row["votes"]) if pd.notna(row.get("votes")) and str(row.get("votes")).replace(".", "").isdigit() else (row.get("votes") if pd.notna(row.get("votes")) else "N/A"),
        "imdb_rating": rating
    }

# ============================================================
# Combined Movie Details
# ============================================================
def get_movie_details(title, dataset_index=None):
    """
    Combine OMDb enrichment with Indian dataset data.

    The Indian dataset is the source of truth for movie
    discovery. OMDb enriches the available information.
    If OMDb has missing fields, dataset values are preserved.
    """

    dataset_details = None

    if dataset_index is not None:
        dataset_details = dataset_movie_details(dataset_index)

    omdb_details = movie_details(title)

    # If OMDb has no result, use the Indian dataset completely.
    if not omdb_details:
        if dataset_details:
            dataset_details["source"] = "Indian Dataset"
            return dataset_details

        return None

    # If dataset information is unavailable, return OMDb.
    if not dataset_details:
        return omdb_details

    # Merge both sources.
    merged = dataset_details.copy()

    for key, value in omdb_details.items():
        if value not in (None, "", "N/A", "No plot available."):
            merged[key] = value

    # OMDb provided useful enrichment, so indicate both sources.
    merged["source"] = "Indian Dataset + OMDb"

    return merged


# ============================================================
# Model-B Local Catalog, Free Gemini, and OMDb Adapters
# ============================================================

def _model_b_title_key(value):
    """Conservative local identity: case/space/punctuation-insensitive only."""
    return re.sub(r"[^\w]+", " ", str(value or "").casefold()).strip()


def _model_b_local_index(title, year=None, language=None):
    if movies is None or not _model_b_title_key(title):
        return None
    key = _model_b_title_key(title)
    matches = movies[MODEL_B_TITLE_KEYS == key].copy()
    if matches.empty:
        return None
    if year is not None:
        by_year = matches[pd.to_numeric(matches["year"], errors="coerce") == int(year)]
        if by_year.empty:
            return None
        matches = by_year.copy()
    if language:
        by_language = matches[matches["language_original"].astype(str).str.casefold().str.contains(re.escape(str(language).casefold()), na=False)]
        if not by_language.empty:
            matches = by_language.copy()
    matches["_rating"] = pd.to_numeric(matches["rating"], errors="coerce").fillna(-1)
    matches["_votes"] = pd.to_numeric(matches.get("votes", 0), errors="coerce").fillna(-1)
    return matches.sort_values(["_rating", "_votes"], ascending=False).index[0]


def _model_b_local_results(query, limit=10):
    if movies is None:
        return []
    key = _model_b_title_key(query)
    if not key:
        return []
    title_keys = MODEL_B_TITLE_KEYS
    matches = movies[title_keys.str.startswith(key, na=False)].copy()
    if matches.empty:
        matches = movies[title_keys.str.contains(re.escape(key), na=False)].copy()
    matches["_exact"] = title_keys.loc[matches.index] == key
    matches["_rating"] = pd.to_numeric(matches["rating"], errors="coerce").fillna(-1)
    matches["_votes"] = pd.to_numeric(matches.get("votes", 0), errors="coerce").fillna(-1)
    matches = matches.sort_values(["_exact", "_rating", "_votes", "title"], ascending=[False, False, False, True])
    results, seen = [], set()
    for index, row in matches.iterrows():
        identity = (_model_b_title_key(row["title"]), str(row.get("year") or ""))
        if identity in seen:
            continue
        seen.add(identity)
        results.append(_model_b_local_payload(index))
        if len(results) == limit:
            break
    return results


def _model_b_local_payload(index):
    details = dataset_movie_details(index)
    details.update({
        "genres": [genre.strip() for genre in str(details.get("genre") or "").split(",") if genre.strip()],
        "overview": details.get("plot") or "",
        "poster_url": details.get("poster") or "",
        "source": "local",
        "local_match": True,
        "availability_status": "unknown",
    })
    return details


def _model_b_language_values(value):
    """Normalize the small language vocabulary used by Model-B's local catalog."""
    aliases = {"te": "telugu", "ta": "tamil", "hi": "hindi", "ml": "malayalam",
               "kn": "kannada", "bn": "bengali", "mr": "marathi", "pa": "punjabi"}
    return {aliases.get(item.strip().casefold(), item.strip().casefold())
            for item in str(value or "").split(",") if item.strip()}


def _model_b_name_values(value):
    return {_model_b_title_key(item) for item in str(value or "").split(",")
            if _model_b_title_key(item) and _model_b_title_key(item) != "n a"}


def _model_b_local_recommendations(title, year=None, genres=None, imdb_id=None, limit=6, language=None,
                                   director=None, cast=None):
    """Return local-only recommendations without provider enrichment."""
    if movies is None:
        return [], "unavailable"
    seed_language = str(language or "").split(",")[0].strip() or None
    selected_index = _model_b_local_index(title, year, seed_language)
    if selected_index is None:
        title_matches = movies[MODEL_B_TITLE_KEYS == _model_b_title_key(title)]
        if not title_matches.empty and title_matches["year"].nunique(dropna=True) <= 1:
            selected_index = _model_b_local_index(title, language=seed_language)
    selected_key = (_model_b_title_key(title), str(movies.loc[selected_index, "year"] or "")) if selected_index is not None else (_model_b_title_key(title), str(year or ""))
    selected_title = selected_key[0]
    selected_imdb = str(imdb_id or "")
    wanted = {str(item).strip().casefold() for item in (genres or []) if str(item).strip()}
    selected_languages = _model_b_language_values(language)
    selected_directors = _model_b_name_values(director)
    selected_cast = _model_b_name_values(cast)

    def candidate_genres(row):
        raw = row.get("genre_original")
        if pd.isna(raw) or not str(raw).strip(): raw = row.get("genre")
        return {part.strip().casefold() for part in str(raw or "").split(",") if part.strip()}

    def candidate_languages(row):
        raw = row.get("language_original")
        if pd.isna(raw) or not str(raw).strip(): raw = row.get("language")
        return _model_b_language_values(raw)

    def score_row(row, similarity=None):
        overlap = len(wanted & candidate_genres(row)) / max(1, len(wanted))
        rating = pd.to_numeric(row.get("rating"), errors="coerce")
        votes = pd.to_numeric(row.get("votes"), errors="coerce")
        candidate_year = pd.to_numeric(row.get("year"), errors="coerce")
        year_score = 0 if pd.isna(candidate_year) or not year else max(0, 1 - abs(float(candidate_year) - int(year)) / 15)
        rating_score = max(0, float(rating) if pd.notna(rating) else 0) / 10
        vote_score = min(1, math.log1p(max(0, float(votes) if pd.notna(votes) else 0)) / math.log1p(100000))
        candidate_directors = _model_b_name_values(row.get("director"))
        candidate_cast = _model_b_name_values(row.get("cast"))
        director_bonus = .15 if selected_directors & candidate_directors else 0
        cast_bonus = .10 * len(selected_cast & candidate_cast) / max(1, len(selected_cast))
        # Current catalog rows have no director/cast fields, so these bonuses are neutral in production.
        if similarity is not None:
            return .25 * overlap + .25 * similarity + .15 * year_score + .07 * rating_score + .03 * vote_score + director_bonus + cast_bonus
        return .65 * overlap + .15 * year_score + .10 * rating_score + .05 * vote_score + director_bonus + cast_bonus

    ranked = []
    if selected_index is not None and tfidf_matrix is not None and neighbors is not None:
        query_neighbors = copy.copy(neighbors)
        query_neighbors.n_jobs = 1
        distances, ordered_indices = query_neighbors.kneighbors(
            tfidf_matrix[selected_index], n_neighbors=min(50, len(movies))
        )
        for distance, index in zip(distances[0], ordered_indices[0]):
            row = movies.loc[index]
            if selected_languages and not (selected_languages & candidate_languages(row)):
                continue
            similarity = max(0, 1 - float(distance))
            ranked.append((index, score_row(row, similarity), similarity))
        strategy = "tfidf_nn"
    else:
        for index, row in movies.iterrows():
            if selected_languages and not (selected_languages & candidate_languages(row)):
                continue
            if wanted & candidate_genres(row):
                ranked.append((index, score_row(row), None))
        strategy = "genre_fallback"
    ranked.sort(key=lambda item: (-item[1], str(movies.loc[item[0], "title"])))
    results, seen = [], set()
    for index, _, similarity in ranked:
        row = movies.loc[index]
        candidate_key = (_model_b_title_key(row.get("title")), str(row.get("year") or ""))
        candidate_title = candidate_key[0]
        candidate_imdb = str(row.get("id") or "")
        if index == selected_index or candidate_title == selected_title or (selected_imdb and candidate_imdb == selected_imdb) or candidate_title in seen:
            continue
        seen.add(candidate_title)
        payload = _model_b_local_payload(index)
        if similarity is not None: payload["similarity_score"] = round(similarity, 3)
        results.append(payload)
        if len(results) == limit:
            break
    return results, strategy


def _model_b_enrich_recommendation_posters(results):
    """Enrich only final local candidates; ranking and source remain local."""
    for result in results[:6]:
        if result.get("poster") or result.get("poster_url"):
            continue
        year = str(result.get("year") or "")
        imdb_id = str(result.get("imdb_id") or "")
        details = _model_b_omdb_movie(
            result["title"], int(year) if year.isdigit() else None,
            imdb_id=imdb_id if imdb_id.startswith("tt") else None,
        )
        poster = details.get("poster") if details else None
        if poster in (None, "", "N/A"):
            poster = None
        result["poster"] = poster or None
        result["poster_url"] = poster or None
        if details:
            for field in ("year", "rating", "imdb_id"):
                if details.get(field) not in (None, "", "N/A"):
                    result[field] = details[field]


@lru_cache(maxsize=128)
def _model_b_gemini(title, year=None, language=None):
    return MODEL_B_GEMINI.identify_and_discover(title, year=year, language=language)


def _model_b_gemini_payload(data):
    selected = data["selected_movie"]
    return {
        "title": selected["title"], "year": selected.get("year") or "N/A",
        "rating": "N/A", "genre": ", ".join(selected.get("genres") or []) or "N/A",
        "genres": selected.get("genres") or [], "runtime": "N/A",
        "director": "N/A", "cast": "N/A", "plot": selected.get("overview") or "No plot available.",
        "overview": selected.get("overview") or "", "poster": "", "poster_url": "",
        "language": selected.get("language") or "N/A", "source": "gemini_omdb",
        "local_match": False, "availability_status": "unknown",
    }


def _model_b_omdb_verified(title, year=None, imdb_id=None):
    """Return trusted OMDb metadata only for the requested movie identity."""
    raw = _omdb(title, imdb_id=imdb_id)
    if not isinstance(raw, dict) or raw.get("Type") != "movie":
        return None
    verified_title = raw.get("Title")
    if not imdb_id and _model_b_title_key(verified_title) != _model_b_title_key(title):
        return None
    verified_year = str(raw.get("Year") or "")[:4]
    if year is not None and verified_year.isdigit() and int(verified_year) != int(year):
        return None
    return movie_details(title, imdb_id=imdb_id)


def _model_b_omdb_movie(title, year=None, imdb_id=None):
    """Build the Phase 1 selected-movie card from verified OMDb data."""
    details = _model_b_omdb_verified(title, year, imdb_id=imdb_id)
    if not details:
        return None
    local_index = _model_b_local_index(details["title"], year)
    details.update({
        "genres": [genre.strip() for genre in str(details.get("genre") or "").split(",") if genre.strip()],
        "overview": details.get("plot") or "", "poster_url": details.get("poster") or "",
        "source": "omdb", "local_match": local_index is not None,
        "availability_status": "unknown",
    })
    return details


def _model_b_error(response):
    error = response.error or "provider_unavailable"
    messages = {
        "missing_configuration": "Gemini is not configured.", "timeout": "Gemini request timed out.",
        "rate_limited": "Gemini rate limit reached. Please try again shortly.",
        "unauthorized": "Gemini access is unavailable.",
        "ambiguous": "The movie could not be identified confidently.",
        "malformed_response": "Gemini returned an invalid response.",
        "omdb_unverified": "OMDb could not verify the movie.",
    }
    provider = "omdb" if error == "omdb_unverified" else "gemini"
    status = 504 if error == "timeout" else 429 if error == "rate_limited" else 422 if error == "ambiguous" else 400 if error == "invalid_request" else 503
    return jsonify({"error": messages.get(error, "Gemini movie lookup is unavailable."), "provider": provider, "provider_status": error}), status


def _model_b_selected(title, year=None, language=None):
    local_index = _model_b_local_index(title, year, language)
    if local_index is not None:
        print("[MODEL-B] movie identification provider=local")
        return _model_b_local_payload(local_index), None
    response = _model_b_gemini(title, year, language)
    if not response.ok:
        return None, response
    selected = _model_b_gemini_payload(response.data)
    omdb_details = _model_b_omdb_verified(selected["title"], response.data["selected_movie"].get("year"))
    if not omdb_details:
        return None, type(response)(False, error="omdb_unverified")
    selected.update(omdb_details)
    selected.update({"overview": selected.get("plot") or "", "poster_url": selected.get("poster") or "",
                     "source": "gemini_omdb", "local_match": False, "availability_status": "unknown"})
    local_index = _model_b_local_index(selected["title"], response.data["selected_movie"].get("year"), response.data["selected_movie"].get("language"))
    if local_index is not None:
        selected = _model_b_local_payload(local_index)
    print(f"[MODEL-B] movie identification provider={'local' if selected['local_match'] else 'gemini'}")
    return selected, response


def _model_b_candidate_results(selected, gemini, limit):
    selected_key = _model_b_title_key(selected["title"])
    selected_year = str(selected.get("year") or "")
    results, seen = [], set()
    for candidate in gemini.data.get("candidates", []):
        title, year = candidate.get("title"), candidate.get("year")
        key = _model_b_title_key(title)
        identity = (key, str(year or ""))
        if not key or key == selected_key and (not year or str(year) == selected_year):
            continue
        if identity in seen or key in {item[0] for item in seen}:
            continue
        local_index = _model_b_local_index(title, year, candidate.get("language"))
        if local_index is not None:
            payload = _model_b_local_payload(local_index)
            payload["recommendation_source"] = "local"
        else:
            payload = _model_b_omdb_verified(title, year)
            if not payload:
                continue
            payload.update({
                "genres": [genre.strip() for genre in str(payload.get("genre") or "").split(",") if genre.strip()],
                "overview": payload.get("plot") or "", "poster_url": payload.get("poster") or "",
                "source": "gemini_omdb", "recommendation_source": "gemini",
                "availability_status": "unknown", "explanation": candidate.get("reason") or "",
            })
        seen.add(identity)
        results.append(payload)
        if len(results) == limit:
            break
    return results


def _model_b_verify_ott(results, region):
    candidates = [MovieCandidate(title=item["title"], year=item.get("year") if isinstance(item.get("year"), int) else None) for item in results]
    outcome = WATCHMODE_OTT_ENRICHER.enrich(candidates, region=region, limit=len(candidates))
    for item, candidate in zip(results, outcome.candidates):
        item["availability_status"] = candidate.availability_status
        if candidate.streaming_sources:
            item["streaming_sources"] = candidate.streaming_sources
    print(f"[MODEL-B] watchmode status={'verified' if outcome.verified else 'unknown'}")
    return results
# ============================================================
# Gemini AI Explanation
# ============================================================

@lru_cache(maxsize=256)
def ai_explanation(base, candidate):
    """
    Describe the title-based recommendation without inventing movie facts.
    """
    return (
        f"{candidate} was selected by the existing recommendation model "
        f"for title similarity to {base}."
    )


@lru_cache(maxsize=128)
def _gemini_relevant_explanation_fields(user_request):
    if not GEMINI_API_KEY:
        return ()

    try:
        client = _create_gemini_client()
        prompt = (
            "Choose which metadata field names are relevant to this movie request. "
            'Return only JSON in this form: {"relevant_fields": []}. '
            "Allowed fields: genre, language, year, rating. Return no movie facts or prose.\n"
            f"User request: {user_request}"
        )
        text = _generate_with_gemini(client, prompt)
        if not text:
            return ()

        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        import json
        response = json.loads(text)
        requested_fields = response.get("relevant_fields", [])
        if not isinstance(requested_fields, list):
            return ()

        allowed_fields = {"genre", "language", "year", "rating"}
        return tuple(
            dict.fromkeys(
                field
                for field in requested_fields
                if isinstance(field, str) and field in allowed_fields
            )
        )
    except Exception:
        print("Gemini natural-language explanation request failed. Using dataset metadata.")
        return ()


@lru_cache(maxsize=256)
def nl_ai_explanation(user_request, title, year, rating, genre, language):
    metadata = {
        "genre": genre,
        "language": language,
        "year": year,
        "rating": rating,
    }
    available_metadata = {
        key: str(value).strip()
        for key, value in metadata.items()
        if value not in (None, "", "N/A")
    }

    def grounded_explanation(fields):
        if not fields:
            return f"{title} was selected using the available movie dataset metadata."

        details = "; ".join(
            f"{field}: {available_metadata[field]}"
            for field in fields
        )
        return f"{title} matches your request based on dataset metadata ({details})."

    if not GEMINI_API_KEY:
        return grounded_explanation(list(available_metadata))

    selected_fields = [
        field
        for field in _gemini_relevant_explanation_fields(user_request)
        if field in available_metadata
    ]
    return grounded_explanation(selected_fields or list(available_metadata))
# ============================================================
# Find Movie Index
# ============================================================

def find_movie_index(title):
    """
    Find the best matching movie in the Indian dataset.

    Exact normalized title is preferred.

    If multiple records have the same title,
    the record with the strongest rating/vote
    information is selected.
    """

    if movies is None:
        return None

    normalized_title = (
        title
        .strip()
        .casefold()
    )

    # --------------------------------------------------------
    # Exact normalized title
    # --------------------------------------------------------

    matches = movies[
        movies["title_normalized"]
        .astype(str)
        .str.casefold()
        == normalized_title
    ]

    # --------------------------------------------------------
    # Prefix fallback
    # --------------------------------------------------------

    if matches.empty:

        matches = movies[
            movies["title"]
            .astype(str)
            .str.casefold()
            .str.startswith(
                normalized_title
            )
        ]

    if matches.empty:
        return None

    # --------------------------------------------------------
    # Handle duplicate titles
    # --------------------------------------------------------

    if len(matches) > 1:

        matches = matches.copy()

        matches["rating_sort"] = pd.to_numeric(
            matches["rating"],
            errors="coerce"
        ).fillna(-1)

        matches["votes_sort"] = pd.to_numeric(
            matches["votes"],
            errors="coerce"
        ).fillna(-1)

        matches = matches.sort_values(
            by=[
                "rating_sort",
                "votes_sort"
            ],
            ascending=False
        )

    return matches.index[0]

# ============================================================
# Recommendation Title Deduplication
# ============================================================

def _title_key(title):
    """
    Normalize a movie title for user-facing duplicate detection.
    """

    return str(title).strip().casefold()
# ============================================================
# ML Recommendation Engine
# ============================================================

def recommend_titles(title, limit=8):
    """
    Find movies similar to the requested movie using:

        TF-IDF
            +
        Cosine NearestNeighbors

    The ML model decides which movies are similar.

    OMDb and Gemini are used only for enrichment
    and explanation.
    """

    if (
        not MODEL_LOADED
        or movies is None
        or tfidf_matrix is None
        or neighbors is None
    ):

        return []

    movie_index = find_movie_index(
        title
    )

    if movie_index is None:
        return []

    # --------------------------------------------------------
    # Get selected movie vector
    # --------------------------------------------------------

    movie_vector = tfidf_matrix[
        movie_index
    ]

    # --------------------------------------------------------
    # Find nearest movies
    # --------------------------------------------------------

    # Do not mutate the loaded estimator for an individual request.  A shallow
    # copy retains its trained index and parameters while avoiding an
    # all-CPU worker pool in restricted deployment/test hosts.
    query_neighbors = copy.copy(neighbors)
    query_neighbors.n_jobs = 1
    distances, indices = query_neighbors.kneighbors(
        movie_vector,
        n_neighbors=min(
            max(limit + 1, neighbors.n_neighbors),
            len(movies),
        )
    )

    output = []
    seen_titles = {
        _title_key(movies.iloc[movie_index]["title"])
    }
    for distance, index in zip(
        distances[0],
        indices[0]
    ):

        # ----------------------------------------------------
        # Skip selected movie
        # ----------------------------------------------------

        if index == movie_index:
            continue

        candidate = str(
            movies.iloc[index]["title"]
        )
        title_key = _title_key(candidate)

        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        # ----------------------------------------------------
        # Convert cosine distance to similarity
        # ----------------------------------------------------

        similarity_score = (
            1.0 - float(distance)
        )

        # ----------------------------------------------------
        # Get OMDb enrichment
        # ----------------------------------------------------

        details = get_movie_details(
            candidate,
            dataset_index=index
        )

        if not details:
            continue

        # ----------------------------------------------------
        # Add ML similarity score
        # ----------------------------------------------------

        details["similarity"] = round(
            similarity_score,
            3
        )

        # ----------------------------------------------------
        # Gemini explanation
        # ----------------------------------------------------

        details["explanation"] = ai_explanation(
            title,
            candidate
        )

        output.append(
            details
        )

        if len(output) >= limit:
            break

    return output


# ============================================================
# API — Health Check
# ============================================================

@app.get("/api/health")
def health():

    return jsonify({

        "ok": True,

        "model_loaded": MODEL_LOADED,

        "movies_loaded": (
            len(movies)
            if movies is not None
            else 0
        ),

        "tfidf_features": (
            tfidf_matrix.shape[1]
            if tfidf_matrix is not None
            else 0
        ),

        "omdb_configured": bool(
            OMDB_API_KEY
        ),

        "gemini_configured": bool(
            GEMINI_API_KEY
        ),

        "watchmode_configured": WATCHMODE_CLIENT.configured,

        "recommendation_source": RECOMMENDATION_SOURCE,
    })


# ============================================================
# API — Watchmode Discovery Provider
# ============================================================

def _watchmode_error(response):
    """Convert a normalized Watchmode failure into a safe Flask response."""
    error = response.error
    if error == "missing_configuration":
        message, status = "Watchmode is not configured.", 503
    elif error == "invalid_request":
        message, status = "Invalid Watchmode request.", 400
    elif error == "timeout":
        message, status = "Watchmode request timed out.", 504
    elif error == "rate_limited":
        message, status = "Watchmode rate limit reached.", 429
    elif error in {"authentication_failed", "unauthorized"}:
        message, status = "Watchmode authentication or account access failed.", 502
    else:
        message, status = "Watchmode provider is unavailable.", 502

    payload = {"error": message, "provider": "watchmode"}
    if response.retry_after:
        payload["retry_after"] = response.retry_after
    return jsonify(payload), status


def _valid_watchmode_id(value):
    return bool(re.fullmatch(r"[0-9]{1,12}", str(value)))


@app.get("/api/watchmode/status")
def watchmode_status():
    response = WATCHMODE_CLIENT.status()
    if not response.ok:
        return _watchmode_error(response)
    return jsonify({
        "provider": "watchmode",
        "configured": True,
        "authenticated": True,
        "endpoint_accessible": True,
    })


@app.get("/api/watchmode/search")
def watchmode_search():
    query = request.args.get("q", "").strip()
    if not query or len(query) < 2:
        return jsonify({"error": "Movie title query must contain at least 2 characters."}), 400
    if len(query) > 150:
        return jsonify({"error": "Movie title query is too long."}), 400

    response = WATCHMODE_CLIENT.search_by_title(query)
    if not response.ok:
        return _watchmode_error(response)
    titles = response.data["title_results"]
    return jsonify({"provider": "watchmode", "results": titles, "count": len(titles)})


@app.get("/api/watchmode/title/<watchmode_id>")
def watchmode_title(watchmode_id):
    if not _valid_watchmode_id(watchmode_id):
        return jsonify({"error": "Watchmode ID must be numeric."}), 400

    response = WATCHMODE_CLIENT.movie_details(watchmode_id)
    if not response.ok:
        return _watchmode_error(response)
    return jsonify({"provider": "watchmode", "result": response.data})


@app.get("/api/watchmode/sources/<watchmode_id>")
def watchmode_sources(watchmode_id):
    if not _valid_watchmode_id(watchmode_id):
        return jsonify({"error": "Watchmode ID must be numeric."}), 400
    region = request.args.get("region", "IN").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", region):
        return jsonify({"error": "Region must be a two-letter country code."}), 400

    response = WATCHMODE_CLIENT.streaming_sources(watchmode_id, regions=region)
    if not response.ok:
        return _watchmode_error(response)
    return jsonify({"provider": "watchmode", "region": region, "sources": response.data})


# ============================================================
# API — Additive Hybrid Retrieval
# ============================================================

@app.get("/api/recommend-hybrid")
def recommend_hybrid():
    """Hybrid retrieval without changing legacy recommendation contracts.

    ``text`` carries preferences; ``title`` is optional except for an exact
    title/OTT availability request.  The endpoint deliberately does not call
    unverified Watchmode discovery operations.
    """
    text = request.args.get("text", "").strip()
    title = request.args.get("title", "").strip()
    if len(text) > 500:
        return jsonify({"error": "Natural-language movie request is too long."}), 400
    if len(title) > 150:
        return jsonify({"error": "Movie title is too long."}), 400
    if not text and not title:
        return jsonify({"error": "Natural-language movie request or title is required."}), 400

    region = request.args.get("region", "IN").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", region):
        return jsonify({"error": "Region must be a two-letter country code."}), 400
    limit_value = request.args.get("limit", "10")
    try:
        limit = int(limit_value)
    except ValueError:
        return jsonify({"error": "Limit must be an integer."}), 400
    if not 1 <= limit <= 20:
        return jsonify({"error": "Limit must be between 1 and 20."}), 400

    query = text or title
    intent, unsupported_terms = parse_recommendation_intent(query, DATASET_VOCABULARY)
    if intent is None:
        return jsonify({"error": "Unable to understand the movie request."}), 503
    if unsupported_terms["genres"] or unsupported_terms["languages"]:
        return jsonify({"error": "Unsupported movie request.", "unsupported": unsupported_terms}), 422

    return jsonify(retrieve_hybrid(
        text=query,
        title=title or None,
        region=region,
        limit=limit,
        intent=intent,
        movies=movies,
        tfidf_matrix=tfidf_matrix,
        neighbors=neighbors,
        find_movie_index=find_movie_index,
        watchmode_client=WATCHMODE_CLIENT,
        discovery_provider=WATCHMODE_DISCOVERY,
        tmdb_discovery_provider=TMDB_DISCOVERY,
        watchmode_ott_enricher=WATCHMODE_OTT_ENRICHER,
        recommendation_source=RECOMMENDATION_SOURCE,
    ))


# ============================================================
# API — Autocomplete
# ============================================================

@app.get("/api/autocomplete")
def autocomplete():

    q = request.args.get(
        "q",
        ""
    ).strip().casefold()

    if len(q) > 150:
        return jsonify({"error": "Search query is too long."}), 400

    if len(q) < 2:
        return jsonify([])

    titles, seen = [], set()
    for item in _model_b_local_results(q, limit=8):
        title, key = item["title"], _model_b_title_key(item["title"])
        if key not in seen:
            seen.add(key)
            titles.append(title)
    print("[MODEL-B] autocomplete source=local")
    return jsonify(titles)


# ============================================================
# API — Search
# ============================================================

@app.get("/api/search")
def search():

    q = request.args.get(
        "q",
        ""
    ).strip()

    if len(q) > 150:
        return jsonify({"error": "Search query is too long."}), 400

    if len(q) < 2:

        return jsonify({
            "results": []
        })

    selected = _model_b_omdb_movie(q)
    if selected:
        print("[MODEL-B] movie search provider=omdb")
        return jsonify({"results": [selected], "source": "omdb"})
    results = _model_b_local_results(q)
    if results:
        return jsonify({"results": results, "source": "local"})
    if not OMDB_API_KEY:
        return jsonify({"error": "OMDb is not configured.", "provider": "omdb", "provider_status": "missing_configuration"}), 503
    return jsonify({"results": [], "source": "omdb"})


# ============================================================
# API — Movie Details
# ============================================================

def _model_b_enriched_local(local_index, title, year, imdb_id=None):
    payload = _model_b_local_payload(local_index)
    cid = imdb_id or payload.get("imdb_id")
    if cid and OMDB_API_KEY:
        enrich = _model_b_omdb_movie(title, int(year) if year else None, imdb_id=cid)
        if enrich:
            for k, v in enrich.items():
                if v not in (None, "", "N/A", "Details unavailable.", "No plot available."):
                    payload[k] = v
            payload["source"] = "Indian Dataset + OMDb"
    return payload

@app.get("/api/movie")
def movie():

    title = request.args.get("title", "").strip()
    year = request.args.get("year", "").strip()
    language = request.args.get("language", "").strip() or None
    imdb_id = request.args.get("imdb_id", "").strip() or None

    if len(title) > 150:
        return jsonify({"error": "Movie title is too long."}), 400

    if not title:

        return jsonify({
            "error": "Movie title is required."
        }), 400

    if year and (not year.isdigit() or not 1888 <= int(year) <= 2100):
        return jsonify({"error": "Year must be a valid four-digit year."}), 400
    data = _model_b_omdb_movie(title, int(year) if year else None, imdb_id=imdb_id)
    if data:
        print("[MODEL-B] movie details provider=omdb")
        return jsonify(data)
    local_index = _model_b_local_index(title, int(year) if year else None, language)
    if local_index is not None:
        return jsonify(_model_b_enriched_local(local_index, title, year, imdb_id))
    if not OMDB_API_KEY:
        return jsonify({"error": "OMDb is not configured.", "provider": "omdb", "provider_status": "missing_configuration"}), 503
    return jsonify({"error": "Movie was not found in OMDb.", "provider": "omdb", "provider_status": "not_found"}), 404


# ============================================================
# API — Recommendations
# ============================================================

@app.get("/api/recommend")
def recommend():
    title = request.args.get("title", "").strip()
    year = request.args.get("year", "").strip()
    genres = [item.strip() for item in request.args.get("genre", "").split(",") if item.strip()]
    language = request.args.get("language", "").strip() or None
    director = request.args.get("director", "").strip() or None
    cast = request.args.get("cast", "").strip() or None
    imdb_id = request.args.get("imdb_id", "").strip() or None
    limit_value = request.args.get("limit", "6")
    if not title or len(title) > 150:
        return jsonify({"error": "Movie title is required and must be at most 150 characters."}), 400
    if year and (not year.isdigit() or not 1888 <= int(year) <= 2100):
        return jsonify({"error": "Year must be a valid four-digit year."}), 400
    try:
        limit = int(limit_value)
    except ValueError:
        return jsonify({"error": "Limit must be an integer."}), 400
    if not 1 <= limit <= 6:
        return jsonify({"error": "Limit must be between 1 and 6."}), 400
    results, strategy = _model_b_local_recommendations(
        title, int(year) if year else None, genres, imdb_id, limit, language, director, cast
    )
    _model_b_enrich_recommendation_posters(results)
    selected_movie = {"title": title, "year": year or None, "genre": genres, "language": language}
    return jsonify({"selected_movie": selected_movie, "recommendations": results, "results": results,
                    "recommendation_source": strategy, "source": "local", "count": len(results)})

# ============================================================
# API — Natural-Language Recommendations
# ============================================================

@app.get("/api/recommend-text")
def recommend_text():

    text = request.args.get(
        "text",
        ""
    ).strip()

    if len(text) > 500:
        return jsonify({"error": "Natural-language movie request is too long."}), 400

    if not text:
        return jsonify({
            "error": "Natural-language movie request is required."
        }), 400

    # --------------------------------------------------------
    # Convert natural language into structured intent
    # --------------------------------------------------------

    intent, unsupported_terms = parse_recommendation_intent(
        text,
        DATASET_VOCABULARY
    )

    if intent is None:
        return jsonify({
            "error": "Unable to understand the movie request."
        }), 503

    if (
        unsupported_terms["genres"]
        or unsupported_terms["languages"]
    ):
        return jsonify({
            "error": "Unsupported movie request.",
            "unsupported": unsupported_terms
        }), 422

    # `/api/recommend` remains the explicit legacy Model-A endpoint.  Natural
    # language requests use the configured source boundary instead.
    if RECOMMENDATION_SOURCE != "local":
        return jsonify(retrieve_hybrid(
            text=text,
            title=None,
            region="IN",
            limit=10,
            intent=intent,
            movies=movies,
            tfidf_matrix=tfidf_matrix,
            neighbors=neighbors,
            find_movie_index=find_movie_index,
            watchmode_client=WATCHMODE_CLIENT,
            discovery_provider=WATCHMODE_DISCOVERY,
            tmdb_discovery_provider=TMDB_DISCOVERY,
            watchmode_ott_enricher=WATCHMODE_OTT_ENRICHER,
            recommendation_source=RECOMMENDATION_SOURCE,
        ))


    # --------------------------------------------------------
    # Retrieve and deterministically rank movies
    # --------------------------------------------------------

    results = recommend_from_intent(
        movies,
        intent,
        limit=10
    )

    if results is None or results.empty:

        return jsonify({
            "query": text,
            "intent": intent,
            "results": []
        })

        # --------------------------------------------------------
    # Enrich selected movies with OMDb
    # and generate Gemini explanations
    # --------------------------------------------------------

    output = []
    seen_titles = set()

    for index, row in results.iterrows():

        title = str(row["title"])
        title_key = _title_key(title)

        if title_key in seen_titles:
            continue

        seen_titles.add(title_key)
        # ----------------------------------------------------
        # Get combined dataset + OMDb details
        # ----------------------------------------------------

        details = get_movie_details(
            title,
            dataset_index=index
        )

        if not details:
            continue
        # ----------------------------------------------------
        # Preserve Indian dataset fields as recommendation truth
        # ----------------------------------------------------
        dataset_genre = (
            str(row["genre_original"])
            if pd.notna(row.get("genre_original"))
            else "N/A"
        )
        dataset_language = (
            str(row["language_original"])
            if pd.notna(row.get("language_original"))
            else "N/A"
        )
        details["genre"] = dataset_genre
        details["language"] = dataset_language
        dataset_year = (
            int(row["year"])
            if pd.notna(row.get("year"))
            else "N/A"
        )

        dataset_rating = (
            float(row["rating"])
            if pd.notna(row.get("rating"))
            else "N/A"
        )

        details["year"] = dataset_year
        details["rating"] = dataset_rating
        dataset_duration = row.get("duration_min")
        details["runtime"] = (
            f"{int(dataset_duration)} min"
            if pd.notna(dataset_duration)
            else "N/A"
        )
        # ----------------------------------------------------
        # Gemini explanation
        # ----------------------------------------------------
        details["explanation"] = nl_ai_explanation(
            text,
            details.get("title", title),
            details.get("year", "N/A"),
            details.get("rating", "N/A"),
            dataset_genre,
            dataset_language
        )
        # ----------------------------------------------------
        # Preserve deterministic ranking information
        # ----------------------------------------------------
        details["votes"] = (
            int(row["votes"])
            if pd.notna(row["votes"])
            else "N/A"
        )
        output.append(details)

    return jsonify({
        "query": text,
        "intent": intent,
        "results": output
    })
# ============================================================
# Frontend Serving
# ============================================================

@app.get("/")
@app.get("/<path:path>")
def frontend(path=""):

    target = os.path.join(
        FRONTEND_DIR,
        path
    )

    if (
        path
        and os.path.isfile(target)
    ):

        return send_from_directory(
            FRONTEND_DIR,
            path
        )

    return send_from_directory(
        FRONTEND_DIR,
        "index.html"
    )


# ============================================================
# Run Application
# ============================================================

if __name__ == "__main__":

    app.run(
        debug=False,
        port=int(
            os.getenv(
                "PORT",
                "5000"
            )
        )
    )
