import os
from dotenv import load_dotenv
import google.generativeai as genai
import requests
from flask import Flask, redirect, render_template, request,jsonify
import pickle
import sqlite3
from database import (
    add_favorite,
    get_favorites,
    delete_favorite
)
from database import delete_favorite, get_favorites

app = Flask(__name__)
load_dotenv()

genai.configure(
    api_key=os.getenv("GEMINI_API_KEY")
)

gemini_model = genai.GenerativeModel(
    "gemini-2.5-flash"
)

OMDB_API_KEY = "54fab1b3"

# Load trained model files
movies = pickle.load(open('model/movies.pkl', 'rb'))
similarity = pickle.load(open('model/similarity.pkl', 'rb'))


def fetch_movie_details(movie_name):

    url = f"https://www.omdbapi.com/?t={movie_name}&apikey={OMDB_API_KEY}"

    response = requests.get(url)

    data = response.json()

    return {
        "title": data.get("Title", movie_name),
        "poster": data.get("Poster", "https://via.placeholder.com/300x450"),
        "year": data.get("Year", "N/A"),
        "rating": data.get("imdbRating", "N/A")
    }

def search_movie(movie_name):

    url = f"https://www.omdbapi.com/?t={movie_name}&plot=full&apikey={OMDB_API_KEY}"

    response = requests.get(url)

    data = response.json()

    if data.get("Response") == "False":
        return None
    return {
        "title": data.get("Title"),
        "poster": data.get("Poster"),
        "year": data.get("Year"),
        "rating": data.get("imdbRating"),
        "genre": data.get("Genre"),
        "runtime": data.get("Runtime"),
        "director": data.get("Director"),
        "plot": data.get("Plot"),
        "insight": generate_movie_insight(
            data.get("Title"),
            data.get("Genre"),
            data.get("Plot")
        )
}
    



def generate_explanation(base_movie, recommended_movie):

    try:

        prompt = f"""
        Explain in one short sentence why
        '{recommended_movie}'
        is recommended for someone who likes
        '{base_movie}'.

        Keep it under 20 words.
        """

        response = gemini_model.generate_content(
            prompt
        )

        return response.text.strip()

    except Exception:

        return "Similar themes and storytelling style."

def generate_movie_insight(
    title,
    genre,
    plot
):

    try:

        prompt = f"""
        Movie: {title}

        Genre: {genre}

        Plot:
        {plot}

        Give a short AI insight
        in 1 sentence.

        Keep it under 25 words.
        """

        response = (
            gemini_model.generate_content(
                prompt
            )
        )

        return response.text.strip()

    except:

        return (
            "Interesting movie with strong storytelling and audience appeal."
        )
    
    
def recommend(movie):

    movie = movie.strip()

    matches = movies[
        movies['title'].str.lower()
        == movie.lower()
    ]

    if matches.empty:
        return []

    movie_index = matches.index[0]

    distances = similarity[movie_index]

    movies_list = sorted(
        list(enumerate(distances)),
        reverse=True,
        key=lambda x: x[1]
    )[1:6]

    recommendations = []

    for i in movies_list:

        movie_title = movies.iloc[i[0]].title

        movie_data = fetch_movie_details(
            movie_title
        )

        movie_data["explanation"] = generate_explanation(
            movie,
            movie_title
        )

        recommendations.append(
            movie_data
        )

        movie_match = movies[
            movies['title'].str.lower() == movie.lower()
        ]

        if movie_match.empty:
            return []

        movie_index = movie_match.index[0]
    return recommendations

@app.route('/test')
def test():

    return jsonify(
        movies['title']
        .head(50)
        .tolist()
    )

@app.route('/', methods=['GET', 'POST'])
def home():

    recommendations = []
    movie_details = None

    if request.method == 'POST':

        action = request.form.get('action')
        movie = request.form['movie']

        if action == 'recommend':
           recommendations = recommend(movie)  

        elif action == 'search':
            movie_details = search_movie(movie)

            if movie_details:
               recommendations = recommend(movie) 

    favorite_count = len(get_favorites())
    return render_template(
        'index.html',
        recommendations=recommendations,
        movie_details=movie_details,
        favorite_count=favorite_count
    )
@app.route('/autocomplete')
def autocomplete():

    query = request.args.get('query', '').lower()

    if not query:
        return jsonify([])

    titles = movies['title'].tolist()

    exact_matches = [
        title for title in titles
        if title.lower().startswith(query)
    ]

    matches = exact_matches[:8]

    return jsonify(matches)

@app.route('/movie/<movie_name>')
def movie_details(movie_name):

    movie_details = search_movie(movie_name)

    return render_template(
        'movie_details.html',
        movie_details=movie_details
    )

@app.route(
    '/add_favorite',
    methods=['POST']
)
def add_favorite_route():

    title = request.form['title']
    poster = request.form['poster']
    rating = request.form['rating']
    year = request.form['year']

    add_favorite(
        title,
        poster,
        rating,
        year
    )

    return redirect('/')

@app.route('/favorites')
def favorites():

    favorites_data = get_favorites()

    favorite_count = len(favorites_data)

    return render_template(
        'favorites.html',
        favorites=favorites_data,
        favorite_count=favorite_count
    )

@app.route(
    '/delete_favorite/<int:id>'
)
def remove_favorite(id):

    delete_favorite(id)

    return redirect(
        '/favorites'
    )

@app.route(
    '/toggle_favorite',
    methods=['POST']
)
def toggle_favorite():

    data = request.get_json()

    add_favorite(
        data['title'],
        data['poster'],
        data['rating'],
        data['year']
    )

    return jsonify({
        "success": True
    })


if __name__ == '__main__':
    app.run(debug=True)

@app.route(
    '/toggle_favorite',
    methods=['POST']
)
def toggle_favorite():

    data = request.get_json()

    add_favorite(
        data["title"],
        data["poster"],
        data["rating"],
        data["year"]
    )

    return jsonify({
        "success": True
    })

if not recommendations:

    recommendations = [
        fetch_movie_details("RRR"),
        fetch_movie_details("Pushpa"),
        fetch_movie_details("Kalki 2898 AD"),
        fetch_movie_details("Salaar")
    ]