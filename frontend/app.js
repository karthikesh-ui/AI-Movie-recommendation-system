"use strict";

/*
=============================================================
MOVIEAI
F0 — CINEMATIC INTRO
F3 — RECOMMENDATION MODE SELECTION
=============================================================

RESPONSIBILITIES

F0:
- Cinematic landing page
- Enter transition

F3:
- Recommendation mode selection
- Movie search mode selection
- Cursor-reactive character
- Smooth eye tracking
- Four-region facial expressions
- Keyboard interaction
- Touch fallback
- Navigation to existing mode pages
- Direct return to mode selection

ARCHITECTURE

index.html
    ↓
Mode Selection
    ↓
    ├── recommendation.html
    │       ↓
    │   recommendation.js
    │       ↓
    │   Flask API
    │
    └── movie-search.html
            ↓
        movie-search.js
            ↓
        Flask API

IMPORTANT

This file does NOT:
- call Gemini
- call OMDb
- perform TF-IDF
- perform recommendation ranking
- perform filtering
- perform recommendation scoring

Those responsibilities remain in the backend.
=============================================================
*/


/* =========================================================
   DOM REFERENCES
   ========================================================= */

let enterButton = null;
let introPage = null;
let nextPage = null;
let transitionLight = null;

let recommendationMode = null;
let movieSearchMode = null;

let modeSelectionStage = null;
let modeCharacterZone = null;
let movieCharacter = null;
let modeSelectionStatus = null;
let statusText = null;

let characterEyes = [];
let characterBrows = [];
let characterMouth = null;


/* =========================================================
   F0 STATE
   ========================================================= */

let transitionStarted = false;
let f0Locked = false;


/* =========================================================
   F3 STATE
   ========================================================= */

const movieAIState = {
    currentMode: null,
    pointerActive: false,
    pointerX: 0.5,
    pointerY: 0.5,
    expression: "neutral"
};


/* =========================================================
   GLOBAL MOVIEAI OBJECT
   ========================================================= */

window.MovieAI = window.MovieAI || {};

window.MovieAI.state = movieAIState;


/* =========================================================
   F3 CHARACTER CONFIGURATION
   ========================================================= */

const characterConfig = {
    eyeMaxX: 6,
    eyeMaxY: 4,

    smoothing: 0.16,

    deadZoneX: 0.08,
    deadZoneY: 0.08,

    maxAllowedX: 6,
    maxAllowedY: 4
};


/* =========================================================
   CHARACTER ANIMATION STATE
   ========================================================= */

const characterAnimation = {
    currentX: 0,
    currentY: 0,

    targetX: 0,
    targetY: 0,

    frame: null
};


/* =========================================================
   APPLICATION INITIALIZATION
   ========================================================= */

