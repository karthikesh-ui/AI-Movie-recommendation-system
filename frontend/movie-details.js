"use strict";

const API_BASE = window.MOVIEAI_API_BASE ||
    (window.location.protocol === "file:" || ["5500", "5501"].includes(window.location.port)
        ? "http://127.0.0.1:5000/api" : `${window.location.origin}/api`);
let expandableContentId = 0;

document.addEventListener("DOMContentLoaded", () => {
    const container = document.getElementById("movieDetailsContent");
    const backButton = document.getElementById("backToSearchBtn");
    const params = new URLSearchParams(window.location.search);
    const title = params.get("title")?.trim();
    backButton?.addEventListener("click", () => {
        if (document.referrer && window.history.length > 1) window.history.back();
        else window.location.assign("movie-search.html");
    });
    if (!container) return;
    if (!title) return renderMessage(container, "Movie details are unavailable.", "Return to search and choose a movie.");
    loadMovie(container, title, params);
});

async function loadMovie(container, title, params) {
    renderLoading(container);
    const identity = new URLSearchParams({ title });
    if (/^\d{4}$/.test(params.get("year") || "")) identity.set("year", params.get("year"));
    if (isPresent(params.get("imdb_id"))) identity.set("imdb_id", params.get("imdb_id"));
    try {
        const response = await fetch(`${API_BASE}/movie?${identity.toString()}`, { headers: { Accept: "application/json" } });
        const movie = await parseJSON(response);
        if (!response.ok || !movie?.title) throw new Error(movie?.error || "Movie details are unavailable.");
        renderMovieDetails(container, movie);
        loadRecommendations(container, movie);
    } catch (error) {
        console.error("Movie details error:", error);
        renderMessage(container, "Movie details are unavailable.", error.message || "Please return to search and try again.");
    } finally {
        container.setAttribute("aria-busy", "false");
    }
}

function renderMovieDetails(container, movie) {
    container.replaceChildren();
    const layout = element("article", "details-layout");
    const showcase = element("div", "details-3d-showcase");
    const wrapper = element("div", "details-3d-card-wrapper");
    const card = element("div", "large-3d-movie-card");
    card.tabIndex = 0;
    card.setAttribute("aria-label", `${movie.title} poster. Move the pointer over the card for a visual effect.`);
    const cardContent = element("div", "card-3d-content");
    const poster = movie.poster_url || movie.poster;
    if (isPresent(poster)) {
        const image = document.createElement("img");
        image.className = "card-3d-poster";
        image.src = poster;
        image.alt = `${movie.title} poster`;
        image.onerror = () => image.replaceWith(posterFallback(movie));
        cardContent.appendChild(image);
    } else cardContent.appendChild(posterFallback(movie));
    const badges = element("div", "card-3d-badges");
    if (isPresent(movie.rating)) badges.appendChild(badge("star", movie.rating, "badge-3d badge-3d--rating"));
    if (isPresent(movie.year)) badges.appendChild(badge("calendar_month", movie.year, "badge-3d badge-3d--year"));
    cardContent.appendChild(badges);
    const footer = element("div", "card-3d-footer");
    footer.append(icon("verified"), text(movie.source || "Movie details"));
    cardContent.appendChild(footer);
    card.append(cardContent, element("div", "card-3d-glare"), element("div", "card-3d-glow"));
    wrapper.appendChild(card);
    showcase.appendChild(wrapper);
    layout.append(showcase, createInformation(movie));
    container.appendChild(layout);
    enableHeroTilt(card);
}

