````markdown
# Movie AI — AI Movie Recommendation System

MovieAI is an AI-assisted Indian movie recommendation system that combines a deterministic content-based recommendation engine with natural-language understanding and optional external movie enrichment.

The system is designed so that the **Indian movie dataset remains the source of truth for movie recommendations**.

---

## Project Overview

The system provides:

- Movie title-based recommendations
- Natural-language movie recommendation requests
- Autocomplete/search support
- Deterministic filtering and ranking
- Content-based movie similarity using TF-IDF
- OMDb-based movie information enrichment
- Gemini-generated natural-language intent parsing
- Dataset-grounded recommendation explanations, with optional Gemini field selection
- Duplicate-free recommendation results
- Graceful handling of missing data and external API failures

---

## Current Architecture

The current backend follows this flow:

```text
User Request
     │
     ▼
Natural Language Request
     │
     ▼
Gemini Intent Parsing
     │
     ▼
Backend Intent Validation
     │
     ▼
Indian Movie Dataset
     │
     ▼
Deterministic Filtering
     │
     ▼
Deterministic Ranking
     │
     ▼
Selected Movies
     │
     ├──────────────► OMDb Enrichment
     │
     ▼
     Grounded Explanation Assembly
     │
     ▼
Final Recommendation Response
````

Gemini may identify which supplied dataset fields are relevant to an explanation. The backend constructs displayed explanations from actual dataset values; Gemini does not supply movie facts or choose recommendations.

### Important Architecture Boundary

Gemini is **not** responsible for choosing or ranking movies.

The backend determines which movies are recommended using the Indian movie dataset and deterministic recommendation logic.

OMDb is used only for additional movie information and enrichment.

---

## Recommendation Source

The primary recommendation source is the Indian movie dataset:

```text
data/raw/indian movies.csv
```

The processed dataset is:

```text
data/processed/indian_movies_clean.csv
```

The current processed dataset contains approximately:

```text
48,599 movies
```

with fields including:

* title
* year
* duration
* rating
* votes
* genre
* language
* normalized title information

The dataset is the authoritative source for recommendation selection.

---

## Recommendation Engine

The title-based recommendation system uses a content-based machine-learning pipeline.

The active model artifacts are stored in:

```text
backend/models/
```

The active recommendation components include:

```text
movies.pkl
vectorizer.pkl
tfidf_matrix.pkl
neighbors.pkl
```

The current model uses:

* TF-IDF vectorization
* 50,000 TF-IDF features
* NearestNeighbors
* Content-based similarity

The current model operates on approximately:

```text
48,599 movies
```

and the TF-IDF matrix is:

```text
(48599, 50000)
```

The recommendation engine does not depend on TMDB.

---

## Natural-Language Recommendations

Natural-language requests are handled through the following process:

```text
User Text
   ↓
Gemini Intent Parser
   ↓
Structured Intent
   ↓
Backend Validation
   ↓
Dataset Filtering
   ↓
Deterministic Ranking
   ↓
Movie Selection
   ↓
Optional OMDb Enrichment
   ↓
