"use strict";

const API_BASE = window.MOVIEAI_API_BASE || (window.location.protocol === "file:" || ["5500", "5501"].includes(window.location.port) ? "http://127.0.0.1:5000/api" : `${window.location.origin}/api`);
const form = document.getElementById("recommendationForm");
const input = document.getElementById("recommendationInput");
const button = document.getElementById("recommendationButton");
const clearBtn = document.getElementById("clearInputBtn");
const promptChips = document.querySelectorAll(".prompt-chip");
const resultsContainer = document.getElementById("recommendationResults");
const recommendationSearchIcon = document.getElementById("recommendationSearchIcon");
const LATEST_DISCOVERY_PATTERN = /\b(latest|new|newest|recent|recently released|upcoming)\b/i;
const SIMILARITY_PATTERN = /\b(?:recommend(?:\s+(?:me|movies?))?\s*(?:similar to|like)|movies?\s+like)\s+(.+)/i;
const NATURAL_LANGUAGE_WORDS = /\b(i|want|show|suggest|find|movie|movies|telugu|hindi|tamil|malayalam|kannada|action|comedy|romance|thriller|drama|family|mood|feel)\b/i;
const LANGUAGE_NAMES = { te: "Telugu", hi: "Hindi", ta: "Tamil", ml: "Malayalam", kn: "Kannada", en: "English", bn: "Bengali", mr: "Marathi", pa: "Punjabi", gu: "Gujarati", or: "Odia", as: "Assamese", ur: "Urdu" };
let activeRequest = null;

if (typeof window.matchMedia === "function" && window.matchMedia("(max-width: 767px)").matches && input) input.placeholder = "Describe a movie you want to watch";

promptChips.forEach(chip => chip.addEventListener("click", () => {
    if (!input || !chip.dataset.prompt) return;
    input.value = chip.dataset.prompt;
    updateClearButton();
    input.focus();
    form?.requestSubmit();
}));
resultsContainer?.addEventListener("click", event => {
    if (event.target.closest("[data-empty-clear]")) {
        if (!input) return;
        input.value = "";
        updateClearButton();
        input.focus();
        return;
    }
    const suggestion = event.target.closest("[data-empty-query], [data-empty-prompt]");
    if (!suggestion || !input) return;
    input.value = suggestion.dataset.emptyQuery || suggestion.dataset.emptyPrompt || "";
    updateClearButton();
    input.focus();
    form?.requestSubmit();
});
input?.addEventListener("input", updateClearButton);
clearBtn?.addEventListener("click", () => { activeRequest?.abort(); input.value = ""; updateClearButton(); input.focus(); });
form?.addEventListener("submit", handleRecommendationSubmit);

function updateClearButton() { if (clearBtn && input) clearBtn.hidden = !input.value; }

async function handleRecommendationSubmit(event) {
    event.preventDefault();
    const text = input?.value.trim() || "";
    if (!text) return renderError("Please describe what kind of movie you want.");
    activeRequest?.abort();
    const request = new AbortController();
    activeRequest = request;
    setLoading(true);
    window.MovieAISearchIcon?.setLoading(recommendationSearchIcon, true);
    renderLoading();
    try {
        const endpoint = recommendationEndpoint(text);
        console.log("[MovieAI] recommendation endpoint:", endpoint);
        const response = await fetch(endpoint, { headers: { Accept: "application/json" }, signal: request.signal });
        const data = await response.json();
        console.log("[MovieAI] response:", data);
        console.log("[MovieAI] result count:", data.results?.length);
        if (!response.ok) throw { status: response.status, data };
        if (!Array.isArray(data.results)) return renderError("No recommendation results were returned.");
        if (!data.results.length) return renderEmpty();
        renderResults(data);
    } catch (error) {
        if (error?.name !== "AbortError") handleAPIError(error);
    } finally {
        if (activeRequest === request) { activeRequest = null; setLoading(false); window.MovieAISearchIcon?.setLoading(recommendationSearchIcon, false); }
    }
}

function setLoading(isLoading) {
    if (!button || !resultsContainer) return;
    button.disabled = isLoading;
    button.classList.toggle("is-loading", isLoading);
    button.setAttribute("aria-label", isLoading ? "Rolling movie recommendations" : "Roll the reel and find movies");
    resultsContainer.setAttribute("aria-busy", String(isLoading));
}

function recommendationEndpoint(text) {
    const encodedText = encodeURIComponent(text);
    if (LATEST_DISCOVERY_PATTERN.test(text)) return `${API_BASE}/recommend-hybrid?text=${encodedText}`;
    const similarityMatch = text.match(SIMILARITY_PATTERN);
    const title = similarityMatch?.[1]?.trim() || (isDirectTitle(text) ? text : null);
    return title ? `${API_BASE}/recommend?title=${encodeURIComponent(title)}` : `${API_BASE}/recommend-text?text=${encodedText}`;
}
function isDirectTitle(text) { return text.split(/\s+/).length <= 7 && !NATURAL_LANGUAGE_WORDS.test(text); }