async function loadRecommendations(container, movie) {
    const section = element("section", "local-recommendations");
    const heading = element("div", "local-recommendations-heading");
    heading.append(text("YOU MAY ALSO LIKE", "movie-search-eyebrow"), text("You May Also Like", "local-recommendations-title", "h2"));
    const genres = (Array.isArray(movie.genres) ? movie.genres : String(movie.genre || "").split(",")).filter(isPresent);
    heading.appendChild(text(genres.length ? `Based on ${genres.join(" · ")}` : "From the local movie catalog", "local-recommendations-subtitle", "p"));
    const grid = element("div", "local-recommendations-grid");
    grid.appendChild(text("Finding local recommendations…", "local-recommendations-loading", "p"));
    section.append(heading, grid);
    container.appendChild(section);
    const query = new URLSearchParams({ title: movie.title, genre: genres.join(",") });
    if (/^\d{4}$/.test(String(movie.year || ""))) query.set("year", movie.year);
    if (isPresent(movie.imdb_id)) query.set("imdb_id", movie.imdb_id);
    if (isPresent(movie.language)) query.set("language", movie.language);
    if (isPresent(movie.director)) query.set("director", movie.director);
    if (isPresent(movie.cast)) query.set("cast", movie.cast);
    try {
        const response = await fetch(`${API_BASE}/recommend?${query.toString()}`, { headers: { Accept: "application/json" } });
        const data = await parseJSON(response);
        if (!response.ok || !Array.isArray(data?.results) || !data.results.length) throw new Error("No local recommendations found.");
        grid.replaceChildren(...data.results.map(createRecommendationCard));
    } catch (error) {
        grid.replaceChildren(text("No local recommendations are available for this movie yet.", "local-recommendations-loading", "p"));
    }
}

function createRecommendationCard(movie) {
    const card = element("article", "local-recommendation-card");
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.setAttribute("aria-label", `View details for ${movie.title}`);
    const open = () => {
        const query = new URLSearchParams({ title: movie.title });
        if (/^\d{4}$/.test(String(movie.year || ""))) query.set("year", movie.year);
        if (isPresent(movie.imdb_id)) query.set("imdb_id", movie.imdb_id);
        window.location.assign(`movie-details.html?${query.toString()}`);
    };
    card.addEventListener("click", open);
    card.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); }
    });
    const poster = movie.poster_url || movie.poster;
    if (isPresent(poster)) {
        const image = document.createElement("img");
        image.className = "local-recommendation-poster";
        image.src = poster;
        image.alt = `${movie.title} poster`;
        image.loading = "lazy";
        image.onerror = () => image.replaceWith(recommendationPosterFallback());
        card.appendChild(image);
    } else card.appendChild(recommendationPosterFallback());
    const content = element("div", "local-recommendation-content");
    content.append(text(movie.title, "local-recommendation-title", "h3"));
    const metadata = [movie.year, isPresent(movie.rating) ? `★ ${movie.rating}` : ""].filter(isPresent).join(" · ");
    if (metadata) content.appendChild(text(metadata, "local-recommendation-meta", "p"));
    const genre = Array.isArray(movie.genres) ? movie.genres.join(" · ") : movie.genre;
    if (isPresent(genre)) content.appendChild(text(genre, "local-recommendation-genre", "p"));
    card.appendChild(content);
    enableCardTilt(card);
    return card;
}

function recommendationPosterFallback() {
    const fallback = element("div", "local-recommendation-poster local-recommendation-poster-fallback");
    fallback.append(icon("movie"), text("Poster unavailable", "local-recommendation-poster-label"));
    return fallback;
}

function createInformation(movie) {
    const info = element("section", "details-info-container");
    const header = element("header", "details-header");
    const badges = element("div", "details-badges-row");
    badges.appendChild(badge("movie", "MOVIE DETAILS", "details-cinema-badge"));
    if (isPresent(movie.source)) badges.appendChild(text(movie.source, "details-source-badge"));
    header.appendChild(badges);
    header.appendChild(text(movie.title, "details-title", "h1"));
    const chips = element("div", "details-meta-chips");
    addIf(chips, movie.year, "calendar_month");
    addIf(chips, movie.rating, "star", "meta-chip meta-chip--star");
    addIf(chips, movie.runtime, "schedule");
    addIf(chips, movie.language, "translate", "meta-chip meta-chip--lang");
    if (chips.children.length) header.appendChild(chips);
    info.appendChild(header);
    const genres = Array.isArray(movie.genres) ? movie.genres : String(movie.genre || "").split(",");
    const validGenres = genres.filter(isPresent);
    if (validGenres.length) {
        const group = element("div", "details-genre-group");
        group.appendChild(text("Genre", "genre-group-label"));
        const pills = element("div", "genre-pills");
        validGenres.forEach(genre => pills.appendChild(text(genre, "genre-pill")));
        group.appendChild(pills);
        info.appendChild(group);
    }
    if (isPresent(movie.plot) || isPresent(movie.overview)) {
        const plot = element("section", "details-plot-card");
        const heading = text("Plot", "details-section-title", "h2");
        heading.prepend(icon("theater_comedy"));
        plot.append(heading, createExpandableText(cleanPlot(movie.plot || movie.overview), "details-plot-text", "Read more", "Show less", 220));
        info.appendChild(plot);
    }
    const credits = element("div", "details-credits-container");
    addCredit(credits, "person", "Director", movie.director);
    addCredit(credits, "edit_note", "Writer", movie.writer);
    addExpandableCredit(credits, "groups", "Cast", movie.cast, true);
    addCredit(credits, "public", "Country", movie.country);
    addCredit(credits, "event", "Released", movie.released);
    addCredit(credits, "workspace_premium", "Awards", movie.awards, true);
    addCredit(credits, "analytics", "Metascore", movie.metascore);
    if (credits.children.length) info.appendChild(credits);
    if (isPresent(movie.imdb_id) || isPresent(movie.imdb_votes) || isPresent(movie.imdb_rating)) info.appendChild(createImdb(movie));
    return info;
}

