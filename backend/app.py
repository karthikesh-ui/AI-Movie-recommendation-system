import os
import sys
import pickle
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


# ============================================================
# CORS Configuration
# ============================================================

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": os.getenv(
                "FRONTEND_ORIGIN",
                "*"
            )
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
# ============================================================
# Gemini Natural-Language Intent Parser
# ============================================================

def _rule_based_intent_parse(user_text, dataset_vocabulary):
    text_lower = user_text.lower()
    valid_genres = dataset_vocabulary.get("genres", set()) if dataset_vocabulary else set()
    valid_languages = dataset_vocabulary.get("languages", set()) if dataset_vocabulary else set()

    matched_genres = [g for g in valid_genres if g in text_lower]
    matched_languages = [l for l in valid_languages if l in text_lower]

    mood = None
    if any(k in text_lower for k in ["feel-good", "feel good", "happy", "fun", "joy"]):
        mood = "feel_good"
    elif any(k in text_lower for k in ["romantic", "romance", "love"]):
        mood = "romantic"
    elif any(k in text_lower for k in ["emotional", "touching", "heartfelt", "sad"]):
        mood = "emotional"
    elif any(k in text_lower for k in ["intense", "thrilling", "action", "suspense"]):
        mood = "intense"
    elif any(k in text_lower for k in ["light", "casual"]):
        mood = "light"

    audience = None
    if "family" in text_lower:
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

    raw_intent = {
        "genres": matched_genres,
        "languages": matched_languages,
        "year_from": None,
        "year_to": None,
        "duration_preference": None,
        "mood": mood,
        "audience": audience,
        "ranking": ranking
    }

    validated_intent = validate_intent(raw_intent, dataset_vocabulary)
    unsupported_terms = {"genres": [], "languages": []}
    return validated_intent, unsupported_terms


def _generate_with_gemini(client, prompt):
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
        except Exception:
            continue
    return None


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
            from google import genai

            client = genai.Client(
                api_key=GEMINI_API_KEY
            )

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

                return validated_intent, unsupported_terms

        except Exception as error:
            print(
                f"Gemini intent error: {error}. Falling back to rule-based parser."
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
def _omdb(title, plot="full"):
    """
    Get movie information from OMDb.

    Results are cached to reduce unnecessary API calls.
    """

    if not OMDB_API_KEY:
        return None

    try:

        response = requests.get(
            "https://www.omdbapi.com/",
            params={
                "t": title,
                "plot": plot,
                "apikey": OMDB_API_KEY
            },
            timeout=8
        )

        response.raise_for_status()

        data = response.json()

        if data.get("Response") == "False":
            return None

        return data

    except requests.RequestException as error:

        print(
            f"OMDb request error: {error}"
        )

        return None


# ============================================================
# Movie Details
# ============================================================

@lru_cache(maxsize=256)
def movie_details(title):
    """
    Get movie details using OMDb.

    OMDb is used for enrichment.
    The Indian dataset remains the source for
    movie discovery and recommendation.
    """

    data = _omdb(title)

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

        "source": "OMDb",

        "imdb_id": data.get(
            "imdbID"
        )
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
        "cast": "N/A",
        "plot": "Details unavailable.",
        "poster": "",
        "language": language,
        "source": "ML Dataset",
        "imdb_id": imdb_id
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
# Gemini AI Explanation
# ============================================================

def _fallback_explanation(base, candidate):
    """
    Fallback explanation when Gemini is unavailable.
    """

    return (
        f"{candidate} shares themes, genre signals, "
        f"or storytelling elements with {base}."
    )


@lru_cache(maxsize=256)
def ai_explanation(base, candidate):
    """
    Generate a short AI explanation using Gemini.

    Gemini is explanation-only.
    It does not decide the recommendation.
    """

    if not GEMINI_API_KEY:

        return _fallback_explanation(
            base,
            candidate
        )

    try:

        from google import genai

        client = genai.Client(
            api_key=GEMINI_API_KEY
        )

        prompt = (
            f"Explain in one concise sentence "
            f"(maximum 22 words) why '{candidate}' "
            f"fits someone who liked '{base}'. "
            f"Avoid spoilers and do not mention being an AI."
        )

        text = _generate_with_gemini(client, prompt)

        return (
            text
            if text
            else _fallback_explanation(
                base,
                candidate
            )
        )

    except Exception as error:

        print(
            f"Gemini error: {error}"
        )

        return _fallback_explanation(
            base,
            candidate
        )

@lru_cache(maxsize=256)
def nl_ai_explanation(user_request, title, year, rating, genre, language):
    if not GEMINI_API_KEY:
        return (
            f"'{title}' matches your request based on its "
            f"dataset genre, language, year, and rating."
        )

    try:
        from google import genai

        client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = (
            "Explain in one concise sentence (maximum 22 words) "
            "why this movie fits the user's natural-language request. "
            "Use only the supplied movie information. "
            "Do not recommend another movie. "
            "Do not change or invent movie facts. "
            "Avoid spoilers and do not mention being an AI.\n\n"
            f"User request: {user_request}\n"
            f"Movie title: {title}\n"
            f"Year: {year}\n"
            f"Rating: {rating}\n"
            f"Genre: {genre}\n"
            f"Language: {language}"
        )

        text = _generate_with_gemini(client, prompt)

        if text:
            return text

        return (
            f"'{title}' matches your request based on its "
            f"available movie details."
        )

    except Exception as error:
        print(f"Gemini NL explanation error: {error}")
        return (
            f"'{title}' matches your request based on its "
            f"available movie details."
        )
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

    distances, indices = neighbors.kneighbors(
        movie_vector,
        n_neighbors=limit + 1
    )

    output = []
    seen_titles = set()
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
        )
    })


