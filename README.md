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
- Gemini-generated explanations for selected recommendations
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
Gemini Explanation
     │
     ▼
Final Recommendation Response
````

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
Gemini Explanation
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
2. Natural-language explanations

Gemini does not directly select, filter, or rank movies.

If Gemini is unavailable because of an API error or quota limitation, the backend handles the failure through a controlled response path rather than exposing an internal exception.

---

## API

### Title-Based Recommendations

```http
GET /api/recommend?title=3%20Idiots
```

Returns content-based recommendations for a supplied movie title.

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
FRONTEND_ORIGIN=http://localhost:5500
PORT=5000
```

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
│
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

No `TMDB_API_KEY` is required by the current backend.

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

From the project root:

```bash
cd backend
python -m venv .venv
```

Activate the environment.

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

---

### 2. Install dependencies

```bash
pip install -r requirements.txt
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

From the `backend/` directory:

```bash
python app.py
```

The backend uses the configured `PORT` value and defaults to:

```text
5000
```

---

## Testing

The backend has undergone phased testing covering:

* Gemini parser integration
* Gemini failure handling
* OMDb fallback
* missing-data robustness
* explanation grounding
* API response consistency
* duplicate prevention
* caching behavior
* recommendation performance
* environment configuration
* secret-file safety
* application startup
* API integration
* TMDB dependency auditing

The current recommendation dataset contains approximately 48,599 movies.

---

## Design Principles

The current system follows these principles:

### 1. Dataset First

The Indian movie dataset is the source of truth for recommendation selection.

### 2. Deterministic Recommendations

Filtering and ranking are performed by backend code rather than by an LLM.

### 3. Gemini as an AI Interface

Gemini converts natural-language requests into structured intent and generates explanations.

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
* Gemini explanations
* Vanilla HTML/CSS/JavaScript frontend
* API-based Flask backend

### Out of Scope

* TMDB recommendation dependency
* TMDB API integration
* TMDB API key
* LLM-based movie ranking
* LLM-based movie selection

````

### After replacing the README

Run the **same audit again**:

```powershell
python test_b10_11_documentation_audit.py
````

This time we're expecting the old `REVIEW REQUIRED` items to disappear.

**Don't move to B10.11.4 yet.** Send me the complete output of this audit first. We will only mark **B10.11.3 COMPLETE** after the verification passes.