function createImdb(movie) {
    const section = element("section", "details-imdb-section");
    section.appendChild(text("IMDb", "imdb-brand-badge"));
    const meta = element("div", "imdb-meta-content");
    if (isPresent(movie.imdb_rating)) {
        const rating = element("div", "imdb-rating-row");
        rating.append(icon("star", "imdb-star-icon"), text(movie.imdb_rating, "imdb-rating-val"), text("/ 10", "imdb-rating-max"));
        if (isPresent(movie.imdb_votes)) rating.appendChild(text(`${movie.imdb_votes} votes`, "imdb-votes-text"));
        meta.appendChild(rating);
    }
    if (isPresent(movie.imdb_id)) meta.appendChild(text(`IMDb ID: ${movie.imdb_id}`, "imdb-id-display"));
    section.appendChild(meta);
    if (isPresent(movie.imdb_id)) {
        const link = document.createElement("a");
        link.className = "imdb-external-button";
        link.href = `https://www.imdb.com/title/${encodeURIComponent(movie.imdb_id)}/`;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.append(icon("open_in_new"), text("Open IMDb"));
        section.appendChild(link);
    }
    return section;
}

function addCredit(container, iconName, label, value, wide = false) {
    if (!isPresent(value)) return;
    const box = element("div", `credit-box${wide ? " credit-box--wide" : ""}`);
    const iconBox = element("div", "credit-icon-wrapper");
    iconBox.appendChild(icon(iconName));
    const content = element("div", "credit-content");
    content.append(text(label, "credit-label"), text(value, "credit-name"));
    box.append(iconBox, content);
    container.appendChild(box);
}

function addExpandableCredit(container, iconName, label, value, wide = false) {
    if (!isPresent(value)) return;
    const cast = String(value).split(",").map(item => item.trim()).filter(Boolean);
    const box = element("div", `credit-box${wide ? " credit-box--wide" : ""}`);
    const iconBox = element("div", "credit-icon-wrapper");
    const content = element("div", "credit-content");
    iconBox.appendChild(icon(iconName));
    content.appendChild(text(label, "credit-label"));
    content.appendChild(createExpandableText(cast.join(", "), "credit-name", "Show full cast", "Show less", 3, cast));
    box.append(iconBox, content);
    container.appendChild(box);
}

function createExpandableText(value, className, moreLabel, lessLabel, threshold, listItems = null) {
    const full = String(value || "").trim();
    const itemCount = listItems?.length || 0;
    const shouldExpand = itemCount ? itemCount > threshold : full.length > threshold;
    const preview = itemCount ? `${listItems.slice(0, threshold).join(", ")}, \u2026` : truncateAtWord(full, threshold);
    const content = text(shouldExpand ? preview : full, className, "p");
    if (!shouldExpand) return content;
    const id = `expandable-content-${++expandableContentId}`;
    const wrapper = element("div", "expandable-content");
    const button = element("button", "details-expand-button", "button");
    content.id = id;
    button.type = "button";
    button.setAttribute("aria-controls", id);
    button.setAttribute("aria-expanded", "false");
    button.textContent = moreLabel;
    button.addEventListener("click", () => {
        const expanded = button.getAttribute("aria-expanded") === "true";
        button.setAttribute("aria-expanded", String(!expanded));
        button.textContent = expanded ? moreLabel : lessLabel;
        content.textContent = expanded ? preview : full;
    });
    wrapper.append(content, button);
    return wrapper;
}