function initializeMovieAI() {

    /*
     * -------------------------------------------------------
     * F0 DOM
     * -------------------------------------------------------
     */

    enterButton =
        document.getElementById("enterButton");

    introPage =
        document.getElementById("introPage");

    nextPage =
        document.getElementById("nextPage");

    transitionLight =
        document.getElementById("transitionLight");


    /*
     * -------------------------------------------------------
     * F3 DOM
     * -------------------------------------------------------
     */

    recommendationMode =
        document.getElementById("recommendationMode");

    movieSearchMode =
        document.getElementById("movieSearchMode");

    modeSelectionStage =
        document.getElementById("modeSelectionStage");

    modeCharacterZone =
        document.getElementById("modeCharacterZone");

    movieCharacter =
        document.getElementById("movieCharacter");

    modeSelectionStatus =
        document.getElementById("modeSelectionStatus");


    /*
     * The HTML uses:
     *
     *     class="status-text"
     *
     * so query it from the status container.
     */

    statusText =
        modeSelectionStatus
            ? modeSelectionStatus.querySelector(
                ".status-text"
            )
            : null;


    /*
     * -------------------------------------------------------
     * Validate F0
     * -------------------------------------------------------
     */

    if (!enterButton) {

        console.error(
            "MovieAI F0: #enterButton was not found."
        );
    }


    if (!introPage) {

        console.error(
            "MovieAI F0: #introPage was not found."
        );
    }


    if (!nextPage) {

        console.error(
            "MovieAI F0: #nextPage was not found."
        );
    }


    if (!transitionLight) {

        console.error(
            "MovieAI F0: #transitionLight was not found."
        );
    }


    /*
     * -------------------------------------------------------
     * Initialize F0 or Direct Mode Selection
     * -------------------------------------------------------
     */

    const isDirectMode =
        window.location.hash === "#nextPage" ||
        document.documentElement.classList.contains("direct-mode");

    if (isDirectMode) {

        document.documentElement.classList.add(
            "direct-mode"
        );

        initializeModeSelection();

        initializeDirectModeSelection();

    } else {

        document.documentElement.classList.remove(
            "direct-mode"
        );

        initializeF0();

        initializeModeSelection();
    }


    /*
     * -------------------------------------------------------
     * Handle browser history & back/forward navigation
     * -------------------------------------------------------
     */

    window.removeEventListener(
        "hashchange",
        handleHashChange
    );

    window.addEventListener(
        "hashchange",
        handleHashChange
    );


    /*
     * -------------------------------------------------------
     * Final message
     * -------------------------------------------------------
     */

    console.log(
        "MovieAI initialized successfully."
    );
}


/* =========================================================
   HASH CHANGE NAVIGATION HANDLER
   ========================================================= */

function handleHashChange() {

    if (window.location.hash === "#nextPage") {

        document.documentElement.classList.add(
            "direct-mode"
        );

        initializeDirectModeSelection();

    } else if (
        !window.location.hash ||
        window.location.hash === "#" ||
        window.location.hash === "#introPage"
    ) {

        document.documentElement.classList.remove(
            "direct-mode"
        );

        resetF0();

        initializeF0();
    }
}


/* =========================================================
   DIRECT MODE SELECTION ENTRY
   ========================================================= */

function initializeDirectModeSelection() {

    /*
     * Required DOM must exist.
     */

    if (!nextPage) {

        console.error(
            "MovieAI: Cannot open mode selection because #nextPage was not found."
        );

        return;
    }


    /*
     * Activate direct mode styling.
     */

    document.documentElement.classList.add(
        "direct-mode"
    );


    /*
     * Mark F0 as already completed.
     */

    transitionStarted = true;
    f0Locked = true;


    /*
     * Hide/disable the landing page.
     */

    if (introPage) {

        introPage.classList.add(
            "exit"
        );

        introPage.classList.remove(
            "animating"
        );

        introPage.style.pointerEvents =
            "none";
    }


    /*
     * The transition light is not needed
     * when returning from another page.
     */

    if (transitionLight) {

        transitionLight.classList.remove(
            "active"
        );
    }


    /*
     * Show the model selection page
     * immediately.
     */

    nextPage.classList.add(
        "visible"
    );


    /*
     * Reset the character so it starts
     * in a clean neutral position.
     */

    resetCharacter();


    /*
     * Ensure no previous mode is selected.
     */

    movieAIState.currentMode =
        null;


    clearCardSelection();


    /*
     * Reset scroll coordinates to (0,0) to prevent
     * horizontal/vertical viewport shift.
     */

    window.scrollTo(0, 0);

    if (document.documentElement) {
        document.documentElement.scrollLeft = 0;
        document.documentElement.scrollTop = 0;
    }

    if (document.body) {
        document.body.scrollLeft = 0;
        document.body.scrollTop = 0;
    }


    console.log(
        "MovieAI F3: Returned directly to mode selection."
    );
}


/* =========================================================
   F0 INITIALIZATION
   ========================================================= */

