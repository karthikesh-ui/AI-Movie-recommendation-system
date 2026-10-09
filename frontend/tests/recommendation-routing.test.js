"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

class Element {
    constructor() {
        this.children = [];
        this.style = {};
        this.textContent = "";
    }

    appendChild(child) {
        this.children.push(child);
        return child;
    }
}

const context = {
    window: { location: { protocol: "http:", port: "5000", origin: "http://127.0.0.1:5000" } },
    document: {
        getElementById: () => null,
        querySelectorAll: () => [],
        createElement: () => new Element(),
    },
    console,
    setTimeout,
    clearTimeout,
};

vm.createContext(context);
vm.runInContext(
    `${fs.readFileSync("frontend/recommendation.js", "utf8")}\nglobalThis.movieAiTest = { recommendationEndpoint, createMovieCard };`,
    context,
);

const { recommendationEndpoint, createMovieCard } = context.movieAiTest;

assert.match(recommendationEndpoint("RRR"), /\/recommend\?title=RRR$/);
assert.match(recommendationEndpoint("recommend movies similar to RRR"), /\/recommend\?title=RRR$/);
assert.match(recommendationEndpoint("latest Telugu action movies"), /\/recommend-hybrid\?text=latest%20Telugu%20action%20movies$/);
assert.match(recommendationEndpoint("latest Telugu movies"), /\/recommend-hybrid\?text=latest%20Telugu%20movies$/);
assert.match(recommendationEndpoint("I want an impossible genre"), /\/recommend-text\?text=/);

const hybridCard = createMovieCard({
    title: "Anakapalli",
    poster_url: "https://image.test/tmdb.jpg",
    poster: "https://image.test/local.jpg",
    genres: ["Action"],
    language: ["te"],
    overview: "Live TMDB result.",
    availability_status: "not_checked",
    streaming_sources: [{ name: "Netflix" }],
});
assert.equal(hybridCard.children[0].src, "https://image.test/tmdb.jpg");
assert(!hybridCard.children[1].children.some(item => item.textContent.startsWith("Streaming:")));

const availableCard = createMovieCard({
    title: "Example",
    availability_status: "verified_available",
    streaming_sources: [{ name: "Netflix" }],
});
assert(availableCard.children[0].children.some(item => item.textContent === "Streaming: Netflix"));

console.log("recommendation routing and hybrid card mapping passed");