Dataset-Grounded Explanation Assembly
```

Supported intent fields include:

* genres
* languages
* year range
* duration preference
* mood
* audience
* ranking preference

Supported ranking modes include:

* general
* best
* highly rated
* popular
* underrated

### Ranking Responsibility

Ranking is performed by the backend.

Gemini does not decide which movie is better, more popular, underrated, or recommended.

---

## Filtering

The backend supports deterministic filtering using:

* genre
* language
* year range
* duration preference

Mood and audience are treated as contextual/soft signals rather than unsafe assumptions about movie suitability.

Missing dataset values are handled safely without crashing the recommendation pipeline.

---

## Ranking

The backend provides deterministic ranking modes.

### General

Balances movie quality and popularity.

### Best

Uses the deterministic quality ranking.

### Highly Rated

Prioritizes movies with strong ratings while accounting for vote confidence.

### Popular

Uses vote/popularity information.

### Underrated

Identifies movies with comparatively strong quality relative to their popularity.

The ranking logic is deterministic, meaning the same input dataset and request produce stable recommendation ordering.

---

## OMDb Integration

OMDb is used as an **enrichment service**.

The recommendation engine does not depend on OMDb to decide which movies should be recommended.

The system can fall back to Indian dataset information when OMDb is unavailable.

The OMDb API key is stored only in the backend environment configuration.

---

## Gemini Integration

Gemini is used for two main purposes:

1. Natural-language intent parsing
2. Selecting relevant fields for a grounded explanation

Gemini does not directly select, filter, or rank movies.

The backend constructs displayed explanations from actual dataset values. Missing configuration, timeouts, invalid JSON, and unsupported intent values fall back safely without exposing exception details or inventing movie facts.

---

## API

### Health

```http
GET /api/health
```

Returns model readiness and booleans indicating whether optional providers are configured. It never returns API keys.

### Search and Autocomplete

```http
GET /api/autocomplete?q=RR
GET /api/search?q=RRR
```

Autocomplete returns up to eight dataset titles. Search returns up to ten movie records, with exact and prefix matches prioritized.

### Movie Details

```http
GET /api/movie?title=3%20Idiots
```

Returns Indian dataset details, optionally enriched with OMDb metadata.

### Title-Based Recommendations

```http
GET /api/recommend?title=3%20Idiots
```

Returns content-based recommendations for a supplied movie title.

### Watchmode Discovery

```http
GET /api/watchmode/status
GET /api/watchmode/search?q=RRR
GET /api/watchmode/title/1569154
GET /api/watchmode/sources/1569154?region=IN
```

These routes are separate from the recommender and return Watchmode discovery
data only. Status returns safe configuration/authentication state without the
provider response body or credentials. Search returns `{ "provider",
"results", "count" }`; title details return `{ "provider", "result" }`; and
sources return `{ "provider", "region", "sources" }`. Requests validate title
queries, numeric Watchmode IDs, and two-letter region codes. Provider timeouts,
rate limits, configuration problems, and upstream failures return controlled
JSON errors and never include a key or stack trace.

The API supports `region=IN` for streaming-source lookup when the Watchmode
account permits it. Advanced release discovery is intentionally not exposed:
it has account-specific paid-plan/credit behavior and must not be treated as
Indian OTT availability based on US release data.

### Hybrid Recommendations (A6)

```http
GET /api/recommend-hybrid?text=Suggest%20a%20Telugu%20action%20movie
GET /api/recommend-hybrid?text=Where%20can%20I%20watch%20RRR%3F&title=RRR&region=IN
```

This additive endpoint does not change `/api/recommend` or
`/api/recommend-text`. It returns a provider-normalized `results` array,
`mode`, verification states, and `local_fallback_used`. `title` supplies the
exact title for similarity and OTT-availability requests; `text` provides the
natural-language preferences. `region` defaults to `IN`; `limit` defaults to
10 and accepts 1--20.

For an exact OTT lookup, Watchmode title search is used only to resolve an
unambiguous title, then sources are requested for the specified region. A
timeout, rate limit, account failure, malformed response, or no exact match is
reported as `availability: "not_verified"` without exposing provider details.

Requests containing latest/recent/upcoming wording use the local catalog only
and return `freshness: "local_catalog_only"` with an explicit limitation.
Watchmode genre/language/latest/OTT-release discovery is not currently
supported or claimed, so the endpoint never presents local historical results
as verified latest market releases.

### Capability-Gated Live Discovery (A7)

Set these server-only values in the ignored `backend/.env` only after verifying
the Watchmode plan and India entitlement:

```dotenv
WATCHMODE_DISCOVERY_ENABLED=true
WATCHMODE_DISCOVERY_WINDOW_DAYS=90
```

When enabled, a latest request with exactly one supported language and genre
uses Watchmode `list-titles` for its genre/language/region/date filter, then
cross-checks IDs against `title-release-dates` for the actual regional release
type and date. The API emits a fresh candidate only when both operations agree.
The result distinguishes `verified_release_date` from
`verified_ott_premiere_date`; streaming confirmation is a separate availability
state. This path uses paid catalog calls: one cached genre-reference request,
one `list-titles` page, and one advanced release-date page per fresh discovery
flow (each documented as one credit on success).

With the flag disabled, missing configuration, a 401 entitlement response,
rate limit, provider failure, malformed data, or no matching verified release
row, the endpoint preserves the local fallback and returns an explicit
limitation. No frontend changes are required.

### TMDB Live Movie Discovery (A8.1)

`TMDB_API_READ_ACCESS_TOKEN` is server-side only and is sent as an
`Authorization: Bearer` header. For freshness requests, TMDB is the first
live-discovery provider. It filters `/3/discover/movie` by TMDB genre, original
language, `IN` region, and a configurable 90-day release window, then returns
only candidates with real TMDB release dates. Its results use
`provider: ["tmdb"]`, `data_source: ["tmdb_discovery"]`, and
`freshness_status: "verified_release_date"`.

TMDB release discovery does not establish OTT availability. Watchmode remains
the source for per-title India streaming availability; if no availability lookup
is performed, a TMDB candidate remains `availability_status: "not_checked"`.

---

### Natural-Language Recommendations

```http
GET /api/recommend-text?text=recommend%20highly%20rated%20Hindi%20movies
```

Accepts a natural-language movie request and returns recommendations based on the validated intent and deterministic backend ranking.

---

## API Response Principles

The backend maintains consistent JSON responses.

Successful natural-language responses contain:

```json
{
  "query": "...",
  "intent": {},
  "results": []
}
```

Controlled error responses contain an appropriate error structure rather than exposing internal implementation details.

Recommendation results are deduplicated by normalized movie title.

---

## Configuration

Backend configuration is stored in:

```text
backend/.env
```

The following configuration variables are currently used:

```env
OMDB_API_KEY=
GEMINI_API_KEY=
TMDB_API_READ_ACCESS_TOKEN=YOUR_TMDB_READ_ACCESS_TOKEN
WATCHMODE_API_KEY=
FRONTEND_ORIGIN=http://localhost:5500
PORT=5000
```
`FRONTEND_ORIGIN` accepts one or more comma-separated exact origins. If unset, it defaults to `http://localhost:5500`; wildcard origins are discarded.