function initializeF0() {

    resetF0();


    if (!enterButton) {
        return;
    }


    enterButton.removeEventListener(
        "click",
        handleCinemaEntry
    );


    enterButton.addEventListener(
        "click",
        handleCinemaEntry
    );


    enterButton.addEventListener(
        "keydown",
        handleEnterKeyboard
    );


    document.addEventListener(
        "keydown",
        handleGlobalKeyboard
    );
}


/* =========================================================
   F0 RESET
   ========================================================= */

function resetF0() {

    transitionStarted = false;
    f0Locked = false;

    document.documentElement.classList.remove(
        "direct-mode"
    );


    if (introPage) {

        introPage.classList.remove(
            "animating",
            "exit"
        );

        introPage.style.pointerEvents = "";
    }


    if (nextPage) {

        nextPage.classList.remove(
            "visible"
        );
    }


    if (transitionLight) {

        transitionLight.classList.remove(
            "active"
        );
    }


    if (enterButton) {

        enterButton.disabled = false;

        enterButton.removeAttribute(
            "aria-disabled"
        );
    }
}


/* =========================================================
   F0 ENTER CINEMA
   ========================================================= */

function handleCinemaEntry() {

    if (
        transitionStarted ||
        f0Locked
    ) {
        return;
    }


    if (prefersReducedMotion()) {

        enterCinemaAccessible();

        return;
    }


    enterCinema();
}


/* =========================================================
   F0 CINEMATIC TRANSITION
   ========================================================= */

function enterCinema() {

    if (
        !enterButton ||
        !introPage ||
        !nextPage ||
        !transitionLight
    ) {
        return;
    }


    document.documentElement.classList.remove(
        "direct-mode"
    );


    transitionStarted = true;


    enterButton.disabled = true;

    enterButton.setAttribute(
        "aria-disabled",
        "true"
    );


    transitionLight.classList.add(
        "active"
    );


    introPage.classList.add(
        "animating"
    );


    window.setTimeout(
        () => {

            if (nextPage) {

                nextPage.classList.add(
                    "visible"
                );
            }

            resetCharacter();

        },
        350
    );


    window.setTimeout(
        () => {

            if (introPage) {

                introPage.classList.add(
                    "exit"
                );
            }

        },
        600
    );


    window.setTimeout(
        () => {

            f0Locked = true;

            if (introPage) {

                introPage.style.pointerEvents =
                    "none";
            }

            try {
                history.replaceState(
                    null,
                    "",
                    "#nextPage"
                );
            } catch (error) {
                // Ignore navigation state restrictions if any
            }

        },
        1300
    );
}


/* =========================================================
   F0 ACCESSIBLE TRANSITION
   ========================================================= */

function enterCinemaAccessible() {

    if (
        !enterButton ||
        !introPage ||
        !nextPage
    ) {
        return;
    }


    document.documentElement.classList.remove(
        "direct-mode"
    );


    transitionStarted = true;


    enterButton.disabled = true;

    enterButton.setAttribute(
        "aria-disabled",
        "true"
    );


    nextPage.classList.add(
        "visible"
    );


    introPage.classList.add(
        "exit"
    );


    resetCharacter();


    f0Locked = true;

    introPage.style.pointerEvents =
        "none";


    try {
        history.replaceState(
            null,
            "",
            "#nextPage"
        );
    } catch (error) {
        // Ignore navigation state restrictions if any
    }
}


/* =========================================================
   REDUCED MOTION
   ========================================================= */

function prefersReducedMotion() {

    return window.matchMedia(
        "(prefers-reduced-motion: reduce)"
    ).matches;
}


/* =========================================================
   F0 KEYBOARD
   ========================================================= */

function handleEnterKeyboard(event) {

    if (
        event.key === "Enter" ||
        event.key === " "
    ) {

        event.preventDefault();

        handleCinemaEntry();
    }
}


/* =========================================================
   GLOBAL KEYBOARD
   ========================================================= */

