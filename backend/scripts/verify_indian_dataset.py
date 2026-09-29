import os
import pandas as pd


# ============================================================
# PATH
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

PROCESSED_FILE = os.path.join(
    BASE_DIR,
    "..",
    "data",
    "processed",
    "indian_movies_clean.csv"
)


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 65)
    print("INDIAN MOVIE DATASET VERIFICATION")
    print("=" * 65)

    # --------------------------------------------------------
    # Check file
    # --------------------------------------------------------

    if not os.path.exists(PROCESSED_FILE):
        print("\nERROR: Processed dataset not found.")
        print(PROCESSED_FILE)
        return

    print("\nProcessed file found:")
    print(PROCESSED_FILE)

    # --------------------------------------------------------
    # Load
    # --------------------------------------------------------

    df = pd.read_csv(
        PROCESSED_FILE,
        low_memory=False
    )

    print("\nDataset loaded successfully.")

    # --------------------------------------------------------
    # Basic information
    # --------------------------------------------------------

    print("\n" + "-" * 65)
    print("BASIC INFORMATION")
    print("-" * 65)

    print(f"Rows:    {len(df):,}")
    print(f"Columns: {len(df.columns)}")

    print("\nColumns:")

    for column in df.columns:
        print(f"  ✓ {column}")

    # --------------------------------------------------------
    # Required columns
    # --------------------------------------------------------

    required_columns = [
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

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    print("\nRequired column check:")

    if missing_columns:
        print("  ❌ Missing columns:")
        for column in missing_columns:
            print(f"     - {column}")
    else:
        print("  ✓ All required columns are present")

    # --------------------------------------------------------
    # Empty titles
    # --------------------------------------------------------

    empty_titles = (
        df["title"]
        .fillna("")
        .astype(str)
        .str.strip()
        .eq("")
        .sum()
    )

    print("\nTitle check:")

    if empty_titles == 0:
        print("  ✓ No empty movie titles")
    else:
        print(f"  ❌ Empty titles: {empty_titles:,}")

    # --------------------------------------------------------
    # Empty languages
    # --------------------------------------------------------

    empty_languages = (
        df["language"]
        .fillna("")
        .astype(str)
        .str.strip()
        .eq("")
        .sum()
    )

    print("\nLanguage check:")

    if empty_languages == 0:
        print("  ✓ No empty languages")
    else:
        print(f"  ⚠ Empty languages: {empty_languages:,}")

    # --------------------------------------------------------
    # Duplicate IDs
    # --------------------------------------------------------

    duplicate_ids = df["id"].duplicated().sum()

    print("\nID check:")
    print(f"  Duplicate ID rows: {duplicate_ids:,}")

    # --------------------------------------------------------
    # Duplicate normalized titles
    # --------------------------------------------------------

    duplicate_titles = (
        df["title_normalized"]
        .duplicated()
        .sum()
    )

    print("\nTitle duplication check:")
    print(
        f"  Duplicate normalized-title rows: "
        f"{duplicate_titles:,}"
    )

    # --------------------------------------------------------
    # Languages
    # --------------------------------------------------------

    print("\n" + "-" * 65)
    print("LANGUAGE DISTRIBUTION")
    print("-" * 65)

    language_counts = (
        df["language_original"]
        .value_counts()
    )

    for language, count in language_counts.items():
        print(f"  {language:<15} {count:>7,}")

    # --------------------------------------------------------
    # Numeric fields
    # --------------------------------------------------------

    print("\n" + "-" * 65)
    print("NUMERIC FIELD CHECK")
    print("-" * 65)

    numeric_columns = [
        "year",
        "duration_min",
        "rating",
        "votes"
    ]

    for column in numeric_columns:

        print(f"\n{column}:")

        print(
            f"  Data type: {df[column].dtype}"
        )

        print(
            f"  Missing:   {df[column].isna().sum():,}"
        )

        non_null = df[column].dropna()

        if len(non_null) > 0:

            print(
                f"  Minimum:   {non_null.min()}"
            )

            print(
                f"  Maximum:   {non_null.max()}"
            )

    # --------------------------------------------------------
    # Rating validation
    # --------------------------------------------------------

    invalid_ratings = df[
        (df["rating"].notna()) &
        (
            (df["rating"] < 0) |
            (df["rating"] > 10)
        )
    ]

    print("\nRating validation:")

    if len(invalid_ratings) == 0:
        print("  ✓ All ratings are between 0 and 10")
    else:
        print(
            f"  ⚠ Invalid ratings: "
            f"{len(invalid_ratings):,}"
        )

    # --------------------------------------------------------
    # Year validation
    # --------------------------------------------------------

    invalid_years = df[
        (df["year"].notna()) &
        (
            (df["year"] < 1800) |
            (df["year"] > 2100)
        )
    ]

    print("\nYear validation:")

    if len(invalid_years) == 0:
        print("  ✓ No obviously invalid years")
    else:
        print(
            f"  ⚠ Invalid years: "
            f"{len(invalid_years):,}"
        )

    # --------------------------------------------------------
    # Sample records
    # --------------------------------------------------------

    print("\n" + "-" * 65)
    print("SAMPLE CLEANED RECORDS")
    print("-" * 65)

    sample_columns = [
        "id",
        "title",
        "year",
        "rating",
        "votes",
        "genre",
        "language"
    ]

    print(
        df[sample_columns]
        .head(10)
        .to_string(index=False)
    )

    # --------------------------------------------------------
    # Final result
    # --------------------------------------------------------

    print("\n" + "=" * 65)
    print("VERIFICATION COMPLETE")
    print("=" * 65)

    print("\nDataset is ready for model building if:")
    print("  ✓ Required columns exist")
    print("  ✓ Titles are present")
    print("  ✓ Languages are preserved")
    print("  ✓ Numeric fields are parsed")
    print("  ✓ Ratings are valid")
    print("  ✓ Years are reasonable")

    print("\nNext step: B3 - Build Recommendation Model")


if __name__ == "__main__":
    main()