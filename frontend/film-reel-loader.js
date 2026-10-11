"use strict";

window.MovieAILoader = Object.freeze({
    inline(label = "Loading") {
        return `<div class="film-reel-loader" role="status" aria-live="polite"><div class="film-reel" aria-hidden="true"><span></span><span></span><span></span><span></span><span></span><b></b></div><span class="film-reel-loader-label">${escapeHTML(label)}</span></div>`;
    },
    showFullPage(label = "Loading") {
        let overlay = document.getElementById("movieAiFullPageLoader");
        if (!overlay) {
            overlay = document.createElement("div");
            overlay.id = "movieAiFullPageLoader";
            overlay.className = "film-reel-full-page";
            document.body.appendChild(overlay);
        }
        overlay.innerHTML = this.inline(label);
        overlay.hidden = false;
    },
    hideFullPage() {
        const overlay = document.getElementById("movieAiFullPageLoader");
        if (overlay) overlay.hidden = true;
    }
});

function escapeHTML(value) {
    return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}