function truncateAtWord(value, limit) {
    if (value.length <= limit) return value;
    const shortened = value.slice(0, limit + 1).replace(/\s+\S*$/, "").trim();
    return `${shortened || value.slice(0, limit).trim()}\u2026`;
}

function cleanPlot(value) {
    return String(value || "").replace(/\s+/g, " ").replace(/\s+([,.;:!?])/g, "$1").trim();
}

function addIf(container, value, iconName, className = "meta-chip") {
    if (isPresent(value)) container.appendChild(badge(iconName, value, className));
}

function badge(iconName, value, className) {
    const item = element("span", className);
    item.append(icon(iconName), text(value));
    return item;
}

function posterFallback(movie) {
    const fallback = element("div", "card-3d-poster-fallback");
    fallback.append(icon("movie", "fallback-icon"), text(movie.title || "Movie", "fallback-title"));
    if (isPresent(movie.genre)) fallback.appendChild(text(movie.genre, "fallback-genre"));
    return fallback;
}

function enableHeroTilt(card) {
    const canTilt = window.matchMedia("(hover: hover) and (pointer: fine)").matches &&
        !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!canTilt) return;
    card.addEventListener("pointermove", event => {
        const bounds = card.getBoundingClientRect();
        const x = (event.clientX - bounds.left) / bounds.width;
        const y = (event.clientY - bounds.top) / bounds.height;
        card.style.setProperty("--tilt-x", `${(0.5 - y) * 14}deg`);
        card.style.setProperty("--tilt-y", `${(x - 0.5) * 14}deg`);
        card.style.setProperty("--glare-x", `${x * 100}%`);
        card.style.setProperty("--glare-y", `${y * 100}%`);
        card.classList.add("is-tilting");
    });
    card.addEventListener("pointerleave", () => card.classList.remove("is-tilting"));
}

function enableCardTilt(card) {
    if (!window.matchMedia("(hover: hover) and (pointer: fine)").matches || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    card.addEventListener("pointermove", event => {
        const bounds = card.getBoundingClientRect();
        const x = (event.clientX - bounds.left) / bounds.width;
        const y = (event.clientY - bounds.top) / bounds.height;
        card.style.setProperty("--card-x", `${x * 100}%`);
        card.style.setProperty("--card-y", `${y * 100}%`);
        card.style.setProperty("--card-tilt-x", `${(0.5 - y) * 12}deg`);
        card.style.setProperty("--card-tilt-y", `${(x - 0.5) * 12}deg`);
        card.classList.add("is-tilting");
    });
    card.addEventListener("pointerleave", () => card.classList.remove("is-tilting"));
}

function renderLoading(container) {
    container.innerHTML = '<div class="movie-search-loading"><div class="movie-search-spinner"></div><p>Loading movie details...</p></div>';
}
function renderMessage(container, title, message) {
    container.innerHTML = `<div class="movie-search-error"><h2>${escapeHTML(title)}</h2><p>${escapeHTML(message)}</p></div>`;
    container.setAttribute("aria-busy", "false");
}
function element(tag, className = "") { const node = document.createElement(tag); node.className = className; return node; }
function text(value, className = "", tag = "span") { const node = element(tag, className); node.textContent = String(value); return node; }
function icon(name, className = "") { const node = text(name, `material-symbols-rounded ${className}`.trim()); node.setAttribute("aria-hidden", "true"); return node; }
function isPresent(value) { return value !== null && value !== undefined && String(value).trim() !== "" && String(value).trim() !== "N/A"; }
async function parseJSON(response) { const content = await response.text(); try { return content ? JSON.parse(content) : null; } catch (_) { return null; } }
function escapeHTML(value) { const node = document.createElement("div"); node.textContent = String(value || ""); return node.innerHTML; }