function handleGlobalKeyboard(event) {

    const activeElement =
        document.activeElement;


    if (
        activeElement &&
        (
            activeElement.tagName === "INPUT" ||
            activeElement.tagName === "TEXTAREA" ||
            activeElement.tagName === "SELECT"
        )
    ) {
        return;
    }


    if (
        event.key === "Escape" &&
        !transitionStarted
    ) {

        resetF0();
    }
}


/* =========================================================
   F3 INITIALIZATION
   ========================================================= */

function initializeModeSelection() {

    if (!nextPage) {

        console.warn(
            "MovieAI F3: #nextPage was not found."
        );

        return;
    }


    characterEyes =
        Array.from(
            document.querySelectorAll(
                ".character-pupil"
            )
        );


    characterBrows =
        Array.from(
            document.querySelectorAll(
                ".character-brow"
            )
        );


    characterMouth =
        document.querySelector(
            ".character-mouth"
        );


    if (!movieCharacter) {

        console.warn(
            "MovieAI F3: #movieCharacter was not found."
        );
    }


    if (characterEyes.length === 0) {

        console.warn(
            "MovieAI F3: No .character-pupil elements were found."
        );
    }


    /*
     * Recommendation card.
     */

    if (recommendationMode) {

        recommendationMode.addEventListener(
            "click",
            handleRecommendationClick
        );


        recommendationMode.addEventListener(
            "focus",
            () => {

                setExpression(
                    "neutral"
                );
            }
        );
    }


    /*
     * Movie search card.
     */

    if (movieSearchMode) {

        movieSearchMode.addEventListener(
            "click",
            handleMovieSearchClick
        );


        movieSearchMode.addEventListener(
            "focus",
            () => {

                setExpression(
                    "neutral"
                );
            }
        );
    }


    /*
     * Pointer tracking.
     */

    nextPage.addEventListener(
        "pointermove",
        handlePointerMove,
        {
            passive: true
        }
    );


    nextPage.addEventListener(
        "pointerleave",
        handlePointerLeave,
        {
            passive: true
        }
    );


    /*
     * Touch.
     */

    nextPage.addEventListener(
        "touchstart",
        handleTouchStart,
        {
            passive: true
        }
    );


    nextPage.addEventListener(
        "touchmove",
        handleTouchMove,
        {
            passive: true
        }
    );


    resetCharacter();


    console.log(
        "MovieAI F3 mode selection initialized."
    );


    console.log(
        `MovieAI F3: ${characterEyes.length} pupils detected.`
    );
}


/* =========================================================
   F3 CARD CLICK — RECOMMENDATION
   ========================================================= */

function handleRecommendationClick() {

    selectMode(
        "recommendation"
    );
}


/* =========================================================
   F3 CARD CLICK — MOVIE SEARCH
   ========================================================= */

function handleMovieSearchClick() {

    selectMode(
        "movie-search"
    );
}


/* =========================================================
   F3 MODE SELECTION
   ========================================================= */

function selectMode(mode) {

    if (
        mode !== "recommendation" &&
        mode !== "movie-search"
    ) {
        return;
    }


    if (
        movieAIState.currentMode !== null
    ) {
        return;
    }


    movieAIState.currentMode =
        mode;


    clearCardSelection();


    /*
     * Recommendation.
     */

    if (
        mode === "recommendation"
    ) {

        if (recommendationMode) {

            recommendationMode.classList.add(
                "is-selected"
            );

            recommendationMode.setAttribute(
                "aria-pressed",
                "true"
            );
        }


        setExpression(
            "neutral"
        );


        updateModeStatus(
            "Opening recommendation mode..."
        );


        window.setTimeout(
            () => {

                window.location.href =
                    "recommendation.html";

            },
            260
        );


        return;
    }


    /*
     * Movie search.
     */

    if (
        mode === "movie-search"
    ) {

        if (movieSearchMode) {

            movieSearchMode.classList.add(
                "is-selected"
            );

            movieSearchMode.setAttribute(
                "aria-pressed",
                "true"
            );
        }


        setExpression(
            "neutral"
        );


        updateModeStatus(
            "Opening movie search..."
        );


        window.setTimeout(
            () => {

                window.location.href =
                    "movie-search.html";

            },
            260
        );
    }
}