`WATCHMODE_API_KEY` is read only by the backend. Watchmode status, search, and
streaming-source data are optional discovery-provider capabilities; they do not
change Model A ranking or require rebuilding any model artifacts.


### Security

The actual `.env` file must never be committed to source control.

A safe configuration template is provided as:

```text
backend/.env.example
```

The template contains variable names and example/default configuration only. It must not contain real API keys.

---

## Project Structure

```text
AI-Movie-recommendation-system/
│
├── backend/
│   ├── app.py
│   ├── nl_intent.py
│   ├── nl_pipeline.py
│   ├── nl_recommender.py
│   ├── nl_ranking.py
│   ├── tests/
│   │   ├── test_api_integration.py
│   │   └── test_model_b.py
│   ├── .env
│   ├── .env.example
│   │
│   ├── models/
│   │   ├── movies.pkl
│   │   ├── vectorizer.pkl
│   │   ├── tfidf_matrix.pkl
│   │   └── neighbors.pkl
│   │
│   └── model/
│       ├── movies_old.pkl
│       └── similarity_old.pkl
│
├── data/
│   ├── raw/
│   │   └── indian movies.csv
│   │
│   └── processed/
│       └── indian_movies_clean.csv
│
├── frontend/
│   ├── index.html
│   ├── recommendation.html
│   ├── movie-search.html
│   ├── app.js
│   ├── recommendation.js
│   ├── movie-search.js
│   ├── theme.js
│   └── styles.css
│
├── MODEL_QUALITY_EVALUATION.md
├── IMPLEMENTATION_PROGRESS.md
└── README.md
```

---

## Legacy Artifacts

The following files are retained as legacy artifacts:

```text
backend/model/movies_old.pkl
backend/model/similarity_old.pkl
```

They are **not the active recommendation model**.

They are retained for historical/reference purposes and should not be confused with the current model under:

```text
backend/models/
```

---

## Legacy TMDB Data

Older project data may contain files such as:

```text
data/raw/tmdb_5000_movies.csv
data/raw/tmdb_5000_credits.csv
```

These are legacy files from an earlier version of the project.

They are **not used by the current backend recommendation pipeline**.

TMDB is outside the scope of the current architecture.

Set `TMDB_API_READ_ACCESS_TOKEN=YOUR_TMDB_READ_ACCESS_TOKEN` in `backend/.env`
to enable live TMDB discovery. The token is never sent to the frontend.

---

## Frontend

The frontend uses:

* HTML
* CSS
* Vanilla JavaScript

The frontend communicates with the Flask backend through HTTP API endpoints.

