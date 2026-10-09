---
version: alpha
name: "MovieAI"
description: "A blue-and-white movie discovery product that makes current Indian cinema searchable without losing the familiar local-similarity experience."
colors:
  primary: "#0879df"
  background: "#ffffff"
  text: "#11151b"
  muted: "#52667d"
  surface: "#edf4fa"
typography:
  display:
    fontFamily: "Outfit, sans-serif"
  sans:
    fontFamily: "Plus Jakarta Sans, sans-serif"
rounded:
  card: "22px"
  poster: "14px"
spacing:
  grid-gap: "20px"
  card-padding: "18px"
components:
  movie-card: {}
  search-input: {}
  button: {}
---

# MovieAI Design System

## Overview

### Creative North Star

MovieAI takes its visual cues from a well-kept cinema programme: clear information, a bright blue cue for discovery, and one restrained moment of motion on a film card.

### Product context and register

- **Audience and primary job:** People searching for an Indian film and deciding what to watch next.
- **Register:** Hybrid product/brand. Search and metadata are practical; posters and recommendation cards carry the cinematic expression.
- **Memorable signature:** The dedicated movie-details hero responds with a small physical tilt and a cool-blue moving light.
- **Restraint:** Search controls, search-result cards, and metadata stay flat, readable, and stable.
- **Anti-references:** Do not turn the product into a dark streaming dashboard, a generic admin UI, or a high-motion gaming-card interface.
- **Token ownership/runtime mapping:** `frontend/styles.css` remains the canonical runtime source. This document mirrors the accepted values used by the search page.

## Colors

`#0879df` is the action and discovery blue. White is the primary content surface; `#11151b` carries titles and `#52667d` carries supporting facts. `#edf4fa` is reserved for poster fallbacks and quiet supporting surfaces. Dark mode uses the existing theme overrides in `frontend/styles.css` without changing semantic hierarchy.

## Typography

Outfit is the display face for movie titles and section headings. Plus Jakarta Sans supports metadata, labels, controls, and explanations. Movie title and metadata truncation must never hide the only actionable identity.

## Layout

The search page keeps its existing generous whitespace, two-column desktop result grid, and single-column mobile grid. The dedicated details route keeps the same visual system and presents one large hero card beside verified metadata.

## Elevation & Depth

Cards use a soft blue-grey shadow and a thin blue border. Search-result cards receive only a lift; the details hero card alone uses transform-based tilt, without changing layout.

## Shapes

Search and movie cards use rounded, friendly corners. Standard movie cards use the `card` radius; posters use the smaller `poster` radius.

## Components

### Foundational visual states

Search cards retain the existing hover, focus, error, empty, and loading states. The details hero card adds a focus-visible state and reduced-motion-safe pointer tilt.

### Motion

The details hero effect uses a maximum 9-degree axis rotation and a low-opacity blue spotlight. It is disabled for reduced motion and non-fine pointers.

## Do's and Don'ts

- **Do:** Show provider-backed movie metadata exactly as returned, with missing values omitted rather than invented.
- **Do:** Keep TMDB identity through selection and recommendation requests.
- **Don't:** Replace real posters with stock imagery.
- **Don't:** use tilt on search results or selected-movie details; it belongs only to the “You may also like” cards.
