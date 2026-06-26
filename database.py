import sqlite3

conn = sqlite3.connect(
    "movies.db"
)

cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS favorites (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    movie_title TEXT UNIQUE,

    poster TEXT,

    rating TEXT,

    year TEXT

)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS history (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    movie_title TEXT,

    searched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

)
""")

conn.commit()

conn.close()

print("Database Created Successfully")
def add_favorite(
    title,
    poster,
    rating,
    year
):

    conn = sqlite3.connect(
        "movies.db"
    )

    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT OR IGNORE INTO favorites
        (
            movie_title,
            poster,
            rating,
            year
        )
        VALUES
        (?, ?, ?, ?)
        """,
        (
            title,
            poster,
            rating,
            year
        )
    )

    conn.commit()

    conn.close()

def add_favorite(
    title,
    poster,
    rating,
    year
):

    conn = sqlite3.connect(
        "movies.db"
    )

    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT OR IGNORE INTO favorites
        (
            movie_title,
            poster,
            rating,
            year
        )
        VALUES
        (?, ?, ?, ?)
        """,
        (
            title,
            poster,
            rating,
            year
        )
    )

    conn.commit()

    conn.close()

def get_favorites():

    conn = sqlite3.connect(
        "movies.db"
    )

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM favorites
        ORDER BY id DESC
        """
    )

    data = cursor.fetchall()

    conn.close()

    return data


def delete_favorite(movie_id):

    conn = sqlite3.connect(
        "movies.db"
    )

    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM favorites
        WHERE id = ?
        """,
        (movie_id,)
    )

    conn.commit()

    conn.close()