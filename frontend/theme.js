"use strict";

(() => {
    const storageKey = "movieai-theme";
    const buttons = document.querySelectorAll("[data-theme-toggle]");

    let savedTheme = null;
    try {
        savedTheme = localStorage.getItem(storageKey);
    } catch {
        savedTheme = null;
    }

    const initialTheme = ["light", "dark"].includes(savedTheme)
        ? savedTheme
        : window.matchMedia("(prefers-color-scheme: dark)").matches
            ? "dark"
            : "light";

    function applyTheme(theme) {
        const isDark = theme === "dark";
        document.documentElement.dataset.theme = theme;

        buttons.forEach(button => {
            const label = isDark ? "Switch to light mode" : "Switch to dark mode";
            button.setAttribute("aria-label", label);
            button.setAttribute("title", label);
            button.setAttribute("aria-pressed", String(isDark));
            button.innerHTML = `<span class="material-symbols-rounded" aria-hidden="true">${isDark ? "light_mode" : "dark_mode"}</span>`;
        });
    }

    applyTheme(initialTheme);

    buttons.forEach(button => {
        button.addEventListener("click", () => {
            const nextTheme = document.documentElement.dataset.theme === "dark"
                ? "light"
                : "dark";

            applyTheme(nextTheme);
            try {
                localStorage.setItem(storageKey, nextTheme);
            } catch {
                // Theme remains active for the current page.
            }
        });
    });
})();