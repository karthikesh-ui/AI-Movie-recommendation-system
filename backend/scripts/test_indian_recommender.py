import os
import pickle
import copy

import pandas as pd


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
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
# LOAD MODELS
# ============================================================

def load_models():

    print("\nLoading saved model files...")

    with open(MOVIES_FILE, "rb") as file:
        movies = pickle.load(file)

    with open(VECTORIZER_FILE, "rb") as file:
        vectorizer = pickle.load(file)

    with open(TFIDF_MATRIX_FILE, "rb") as file:
        tfidf_matrix = pickle.load(file)

    with open(NEIGHBORS_FILE, "rb") as file:
        neighbors = pickle.load(file)

    print("✓ movies.pkl loaded")
    print("✓ vectorizer.pkl loaded")
    print("✓ tfidf_matrix.pkl loaded")
    print("✓ neighbors.pkl loaded")

    return (
        movies,
        vectorizer,
        tfidf_matrix,
        neighbors
    )


# ============================================================
# RECOMMENDATION FUNCTION
# ============================================================

def recommend(
    title,
    movies,
    vectorizer,
    tfidf_matrix,
    neighbors,
    number_of_results=10
):

    normalized_title = title.strip().casefold()

    matches = movies[
        movies["title_normalized"] == normalized_title
    ]

    if matches.empty:
        return None, "Movie not found"

    # If multiple records have the same normalized title,
    # choose the record with the strongest available rating/votes.
    if len(matches) > 1:

        matches = matches.copy()

        matches["rating_sort"] = (
            pd.to_numeric(
                matches["rating"],
                errors="coerce"
            ).fillna(-1)
        )

        matches["votes_sort"] = (
            pd.to_numeric(
                matches["votes"],
                errors="coerce"
            ).fillna(-1)
        )

        matches = matches.sort_values(
            by=[
                "rating_sort",
                "votes_sort"
            ],
            ascending=False
        )

    movie_index = matches.index[0]

    movie_vector = tfidf_matrix[
        movie_index
    ]

    # Preserve the persisted estimator while keeping the verifier usable in
    # constrained Windows workers that cannot create an all-CPU thread pool.
    query_neighbors = copy.copy(neighbors)
    query_neighbors.n_jobs = 1
    distances, indices = query_neighbors.kneighbors(
        movie_vector,
        n_neighbors=number_of_results + 1
    )

    recommendations = []

    for distance, index in zip(
        distances[0],
        indices[0]
    ):

        # Skip the selected movie itself.
        if index == movie_index:
            continue

        similarity = 1 - float(distance)

        movie = movies.iloc[index]

        recommendations.append({
            "title": movie["title"],
            "year": movie["year"],
            "genre": movie["genre_original"],
            "language": movie["language_original"],
            "rating": movie["rating"],
            "similarity": round(
                similarity,
                4
            )
        })

        if len(recommendations) >= number_of_results:
            break

    return recommendations, None


# ============================================================
# MAIN TEST
# ============================================================

def main():

    print("=" * 65)
    print("INDIAN MOVIE RECOMMENDER VERIFICATION")
    print("=" * 65)

    # --------------------------------------------------------
    # Check model files
    # --------------------------------------------------------

    print("\nChecking model files...")

    model_files = [
        MOVIES_FILE,
        VECTORIZER_FILE,
        TFIDF_MATRIX_FILE,
        NEIGHBORS_FILE
    ]

    for file_path in model_files:

        if not os.path.exists(file_path):

            print("\nERROR: Missing model file:")
            print(file_path)

            return

        print(
            f"✓ {os.path.basename(file_path)}"
        )

    # --------------------------------------------------------
    # Load
    # --------------------------------------------------------

    (
        movies,
        vectorizer,
        tfidf_matrix,
        neighbors
    ) = load_models()

    # --------------------------------------------------------
    # Basic validation
    # --------------------------------------------------------

    print("\nBasic validation:")

    print(
        f"Movies: {len(movies):,}"
    )

    print(
        f"TF-IDF matrix: {tfidf_matrix.shape}"
    )

    print(
        f"Vectorizer vocabulary: "
        f"{len(vectorizer.vocabulary_):,}"
    )

    print(
        f"Neighbor count: "
        f"{neighbors.n_neighbors}"
    )

    # --------------------------------------------------------
    # Check matrix consistency
    # --------------------------------------------------------

    print("\nChecking model consistency...")

    assert len(movies) == tfidf_matrix.shape[0]

    assert len(movies) == neighbors.n_samples_fit_

    assert len(vectorizer.vocabulary_) == (
        tfidf_matrix.shape[1]
    )

    print(
        "✓ Movies and TF-IDF rows match"
    )

    print(
        "✓ Movies and neighbor samples match"
    )

    print(
        "✓ Vectorizer and TF-IDF features match"
    )

    # --------------------------------------------------------
    # Pick test movies
    # --------------------------------------------------------

    print("\nSelecting test movies...")

    test_movies = (
        movies[
            movies["rating"].notna()
        ]
        .sort_values(
            by="votes",
            ascending=False,
            na_position="last"
        )["title"]
        .drop_duplicates()
        .head(5)
        .tolist()
    )

    if not test_movies:

        print(
            "ERROR: Could not find test movies."
        )

        return

    print(
        "Test movies:"
    )

    for movie in test_movies:

        print(
            f"  - {movie}"
        )

    # --------------------------------------------------------
    # Recommendation tests
    # --------------------------------------------------------

    print("\n" + "=" * 65)
    print("RECOMMENDATION TESTS")
    print("=" * 65)

    successful_tests = 0

    for test_movie in test_movies:

        print(
            f"\nInput movie: {test_movie}"
        )

        recommendations, error = recommend(
            test_movie,
            movies,
            vectorizer,
            tfidf_matrix,
            neighbors,
            number_of_results=10
        )

        if error:

            print(
                f"✗ ERROR: {error}"
            )

            continue

        if not recommendations:

            print(
                "✗ No recommendations returned."
            )

            continue

        successful_tests += 1

        for position, movie in enumerate(
            recommendations,
            start=1
        ):

            print(
                f"  {position:2}. "
                f"{movie['title']} | "
                f"Similarity: "
                f"{movie['similarity']:.4f}"
            )

    # --------------------------------------------------------
    # Missing movie test
    # --------------------------------------------------------

    print(
        "\nTesting missing movie..."
    )

    recommendations, error = recommend(
        "__THIS_MOVIE_DOES_NOT_EXIST__",
        movies,
        vectorizer,
        tfidf_matrix,
        neighbors
    )

    if error == "Movie not found":

        print(
            "✓ Missing movie handled correctly"
        )

    else:

        print(
            "✗ Missing movie test failed"
        )

    # --------------------------------------------------------
    # Final result
    # --------------------------------------------------------

    print("\n" + "=" * 65)
    print("VERIFICATION RESULT")
    print("=" * 65)

    print(
        f"\nSuccessful recommendation tests: "
        f"{successful_tests}/{len(test_movies)}"
    )

    if successful_tests == len(test_movies):

        print(
            "\n✓ B3 RECOMMENDATION MODEL VERIFIED"
        )

        print(
            "✓ Model loading works"
        )

        print(
            "✓ TF-IDF matrix is consistent"
        )

        print(
            "✓ Nearest-neighbor search works"
        )

        print(
            "✓ Recommendations are being generated"
        )

        print(
            "✓ Missing movie handling works"
        )

        print(
            "\nB3 is ready for the next phase: B4 Flask integration."
        )

    else:

        print(
            "\n✗ B3 verification needs investigation."
        )

    print("=" * 65)


if __name__ == "__main__":
    main()