function renderLoading() {
    if (!resultsContainer) return;
    resultsContainer.innerHTML = `<div class="recommendation-results-heading"><span>YOUR MOVIE PICKS</span><h2>Finding your movies</h2></div>${window.MovieAILoader.inline("Reading your mood…")}<div class="recommendation-loading-skeletons" aria-hidden="true"><div></div><div></div><div></div></div>`;
}
function renderEmpty() {
    if (!resultsContainer) return;
    const actions = [
        { label: "Latest Telugu action", query: "Latest Telugu action movies" },
        { label: "Feel-good comedy", query: "Feel-good Indian comedy movies" },
        { label: "Suspense thriller", query: "Suspense thriller movies" }
    ];
    resultsContainer.innerHTML = window.MovieAIEmptyState?.render({ actions }) || '<div class="recommendation-empty"><h2>No matching movies found.</h2><p>Try changing the language, mood, genre, or description.</p></div>';
}
function renderError(message) { if (resultsContainer) resultsContainer.innerHTML = `<div class="recommendation-error"><h2>Something went wrong</h2><p>${escapeHTML(message)}</p></div>`; }

function renderResults(data) {
    resultsContainer.innerHTML = "";
    const heading = document.createElement("div"); heading.className = "recommendation-results-heading"; heading.innerHTML = "<span>YOUR MOVIE PICKS</span><h2>Movies for your mood</h2>"; resultsContainer.appendChild(heading);
    const parts = [...asArray(data.intent?.genres), ...asArray(data.intent?.languages).map(displayLanguage)];
    if (data.intent?.mood) parts.push(String(data.intent.mood).replace(/_/g, " "));
    if (data.intent?.audience) parts.push(data.intent.audience);
    if (parts.length) {
        const matches = document.createElement("div"); matches.className = "recommendation-match-tags";
        const label = document.createElement("span"); label.textContent = "Matched:"; matches.appendChild(label);
        parts.forEach(part => { const tag = document.createElement("span"); tag.className = "recommendation-match-tag"; tag.textContent = part; matches.appendChild(tag); });
        resultsContainer.appendChild(matches);
    }
    const grid = document.createElement("div"); grid.className = "recommendation-grid";
    data.results.forEach(movie => grid.appendChild(createMovieCard(movie)));
    resultsContainer.appendChild(grid);
}

function createMovieCard(movie) {
    const card = document.createElement("article"); card.className = "recommendation-movie-card";
    const posterUrl = movie.poster_url || movie.poster || movie.posterUrl;
    if (posterUrl) { const poster = document.createElement("img"); poster.src = posterUrl; poster.alt = `${movie.title || "Movie"} poster`; poster.className = "recommendation-poster"; poster.loading = "lazy"; poster.onerror = () => { poster.style.display = "none"; }; card.appendChild(poster); }
    const content = document.createElement("div"); content.className = "recommendation-card-content";
    const title = document.createElement("h3"); title.textContent = movie.title || movie.original_title || "Untitled movie"; content.appendChild(title);
    const metaParts = []; const year = movie.year || movie.release_date?.slice(0, 4); if (year) metaParts.push(year);
    const rating = validRating(movie.rating); if (rating !== null) metaParts.push(`★ ${rating.toFixed(1)}`);
    if (movie.runtime) metaParts.push(movie.runtime);
    const languages = asArray(movie.language).map(displayLanguage).filter(Boolean); if (languages.length) metaParts.push(languages.join(", "));
    if (metaParts.length) { const meta = document.createElement("p"); meta.className = "recommendation-meta"; meta.textContent = metaParts.join(" · "); content.appendChild(meta); }
    const genres = asArray(movie.genres || movie.genre).map(String).filter(Boolean); if (genres.length) { const genre = document.createElement("p"); genre.className = "recommendation-genre"; genre.textContent = genres.join(", "); content.appendChild(genre); }
    const overview = movie.overview || movie.explanation; if (overview) { const explanation = document.createElement("p"); explanation.className = "recommendation-explanation"; explanation.textContent = overview; content.appendChild(explanation); }
    if (movie.availability_status === "verified_available") { const providers = asArray(movie.streaming_sources).map(source => source?.name).filter(Boolean).join(", "); if (providers) { const availability = document.createElement("p"); availability.className = "recommendation-availability"; availability.textContent = `Streaming: ${providers}`; content.appendChild(availability); } }
    card.appendChild(content); return card;
}
function asArray(value) { return Array.isArray(value) ? value : value ? [value] : []; }
function displayLanguage(value) { const key = String(value || "").trim().toLowerCase(); return LANGUAGE_NAMES[key] || key.replace(/\b\w/g, letter => letter.toUpperCase()); }
function validRating(value) { const rating = Number.parseFloat(value); return Number.isFinite(rating) && rating > 0 && rating < 10 ? rating : null; }
function handleAPIError(error) { if (error?.status === 422) return renderError("That request contains a genre or language that is not available in the current movie dataset."); if (error?.status === 503) return renderError("The recommendation service is temporarily unavailable. Please try again shortly."); renderError("Unable to connect to the recommendation service. Make sure the Flask backend is running."); }
function escapeHTML(value) { return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;"); }
