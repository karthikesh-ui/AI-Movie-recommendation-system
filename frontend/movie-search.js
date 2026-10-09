"use strict";

/* Search is intentionally local/OMDb-backed. Selecting a result moves to the
 * dedicated details page; this file never requests recommendations. */
const API_BASE = window.MOVIEAI_API_BASE ||
    (window.location.protocol === "file:" || ["5500", "5501"].includes(window.location.port)
        ? "http://127.0.0.1:5000/api" : `${window.location.origin}/api`);
const SEARCH_STATE_KEY = "movieai_search_state";

document.addEventListener("DOMContentLoaded", initializeMovieSearch);

function initializeMovieSearch() {
    const input = document.getElementById("movieSearchInput");
    const searchButton = document.getElementById("movieSearchButton");
    const autocomplete = document.getElementById("autocompleteResults");
    const searchResults = document.getElementById("searchResults");
    const clearSearchBtn = document.getElementById("clearSearchBtn");
    if (!input || !searchButton || !autocomplete || !searchResults) return;

    let autocompleteTimer;
    let autocompleteController;
    let searchController;
    restoreSearchState();

    document.querySelectorAll(".search-chip").forEach(chip => chip.addEventListener("click", () => {
        input.value = chip.dataset.movie || "";
        if (clearSearchBtn) clearSearchBtn.hidden = !input.value;
        hideAutocomplete();
        searchMovies();
    }));
    clearSearchBtn?.addEventListener("click", () => {
        input.value = "";
        clearSearchBtn.hidden = true;
        hideAutocomplete();
        input.focus();
    });
    input.addEventListener("input", () => {
        if (clearSearchBtn) clearSearchBtn.hidden = !input.value.trim();
        window.clearTimeout(autocompleteTimer);
        autocompleteController?.abort();
        const query = input.value.trim();
        if (query.length < 2) return hideAutocomplete();
        autocompleteTimer = window.setTimeout(() => loadAutocomplete(query), 250);
    });
    input.addEventListener("keydown", event => {
        if (event.key === "Escape") return hideAutocomplete();
        if (event.key === "Enter") {
            event.preventDefault();
            hideAutocomplete();
            searchMovies();
        }
    });
    searchButton.addEventListener("click", () => {
        hideAutocomplete();
        searchMovies();
    });
    document.addEventListener("click", event => {
        if (!autocomplete.contains(event.target) && event.target !== input) hideAutocomplete();
    });

    async function loadAutocomplete(query) {
        autocompleteController?.abort();
        autocompleteController = new AbortController();
        try {
            const response = await fetch(`${API_BASE}/autocomplete?q=${encodeURIComponent(query)}`, {
                headers: { Accept: "application/json" }, signal: autocompleteController.signal
            });
            const titles = await parseJSON(response);
            if (!response.ok || input.value.trim() !== query) return hideAutocomplete();
            renderAutocomplete(titles);
        } catch (error) {
            if (error.name !== "AbortError") console.error("Autocomplete error:", error);
        }
    }

    function renderAutocomplete(titles) {
        autocomplete.replaceChildren();
        if (!Array.isArray(titles)) return hideAutocomplete();
        titles.slice(0, 8).filter(Boolean).forEach(title => {
            const item = document.createElement("button");
            item.type = "button";
            item.className = "autocomplete-item";
            item.textContent = String(title);
            item.addEventListener("click", () => openMovieDetails({ title: String(title) }));
            autocomplete.appendChild(item);
        });
        autocomplete.hidden = !autocomplete.children.length;
    }

    async function searchMovies() {
        const query = input.value.trim();
        if (!query) return renderMessage("error", "Please enter a movie title.");
        searchController?.abort();
        searchController = new AbortController();
        renderMessage("loading", "Searching movies...");
        try {
            const response = await fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}`, {
                headers: { Accept: "application/json" }, signal: searchController.signal
            });
            const data = await parseJSON(response);
            if (!response.ok) throw new Error(data?.error || "Unable to search movies.");
            if (!Array.isArray(data?.results) || !data.results.length) {
                return renderMessage("empty", "No matching movies found.", "Try another movie title.");
            }
            renderSearchResults(data.results, true);
        } catch (error) {
            if (error.name !== "AbortError") {
                console.error("Search error:", error);
                renderMessage("error", error.message || "Unable to search movies. Make sure the Flask backend is running.");
            }
        }
    }

    function renderSearchResults(results, persist) {
        searchResults.replaceChildren();
        const heading = document.createElement("div");
        heading.className = "movie-search-section-title";
        heading.innerHTML = "<span>SEARCH RESULTS</span><h2>Select a movie</h2>";
        const grid = document.createElement("div");
        grid.className = "movie-search-grid";
        results.forEach(movie => {
            const card = createMovieCard(movie);
            card.addEventListener("click", () => openMovieDetails(movie));
            grid.appendChild(card);
        });
        searchResults.append(heading, grid);
        if (persist) saveSearchState(results);
    }

    function createMovieCard(movie) {
        const card = document.createElement("article");
        card.className = "movie-search-card";
        card.tabIndex = 0;
        card.setAttribute("role", "button");
        card.setAttribute("aria-label", `View details for ${movie?.title || "movie"}`);
        card.addEventListener("keydown", event => {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                card.click();
            }
        });
        const posterUrl = movie?.poster_url || movie?.poster;
        if (isPresent(posterUrl)) {
            const poster = document.createElement("img");
            poster.src = posterUrl;
            poster.alt = `${movie.title || "Movie"} poster`;
            poster.className = "movie-search-poster";
            poster.loading = "lazy";
            poster.onerror = () => poster.remove();
            card.appendChild(poster);
        }
        const content = document.createElement("div");
        content.className = "movie-search-card-content";
        const title = document.createElement("h3");
        title.textContent = movie?.title || "Untitled movie";
        const meta = document.createElement("p");
        meta.textContent = [movie?.year, isPresent(movie?.rating) ? `★ ${movie.rating}` : "", movie?.runtime]
            .filter(isPresent).join(" · ");
        content.append(title, meta);
        card.appendChild(content);
        return card;
    }

    function openMovieDetails(movie) {
        const title = String(movie?.title || "").trim();
        if (!title) return;
        const identity = new URLSearchParams({ title });
        if (/^\d{4}$/.test(String(movie?.year || ""))) identity.set("year", movie.year);
        if (isPresent(movie?.imdb_id)) identity.set("imdb_id", movie.imdb_id);
        window.location.assign(`movie-details.html?${identity.toString()}`);
    }

    function saveSearchState(results) {
        try {
            sessionStorage.setItem(SEARCH_STATE_KEY, JSON.stringify({ query: input.value.trim(), results }));
        } catch (error) {
            console.warn("Unable to preserve the search state.", error);
        }
    }

    function restoreSearchState() {
        try {
            const saved = JSON.parse(sessionStorage.getItem(SEARCH_STATE_KEY));
            if (!saved || !Array.isArray(saved.results) || !saved.results.length) return;
            input.value = typeof saved.query === "string" ? saved.query : "";
            if (clearSearchBtn) clearSearchBtn.hidden = !input.value;
            renderSearchResults(saved.results, false);
        } catch (_) {
            sessionStorage.removeItem(SEARCH_STATE_KEY);
        }
    }

    function renderMessage(kind, title, detail = "") {
        searchResults.innerHTML = `<div class="movie-search-${kind}"><h2>${escapeHTML(title)}</h2>${detail ? `<p>${escapeHTML(detail)}</p>` : ""}</div>`;
    }

    function hideAutocomplete() {
        window.clearTimeout(autocompleteTimer);
        autocompleteController?.abort();
        autocompleteController = null;
        autocomplete.replaceChildren();
        autocomplete.hidden = true;
    }
}

async function parseJSON(response) {
    const text = await response.text();
    try { return text ? JSON.parse(text) : null; } catch (_) { return null; }
}

function isPresent(value) {
    return value !== null && value !== undefined && String(value).trim() !== "" && String(value).trim() !== "N/A";
}

function escapeHTML(value) {
    const element = document.createElement("div");
    element.textContent = String(value || "");
    return element.innerHTML;
}
