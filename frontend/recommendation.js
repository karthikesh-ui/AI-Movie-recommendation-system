"use strict";

const API_BASE = window.MOVIEAI_API_BASE || (window.location.protocol === "file:" || ["5500", "5501"].includes(window.location.port) ? "http://127.0.0.1:5000/api" : `${window.location.origin}/api`);
const form = document.getElementById("recommendationForm");
const input = document.getElementById("recommendationInput");
const button = document.getElementById("recommendationButton");
const clearBtn = document.getElementById("clearInputBtn");
const promptChips = document.querySelectorAll(".prompt-chip");
const resultsContainer = document.getElementById("recommendationResults");
const recommendationSearchIcon = document.getElementById("recommendationSearchIcon");
const discoveryGuide = document.getElementById("discoveryGuide");
const discoveryModeButtons = document.querySelectorAll("[data-discovery-mode]");
const dismissDiscoveryGuide = document.getElementById("dismissDiscoveryGuide");
const openDiscoveryGuide = document.getElementById("openDiscoveryGuide");
const showSearchExamples = document.getElementById("showSearchExamples");
const searchExamples = document.getElementById("searchExamples");
const discoveryModeHelp = document.getElementById("discoveryModeHelp");
const queryBuilderSentence = document.getElementById("queryBuilderSentence");
const queryBuilderButtons = document.querySelectorAll("[data-query-group] button");
const resetQueryBuilder = document.getElementById("resetQueryBuilder");
const discoveryOnboarding = document.getElementById("discoveryOnboarding");
const onboardingShowHow = document.getElementById("onboardingShowHow");
const onboardingDismiss = document.getElementById("onboardingDismiss");
const LATEST_DISCOVERY_PATTERN = /\b(latest|new|newest|recent|recently released|upcoming)\b/i;
const OTT_DISCOVERY_PATTERN = /\b(ott|stream(?:ing)?|available on)\b/i;
const SIMILARITY_PATTERN = /\b(?:recommend(?:\s+(?:me|movies?))?\s*(?:similar to|like)|movies?\s+like)\s+(.+)/i;
const NATURAL_LANGUAGE_WORDS = /\b(i|want|show|suggest|find|movie|movies|telugu|hindi|tamil|malayalam|kannada|action|comedy|romance|thriller|drama|family|mood|feel)\b/i;
const LANGUAGE_NAMES = { te: "Telugu", hi: "Hindi", ta: "Tamil", ml: "Malayalam", kn: "Kannada", en: "English", bn: "Bengali", mr: "Marathi", pa: "Punjabi", gu: "Gujarati", or: "Odia", as: "Assamese", ur: "Urdu" };
let activeRequest = null;
let discoveryMode = "catalog";
const queryBuilder = { language: "", genres: [], time: "", mood: "" };

const MODE_HELP = {
    catalog: "Find matches in our movie collection. Add a title, language, genre, or mood.",
    theatrical: "Discover recent theatrical releases. Add a language or genre to narrow your search.",
    streaming: "Find recent movies with verified streaming availability in India. Platforms appear only when verified."
};
const GENRE_ORDER = ["Action", "Thriller", "Romance", "Comedy", "Horror", "Sci-fi", "Family", "Drama"];

if (typeof window.matchMedia === "function" && window.matchMedia("(max-width: 767px)").matches && input) input.placeholder = "Try: Telugu action thrillers";

scheduleOnboarding();

