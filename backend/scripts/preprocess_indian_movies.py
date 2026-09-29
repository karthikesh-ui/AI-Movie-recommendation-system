import os
import re
import unicodedata

import pandas as pd


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

RAW_FILE = os.path.join(
    BASE_DIR,
    "..",
    "data",
    "raw",
    "indian movies.csv"
)

PROCESSED_DIR = os.path.join(
    BASE_DIR,
    "..",
    "data",
    "processed"
)

OUTPUT_FILE = os.path.join(
    PROCESSED_DIR,
    "indian_movies_clean.csv"
)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def clean_text(value):
    """
    Clean text while preserving Unicode characters.
    """

    if pd.isna(value):
        return ""

    value = str(value).strip()

    if value == "-" or value == "":
        return ""

    value = unicodedata.normalize(
        "NFKC",
        value
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


def normalize_title(value):
    """
    Create a normalized version of the movie title
    for searching and recommendation processing.
    """

    value = clean_text(value)

    if not value:
        return ""

    return value.casefold()


def parse_year(value):
    """
    Extract the first valid four-digit year.

    Examples:
        2014–2019  -> 2014
        2020 Video -> 2020
        I 2019     -> 2019
        2018–      -> 2018
    """

    value = clean_text(value)

    if not value:
        return pd.NA

    match = re.search(
        r"(18|19|20)\d{2}",
        value
    )

    if match:
        return int(match.group())

    return pd.NA


def parse_duration(value):
    """
    Convert duration values to integer minutes.

    Examples:
        134 min -> 134
        120     -> 120
        -       -> missing
    """

    value = clean_text(value)

    if not value:
        return pd.NA

    match = re.search(
        r"\d+",
        value
    )

    if match:
        return int(match.group())

    return pd.NA


def parse_rating(value):
    """
    Convert movie rating to float.
    """

    value = clean_text(value)

    if not value:
        return pd.NA

    try:
        return float(value)

    except ValueError:
        return pd.NA


def parse_votes(value):
    """
    Convert vote counts to integers.

    Examples:
        26,885 -> 26885
        1,892  -> 1892
    """

    value = clean_text(value)

    if not value:
        return pd.NA

    value = value.replace(
        ",",
        ""
    )

    try:
        return int(value)

    except ValueError:
        return pd.NA


def combine_languages(series):
    """
    Combine multiple language values into one comma-separated
    string without duplicates.
    """

    languages = []

    for value in series:

        value = clean_text(value)

        if value and value not in languages:
            languages.append(value)

    return ", ".join(
        sorted(languages)
    )


def combine_normalized_languages(series):
    """
    Combine normalized language values.
    """

    languages = []

    for value in series:

        value = clean_text(value).casefold()

        if value and value not in languages:
            languages.append(value)

    return ", ".join(
        sorted(languages)
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("INDIAN MOVIE DATASET PREPROCESSING")
    print("=" * 60)

    # --------------------------------------------------------
    # Check input file
    # --------------------------------------------------------

    if not os.path.exists(RAW_FILE):

        print("\nERROR: Dataset not found:")
        print(RAW_FILE)

        return

    print("\nInput file:")
    print(RAW_FILE)

    # --------------------------------------------------------
    # Create processed directory
    # --------------------------------------------------------

    os.makedirs(
        PROCESSED_DIR,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Load dataset
    # --------------------------------------------------------

    print("\nLoading dataset...")

    df = pd.read_csv(
        RAW_FILE,
        dtype=str,
        low_memory=False
    )

    raw_rows = len(df)

    print(
        f"Raw rows: {raw_rows:,}"
    )

    print(
        f"Raw columns: {len(df.columns)}"
    )

    # --------------------------------------------------------
    # Validate columns
    # --------------------------------------------------------

    required_columns = [
        "ID",
        "Movie Name",
        "Year",
        "Timing(min)",
        "Rating(10)",
        "Votes",
        "Genre",
        "Language"
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:

        print(
            "\nERROR: Missing required columns:"
        )

        for column in missing_columns:
            print(
                f"  - {column}"
            )

        return

    # --------------------------------------------------------
    # Preserve original information
    # --------------------------------------------------------

    df["title_original"] = (
        df["Movie Name"]
        .apply(clean_text)
    )

    df["year_raw"] = (
        df["Year"]
        .apply(clean_text)
    )

    df["genre_original"] = (
        df["Genre"]
        .apply(clean_text)
    )

    df["language_original"] = (
        df["Language"]
        .apply(clean_text)
    )

    # --------------------------------------------------------
    # Clean IDs and titles
    # --------------------------------------------------------

    df["id"] = (
        df["ID"]
        .apply(clean_text)
    )

    df["title"] = (
        df["Movie Name"]
        .apply(clean_text)
    )

    df["title_normalized"] = (
        df["Movie Name"]
        .apply(normalize_title)
    )

    # --------------------------------------------------------
    # Clean language
    # --------------------------------------------------------

    df["language"] = (
        df["Language"]
        .apply(
            lambda value:
            clean_text(value).casefold()
        )
    )

    # --------------------------------------------------------
    # Clean genre
    # --------------------------------------------------------

    df["genre"] = (
        df["Genre"]
        .apply(
            lambda value:
            clean_text(value).casefold()
        )
    )

    # --------------------------------------------------------
    # Parse numerical fields
    # --------------------------------------------------------

    print("\nParsing year...")

    df["year"] = (
        df["Year"]
        .apply(parse_year)
    )

    print("Parsing duration...")

    df["duration_min"] = (
        df["Timing(min)"]
        .apply(parse_duration)
    )

    print("Parsing rating...")

    df["rating"] = (
        df["Rating(10)"]
        .apply(parse_rating)
    )

    print("Parsing votes...")

    df["votes"] = (
        df["Votes"]
        .apply(parse_votes)
    )

    # --------------------------------------------------------
    # Remove records without movie titles
    # --------------------------------------------------------

    before_title_filter = len(df)

    df = df[
        df["title"] != ""
    ].copy()

    removed_title_rows = (
        before_title_filter - len(df)
    )

    # --------------------------------------------------------
    # Remove exact duplicate records
    # --------------------------------------------------------

    before_exact_duplicates = len(df)

    duplicate_columns = [
        "id",
        "title",
        "year",
        "language",
        "genre",
        "rating",
        "votes",
        "duration_min"
    ]

    df = df.drop_duplicates(
        subset=duplicate_columns
    ).copy()

    removed_exact_duplicates = (
        before_exact_duplicates - len(df)
    )

    # --------------------------------------------------------
    # Separate records with and without IMDb IDs
    # --------------------------------------------------------

    with_id = df[
        df["id"] != ""
    ].copy()

    without_id = df[
        df["id"] == ""
    ].copy()

    print("\nHandling duplicate IMDb IDs...")

    print(
        f"Records with IMDb ID: "
        f"{len(with_id):,}"
    )

    print(
        f"Records without IMDb ID: "
        f"{len(without_id):,}"
    )

    # --------------------------------------------------------
    # Combine repeated IMDb IDs
    #
    # Same IMDb ID = same movie.
    #
    # If the movie appears under multiple Indian languages,
    # preserve all languages in a single record.
    # --------------------------------------------------------

    if not with_id.empty:

        with_id = (
            with_id
            .groupby(
                "id",
                as_index=False
            )
            .agg(
                {
                    "title": "first",
                    "title_normalized": "first",
                    "year": "first",
                    "year_raw": "first",
                    "duration_min": "first",
                    "rating": "first",
                    "votes": "first",
                    "genre": "first",
                    "genre_original": "first",
                    "language": combine_normalized_languages,
                    "language_original": combine_languages,
                    "title_original": "first"
                }
            )
        )

    # --------------------------------------------------------
    # Handle records without IMDb IDs
    #
    # Keep them because they may still be valid movies.
    #
    # Remove only duplicate combinations of:
    # title + year + language
    # --------------------------------------------------------

    if not without_id.empty:

        without_id = without_id.drop_duplicates(
            subset=[
                "title_normalized",
                "year",
                "language"
            ]
        ).copy()

    # --------------------------------------------------------
    # Combine both groups
    # --------------------------------------------------------

    df = pd.concat(
        [
            with_id,
            without_id
        ],
        ignore_index=True
    )

    # --------------------------------------------------------
    # Final columns
    # --------------------------------------------------------

    final_columns = [
        "id",
        "title",
        "title_normalized",
        "year",
        "year_raw",
        "duration_min",
        "rating",
        "votes",
        "genre",
        "genre_original",
        "language",
        "language_original",
        "title_original"
    ]

    df = df[
        final_columns
    ]

    # --------------------------------------------------------
    # Sort
    # --------------------------------------------------------

    df = df.sort_values(
        by=[
            "title_normalized",
            "year"
        ],
        na_position="last"
    ).reset_index(
        drop=True
    )

    # --------------------------------------------------------
    # Save processed dataset
    # --------------------------------------------------------

    df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # FINAL REPORT
    # ========================================================

    print("\n" + "=" * 60)
    print("PREPROCESSING COMPLETE")
    print("=" * 60)

    print(
        f"\nRaw rows:                 "
        f"{raw_rows:,}"
    )

    print(
        f"Rows without title:      "
        f"{removed_title_rows:,}"
    )

    print(
        f"Exact duplicates removed: "
        f"{removed_exact_duplicates:,}"
    )

    print(
        f"Final rows:               "
        f"{len(df):,}"
    )

    print("\nMissing values:")

    print(
        f"  Year:         "
        f"{df['year'].isna().sum():,}"
    )

    print(
        f"  Duration:     "
        f"{df['duration_min'].isna().sum():,}"
    )

    print(
        f"  Rating:       "
        f"{df['rating'].isna().sum():,}"
    )

    print(
        f"  Votes:        "
        f"{df['votes'].isna().sum():,}"
    )

    print(
        f"  Genre:        "
        f"{(df['genre'] == '').sum():,}"
    )

    print(
        f"  Language:     "
        f"{(df['language'] == '').sum():,}"
    )

    # --------------------------------------------------------
    # Language report
    # --------------------------------------------------------

    print("\nLanguages preserved:")

    language_counts = (
        df["language_original"]
        .replace("", pd.NA)
        .dropna()
    )

    # Because multiple languages can now exist in one cell,
    # split them for a more useful count.
    language_counter = {}

    for value in language_counts:

        for language in str(value).split(","):

            language = language.strip()

            if not language:
                continue

            language_counter[language] = (
                language_counter.get(
                    language,
                    0
                ) + 1
            )

    for language, count in sorted(
        language_counter.items(),
        key=lambda item: item[1],
        reverse=True
    ):

        print(
            f"  {language:<15} {count:>7,}"
        )

    # --------------------------------------------------------
    # Output
    # --------------------------------------------------------

    print("\nOutput file:")
    print(OUTPUT_FILE)

    print("\n" + "=" * 60)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()