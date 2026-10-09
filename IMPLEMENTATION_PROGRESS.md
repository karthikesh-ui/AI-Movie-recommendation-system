# Implementation Progress

## Phase A9 — Configurable Active Recommendation Source

- Added the server-only `RECOMMENDATION_SOURCE` boundary. Valid values are `tmdb` (default), `local`, and `hybrid`; invalid values safely normalize to `tmdb`.
- In TMDB mode, latest requests use TMDB only. The retrieval branch does not invoke the local general or TF-IDF/NearestNeighbors helpers, and TMDB failures return no local catalog results.
- Local retains existing behavior; hybrid retains the existing A8 merge/fallback path without a new ranking design. `/api/recommend` remains the explicit legacy Model-A endpoint; natural-language endpoints obey the source boundary.
- Added source configuration, TMDB isolation/no-silent-fallback, local-mode, and configured natural-language tests. Existing A8.1/A8.2 and Model A/B tests remain in the suite.
- Live verification on 2026-10-07 reached the current Flask process with `recommendation_source: tmdb`, but TMDB `/discover/movie` was temporarily unavailable (`provider_unavailable`, no HTTP status). The API returned zero results and `local_fallback_used: false`; no live TMDB result claim was made.

## Phase A4 — Watchmode Live Verification and Flask Integration

- Added independent Flask routes: `GET /api/watchmode/status`, `/api/watchmode/search?q=...`, `/api/watchmode/title/<watchmode_id>`, and `/api/watchmode/sources/<watchmode_id>?region=IN`.
- The routes leave existing API contracts, Model A/Model B ranking, frontend files, dataset, and saved artifacts unchanged.
- Requests validate 2–150-character search queries, numeric Watchmode IDs, and two-letter regions. Provider failures map to controlled JSON errors with no credentials, stack traces, or provider status body leakage. `/api/health` reports the boolean `watchmode_configured` only.

## Live Provider Verification

- `backend/.env` was present with a non-empty `WATCHMODE_API_KEY`; its value was never read, printed, or logged.
- Zero-credit `/v1/status/`: HTTP 200; authentication succeeded.
- One minimal `/v1/search/` request for `RRR`: HTTP 200; 9 results; first title `RRR`, Watchmode ID `1569154`, year `2022`.
- One streaming-sources request for Watchmode ID `1569154` and `regions=IN`: HTTP 200; 2 India sources; first source was Netflix, type `sub`, region `IN`.
- Advanced `title-release-dates` discovery was not called and is not exposed. Its paid-plan/credit behavior remains unverified. US-focused release data is not used as a proxy for Indian OTT availability.

## Tests

- Added mocked Flask endpoint tests in `backend/tests/test_watchmode_api.py` for status, missing configuration, search success/empty/invalid input, title details/invalid ID, regional sources/access restriction, timeout, rate limit, and provider error.
- Watchmode client and Flask mocked tests: 18/18 passed.
- Full backend suite: 49/49 passed.
- Model A artifact verification: 5/5 recommendation cases passed. The first Windows-console run stopped only because the active cp1252 console could not print the verifier's checkmark; rerunning with UTF-8 output completed successfully.

## Phase A5 — Model A Product Contract and Hybrid Retrieval Design

- Audited the current `/api/recommend`, `/api/recommend-text`, `/api/search`, `/api/movie`, and Watchmode route contracts, plus the exact fields consumed by the existing frontend.
- Added `MODEL_A_PRODUCT_CONTRACT.md`, defining query modes, freshness terms/windows, Watchmode capability boundaries, a normalized internal schema, frontend behavior, and a proposed A6 sequence.
- Added `MODEL_A_HYBRID_RETRIEVAL_DESIGN.md`, defining failure-isolated orchestration, conservative cross-source deduplication, mode-specific ranking rules, a versioned/additive response approach, and mocked test scenarios.
- No Model A ranking, TF-IDF artifacts, datasets, frontend files, existing endpoint behavior, or external Watchmode calls were changed in this phase.

## Next Step — Phase A6 (Proposed)

