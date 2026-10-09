from pathlib import Path

import pandas as pd


# ============================================================
# Configuration
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[2]

DATASET_PATH = (
    BASE_DIR
    / "data"
    / "raw"
    / "indian movies.csv"
)


# ============================================================
# Load Dataset
# ============================================================

print("=" * 70)
print("INDIAN MOVIES DATASET INSPECTION")
print("=" * 70)

print(f"\nDataset path:")
print(DATASET_PATH)

if not DATASET_PATH.exists():
    raise FileNotFoundError(
        f"Dataset not found: {DATASET_PATH}"
    )

df = pd.read_csv(
    DATASET_PATH,
    low_memory=False
)


# ============================================================
# Basic Information
# ============================================================

print("\n" + "=" * 70)
print("1. DATASET SHAPE")
print("=" * 70)

print(f"Rows    : {df.shape[0]:,}")
print(f"Columns : {df.shape[1]}")


# ============================================================
# Columns
# ============================================================

print("\n" + "=" * 70)
print("2. COLUMNS")
print("=" * 70)

for column in df.columns:
    print(f"- {column}")


# ============================================================
# Data Types
# ============================================================

print("\n" + "=" * 70)
print("3. DATA TYPES")
print("=" * 70)

print(df.dtypes)


# ============================================================
# Missing Values
# ============================================================

print("\n" + "=" * 70)
print("4. MISSING VALUES")
print("=" * 70)

missing = df.isna().sum()

for column, count in missing.items():
    percentage = (count / len(df)) * 100

    print(
        f"{column:<20} "
        f"{count:>7,} "
        f"({percentage:>6.2f}%)"
    )


# ============================================================
# Complete Duplicate Rows
# ============================================================

print("\n" + "=" * 70)
print("5. DUPLICATE ROWS")
print("=" * 70)

print(
    "Complete duplicate rows:",
    df.duplicated().sum()
)


# ============================================================
# Duplicate Movie Titles
# ============================================================

print("\n" + "=" * 70)
print("6. DUPLICATE MOVIE TITLES")
print("=" * 70)

normalized_titles = (
    df["Movie Name"]
    .astype(str)
    .str.strip()
    .str.casefold()
)

print(
    "Unique movie titles:",
    normalized_titles.nunique()
)

print(
    "Rows with duplicated titles:",
    normalized_titles.duplicated(keep=False).sum()
)


# ============================================================
# Languages
# ============================================================

print("\n" + "=" * 70)
print("7. LANGUAGES")
print("=" * 70)

print(
    df["Language"]
    .value_counts(dropna=False)
    .head(30)
)


# ============================================================
# Genres
# ============================================================

print("\n" + "=" * 70)
print("8. GENRES")
print("=" * 70)

print(
    df["Genre"]
    .value_counts(dropna=False)
    .head(30)
)


# ============================================================
# Years
# ============================================================

print("\n" + "=" * 70)
print("9. YEAR VALUES")
print("=" * 70)

print(
    df["Year"]
    .value_counts(dropna=False)
    .head(30)
)


# ============================================================
# Ratings
# ============================================================

print("\n" + "=" * 70)
print("10. RATINGS")
print("=" * 70)

print(
    df["Rating(10)"]
    .value_counts(dropna=False)
    .head(30)
)


# ============================================================
# Votes
# ============================================================

print("\n" + "=" * 70)
print("11. VOTES")
print("=" * 70)

print(
    df["Votes"]
    .value_counts(dropna=False)
    .head(30)
)


# ============================================================
# Duration
# ============================================================

print("\n" + "=" * 70)
print("12. DURATION")
print("=" * 70)

print(
    df["Timing(min)"]
    .value_counts(dropna=False)
    .head(30)
)


# ============================================================
# Sample Records
# ============================================================

print("\n" + "=" * 70)
print("13. SAMPLE RECORDS")
print("=" * 70)

print(
    df.head(10).to_string(index=False)
)


# ============================================================
# Final
# ============================================================

print("\n" + "=" * 70)
print("INSPECTION COMPLETE")
print("=" * 70)