"use strict";

/* A shared, frontend-only zero-results treatment. It is never used for API failures. */
window.MovieAIEmptyState = (() => {
    const states = [
        { expression: "confused", title: "This movie trail went cold.", subtitle: "Even our tiny cinema detective could not find a match. Try broadening the mood, language, or genre." },
        { expression: "shocked", title: "Plot twist: nothing showed up.", subtitle: "We checked behind the couch, under the popcorn, and inside the trailer. Try a simpler movie idea." },
        { expression: "suspicious", title: "Wrong universe, perhaps?", subtitle: "Those movies may be playing in another multiverse. A shorter search can bring them back to this screen." },
        { expression: "sleepy", title: "This scene missed the final cut.", subtitle: "Our projector is taking a tiny intermission. Change one detail and let us roll again." },
        { expression: "determined", title: "The movies escaped this time.", subtitle: "They slipped out through the end credits. Pick an idea below and our detective will chase them down." },
        { expression: "confused", title: "The director shouted action. Nobody came.", subtitle: "Our cast list is empty for that search. Try a different genre, language, or a shorter description." },
        { expression: "shocked", title: "The sequel has no first part.", subtitle: "We searched every reel we could find, but this query did not make it past auditions." },
        { expression: "suspicious", title: "This clue needs a better screenplay.", subtitle: "Give us one strong detail — a title, language, mood, or genre — and we will investigate again." },
        { expression: "sleepy", title: "Our popcorn went cold waiting for that one.", subtitle: "No matching title arrived. Try a broader request before the lights come back up." },
        { expression: "determined", title: "The credits rolled a little early.", subtitle: "There are no matches in this take, but a new search could be the comeback scene." },
        { expression: "confused", title: "This trailer forgot to release the movie.", subtitle: "We have the screen ready, but not a matching title. Try fewer details or a familiar movie name." },
        { expression: "shocked", title: "Even the villain could not find this movie.", subtitle: "That is a dramatic zero. Adjust the genre or language and let us try the next scene." },
        { expression: "suspicious", title: "A suspiciously empty screening.", subtitle: "Our detective found no tickets for that request. Try another clue and we will reopen the case." },
        { expression: "sleepy", title: "This search is stuck in the interval.", subtitle: "No results walked onto the stage. A small rewrite to your search may wake the catalogue up." },
        { expression: "determined", title: "Take two? The camera is ready.", subtitle: "Nothing matched in the first take. Choose a prompt below or send us a fresh movie clue." }
    ];
    let previousIndex = -1;

    function next() {
        const choices = states.map((_, index) => index).filter(index => index !== previousIndex);
        const index = choices[Math.floor(Math.random() * choices.length)];
        previousIndex = index;
        return states[index];
    }

    function escapeHTML(value) {
        return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
    }

    function mascot(expression) {
        return `<svg class="movieai-empty-mascot" viewBox="0 0 180 150" role="img" aria-label="A puzzled MovieAI cinema detective"><g class="movieai-empty-mascot__shadow" aria-hidden="true"><ellipse cx="88" cy="133" rx="48" ry="8" /></g><g class="movieai-empty-mascot__body"><path class="movieai-empty-mascot__ticket" d="M38 45 H113 A15 15 0 0 0 128 60 V70 A9 9 0 0 0 128 88 V98 A15 15 0 0 0 113 113 H38 A15 15 0 0 0 23 98 V88 A9 9 0 0 0 23 70 V60 A15 15 0 0 0 38 45Z"/><path class="movieai-empty-mascot__ticket-line" d="M45 57 H104 M45 103 H104"/><path class="movieai-empty-mascot__brow movieai-empty-mascot__brow--left" d="M49 67 Q58 60 67 66"/><path class="movieai-empty-mascot__brow movieai-empty-mascot__brow--right" d="M82 66 Q91 60 100 67"/><circle class="movieai-empty-mascot__eye movieai-empty-mascot__eye--left" cx="60" cy="81" r="10"/><circle class="movieai-empty-mascot__eye movieai-empty-mascot__eye--right" cx="89" cy="81" r="10"/><circle class="movieai-empty-mascot__pupil movieai-empty-mascot__pupil--left" cx="61" cy="83" r="3.5"/><circle class="movieai-empty-mascot__pupil movieai-empty-mascot__pupil--right" cx="90" cy="83" r="3.5"/><path class="movieai-empty-mascot__mouth" d="M67 99 Q75 104 83 99"/><g class="movieai-empty-mascot__glass"><circle cx="125" cy="96" r="14"/><path d="M135 107 L150 122"/><path class="movieai-empty-mascot__scan" d="M113 84 L91 66"/></g></g></svg>`;
    }

    function render({ actions = [], clear = true } = {}) {
        const state = next();
        const buttons = actions.map(action => `<button type="button" data-empty-query="${escapeHTML(action.query)}">${escapeHTML(action.label)}</button>`).join("");
        return `<section class="movieai-empty-state movieai-empty-state--${state.expression}" role="status"><div class="movieai-empty-state__mascot">${mascot(state.expression)}</div><div class="movieai-empty-state__content"><p class="movieai-empty-state__eyebrow">NO MATCH THIS TIME</p><h2>${escapeHTML(state.title)}</h2><p>${escapeHTML(state.subtitle)}</p><div class="movieai-empty-state__actions">${buttons}</div>${clear ? '<button type="button" class="movieai-empty-state__clear" data-empty-clear>Clear search</button>' : ""}</div></section>`;
    }

    return Object.freeze({ render });
})();