# ============================================================
# API — Autocomplete
# ============================================================

@app.get("/api/autocomplete")
def autocomplete():

    q = request.args.get(
        "q",
        ""
    ).strip().casefold()

    if len(q) < 2:
        return jsonify([])

    if movies is None:
        return jsonify([])

    titles = (
        movies["title"]
        .astype(str)
        .drop_duplicates()
        .tolist()
    )

    # --------------------------------------------------------
    # Titles beginning with query
    # --------------------------------------------------------

    starts = [
        title
        for title in titles
        if title.casefold().startswith(q)
    ]

    # --------------------------------------------------------
    # Titles containing query
    # --------------------------------------------------------

    contains = [
        title
        for title in titles
        if q in title.casefold()
        and title not in starts
    ]

    return jsonify(
        (starts + contains)[:8]
    )


# ============================================================
# API — Search
# ============================================================

@app.get("/api/search")
def search():

    q = request.args.get(
        "q",
        ""
    ).strip()

    if len(q) < 2:

        return jsonify({
            "results": []
        })

    if movies is None:

        return jsonify({
            "results": []
        })

    # --------------------------------------------------------
    # Search primary Indian dataset
    # --------------------------------------------------------

    matches = movies[
        movies["title"]
        .astype(str)
        .str.casefold()
        .str.contains(
            q.casefold(),
            na=False,
            regex=False
        )
    ]

    # Keep first occurrence of each title
    matches = (
        matches
        .drop_duplicates(
            subset=["title_normalized"]
        )
        .head(10)
    )

    results = []

    for index, row in matches.iterrows():

        title = str(
            row["title"]
        )

        details = get_movie_details(
            title,
            dataset_index=index
        )

        if details:
            results.append(
                details
            )

    return jsonify({
        "results": results
    })


# ============================================================
# API — Movie Details
# ============================================================

@app.get("/api/movie")
def movie():

    title = request.args.get(
        "title",
        ""
    ).strip()

    if not title:

        return jsonify({
            "error": "Movie title is required."
        }), 400

    # --------------------------------------------------------
    # Find movie in Indian dataset first
    # --------------------------------------------------------

    movie_index = find_movie_index(
        title
    )

    if movie_index is None:

        return jsonify({
            "error": (
                "Movie is not available "
                "in the current Indian movie dataset."
            )
        }), 404

    dataset_title = str(
        movies.iloc[movie_index]["title"]
    )

    # --------------------------------------------------------
    # Get OMDb information with dataset fallback
    # --------------------------------------------------------

    data = get_movie_details(
        dataset_title,
        dataset_index=movie_index
    )

    if not data:

        return jsonify({
            "error": "Movie details unavailable."
        }), 404

    # --------------------------------------------------------
    # AI insight
    # --------------------------------------------------------

    data["insight"] = ai_explanation(
        dataset_title,
        dataset_title
    )

    return jsonify(data)


# ============================================================
# API — Recommendations
# ============================================================

@app.get("/api/recommend")
def recommend():

    title = request.args.get(
        "title",
        ""
    ).strip()

    if not title:

        return jsonify({
            "error": "Movie title is required."
        }), 400

    limit_value = request.args.get("limit")

    if limit_value is None:
        limit = 8
    else:
        try:
            limit = int(limit_value)
        except ValueError:
            return jsonify({
                "error": "Limit must be an integer."
            }), 400
    if limit < 1:
        return jsonify({
            "error": "Limit must be at least 1."
    }), 400
    results = recommend_titles(
        title,
        limit=limit
    )
    if not results:

        return jsonify({
            "error": (
                "That movie is not available "
                "in the current ML recommendation dataset."
            )
        }), 404

    return jsonify({
        "results": results
    })

# ============================================================
# API — Natural-Language Recommendations
# ============================================================

@app.get("/api/recommend-text")
def recommend_text():

    text = request.args.get(
        "text",
        ""
    ).strip()

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