- Add an additive/versioned hybrid API contract and normalized provider adapters; retain all existing endpoint payloads as regression-protected baseline behavior.
- Implement title resolution and regional availability lookup first. Defer external genre/latest/OTT discovery until Watchmode plan access, India coverage, date semantics, schema, and credit cost are explicitly verified.
- Implement feature-flagged hybrid ranking only after normalization, conservative deduplication, freshness policy, and provider-failure fallback tests pass.

## Phase A6 — Additive Hybrid Retrieval (Partially Complete)

- Added `backend/movie_candidate.py`: a null-safe, provider-neutral candidate schema with local-dataset and Watchmode title/source adapters, source provenance, availability state, and no public ranking internals.
- Added `backend/hybrid_retrieval.py`: conservative ID/title-year deduplication; unchanged-artifact Model A similarity retrieval; local Model B candidate retrieval; exact Watchmode title resolution plus regional source lookup; and safe provider/local failure isolation.
- Added `GET /api/recommend-hybrid`. It accepts `text` and/or `title`, optional `region` (default `IN`), and `limit` (1--20). Existing recommendation and Watchmode routes retain their response contracts.
- `LATEST` requests are deliberately local-catalog fallback only. Their response says `freshness: local_catalog_only` and does not claim verified latest releases because generic Watchmode release/genre/language discovery remains unverified and unused.
- Added focused hybrid tests for normalization, null fields, malformed provider data, conservative deduplication/remake safety, local fallback, Watchmode timeout/401/429/500 failure states, India OTT sources, latest fallback, similarity isolation, and unavailable local data.
- Replaced credential-like values in `backend/.env.example` with placeholders. The actual local `.env` was not read or modified; any previously shared key should be rotated.
- Changed only per-request `NearestNeighbors` query copies to `n_jobs=1` in the existing API and verifier. The saved artifacts and ranking algorithm/order are unchanged; this avoids an all-CPU worker-pool failure in restricted Windows hosts.

## A6 Limitation / Next Step

- A6 is not complete for generic latest Telugu/action discovery: current verified Watchmode operations support title resolution and per-title regional sources, not catalog-wide genre/language/latest discovery or verified OTT release dates.
- Before enabling external discovery candidates, verify account entitlement, India coverage, response schema/date semantics, and paid-credit cost for the appropriate release/discovery operation. Then add a capability-gated adapter and freshness ranking using verified full release dates.

## Phase A7 — Capability-Gated Live Discovery (Implemented, Live Verification Pending)

- Investigated current official Watchmode documentation. `list-titles` supports movie type, region, genre ID, primary-language code, release-date window, release-date sorting, and pagination; successful pages cost one catalog credit per requested region. `title-release-dates` is a paid operation (one credit per page) that supplies regional theatrical/streaming release type, exact date, original language, and streaming verification status.
- Added `backend/discovery_provider.py` and extended `backend/watchmode_client.py` with documented `genres` and `list_titles` operations. The adapter is disabled by default and does not introduce a new dependency.
- Added `WATCHMODE_DISCOVERY_ENABLED=false` and configurable `WATCHMODE_DISCOVERY_WINDOW_DAYS=90` to `backend/.env.example`. Enabled discovery requires exactly one requested dataset genre and language, maps the language to Watchmode's ISO code, filters `list-titles`, then intersects results with paid advanced regional release rows by stable Watchmode ID.
- Candidates receive `verified_release_date` only for matching theatrical rows with actual dates. Streaming rows receive `verified_ott_premiere_date`; only `confirmed_available` becomes `verified_streaming_availability`. Missing dates and list-only matches are never emitted as fresh.
- Extended `/api/recommend-hybrid` additively with `discovery`, `limitations`, and distinct freshness/availability verification fields. Non-latest requests do not invoke discovery. Latest fallback remains `local_catalog_only` when the capability is disabled or unavailable.
- Added mocked tests for supported query normalization, genre/language mapping, release date validation, theatrical-versus-OTT distinction, disabled/401 fallback, missing dates, and non-latest regression; extended Watchmode client tests for discovery request validation.

## A7 Live Verification Status

- One controlled advanced `title-release-dates` probe for `region=IN`, 2026-09-04 through 2026-10-04 was attempted. It returned `missing_configuration` before an HTTP request, so it consumed no catalog credit and did not verify account entitlement, India coverage, or a latest Telugu-action result.
- Generic latest Telugu/action discovery is therefore **not live-verified or enabled**. Add a valid server-only `WATCHMODE_API_KEY`, confirm paid-plan access and `IN` coverage, set `WATCHMODE_DISCOVERY_ENABLED=true`, and perform one controlled request before making a production claim.