promptChips.forEach(chip => chip.addEventListener("click", () => {
    if (!input || !chip.dataset.prompt) return;
    input.value = chip.dataset.prompt;
    if (chip.dataset.mode) setDiscoveryMode(chip.dataset.mode);
    updateClearButton();
    input.focus();
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
openDiscoveryGuide?.addEventListener("click", () => toggleDiscoveryGuide());
showSearchExamples?.addEventListener("click", () => {
    searchExamples?.classList.toggle("is-expanded");
    showSearchExamples.setAttribute("aria-expanded", String(searchExamples?.classList.contains("is-expanded")));
    searchExamples?.scrollIntoView({ behavior: "smooth", block: "nearest" });
});
discoveryModeButtons.forEach(modeButton => modeButton.addEventListener("click", () => setDiscoveryMode(modeButton.dataset.discoveryMode || "catalog")));
dismissDiscoveryGuide?.addEventListener("click", () => setDiscoveryGuideOpen(false));
onboardingShowHow?.addEventListener("click", () => completeOnboarding(true));
onboardingDismiss?.addEventListener("click", () => completeOnboarding(false));
resetQueryBuilder?.addEventListener("click", () => {
    queryBuilder.language = "";
    queryBuilder.genres = [];
    queryBuilder.time = "";
    queryBuilder.mood = "";
    queryBuilderButtons.forEach(chip => chip.setAttribute("aria-pressed", "false"));
    renderQueryBuilder();
});
queryBuilderButtons.forEach(chip => chip.addEventListener("click", () => {
    const group = chip.closest("[data-query-group]")?.dataset.queryGroup;
    const value = chip.dataset.queryValue || "";
    if (!group || !value) return;
    if (group === "genre") {
        queryBuilder.genres = queryBuilder.genres.includes(value) ? queryBuilder.genres.filter(item => item !== value) : [...queryBuilder.genres, value];
    } else {
        queryBuilder[group] = queryBuilder[group] === value ? "" : value;
        if (group === "time" && queryBuilder.time && discoveryMode === "catalog") setDiscoveryMode("theatrical");
    }
    queryBuilderButtons.forEach(buttonElement => {
        const sameGroup = buttonElement.closest("[data-query-group]")?.dataset.queryGroup === group;
        const selected = group === "genre" ? queryBuilder.genres.includes(buttonElement.dataset.queryValue) : sameGroup && queryBuilder[group] === buttonElement.dataset.queryValue;
        buttonElement.setAttribute("aria-pressed", String(selected));
    });
    const sentence = buildQuerySentence();
    if (input && sentence) {
        input.value = sentence;
        updateClearButton();
    }
    renderQueryBuilder();
}));

function updateClearButton() { if (clearBtn && input) clearBtn.hidden = !input.value; }

function scheduleOnboarding() {
    if (!discoveryOnboarding) return;
    window.setTimeout(() => {
        discoveryOnboarding.hidden = false;
        requestAnimationFrame(() => discoveryOnboarding.classList.add("is-visible"));
    }, 180);
}

function completeOnboarding(showBuilder) {
    if (!discoveryOnboarding || discoveryOnboarding.hidden) {
        if (showBuilder) setDiscoveryGuideOpen(true);
        return;
    }
    const triggerBox = openDiscoveryGuide?.getBoundingClientRect();
    const sourceBox = onboardingShowHow?.getBoundingClientRect();
    const reduceMotion = typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    discoveryOnboarding.classList.remove("is-visible");
    discoveryOnboarding.classList.add("is-leaving");
    if (!reduceMotion && showBuilder && openDiscoveryGuide && triggerBox && sourceBox && typeof openDiscoveryGuide.animate === "function") {
        const sourceCenterX = sourceBox.left + sourceBox.width / 2;
        const sourceCenterY = sourceBox.top + sourceBox.height / 2;
        const triggerCenterX = triggerBox.left + triggerBox.width / 2;
        const triggerCenterY = triggerBox.top + triggerBox.height / 2;
        openDiscoveryGuide.animate([
            { transform: `translate(${sourceCenterX - triggerCenterX}px, ${sourceCenterY - triggerCenterY}px) scale(1.04)`, opacity: 0.82 },
            { transform: "translate(0, 0) scale(1)", opacity: 1 }
        ], { duration: 360, easing: "cubic-bezier(.22, 1, .36, 1)" });
    }
    window.setTimeout(() => {
        discoveryOnboarding.hidden = true;
        discoveryOnboarding.classList.remove("is-leaving");
        if (showBuilder) {
            setDiscoveryGuideOpen(true);
            openDiscoveryGuide?.focus({ preventScroll: true });
        }
    }, reduceMotion ? 0 : 190);
}

function setDiscoveryGuideOpen(open) {
    if (!discoveryGuide) return;
    discoveryGuide.classList.toggle("is-open", open);
    discoveryGuide.setAttribute("aria-hidden", String(!open));
    openDiscoveryGuide?.setAttribute("aria-expanded", String(open));
}

function toggleDiscoveryGuide() { setDiscoveryGuideOpen(!discoveryGuide?.classList.contains("is-open")); }

function setDiscoveryMode(mode) {
    discoveryMode = MODE_HELP[mode] ? mode : "catalog";
    discoveryModeButtons.forEach(buttonElement => {
        const selected = buttonElement.dataset.discoveryMode === discoveryMode;
        buttonElement.classList.toggle("is-selected", selected);
        buttonElement.setAttribute("aria-pressed", String(selected));
    });
    if (discoveryModeHelp) discoveryModeHelp.textContent = MODE_HELP[discoveryMode];
    renderQueryBuilder();
}

function buildQuerySentence() {
    const mood = String(queryBuilder.mood || "").toLowerCase();
    const language = String(queryBuilder.language || "").toLowerCase();
    const genres = naturalGenrePhrase(queryBuilder.genres);
    const subject = [mood, language, genres].filter(Boolean).join(" ") || "movies";
    const releaseTime = queryBuilder.time.toLowerCase();
    if (discoveryMode === "streaming") return `Find ${releaseTime ? `the ${releaseTime} ` : ""}${subject} with verified streaming availability in India.`;
    if (discoveryMode === "theatrical") return `Show ${releaseTime ? `the ${releaseTime} ` : "the latest "}${subject}.`;
    return subject !== "movies" || releaseTime ? `Show ${releaseTime ? `the ${releaseTime} ` : ""}${subject}.` : "";
}

function naturalGenrePhrase(genres) {
    const terms = asArray(genres)
        .slice()
        .sort((left, right) => GENRE_ORDER.indexOf(left) - GENRE_ORDER.indexOf(right))
        .map(value => String(value).toLowerCase());
    if (!terms.length) return "movies";
    if (terms.length === 2 && terms[0] === "romance" && terms[1] === "comedy") return "romantic comedies";
    const last = terms.at(-1);
    const pluralLast = { thriller: "thrillers", comedy: "comedies", drama: "dramas" }[last];
    return pluralLast ? [...terms.slice(0, -1), pluralLast].join(" ") : `${terms.join(" ")} movies`;
}

function renderQueryBuilder() {
    const sentence = buildQuerySentence();
    if (!queryBuilderSentence) return;
    queryBuilderSentence.textContent = sentence || "Choose a language, genre, or release time to build your sentence.";
}

async function handleRecommendationSubmit(event) {
    event.preventDefault();
    const text = input?.value.trim() || "";
    if (!text) return renderError("Please describe what kind of movie you want.");
    const requestText = discoveryRequestText(text);
    activeRequest?.abort();
    const request = new AbortController();
    activeRequest = request;
    setLoading(true);
    window.MovieAISearchIcon?.setLoading(recommendationSearchIcon, true);
    renderLoading();
    try {
        const endpoint = recommendationEndpoint(requestText);
        console.log("[MovieAI] recommendation endpoint:", endpoint);
        const response = await fetch(endpoint, { headers: { Accept: "application/json" }, signal: request.signal });
        const data = await response.json();
        console.log("[MovieAI] response:", data);
        console.log("[MovieAI] result count:", data.results?.length);
        if (!response.ok) throw { status: response.status, data };
        if (!Array.isArray(data.results)) return renderError("No recommendation results were returned.");
        if (!data.results.length) return renderEmpty(data);
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
function discoveryRequestText(text) {
    if (discoveryMode === "catalog") return text;
    const liveText = LATEST_DISCOVERY_PATTERN.test(text) ? text : `latest ${text}`;
    return discoveryMode === "streaming" && !OTT_DISCOVERY_PATTERN.test(liveText) ? `${liveText} available on OTT in India` : liveText;
}
function isDirectTitle(text) { return text.split(/\s+/).length <= 7 && !NATURAL_LANGUAGE_WORDS.test(text); }

function renderLoading() {
    if (!resultsContainer) return;
    resultsContainer.innerHTML = `<div class="recommendation-results-heading"><span>YOUR MOVIE PICKS</span><h2>Finding your movies</h2></div>${window.MovieAILoader.inline("Reading your mood…")}<div class="recommendation-loading-skeletons" aria-hidden="true"><div></div><div></div><div></div></div>`;
}
function renderEmpty(data = {}) {
    if (!resultsContainer) return;
    if (data.mode === "LATEST_OTT") return renderError("No verified streaming matches are available right now. We did not replace them with theatrical releases.");
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
    const streaming = data.mode === "LATEST_OTT";
    const heading = document.createElement("div"); heading.className = "recommendation-results-heading"; heading.innerHTML = `<span>${streaming ? "STREAMING PICKS" : "YOUR MOVIE PICKS"}</span><h2>${streaming ? "Streaming now in India" : "Movies for your mood"}</h2>`; resultsContainer.appendChild(heading);
    const sourceNote = document.createElement("p"); sourceNote.className = "recommendation-source-note";
    sourceNote.textContent = streaming ? "Verified streaming availability in India. Platforms appear on each movie." : data.mode === "LATEST" ? "Recent theatrical releases matching your request." : data.local_fallback_used ? "Catalog matches based on your request." : "Movie matches based on your request.";
    resultsContainer.appendChild(sourceNote);
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
