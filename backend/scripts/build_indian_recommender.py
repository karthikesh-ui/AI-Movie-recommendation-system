import os
import pickle

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

DATA_FILE = os.path.join(
    BASE_DIR,
    "..",
    "data",
    "processed",
    "indian_movies_clean.csv"
)

MODEL_DIR = os.path.join(
    BASE_DIR,
    "models"
)

MOVIES_FILE = os.path.join(
    MODEL_DIR,
    "movies.pkl"
)

VECTORIZER_FILE = os.path.join(
    MODEL_DIR,
    "vectorizer.pkl"
)

TFIDF_MATRIX_FILE = os.path.join(
    MODEL_DIR,
    "tfidf_matrix.pkl"
)

NEIGHBORS_FILE = os.path.join(
    MODEL_DIR,
    "neighbors.pkl"
)


# ============================================================
# CONFIGURATION
# ============================================================

MAX_FEATURES = 50000

NGRAM_RANGE = (1, 2)

MIN_DF = 1

N_NEIGHBORS = 20


# ============================================================
# TEXT PREPARATION
# ============================================================

def build_recommendation_text(row):
    """
    Build the textual representation used by TF-IDF.

    We intentionally use:
        - title
        - genre
        - language

    Metadata such as rating, votes, year and duration are
    preserved in the movie dataframe but are not treated as
    semantic text features.
    """

    title = str(row["title"])
    genre = str(row["genre"])
    language = str(row["language"])

    # Repeat language/genre slightly to give these fields
    # meaningful importance without using numeric metadata.
    text = (
        f"{title} "
        f"{genre} "
        f"{genre} "
        f"{language} "
        f"{language}"
    )

    return text.strip()


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 65)
    print("INDIAN MOVIE RECOMMENDATION MODEL BUILDING")
    print("=" * 65)

    # --------------------------------------------------------
    # Check dataset
    # --------------------------------------------------------

    if not os.path.exists(DATA_FILE):

        print("\nERROR: Cleaned dataset not found:")
        print(DATA_FILE)

        return

    print("\nInput dataset:")
    print(DATA_FILE)

    # --------------------------------------------------------
    # Create model directory
    # --------------------------------------------------------

    os.makedirs(
        MODEL_DIR,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Load dataset
    # --------------------------------------------------------

    print("\nLoading cleaned dataset...")

    movies = pd.read_csv(
        DATA_FILE,
        low_memory=False
    )

    print(
        f"Movies loaded: {len(movies):,}"
    )

    # --------------------------------------------------------
    # Validate required columns
    # --------------------------------------------------------

    required_columns = [
        "id",
        "title",
        "title_normalized",
        "year",
        "duration_min",
        "rating",
        "votes",
        "genre",
        "language"
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in movies.columns
    ]

    if missing_columns:

        print("\nERROR: Required columns are missing:")

        for column in missing_columns:
            print(
                f"  - {column}"
            )

        return

    # --------------------------------------------------------
    # Fill missing text values
    # --------------------------------------------------------

    movies["title"] = (
        movies["title"]
        .fillna("")
        .astype(str)
    )

    movies["genre"] = (
        movies["genre"]
        .fillna("")
        .astype(str)
    )

    movies["language"] = (
        movies["language"]
        .fillna("")
        .astype(str)
    )

    # --------------------------------------------------------
    # Build recommendation text
    # --------------------------------------------------------

    print("\nBuilding recommendation text...")

    movies["recommendation_text"] = (
        movies.apply(
            build_recommendation_text,
            axis=1
        )
    )

    # --------------------------------------------------------
    # TF-IDF
    # --------------------------------------------------------

    print("\nCreating TF-IDF vectorizer...")

    vectorizer = TfidfVectorizer(
        lowercase=True,
        strip_accents="unicode",
        ngram_range=NGRAM_RANGE,
        min_df=MIN_DF,
        max_features=MAX_FEATURES,
        sublinear_tf=True
    )

    print("Fitting TF-IDF...")

    tfidf_matrix = vectorizer.fit_transform(
        movies["recommendation_text"]
    )

    print(
        f"TF-IDF matrix shape: "
        f"{tfidf_matrix.shape}"
    )

    print(
        f"TF-IDF matrix type: "
        f"{type(tfidf_matrix).__name__}"
    )

    # --------------------------------------------------------
    # Nearest Neighbors
    # --------------------------------------------------------

    print("\nBuilding cosine nearest-neighbor model...")

    neighbors = NearestNeighbors(
        n_neighbors=N_NEIGHBORS,
        metric="cosine",
        algorithm="brute",
        n_jobs=-1
    )

    neighbors.fit(
        tfidf_matrix
    )

    print("Nearest-neighbor model fitted.")

    # --------------------------------------------------------
    # Remove temporary column before saving
    # --------------------------------------------------------

    movies = movies.drop(
        columns=["recommendation_text"]
    )

    # --------------------------------------------------------
    # Save movies dataframe
    # --------------------------------------------------------

    print("\nSaving movies dataframe...")

    with open(
        MOVIES_FILE,
        "wb"
    ) as file:

        pickle.dump(
            movies,
            file,
            protocol=pickle.HIGHEST_PROTOCOL
        )

    # --------------------------------------------------------
    # Save vectorizer
    # --------------------------------------------------------

    print("Saving TF-IDF vectorizer...")

    with open(
        VECTORIZER_FILE,
        "wb"
    ) as file:

        pickle.dump(
            vectorizer,
            file,
            protocol=pickle.HIGHEST_PROTOCOL
        )

    # --------------------------------------------------------
    # Save TF-IDF matrix
    # --------------------------------------------------------

    print("Saving TF-IDF matrix...")

    with open(
        TFIDF_MATRIX_FILE,
        "wb"
    ) as file:

        pickle.dump(
            tfidf_matrix,
            file,
            protocol=pickle.HIGHEST_PROTOCOL
        )

    # --------------------------------------------------------
    # Save nearest-neighbor model
    # --------------------------------------------------------

    print("Saving nearest-neighbor model...")

    with open(
        NEIGHBORS_FILE,
        "wb"
    ) as file:

        pickle.dump(
            neighbors,
            file,
            protocol=pickle.HIGHEST_PROTOCOL
        )

    # --------------------------------------------------------
    # Final report
    # --------------------------------------------------------

    print("\n" + "=" * 65)
    print("MODEL BUILD COMPLETE")
    print("=" * 65)

    print(
        f"\nMovies:              {len(movies):,}"
    )

    print(
        f"TF-IDF features:     {tfidf_matrix.shape[1]:,}"
    )

    print(
        f"TF-IDF matrix rows:  {tfidf_matrix.shape[0]:,}"
    )

    print(
        f"Nearest neighbors:   {N_NEIGHBORS}"
    )

    print("\nSaved model files:")

    print(
        f"  ✓ {MOVIES_FILE}"
    )

    print(
        f"  ✓ {VECTORIZER_FILE}"
    )

    print(
        f"  ✓ {TFIDF_MATRIX_FILE}"
    )

    print(
        f"  ✓ {NEIGHBORS_FILE}"
    )

    print("\nB3 model construction completed.")

    print(
        "\nNext step: "
        "B3 model verification"
    )

    print("=" * 65)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()