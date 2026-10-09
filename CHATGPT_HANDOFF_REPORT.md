# Watchmode API Integration — Current Handoff

## Phase A9 — Recommendation Source Boundary

- `RECOMMENDATION_SOURCE=tmdb` is the default; `local` and `hybrid` remain explicit alternatives. The normalized source is visible in `/api/health` and hybrid responses only.
- TMDB mode does not invoke local general ranking, TF-IDF, or NearestNeighbors helpers and never silently substitutes local records after a TMDB failure. Model artifacts remain intact for local and future hybrid mode.
- `/api/recommend` stays backward-compatible as the explicit Model-A route. `/api/recommend-text` and `/api/recommend-hybrid` follow the configured source. A8.2 Watchmode verification remains unchanged.
- On 2026-10-07, a bounded live TMDB discovery call reached the running Flask app but normalized to `provider_unavailable` for `discover/movie`. TMDB mode correctly returned no local records and `local_fallback_used: false`; retry live verification when TMDB connectivity recovers.

## Scope Kept Intact

Watchmode remains an independent provider and all existing API routes/frontends
retain their contracts. Model A's TF-IDF + NearestNeighbors algorithm, Model B
behavior, the 48,599-record dataset, and saved artifacts were not rebuilt or
re-ranked. A6 adds an isolated endpoint and uses a per-request shallow model
copy with one worker only to work in restricted Windows hosts.

## Implemented

- Server-only `WATCHMODE_API_KEY` configuration in `backend/.env.example`; `.env` remains Git-ignored.
- Independent `backend/watchmode_client.py` using Watchmode's `X-API-Key` header, 10-second timeout, response validation, normalized failures, and 429 Retry-After backoff.
- Flask routes:
  - `GET /api/watchmode/status`
  - `GET /api/watchmode/search?q=<2-150 character title>`
  - `GET /api/watchmode/title/<numeric Watchmode ID>`
  - `GET /api/watchmode/sources/<numeric Watchmode ID>?region=IN`
- Controlled errors for missing configuration, invalid input, timeout, 429, authentication/access, and provider failures. Secrets and upstream status bodies are not returned.
- Advanced release discovery is deliberately not exposed because its paid-plan/credit behavior remains unverified.

## Live Verification (Completed)

- Status: HTTP 200; authentication succeeded.
- One `RRR` search: HTTP 200; 9 results; first result was `RRR`, Watchmode ID `1569154`, year `2022`.
- One India sources request for that ID: HTTP 200; 2 India sources; first result was Netflix (`sub`, `IN`).
- No API key value was printed or logged.

India streaming-source access is verified for the tested title. This does not establish advanced India release-discovery entitlement or universal India coverage for every title/provider.

## Verification

- Watchmode client + Flask mocked tests: 18/18 passed.
- Full backend suite: 49/49 passed.
- Model A artifact verifier: 5/5 recommendation cases passed.

## Phase A6 — Additive Hybrid Retrieval

- Added `backend/movie_candidate.py` and `backend/hybrid_retrieval.py`.
- Added `GET /api/recommend-hybrid?text=...&title=...&region=IN&limit=10`.
  It supports local general and Model A similarity retrieval, plus exact-title
  India availability lookup through the existing Watchmode search/sources
  methods. It returns normalized candidates, provenance, verification state,
  provider-safe failure state, and whether local fallback was used.
- Existing `/api/recommend`, `/api/recommend-text`, `/api/search`, `/api/movie`,
  and `/api/watchmode/*` payloads are unchanged.
- Latest/recent/upcoming wording is detected but intentionally returns
  `freshness: local_catalog_only`; it does not assert latest Telugu/action or
  OTT-release discovery because that Watchmode capability is not verified.
- `backend/.env.example` now contains placeholders instead of credential-like
  values. Rotate any key that was previously shared or committed.

## Verification

- Focused hybrid tests cover provider mapping, malformed/null data,
  conservative deduplication, local fallback, India sources, timeout/401/429/
  500 handling, latest limitation, similarity isolation, and unavailable local
  data.
- Full backend test suite and Model A verifier were rerun after the A6 change.

