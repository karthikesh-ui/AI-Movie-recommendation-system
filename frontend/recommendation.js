"use strict";

/* See movie-search.js for the API configuration contract. */
const API_BASE =
    window.MOVIEAI_API_BASE ||
    (window.location.protocol === "file:" ||
    ["5500", "5501"].includes(window.location.port)
        ? "http://127.0.0.1:5000/api"
        : `${window.location.origin}/api`);


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


const LATEST_DISCOVERY_PATTERN =
    /\b(latest|new|newest|recent|recently released|upcoming)\b/i;

const SIMILARITY_PATTERN =
    /\b(?:recommend(?:\s+(?:me|movies?))?\s*(?:similar to|like)|movies?\s+like)\s+(.+)/i;

const NATURAL_LANGUAGE_WORDS =
    /\b(i|want|show|suggest|find|movie|movies|telugu|hindi|tamil|malayalam|kannada|action|comedy|romance|thriller|drama|family|mood|feel)\b/i;


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

        const endpoint =
            recommendationEndpoint(text);

        console.log("[MovieAI] recommendation endpoint:", endpoint);

        const response =
            await fetch(
                endpoint,
                {
                    headers: {
                        "Accept":
                            "application/json"
                    }
                }
            );

        const data =
            await response.json();

        console.log("[MovieAI] response:", data);
        console.log("[MovieAI] result count:", data.results?.length);


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


function recommendationEndpoint(text) {

    const encodedText =
        encodeURIComponent(text);

    if (LATEST_DISCOVERY_PATTERN.test(text)) {
        return `${API_BASE}/recommend-hybrid?text=${encodedText}`;
    }

    const similarityMatch =
        text.match(SIMILARITY_PATTERN);

    const title =
        similarityMatch?.[1]?.trim() ||
        (isDirectTitle(text) ? text : null);

    if (title) {
        return `${API_BASE}/recommend?title=${encodeURIComponent(title)}`;
    }

    return `${API_BASE}/recommend-text?text=${encodedText}`;
}


function isDirectTitle(text) {
    return text.split(/\s+/).length <= 7 &&
        !NATURAL_LANGUAGE_WORDS.test(text);
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


    const posterUrl =
        movie.poster_url ||
        movie.poster ||
        movie.posterUrl;

    if (posterUrl) {

        const poster =
            document.createElement("img");

        poster.src =
            posterUrl;

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
        movie.original_title ||
        "Untitled movie";


    content.appendChild(
        title
    );


    const meta =
        document.createElement("p");

    meta.className =
        "recommendation-meta";


    const metaParts = [];


    const releaseYear =
        movie.year ||
        movie.release_date?.slice(0, 4);

    if (releaseYear) {
        metaParts.push(
            releaseYear
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


    const languages =
        Array.isArray(movie.language) ?
            movie.language.join(", ") :
            movie.language;

    if (languages) {
        metaParts.push(languages);
    }


    meta.textContent =
        metaParts.join(" · ");


    content.appendChild(
        meta
    );


    const genres =
        Array.isArray(movie.genres) ?
            movie.genres.join(", ") :
            movie.genres || movie.genre;

    if (genres) {

        const genre =
            document.createElement("p");

        genre.className =
            "recommendation-genre";

        genre.textContent =
            genres;

        content.appendChild(
            genre
        );
    }


    const overview =
        movie.overview || movie.explanation;

    if (overview) {

        const explanation =
            document.createElement("p");

        explanation.className =
            "recommendation-explanation";

        explanation.textContent =
            overview;

        content.appendChild(
            explanation
        );
    }


    if (
        movie.availability_status ===
        "verified_available"
    ) {

        const providers =
            Array.isArray(movie.streaming_sources) ?
                movie.streaming_sources
                    .map(source => source?.name)
                    .filter(Boolean)
                    .join(", ") :
                "";

        if (providers) {
            const availability =
                document.createElement("p");

            availability.className =
                "recommendation-genre";

            availability.textContent =
                `Streaming: ${providers}`;

            content.appendChild(availability);
        }
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