/* =========================================================
   CLEAR CARD SELECTION
   ========================================================= */

function clearCardSelection() {

    if (recommendationMode) {

        recommendationMode.classList.remove(
            "is-selected"
        );

        recommendationMode.setAttribute(
            "aria-pressed",
            "false"
        );
    }


    if (movieSearchMode) {

        movieSearchMode.classList.remove(
            "is-selected"
        );

        movieSearchMode.setAttribute(
            "aria-pressed",
            "false"
        );
    }
}


/* =========================================================
   F3 STATUS
   ========================================================= */

function updateModeStatus(message) {

    if (statusText) {

        statusText.textContent =
            message;
    }


    if (modeSelectionStatus) {

        modeSelectionStatus.classList.add(
            "is-active"
        );
    }
}


/* =========================================================
   F3 POINTER MOVE
   ========================================================= */

function handlePointerMove(event) {

    if (
        !nextPage ||
        !movieCharacter
    ) {
        return;
    }


    if (
        event.pointerType === "mouse" &&
        event.isPrimary === false
    ) {
        return;
    }


    movieAIState.pointerActive =
        true;


    const viewportWidth =
        window.innerWidth;

    const viewportHeight =
        window.innerHeight;


    if (
        viewportWidth <= 0 ||
        viewportHeight <= 0
    ) {
        return;
    }


    let x =
        event.clientX /
        viewportWidth;


    let y =
        event.clientY /
        viewportHeight;


    x =
        clamp(
            x,
            0,
            1
        );


    y =
        clamp(
            y,
            0,
            1
        );


    movieAIState.pointerX =
        x;

    movieAIState.pointerY =
        y;


    updateEyeTarget(
        x,
        y
    );


    updateExpressionFromPointer(
        x,
        y
    );


    startCharacterAnimation();
}


/* =========================================================
   F3 EYE TARGET CALCULATION
   ========================================================= */

function updateEyeTarget(x, y) {

    const centeredX =
        x - 0.5;


    const centeredY =
        y - 0.5;


    let normalizedX =
        centeredX * 2;


    let normalizedY =
        centeredY * 2;


    normalizedX =
        clamp(
            normalizedX,
            -1,
            1
        );


    normalizedY =
        clamp(
            normalizedY,
            -1,
            1
        );


    if (
        Math.abs(normalizedX) <
        characterConfig.deadZoneX
    ) {

        normalizedX = 0;
    }


    if (
        Math.abs(normalizedY) <
        characterConfig.deadZoneY
    ) {

        normalizedY = 0;
    }


    const targetX =
        normalizedX *
        characterConfig.eyeMaxX;


    const targetY =
        normalizedY *
        characterConfig.eyeMaxY;


    characterAnimation.targetX =
        clamp(
            targetX,
            -characterConfig.maxAllowedX,
            characterConfig.maxAllowedX
        );


    characterAnimation.targetY =
        clamp(
            targetY,
            -characterConfig.maxAllowedY,
            characterConfig.maxAllowedY
        );
}


/* =========================================================
   F3 EXPRESSION FROM POINTER
   ========================================================= */

function updateExpressionFromPointer(x, y) {

    /*
     * TOP LEFT     → look left
     * TOP RIGHT    → look right
     * BOTTOM LEFT  → angry
     * BOTTOM RIGHT → confused
     */

    if (y < 0.5) {

        if (x < 0.5) {

            setExpression(
                "left"
            );

        } else {

            setExpression(
                "right"
            );
        }


        return;
    }


    if (x < 0.5) {

        setExpression(
            "angry"
        );

        return;
    }


    setExpression(
        "confused"
    );
}