## Recommended Next Phase

Validate a Watchmode catalog/release-discovery capability (entitlement, India
coverage, response fields, date semantics, and cost) with explicit approval.
Only then add capability-gated external discovery and verified freshness/OTT
release ranking.

## Phase A7 — Capability-Gated Discovery

- Added `backend/discovery_provider.py`, plus Watchmode client wrappers for
  `/genres` and `/list-titles`.
- Latest discovery is disabled by default via `WATCHMODE_DISCOVERY_ENABLED`.
  When explicitly enabled, it requires one supported genre and language,
  cross-checks filtered `list-titles` results against advanced
  `/title-release-dates` rows by Watchmode ID, and only emits candidates with
  an actual verified regional date.
- The API distinguishes theatrical `verified_release_date`, streaming
  `verified_ott_premiere_date`, and `verified_streaming_availability`.
  It keeps `local_catalog_only` on all disabled, entitlement, provider, data,
  or no-match fallbacks.
- Official documentation indicates successful `/genres`, `/list-titles`, and
  `/title-release-dates` calls cost one catalog credit each; the genre mapping
  is cached in-process. The advanced endpoint requires a paid plan.
- A single advanced `IN` probe was attempted but stopped locally with
  `missing_configuration`; no HTTP request, candidate, or paid credit was
  produced. Live entitlement and India/latest Telugu-action coverage remain
  pending manual verification.

## A7.5 — Authorization Root Cause Established

- A fresh Flask import verified that it reads the intended `backend/.env` and
  has a configured Watchmode key with discovery enabled. Credentials were not
  displayed.
- Bounded live diagnostic results: `/v1/genres/` returned HTTP 200 (37
  reference entries), `/v1/list-titles/` returned HTTP 200 (five filtered
  title rows), and `/v1/title-release-dates/` returned HTTP 401 with the
  normalized safe error `unauthorized`.
- Since standard catalog operations succeeded with the exact same configured
  key, the failing operation is advanced `title-release-dates` entitlement,
  not an invalid/missing key or general Watchmode outage. The public hybrid
  response now reports only `operation: title-release-dates`,
  `http_status: 401`, and `state: unauthorized_or_plan_restricted`.
- Action required: enable/upgrade Watchmode advanced release-date access and
  confirm the `IN` region for the account, then restart Flask and execute one
  controlled latest Telugu action request. Continue presenting local fallback
  until it returns verified regional release rows.

## Phase A8.1 — TMDB Live Discovery Verified

- Added `backend/tmdb_client.py` and a TMDB-first discovery adapter within
  `backend/discovery_provider.py`. TMDB uses server-only
  `TMDB_API_READ_ACCESS_TOKEN` with Bearer authentication, without returning
  or logging credentials.
- Latest theatrical requests first call TMDB genre metadata and
  `/3/discover/movie` with the requested genre, original-language code, `IN`
  region, dynamic 90-day release window, and release-date descending sort.
  TMDB returns release metadata only; it does not imply India OTT availability.
- Live verification succeeded on 2026-10-05. The hybrid endpoint returned HTTP
  200, `discovery.provider: tmdb`, `status: available`, 10 dated Telugu action
  candidates, and `local_fallback_used: false`. Sample results: Anakapalli
  (TMDB 1690876, 2026-10-02), Don’t Trouble the Trouble (TMDB 1261763,
  2026-10-02), and The Paradise (TMDB 1376856, 2026-09-23).
- Each verified TMDB candidate has `verified_release_date` and
  `availability_status: not_checked`. Watchmode remains available for a
  separate per-title India streaming lookup; its advanced discovery restriction
  does not affect successful TMDB freshness discovery.

## TMDB Read Access Token Authentication Migration

- `TMDBClient` now reads only `TMDB_API_READ_ACCESS_TOKEN` and sends every
  TMDB request with `Authorization: Bearer <token>` plus `accept: application/json`.
  It no longer supports or emits an `api_key` query parameter.
- Controlled live verification on 2026-10-06 returned HTTP 200 for TMDB movie
  search, movie details, and the existing A8.1 discovery query. The token was
  not logged, returned, or added to frontend code.
