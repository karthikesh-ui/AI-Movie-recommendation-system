"use strict";

/* See movie-search.js for the API configuration contract. */
const API_BASE =
    window.MOVIEAI_API_BASE ||
    (window.location.port === "5000"
        ? "/api"
        : "http://127.0.0.1:5000/api");


const form =
    document.getElementById(
        "recommendationForm"
    );

const input =
    document.getElementById(
        "recommendationInput"
    );

const button =
    document.getElementById(
        "recommendationButton"
    );

const charCounter =
    document.getElementById(
        "charCounter"
    );

const clearBtn =
    document.getElementById(
        "clearInputBtn"
    );

const promptChips =
    document.querySelectorAll(
        ".prompt-chip"
    );

const resultsContainer =
    document.getElementById(
        "recommendationResults"
    );


/* Initialize chip clicks */
promptChips.forEach(chip => {
    chip.addEventListener("click", () => {
        const promptText = chip.getAttribute("data-prompt");
        if (promptText && input) {
            input.value = promptText;
            updateCharCount();
            input.focus();
            
            // Add pulse effect to button
            if (button) {
                button.classList.add("btn-pulse");
                setTimeout(() => button.classList.remove("btn-pulse"), 600);
            }
        }
    });
});

/* Char counter & clear button */
if (input) {
    input.addEventListener("input", updateCharCount);
}

if (clearBtn) {
    clearBtn.addEventListener("click", () => {
        if (input) {
            input.value = "";
            updateCharCount();
            input.focus();
        }
    });
}

function updateCharCount() {
    if (!input) return;
    const len = input.value.length;
    if (charCounter) {
        charCounter.textContent = `${len} / 500`;
    }
    if (clearBtn) {
        clearBtn.hidden = len === 0;
    }
}


if (form && input && button && resultsContainer) {
    form.addEventListener(
        "submit",
        handleRecommendationSubmit
    );
}


async function handleRecommendationSubmit(event) {

    event.preventDefault();

    const text =
        input.value.trim();

    if (!text) {

        renderError(
            "Please describe what kind of movie you want."
        );

        return;
    }

    button.disabled = true;

    button.textContent =
        "Finding movies...";

    renderLoading();

    try {

        const encoded =
            encodeURIComponent(text);

        const response =
            await fetch(
                `${API_BASE}/recommend-text?text=${encoded}`,
                {
                    headers: {
                        "Accept":
                            "application/json"
                    }
                }
            );

        const data =
            await response.json();


        if (!response.ok) {

            throw {
                status:
                    response.status,
                data
            };
        }


        if (
            !data.results ||
            !Array.isArray(data.results)
        ) {

            renderError(
                "No recommendation results were returned."
            );

            return;
        }


        if (
            data.results.length === 0
        ) {

            renderEmpty();

            return;
        }


        renderResults(data);

    } catch (error) {

        console.error(
            "Recommendation API error:",
            error
        );

        handleAPIError(error);

    } finally {

        button.disabled = false;

        button.textContent =
            "Find my movies →";
    }
}


function renderLoading() {

    resultsContainer.innerHTML = `
        <div class="recommendation-loading">
            <div class="recommendation-spinner"></div>
            <p>
                Understanding your request and finding movies...
            </p>
        </div>
    `;
}


function renderEmpty() {

    resultsContainer.innerHTML = `
        <div class="recommendation-empty">
            <h2>No matching movies found.</h2>
            <p>
                Try changing the language, mood, genre, or description.
            </p>
        </div>
    `;
}


function renderError(message) {

    resultsContainer.innerHTML = `
        <div class="recommendation-error">
            <h2>Something went wrong</h2>
            <p>${escapeHTML(message)}</p>
        </div>
    `;
}


function renderResults(data) {

    resultsContainer.innerHTML = "";


    const heading =
        document.createElement("div");

    heading.className =
        "recommendation-results-heading";


    heading.innerHTML = `
        <span>
            YOUR MOVIE PICKS
        </span>
        <h2>
            Movies for your mood
        </h2>
    `;


    resultsContainer.appendChild(
        heading
    );


    if (data.intent) {

        const intent =
            document.createElement("p");

        intent.className =
            "recommendation-intent";


        const parts = [];


        if (
            Array.isArray(
                data.intent.genres
            ) &&
            data.intent.genres.length
        ) {

            parts.push(
                data.intent.genres.join(", ")
            );
        }


        if (
            Array.isArray(
                data.intent.languages
            ) &&
            data.intent.languages.length
        ) {

            parts.push(
                data.intent.languages.join(", ")
            );
        }


        if (data.intent.mood) {

            parts.push(
                data.intent.mood.replace(
                    /_/g,
                    " "
                )
            );
        }


        if (data.intent.audience) {

            parts.push(
                data.intent.audience
            );
        }


        if (parts.length) {

            intent.textContent =
                `Matched: ${parts.join(" · ")}`;

            resultsContainer.appendChild(
                intent
            );
        }
    }


    const grid =
        document.createElement("div");

    grid.className =
        "recommendation-grid";


    data.results.forEach(
        movie => {

            grid.appendChild(
                createMovieCard(movie)
            );

        }
    );


    resultsContainer.appendChild(
        grid
    );
}


function createMovieCard(movie) {

    const card =
        document.createElement("article");

    card.className =
        "recommendation-movie-card";


    if (movie.poster) {

        const poster =
            document.createElement("img");

        poster.src =
            movie.poster;

        poster.alt =
            `${movie.title || "Movie"} poster`;

        poster.className =
            "recommendation-poster";

        poster.loading =
            "lazy";

        poster.onerror =
            () => {
                poster.style.display =
                    "none";
            };

        card.appendChild(
            poster
        );
    }


    const content =
        document.createElement("div");

    content.className =
        "recommendation-card-content";


    const title =
        document.createElement("h3");

    title.textContent =
        movie.title ||
        "Untitled movie";


    content.appendChild(
        title
    );


    const meta =
        document.createElement("p");

    meta.className =
        "recommendation-meta";


    const metaParts = [];


    if (movie.year) {
        metaParts.push(
            movie.year
        );
    }


    if (movie.rating) {
        metaParts.push(
            `★ ${movie.rating}`
        );
    }


    if (movie.runtime) {
        metaParts.push(
            movie.runtime
        );
    }


    meta.textContent =
        metaParts.join(" · ");


    content.appendChild(
        meta
    );


    if (movie.genre) {

        const genre =
            document.createElement("p");

        genre.className =
            "recommendation-genre";

        genre.textContent =
            movie.genre;

        content.appendChild(
            genre
        );
    }


    if (movie.explanation) {

        const explanation =
            document.createElement("p");

        explanation.className =
            "recommendation-explanation";

        explanation.textContent =
            movie.explanation;

        content.appendChild(
            explanation
        );
    }


    card.appendChild(
        content
    );


    return card;
}


function handleAPIError(error) {

    if (
        error &&
        error.status === 422
    ) {

        renderError(
            "That request contains a genre or language that is not available in the current movie dataset."
        );

        return;
    }


    if (
        error &&
        error.status === 503
    ) {

        renderError(
            "The recommendation service is temporarily unavailable. Please try again shortly."
        );

        return;
    }


    renderError(
        "Unable to connect to the recommendation service. Make sure the Flask backend is running."
    );
}


function escapeHTML(value) {

    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}