/* =========================================================
   F3 POINTER LEAVE
   ========================================================= */

function handlePointerLeave() {

    movieAIState.pointerActive =
        false;


    movieAIState.pointerX =
        0.5;

    movieAIState.pointerY =
        0.5;


    characterAnimation.targetX =
        0;

    characterAnimation.targetY =
        0;


    setExpression(
        "neutral"
    );


    startCharacterAnimation();
}


/* =========================================================
   F3 TOUCH START
   ========================================================= */

function handleTouchStart(event) {

    if (
        !event.touches ||
        !event.touches.length
    ) {
        return;
    }


    handleTouchPosition(
        event.touches[0]
    );
}


/* =========================================================
   F3 TOUCH MOVE
   ========================================================= */

function handleTouchMove(event) {

    if (
        !event.touches ||
        !event.touches.length
    ) {
        return;
    }


    handleTouchPosition(
        event.touches[0]
    );
}


/* =========================================================
   F3 TOUCH POSITION
   ========================================================= */

function handleTouchPosition(touch) {

    const viewportWidth =
        window.innerWidth;

    const viewportHeight =
        window.innerHeight;


    if (
        viewportWidth <= 0 ||
        viewportHeight <= 0
    ) {
        return;
    }


    const x =
        clamp(
            touch.clientX /
            viewportWidth,
            0,
            1
        );


    const y =
        clamp(
            touch.clientY /
            viewportHeight,
            0,
            1
        );


    movieAIState.pointerX =
        x;

    movieAIState.pointerY =
        y;

    movieAIState.pointerActive =
        true;


    updateEyeTarget(
        x,
        y
    );


    updateExpressionFromPointer(
        x,
        y
    );


    startCharacterAnimation();
}


/* =========================================================
   F3 CHARACTER EXPRESSION
   ========================================================= */

function setExpression(expression) {

    if (!modeCharacterZone) {
        return;
    }


    const allowedExpressions = [
        "neutral",
        "left",
        "right",
        "angry",
        "confused"
    ];


    if (
        !allowedExpressions.includes(
            expression
        )
    ) {
        expression = "neutral";
    }


    if (
        movieAIState.expression === expression
    ) {
        return;
    }


    movieAIState.expression =
        expression;


    modeCharacterZone.classList.remove(
        "is-neutral",
        "is-left",
        "is-right",
        "is-angry",
        "is-confused",
        "is-top",
        "is-bottom"
    );


    modeCharacterZone.classList.add(
        `is-${expression}`
    );


    applyExpressionStyles(
        expression
    );
}


/* =========================================================
   F3 DIRECT EXPRESSION STYLES
   ========================================================= */

function applyExpressionStyles(expression) {

    characterBrows.forEach(
        brow => {

            brow.style.transform = "";
        }
    );


    if (characterMouth) {

        characterMouth.style.transform = "";
    }


    if (
        expression === "neutral"
    ) {

        return;
    }


    if (
        expression === "left"
    ) {

        setBrowTransforms(
            "-4deg",
            "4deg"
        );

        return;
    }


    if (
        expression === "right"
    ) {

        setBrowTransforms(
            "4deg",
            "-4deg"
        );

        return;
    }


    if (
        expression === "angry"
    ) {

        setBrowTransforms(
            "14deg",
            "-14deg"
        );


        if (characterMouth) {

            characterMouth.style.transform =
                "translateX(-50%) translateY(2px) scaleX(0.82)";
        }


        return;
    }


    if (
        expression === "confused"
    ) {

        setBrowTransforms(
            "-12deg",
            "8deg"
        );


        if (characterMouth) {

            characterMouth.style.transform =
                "translateX(-50%) translateY(1px) rotate(-5deg) scaleX(0.9)";
        }
    }
}


/* =========================================================
   BROW TRANSFORMS
   ========================================================= */

