"use strict";

/* Shared, dependency-free search icon for MovieAI search controls. */
window.MovieAISearchIcon = Object.freeze({
    mount(root = document) {
        root.querySelectorAll("[data-movieai-search-icon]").forEach(element => {
            if (element.firstElementChild) return;
            element.innerHTML = `<svg class="movieai-search-icon-svg magnifier-icon" viewBox="0 0 200 200" aria-hidden="true" focusable="false"><g class="movieai-search-icon__mark"><circle class="movieai-search-icon__ring magnifier-lens" cx="91" cy="81" r="67"/><path class="movieai-search-icon__handle magnifier-handle" d="M140 130 L184 174"/></g></svg>`;
        });
    },
    setLoading(element, isLoading) {
        element?.classList.toggle("is-loading", Boolean(isLoading));
    },
    pop(element) {
        if (!element) return;
        element.classList.remove("is-popping");
        void element.offsetWidth;
        element.classList.add("is-popping");
    }
});

window.MovieAISearchIcon.mount();