The frontend must never receive server-side API keys.

---

## Local Setup

### 1. Create the virtual environment

From the project root (skip creation if `.venv` already exists):

```bash
py -m venv .venv
```

Activate the environment.

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

---

### 2. Install dependencies

```bash
python -m pip install -r backend\requirements.txt
```

---

### 3. Configure environment variables

Create:

```text
backend/.env
```

using:

```text
backend/.env.example
```

as the template.

Add the required server-side API keys to `.env`.

Never place real API keys inside source code or `.env.example`.

---

### 4. Start the backend

From the project root:

```bash
python backend\app.py
```

The backend uses the configured `PORT` value and defaults to:

```text
5000
```

Flask serves the frontend at `http://127.0.0.1:5000/`. To serve the static files separately, open `frontend/index.html` with VS Code Live Server (commonly `http://localhost:5500`) and set `FRONTEND_ORIGIN` in `backend/.env` to that origin. Keep Gemini and OMDb keys on the backend only.

### Production WSGI startup

Do not expose Flask's built-in development server publicly. On a Linux deployment host, set `PORT`, `FRONTEND_ORIGIN` (if the frontend is separate), and optional provider keys in the host's secret environment, then run from the project root:

```bash
./.venv/bin/gunicorn --chdir backend --bind 0.0.0.0:${PORT:-8000} --workers 1 --timeout 120 app:app
```

Gunicorn is declared in `backend/requirements.txt`. It requires a Unix-like host and is not supported by this Windows development environment (`fcntl` is unavailable here). No public deployment was performed; provider credentials and deployment-account configuration must be supplied manually by the deployer. The Flask app serves static frontend files from its configured `frontend/` directory and same-origin API routes under `/api/`.

---

## Testing

From `backend/`, run the offline regression suites with:

```powershell
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Run the Model A artifact and recommendation verifier with:

```powershell
..\.venv\Scripts\python.exe scripts\test_indian_recommender.py
```

The current test environment does not have pytest installed. The unittest suite covers Model B constraints/ranking, Gemini fallbacks and explanation grounding, OMDb fallback/cache cases, API contracts, and invalid or oversized input. The Model A verifier separately checks saved artifacts and five recommendation cases. Browser viewport checks exercised landing, recommendation, search/autocomplete, and selected movie details at 320×568, 375×667, 390×844, 768×1024, 1024×768, and 1440×900. These are focused checks, not exhaustive coverage.

See `IMPLEMENTATION_PROGRESS.md` for exact final test totals and security/performance findings, and `MODEL_QUALITY_EVALUATION.md` for the 9 Model A and 12 Model B qualitative cases. No accuracy metric is claimed because ground-truth labels are unavailable.

Latest executed results: 31/31 unittest cases passed; Model A artifact verification passed 5/5 recommendation cases. One live Gemini intent parse and one OMDb lookup succeeded. A later live explanation-field selection returned no usable labels and correctly used the deterministic dataset-grounded fallback.

The active recommendation dataset contains 48,599 records.

---

## Design Principles

The current system follows these principles:

### 1. Dataset First

The Indian movie dataset is the source of truth for recommendation selection.

### 2. Deterministic Recommendations

Filtering and ranking are performed by backend code rather than by an LLM.

### 3. Gemini as an AI Interface

Gemini converts natural-language requests into structured intent and may select relevant dataset metadata fields. The backend assembles explanations only from those available values.

### 4. OMDb as Enrichment

OMDb provides additional movie information but does not determine recommendations.

### 5. Graceful Failure

External API failures should not cause uncontrolled backend crashes.

### 6. Secret Isolation

External API keys remain on the backend and are loaded from environment variables.

### 7. Stable Results

Recommendation ranking is deterministic and duplicate movie titles are removed from final results.

---

## Current Scope

### Included

* Indian movie dataset
* Content-based recommendations
* TF-IDF
* NearestNeighbors
* Natural-language recommendation requests
* Deterministic filtering
* Deterministic ranking
* OMDb enrichment
* Gemini intent parsing
* Dataset-grounded explanations with optional Gemini field selection
* Vanilla HTML/CSS/JavaScript frontend
* API-based Flask backend

### Out of Scope

* TMDB recommendation dependency
* TMDB API integration
* TMDB API key
* LLM-based movie ranking
* LLM-based movie selection

````
