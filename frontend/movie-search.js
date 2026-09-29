"use strict";

/* =========================================================
   MOVIE SEARCH — FRONTEND API CONFIGURATION
   ========================================================= */

/*
 * When Flask serves this app, use its same-origin API. When the frontend is
 * opened with a separate dev server (or directly from disk), use local Flask.
 * Deployments can override this with window.MOVIEAI_API_BASE.
 */
const API_BASE =
    window.MOVIEAI_API_BASE ||
    (window.location.port === "5000"
        ? "/api"
        : "http://127.0.0.1:5000/api");


/* =========================================================
   DOM INITIALIZATION
   ========================================================= */

document.addEventListener(
    "DOMContentLoaded",
    initializeMovieSearch
);


function initializeMovieSearch() {

    const input =
        document.getElementById(
            "movieSearchInput"
        );

    const searchButton =
        document.getElementById(
            "movieSearchButton"
        );

    const autocomplete =
        document.getElementById(
            "autocompleteResults"
        );

    const searchResults =
        document.getElementById(
            "searchResults"
        );

    const movieDetails =
        document.getElementById(
            "movieDetails"
        );

    const similarMovies =
        document.getElementById(
            "similarMovies"
        );


    /*
     * Prevent JavaScript errors if the HTML
     * structure is incomplete.
     */

    if (
        !input ||
        !searchButton ||
        !autocomplete ||
        !searchResults ||
        !movieDetails ||
        !similarMovies
    ) {

        console.error(
            "Movie search initialization failed: required DOM elements are missing."
        );

        return;
    }


    /* =====================================================
       REQUEST STATE
       ===================================================== */

    let autocompleteTimer = null;

    let autocompleteController = null;

    let searchController = null;

    let movieController = null;

    let recommendationController = null;

    const searchChips =
        document.querySelectorAll(
            ".search-chip"
        );

    const clearSearchBtn =
        document.getElementById(
            "clearSearchBtn"
        );


    /* =====================================================
       TRENDING CHIPS HANDLER
       ===================================================== */

    searchChips.forEach(chip => {
        chip.addEventListener("click", () => {
            const movie = chip.getAttribute("data-movie");
            if (movie && input) {
                input.value = movie;
                if (clearSearchBtn) clearSearchBtn.hidden = false;
                hideAutocomplete();
                
                // Animate button
                if (searchButton) {
                    searchButton.classList.add("btn-pulse");
                    setTimeout(() => searchButton.classList.remove("btn-pulse"), 600);
                }

                searchMovies();
            }
        });
    });


    /* =====================================================
       CLEAR SEARCH BUTTON
       ===================================================== */

    if (clearSearchBtn) {
        clearSearchBtn.addEventListener("click", () => {
            if (input) {
                input.value = "";
                clearSearchBtn.hidden = true;
                hideAutocomplete();
                input.focus();
            }
        });
    }


    /* =====================================================
       INPUT EVENTS
       ===================================================== */

    input.addEventListener(
        "input",
        () => {
            if (clearSearchBtn) {
                clearSearchBtn.hidden = input.value.trim().length === 0;
            }
            handleInput();
        }
    );


    input.addEventListener(
        "keydown",
        event => {

            if (
                event.key === "Enter"
            ) {

                event.preventDefault();

                hideAutocomplete();

                searchMovies();
            }


            if (
                event.key === "Escape"
            ) {

                hideAutocomplete();
            }
        }
    );


    /* =====================================================
       SEARCH BUTTON
       ===================================================== */

    searchButton.addEventListener(
        "click",
        () => {

            hideAutocomplete();

            searchMovies();
        }
    );


    /* =====================================================
       CLOSE AUTOCOMPLETE WHEN CLICKING OUTSIDE
       ===================================================== */

    document.addEventListener(
        "click",
        event => {

            const target =
                event.target;

            if (
                !autocomplete.contains(target) &&
                target !== input
            ) {

                hideAutocomplete();
            }
        }
    );


    /* =====================================================
       INPUT HANDLER
       ===================================================== */

    function handleInput() {

        const query =
            input.value.trim();


        clearTimeout(
            autocompleteTimer
        );


        /*
         * Cancel previous autocomplete request.
         */

        if (
            autocompleteController
        ) {

            autocompleteController.abort();

            autocompleteController =
                null;
        }


        if (
            query.length < 2
        ) {

            autocomplete.innerHTML =
                "";

            autocomplete.hidden =
                true;

            return;
        }


        autocompleteTimer =
            setTimeout(
                () => {

                    loadAutocomplete(
                        query
                    );

                },
                250
            );
    }


    /* =====================================================
       AUTOCOMPLETE API
       ===================================================== */

    async function loadAutocomplete(
        query
    ) {

        if (
            autocompleteController
        ) {

            autocompleteController.abort();
        }


        autocompleteController =
            new AbortController();


        try {

            const response =
                await fetch(
                    `${API_BASE}/autocomplete?q=${encodeURIComponent(query)}`,
                    {
                        method: "GET",
                        headers: {
                            "Accept":
                                "application/json"
                        },
                        signal:
                            autocompleteController.signal
                    }
                );


            if (
                !response.ok
            ) {

                hideAutocomplete();

                return;
            }


            const titles =
                await parseJSON(
                    response
                );


            /*
             * Do not display results if the user
             * has already changed the input.
             */

            if (
                input.value.trim() !== query
            ) {

                return;
            }


            renderAutocomplete(
                titles
            );


        } catch (error) {

            if (
                error.name === "AbortError"
            ) {

                return;
            }


            console.error(
                "Autocomplete error:",
                error
            );

            hideAutocomplete();
        }
    }


    /* =====================================================
       AUTOCOMPLETE RENDER
       ===================================================== */

    function renderAutocomplete(
        titles
    ) {

        autocomplete.innerHTML =
            "";


        if (
            !Array.isArray(titles) ||
            titles.length === 0
        ) {

            autocomplete.hidden =
                true;

            return;
        }


        titles
            .slice(0, 8)
            .forEach(
                title => {

                    if (
                        !title
                    ) {

                        return;
                    }


                    const item =
                        document.createElement(
                            "button"
                        );


                    item.type =
                        "button";


                    item.className =
                        "autocomplete-item";


                    item.textContent =
                        String(title);


                    item.addEventListener(
                        "click",
                        () => {

                            input.value =
                                String(title);

                            hideAutocomplete();

                            loadMovie(
                                String(title)
                            );
                        }
                    );


                    autocomplete.appendChild(
                        item
                    );
                }
            );


        autocomplete.hidden =
            autocomplete.children.length === 0;
    }


    /* =====================================================
       SEARCH MOVIES
       ===================================================== */

    async function searchMovies() {

        const query =
            input.value.trim();


        if (
            !query
        ) {

            renderError(
                searchResults,
                "Please enter a movie title."
            );

            return;
        }


        /*
         * Cancel previous search.
         */

        if (
            searchController
        ) {

            searchController.abort();
        }


        searchController =
            new AbortController();


        renderLoading(
            searchResults,
            "Searching movies..."
        );


        try {

            const response =
                await fetch(
                    `${API_BASE}/search?q=${encodeURIComponent(query)}`,
                    {
                        method: "GET",
                        headers: {
                            "Accept":
                                "application/json"
                        },
                        signal:
                            searchController.signal
                    }
                );


            const data =
                await parseJSON(
                    response
                );


            if (
                !response.ok
            ) {

                throw createAPIError(
                    response.status,
                    data
                );
            }


            if (
                !data ||
                !Array.isArray(data.results) ||
                data.results.length === 0
            ) {

                renderEmpty(
                    searchResults,
                    "No matching movies found.",
                    "Try another movie title."
                );

                return;
            }


            renderSearchResults(
                data.results
            );


        } catch (error) {

            if (
                error.name === "AbortError"
            ) {

                return;
            }


            console.error(
                "Search error:",
                error
            );


            renderError(
                searchResults,
                getAPIErrorMessage(
                    error,
                    "Unable to search movies. Make sure the Flask backend is running."
                )
            );
        }
    }


    /* =====================================================
       LOAD MOVIE DETAILS
       ===================================================== */

    async function loadMovie(
        title
    ) {

        if (
            !title
        ) {

            return;
        }


        /*
         * Cancel previous movie request.
         */

        if (
            movieController
        ) {

            movieController.abort();
        }


        movieController =
            new AbortController();


        renderLoading(
            movieDetails,
            "Loading movie details..."
        );


        similarMovies.innerHTML =
            "";


        try {

            const response =
                await fetch(
                    `${API_BASE}/movie?title=${encodeURIComponent(title)}`,
                    {
                        method: "GET",
                        headers: {
                            "Accept":
                                "application/json"
                        },
                        signal:
                            movieController.signal
                    }
                );


            const movie =
                await parseJSON(
                    response
                );


            if (
                !response.ok
            ) {

                throw createAPIError(
                    response.status,
                    movie
                );
            }


            if (
                !movie ||
                !movie.title
            ) {

                throw new Error(
                    "Movie details are unavailable."
                );
            }


            renderMovieDetails(
                movie
            );


            /*
             * Use the backend's canonical title.
             */

            loadSimilarMovies(
                movie.title || title
            );


        } catch (error) {

            if (
                error.name === "AbortError"
            ) {

                return;
            }


            console.error(
                "Movie details error:",
                error
            );


            renderError(
                movieDetails,
                getAPIErrorMessage(
                    error,
                    "Movie details are unavailable."
                )
            );
        }
    }


    /* =====================================================
       LOAD SIMILAR MOVIES
       ===================================================== */

    async function loadSimilarMovies(
        title
    ) {

        if (
            !title
        ) {

            return;
        }


        /*
         * Cancel previous recommendation request.
         */

        if (
            recommendationController
        ) {

            recommendationController.abort();
        }


        recommendationController =
            new AbortController();


        renderLoading(
            similarMovies,
            "Finding similar movies..."
        );


        try {

            const response =
                await fetch(
                    `${API_BASE}/recommend?title=${encodeURIComponent(title)}&limit=8`,
                    {
                        method: "GET",
                        headers: {
                            "Accept":
                                "application/json"
                        },
                        signal:
                            recommendationController.signal
                    }
                );


            const data =
                await parseJSON(
                    response
                );


            if (
                !response.ok
            ) {

                throw createAPIError(
                    response.status,
                    data
                );
            }


            if (
                !data ||
                !Array.isArray(data.results) ||
                data.results.length === 0
            ) {

                renderEmpty(
                    similarMovies,
                    "No similar movies found.",
                    "Try another movie."
                );

                return;
            }


            renderSimilarMovies(
                data.results
            );


        } catch (error) {

            if (
                error.name === "AbortError"
            ) {

                return;
            }


            console.error(
                "Recommendation error:",
                error
            );


            renderError(
                similarMovies,
                getAPIErrorMessage(
                    error,
                    "Unable to load similar movies."
                )
            );
        }
    }


    /* =====================================================
       RENDER SEARCH RESULTS
       ===================================================== */

    function renderSearchResults(
        results
    ) {

        searchResults.innerHTML =
            `
            <div class="movie-search-section-title">
                <span>SEARCH RESULTS</span>
                <h2>Select a movie</h2>
            </div>
            `;


        const grid =
            document.createElement(
                "div"
            );


        grid.className =
            "movie-search-grid";


        results.forEach(
            movie => {

                const card =
                    createMovieCard(
                        movie
                    );


                card.addEventListener(
                    "click",
                    () => {

                        const title =
                            movie?.title ||
                            "";


                        if (
                            !title
                        ) {

                            return;
                        }


                        input.value =
                            title;


                        hideAutocomplete();

                        loadMovie(
                            title
                        );
                    }
                );


                grid.appendChild(
                    card
                );
            }
        );


        searchResults.appendChild(
            grid
        );
    }


    /* =====================================================
       RENDER MOVIE DETAILS
       ===================================================== */

    function renderMovieDetails(
        movie
    ) {

        movieDetails.innerHTML =
            "";


        const section =
            document.createElement(
                "section"
            );


        section.className =
            "movie-detail-card";


        if (
            movie.poster
        ) {

            const poster =
                document.createElement(
                    "img"
                );


            poster.src =
                movie.poster;


            poster.alt =
                `${movie.title || "Movie"} poster`;


            poster.className =
                "movie-detail-poster";


            poster.loading =
                "lazy";


            poster.onerror =
                () => {

                    poster.remove();
                };


            section.appendChild(
                poster
            );
        }


        const content =
            document.createElement(
                "div"
            );


        content.className =
            "movie-detail-content";


        content.innerHTML =
            `
            <span class="movie-search-eyebrow">
                SELECTED MOVIE
            </span>

            <h2>
                ${escapeHTML(movie.title)}
            </h2>

            <p class="movie-detail-meta">
                ${escapeHTML(movie.year || "")}
                ${
                    movie.rating
                        ? ` · ★ ${escapeHTML(movie.rating)}`
                        : ""
                }
                ${
                    movie.runtime
                        ? ` · ${escapeHTML(movie.runtime)}`
                        : ""
                }
            </p>

            <p>
                ${escapeHTML(movie.genre || "Genre unavailable")}
            </p>

            <p>
                ${escapeHTML(movie.plot || "No plot available.")}
            </p>
            `;


        section.appendChild(
            content
        );


        movieDetails.appendChild(
            section
        );


        /*
         * Bring selected movie details into view
         * after the user selects a result.
         */

        movieDetails.scrollIntoView({
            behavior: "smooth",
            block: "start"
        });
    }


    /* =====================================================
       RENDER SIMILAR MOVIES
       ===================================================== */

    function renderSimilarMovies(
        results
    ) {

        similarMovies.innerHTML =
            `
            <div class="movie-search-section-title">
                <span>SIMILAR MOVIES</span>
                <h2>You may also like</h2>
            </div>
            `;


        const grid =
            document.createElement(
                "div"
            );


        grid.className =
            "movie-search-grid";


        results.forEach(
            movie => {

                /*
                 * IMPORTANT:
                 * This is the corrected syntax.
                 *
                 * Previous broken version had:
                 *
                 * createMovieCard(movie);
                 *
                 * inside appendChild().
                 */

                grid.appendChild(
                    createMovieCard(
                        movie
                    )
                );
            }
        );


        similarMovies.appendChild(
            grid
        );
    }


    /* =====================================================
       CREATE MOVIE CARD
       ===================================================== */

    function createMovieCard(
        movie
    ) {

        const card =
            document.createElement(
                "article"
            );


        card.className =
            "movie-search-card";


        card.tabIndex =
            0;


        card.setAttribute(
            "role",
            "button"
        );


        if (
            movie &&
            movie.poster
        ) {

            const poster =
                document.createElement(
                    "img"
                );


            poster.src =
                movie.poster;


            poster.alt =
                `${movie.title || "Movie"} poster`;


            poster.className =
                "movie-search-poster";


            poster.loading =
                "lazy";


            poster.onerror =
                () => {

                    poster.remove();
                };


            card.appendChild(
                poster
            );
        }


        const content =
            document.createElement(
                "div"
            );


        content.className =
            "movie-search-card-content";


        const title =
            document.createElement(
                "h3"
            );


        title.textContent =
            movie?.title ||
            "Untitled movie";


        content.appendChild(
            title
        );


        const meta =
            document.createElement(
                "p"
            );


        meta.textContent =
            [
                movie?.year,
                movie?.rating
                    ? `★ ${movie.rating}`
                    : "",
                movie?.runtime || ""
            ]
                .filter(
                    Boolean
                )
                .join(
                    " · "
                );


        content.appendChild(
            meta
        );


        card.appendChild(
            content
        );


        return card;
    }


    /* =====================================================
       KEYBOARD SUPPORT FOR MOVIE CARDS
       ===================================================== */

    document.addEventListener(
        "keydown",
        event => {

            const activeElement =
                document.activeElement;


            if (
                !activeElement ||
                !activeElement.classList.contains(
                    "movie-search-card"
                )
            ) {

                return;
            }


            if (
                event.key !== "Enter" &&
                event.key !== " "
            ) {

                return;
            }


            event.preventDefault();

            activeElement.click();
        }
    );


    /* =====================================================
       LOADING STATE
       ===================================================== */

    function renderLoading(
        container,
        message
    ) {

        if (
            !container
        ) {

            return;
        }


        container.innerHTML =
            `
            <div class="movie-search-loading">
                <div class="movie-search-spinner"></div>
                <p>
                    ${escapeHTML(message)}
                </p>
            </div>
            `;
    }


    /* =====================================================
       EMPTY STATE
       ===================================================== */

    function renderEmpty(
        container,
        title,
        message
    ) {

        if (
            !container
        ) {

            return;
        }


        container.innerHTML =
            `
            <div class="movie-search-empty">
                <h2>
                    ${escapeHTML(title)}
                </h2>

                <p>
                    ${escapeHTML(message)}
                </p>
            </div>
            `;
    }


    /* =====================================================
       ERROR STATE
       ===================================================== */

    function renderError(
        container,
        message
    ) {

        if (
            !container
        ) {

            return;
        }


        container.innerHTML =
            `
            <div class="movie-search-error">
                <h2>
                    Something went wrong
                </h2>

                <p>
                    ${escapeHTML(message)}
                </p>
            </div>
            `;
    }


    /* =====================================================
       HIDE AUTOCOMPLETE
       ===================================================== */

    function hideAutocomplete() {

        autocomplete.innerHTML =
            "";

        autocomplete.hidden =
            true;
    }


    /* =====================================================
       SAFE JSON PARSER
       ===================================================== */

    async function parseJSON(
        response
    ) {

        const contentType =
            response.headers.get(
                "content-type"
            ) || "";


        if (
            contentType.includes(
                "application/json"
            )
        ) {

            return await response.json();
        }


        const text =
            await response.text();


        if (
            !text
        ) {

            return null;
        }


        try {

            return JSON.parse(
                text
            );

        } catch {

            return {
                error:
                    text
            };
        }
    }


    /* =====================================================
       API ERROR CREATOR
       ===================================================== */

    function createAPIError(
        status,
        data
    ) {

        const message =
            data &&
            typeof data.error === "string"
                ? data.error
                : `API request failed with status ${status}.`;


        const error =
            new Error(
                message
            );


        error.status =
            status;


        error.data =
            data;


        return error;
    }


    /* =====================================================
       API ERROR MESSAGE
       ===================================================== */

    function getAPIErrorMessage(
        error,
        fallback
    ) {

        if (
            error &&
            error.message
        ) {

            return error.message;
        }


        return fallback;
    }


    /* =====================================================
       ESCAPE HTML
       ===================================================== */

    function escapeHTML(
        value
    ) {

        return String(
            value ?? ""
        )
            .replace(
                /&/g,
                "&amp;"
            )
            .replace(
                /</g,
                "&lt;"
            )
            .replace(
                />/g,
                "&gt;"
            )
            .replace(
                /"/g,
                "&quot;"
            )
            .replace(
                /'/g,
                "&#039;"
            );
    }


    /* =====================================================
       INITIAL STATE
       ===================================================== */

    autocomplete.hidden =
        true;


    console.log(
        "Movie search initialized successfully."
    );
}