## A7.5 — Advanced Discovery Authorization Diagnostic

- Confirmed the fresh Flask import loads `C:\Users\kathi\OneDrive\Documents\Projects\AI-Movie-recommendation-system\backend\.env`; `WATCHMODE_API_KEY` is present, `WATCHMODE_DISCOVERY_ENABLED` is true, and the discovery provider is enabled with its configured 90-day window. No key or request header was printed.
- Performed one bounded live operation trace with the same loaded client and `IN` Telugu/action-style filters. `/v1/genres/` returned HTTP 200 (37 reference entries), and `/v1/list-titles/` returned HTTP 200 (five filtered title rows). `/v1/title-release-dates/` then returned HTTP 401 with the normalized client error `unauthorized`.
- Root cause: the configured API key is valid for standard catalog operations, but the account is not authorized for the advanced `title-release-dates` operation. This is an advanced paid-plan/operation entitlement restriction, not `missing_configuration` or an invalid API key.
- Updated discovery failure metadata to expose only `{operation, http_status, state}`. The affected response now identifies `operation: title-release-dates`, `http_status: 401`, and `state: unauthorized_or_plan_restricted`; no raw provider body, API key, header, or request values are exposed.
- Added mocked coverage for `missing_configuration`, `invalid_api_key`, `unauthorized_or_plan_restricted`, `rate_limited`, `provider_unavailable`, and `malformed_response`, plus operation/status attribution. Local fallback and all existing API contracts remain unchanged.

## Required Manual Action

- Upgrade or enable the Watchmode account entitlement for advanced `/v1/title-release-dates` access and confirm `IN` regional access with Watchmode. Then restart the Flask process (environment is read at process startup) and run one controlled latest Telugu action request. Do not enable a production “Latest” claim until that request returns a verified release-date result.

## Phase A8.1 — TMDB Live Discovery (Implemented and Live-Verified)

- Added `backend/tmdb_client.py`, a server-only TMDB v3 client using `TMDB_API_READ_ACCESS_TOKEN` and `Authorization: Bearer` authentication, timeout, safe status normalization, genre lookup, and paginated `/3/discover/movie` requests. `backend/.env.example` contains only the token placeholder.
- Authentication migration verified on 2026-10-06: removed the legacy query-key path entirely. Controlled live Bearer requests returned HTTP 200 for `/3/search/movie` (11 results for RRR), `/3/movie/579974` (RRR), and existing `/3/discover/movie` (18 results). No token was logged or returned.
- Added `TMDBDiscoveryProvider` to `backend/discovery_provider.py`. TMDB is now the first provider for latest theatrical discovery; Watchmode stays responsible for title search and regional streaming availability. Ordinary non-freshness requests do not call TMDB.
- TMDB candidates use the established `MovieCandidate` representation with TMDB ID, title/original title, returned original language, returned genre names, release date/year, overview, poster URL, rating, `provider: ["tmdb"]`, `data_source: ["tmdb_discovery"]`, and `verified_release_date` freshness. TMDB never marks a candidate OTT available.
- Updated the additive `/api/recommend-hybrid` path. A TMDB success returns `discovery: {provider: "tmdb", status: "available", query_supported: true}`, `freshness: verified_release_date`, `availability: unknown`, and `local_fallback_used: false`. TMDB error/empty/unsupported states keep local fallback and `local_catalog_only`.
- Controlled live verification on 2026-10-05: `GET /api/recommend-hybrid?text=Show%20me%20the%20latest%20Telugu%20action%20movies&region=IN` returned HTTP 200 with TMDB discovery available, 10 candidates, and `local_fallback_used: false`. Sample returned candidates included Anakapalli (TMDB 1690876, 2026-10-02), Don’t Trouble the Trouble (TMDB 1261763, 2026-10-02), and The Paradise (TMDB 1376856, 2026-09-23). All inspected sample results had returned `te` language, Action genre, valid release date, `verified_release_date`, and `availability_status: not_checked`.