function setBrowTransforms(
    leftTransform,
    rightTransform
) {

    const leftBrow =
        document.querySelector(
            ".character-brow-left"
        );


    const rightBrow =
        document.querySelector(
            ".character-brow-right"
        );


    if (leftBrow) {

        leftBrow.style.transform =
            `rotate(${leftTransform})`;
    }


    if (rightBrow) {

        rightBrow.style.transform =
            `rotate(${rightTransform})`;
    }
}


/* =========================================================
   F3 RESET CHARACTER
   ========================================================= */

function resetCharacter() {

    characterAnimation.currentX =
        0;

    characterAnimation.currentY =
        0;

    characterAnimation.targetX =
        0;

    characterAnimation.targetY =
        0;


    if (movieCharacter) {

        movieCharacter.style.setProperty(
            "--look-x",
            "0px"
        );

        movieCharacter.style.setProperty(
            "--look-y",
            "0px"
        );
    }


    movieAIState.pointerX =
        0.5;

    movieAIState.pointerY =
        0.5;

    movieAIState.pointerActive =
        false;


    movieAIState.expression =
        "neutral";


    if (modeCharacterZone) {

        modeCharacterZone.classList.remove(
            "is-neutral",
            "is-left",
            "is-right",
            "is-angry",
            "is-confused",
            "is-top",
            "is-bottom"
        );

        modeCharacterZone.classList.add(
            "is-neutral"
        );
    }


    characterBrows.forEach(
        brow => {

            brow.style.transform = "";
        }
    );


    if (characterMouth) {

        characterMouth.style.transform = "";
    }
}


/* =========================================================
   F3 SMOOTH CHARACTER ANIMATION
   ========================================================= */

function startCharacterAnimation() {

    if (
        characterAnimation.frame !== null
    ) {
        return;
    }


    const animate = () => {

        const differenceX =
            characterAnimation.targetX -
            characterAnimation.currentX;


        const differenceY =
            characterAnimation.targetY -
            characterAnimation.currentY;


        characterAnimation.currentX +=
            differenceX *
            characterConfig.smoothing;


        characterAnimation.currentY +=
            differenceY *
            characterConfig.smoothing;


        applyEyePosition(
            characterAnimation.currentX,
            characterAnimation.currentY
        );


        const stillMoving =
            Math.abs(
                differenceX
            ) > 0.01 ||
            Math.abs(
                differenceY
            ) > 0.01;


        if (stillMoving) {

            characterAnimation.frame =
                window.requestAnimationFrame(
                    animate
                );

        } else {

            characterAnimation.currentX =
                characterAnimation.targetX;

            characterAnimation.currentY =
                characterAnimation.targetY;


            applyEyePosition(
                characterAnimation.currentX,
                characterAnimation.currentY
            );


            characterAnimation.frame =
                null;
        }
    };


    characterAnimation.frame =
        window.requestAnimationFrame(
            animate
        );
}


/* =========================================================
   F3 APPLY EYE POSITION
   ========================================================= */

function applyEyePosition(x, y) {

    const safeX =
        clamp(
            x,
            -characterConfig.maxAllowedX,
            characterConfig.maxAllowedX
        );


    const safeY =
        clamp(
            y,
            -characterConfig.maxAllowedY,
            characterConfig.maxAllowedY
        );


    if (movieCharacter) {

        movieCharacter.style.setProperty(
            "--look-x",
            `${safeX}px`
        );

        movieCharacter.style.setProperty(
            "--look-y",
            `${safeY}px`
        );
    }
}


/* =========================================================
   UTILITY — CLAMP
   ========================================================= */

function clamp(
    value,
    minimum,
    maximum
) {

    return Math.max(
        minimum,
        Math.min(
            maximum,
            value
        )
    );
}


/* =========================================================
   START APPLICATION
   ========================================================= */

document.addEventListener(
    "DOMContentLoaded",
    initializeMovieAI
);