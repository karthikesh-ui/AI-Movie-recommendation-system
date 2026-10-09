# Model A Product Contract

## Purpose and boundary

This document defines the product contract for a future hybrid of Model A and
Watchmode. It is a design artifact only. At the end of Phase A5, no existing
route, ranking rule, saved TF-IDF artifact, dataset, or frontend behavior has
changed.

The local Indian movie dataset remains the authoritative source for the
existing Model A similarity experience. Watchmode is an optional provider of
external title metadata and regional streaming availability. Its failure must
not stop a local result from being returned.

## Current API contract audit

All routes are `GET` and currently return JSON.

| Route | Request contract | Success response actually produced | Error behavior |
| --- | --- | --- | --- |
| `/api/recommend` | `title` required, non-empty and <=150 chars; optional integer `limit`, 1--20, default 8 | `{ "results": [movie, ...] }` | 400 for invalid input; 404 when the title is absent from the current ML dataset. |
| `/api/recommend-text` | `text` required, non-empty and <=500 chars | `{ "query": text, "intent": intent, "results": [movie, ...] }` | 400 for invalid input; 422 with `unsupported: {genres: [], languages: []}` for vocabulary misses; 503 if intent parsing returns no intent. An empty successful match has an empty `results` array. |
| `/api/search` | `q`, with <=150 chars; fewer than 2 chars is allowed | `{ "results": [movie, ...] }` | 400 only for an oversized query; short query or unavailable dataset returns an empty array. At most 10 distinct normalized local titles are returned, prioritizing exact then prefix matches. |
| `/api/movie` | `title` required, non-empty and <=150 chars | one `movie` object with `insight` appended | 400 for absent/oversized title; 404 if absent from the local dataset or details cannot be assembled. |
| `/api/watchmode/status` | no parameters | `{ "provider": "watchmode", "configured": true, "authenticated": true, "endpoint_accessible": true }` | Controlled provider error: 503 missing configuration, 504 timeout, 429 rate limit, otherwise generally 502. |
| `/api/watchmode/search` | `q` required, 2--150 chars | `{ "provider": "watchmode", "results": title_results, "count": n }`; `title_results` is passed through from Watchmode | 400 validation error or controlled provider error. |
| `/api/watchmode/title/<watchmode_id>` | numeric path ID of 1--12 digits | `{ "provider": "watchmode", "result": details }`; details are passed through from Watchmode | 400 invalid ID or controlled provider error. |
| `/api/watchmode/sources/<watchmode_id>` | numeric path ID; optional `region`, default `IN`, exactly two letters | `{ "provider": "watchmode", "region": region, "sources": sources }`; sources are passed through from Watchmode | 400 invalid ID/region or controlled provider error. |

`movie` is the existing presentation object assembled from the Indian dataset
and optional OMDb enrichment. Its observed keys are `title`, `year`, `rating`,
`genre`, `runtime`, `director`, `cast`, `plot`, `poster`, `language`, `source`,
and `imdb_id`. `/api/movie` additionally includes `insight`; title similarity
items additionally include `similarity` and `explanation`; text recommendation
items additionally include `explanation` and `votes`. Values can currently be
`"N/A"` or an empty poster string, rather than null. The contract must retain
that behavior until a deliberate versioned migration.

Watchmode's raw title/detail/source schemas are not normalized by the current
routes. Apart from test fixtures and verified observations (search result ID,
name, and year; an India source name/type/region), callers must treat their
provider payloads as provider-owned rather than depend on undocumented fields.

## Existing frontend expectations

`movie-search.js` calls `/api/search`, then `/api/movie`, then
`/api/recommend?title=...&limit=8`. Search cards render title/year/rating/runtime
and genre; the selected detail view renders title/year/rating/runtime/genre/plot
and optionally poster. Similar cards render title/year/rating/runtime.

`recommendation.js` calls `/api/recommend-text?text=...`. It expects
`results` to be an array, optionally displays `intent.genres`,
`intent.languages`, `intent.mood`, and `intent.audience`, and renders title,
poster, year, rating, runtime, genre, and explanation. Neither frontend reads
Watchmode fields or streaming availability today.

Consequently, A6 must either add a new endpoint or negotiate an explicit
response version/feature flag. It must not repurpose `source`, alter `results`
into a non-array, or make an existing field required.

## Query-mode contract for the hybrid service

The following is the proposed canonical intent shape for a future hybrid entry
point. Fields not supplied are null/empty. `mode` is required after parsing;
the parser must only emit a mode it can justify from the request.

| Mode | Required intent fields | Candidate source | Ranking and response | Fallback |
| --- | --- | --- | --- | --- |
| `SIMILARITY` | `mode`, `seed_title`; optional `seed_year`, genre/language constraints, `limit` | Local Model A only for similarity candidates; Watchmode may resolve/enrich the selected seed if an unambiguous ID exists | Preserve TF-IDF + NearestNeighbors ordering as the primary ranking. Return normalized movies plus mode, query/seed resolution, and availability state where separately verified. | If seed is not local, return a controlled not-found/clarification result; do not pretend a Watchmode title search provides vector similarity. Watchmode failure has no impact on local similarity. |
| `GENERAL` | `mode`; at least one meaningful preference when available (`genres`, `languages`, mood/audience, year bounds, or ranking); `limit` | Existing local natural-language retrieval/ranking. Watchmode may contribute only candidates obtainable through a future verified discovery capability. | Genre/language filters remain high-priority eligibility/relevance signals; existing deterministic ranking ranks local candidates. Include `availability_status` only when looked up. | If no verified external discovery source is enabled, return local results. If filters yield none, use current empty result behavior; never relax explicit language/genre without exposing that relaxation. |
| `LATEST` | `mode`, explicit freshness request (`freshness_kind=latest_released` unless user says upcoming or OTT), `as_of_date`, optional genre/language, `limit` | Local data with reliable release dates; future Watchmode release-discovery results only after plan/access/schema validation. | Filter to released titles, then rank recency first inside the configured freshness window, while retaining genre/language relevance. A theatrical/release date is not an OTT date. | If release discovery is unavailable, label results `freshness_status: local_metadata_only` and use only local dated records. Do not claim a comprehensive latest Telugu-action catalog. |
| `OTT_AVAILABILITY` | `mode`, `seed_title` (and optional `seed_year`/external ID for disambiguation), `region` (default proposed `IN`) | Watchmode exact-title search followed by an unambiguous Watchmode ID and `/sources`; local data can help present metadata | Resolve exact title carefully; report provider and regional sources, not a recommendation score. | Ambiguous search requires a choice or returns candidates. Missing/no sources means `unavailable_or_not_verified`, never “not streaming.” Timeout/rate limit yields local movie metadata when available plus an explicit unverified state. |

`seed_title` and `region` are semantic intent fields, not additions to current
`nl_intent.empty_intent()`. `freshness_kind`, `availability_requested`,
`as_of_date`, and an optional external-ID hint will need schema/parser work in
A6. That work is expressly deferred.

## Freshness vocabulary and rules

All comparisons use an injected/configured `as_of_date` in ISO-8601 calendar
date form and a configurable policy, for example:

```text
FRESHNESS_WINDOWS = {
  recently_released_days: <configuration>,
  upcoming_horizon_days: <configuration>,
  latest_ott_days: <configuration>
}
```

No arbitrary year threshold is a substitute for a date. A title with only a
year may be displayed but cannot receive precise date-window qualification.

| Term | Qualification | What it does not establish |
| --- | --- | --- |
| Latest released | A known release date on or before `as_of_date`; rank newest first among eligible candidates. | Streaming availability, regional release, or an OTT premiere. |
| Recently released | Known release date from `as_of_date - recently_released_days` through `as_of_date`. | That it is the newest title, currently streaming, or in the requested region. |
| Upcoming | Known release date after `as_of_date` through `as_of_date + upcoming_horizon_days`. | A released title or a streaming title. |
| Latest OTT release | A provider-confirmed OTT availability/release timestamp in the requested region inside `latest_ott_days`; source and region must be recorded. | A theatrical release date alone. |
| Available to stream now | At request time, Watchmode sources returned at least one qualifying streaming provider for the requested region. | When it first appeared on OTT, unless that provider event is separately supplied and verified. |

When relevant date type, region, timestamp, or source is absent, the response
must say `not_verified`/`unknown`, omit the freshness assertion, and still may
show the movie as a normal candidate.

## Watchmode capability boundary

| Need | Classification | Evidence and limit |
| --- | --- | --- |
| Exact title search | Verified | `/api/watchmode/search?q=RRR` returned HTTP 200 and nine results. It is a title search, not a genre/language/latest discovery feed. |
| Movie details by Watchmode ID | Partially supported | The route/client exists and has mocked success coverage; a live details call was not included in the recorded verification. It is ID-based after title resolution. |
| India streaming availability by ID | Verified | `/api/watchmode/sources/1569154?region=IN` returned HTTP 200 and two sources for the tested title. This is per resolved title, not market-wide discovery. |
| Genre-based discovery | Unsupported by current integration | No exposed route calls a Watchmode genre/discovery operation. Search-by-title cannot satisfy this need. |
| Latest movie discovery | Not verified | Client code contains a release-discovery method, but no Flask route exposes it and advanced access was explicitly not tested/enabled. Basic releases are documented in code as primarily US-oriented. |
| Latest OTT discovery | Not verified | It would require provider release/availability data with regional semantics and account/plan validation. The tested sources endpoint only answers a known ID's sources. |

## Normalized internal movie schema

Future integration normalizes at provider boundaries. This schema is internal;
it is not a promise to change existing response objects.

```json
{
  "title": "string",
  "normalized_title": "string",
  "release_year": 2022,
  "release_date": "YYYY-MM-DD",
  "genre": ["action"],
  "language": ["telugu"],
  "rating": 7.8,
  "poster": "https://...",
  "imdb_id": "tt1234567",
  "tmdb_id": 123,
  "watchmode_id": 1569154,
  "source": ["local_dataset", "omdb", "watchmode"],
  "streaming_providers": [{"name": "Netflix", "type": "sub"}],
  "availability_region": "IN",
  "metadata_confidence": "high"
}
```

The example illustrates types, not actual RRR metadata. Scalar `source` may
be used during internal assembly if provenance is modelled elsewhere, but the
final canonical form should preserve all contributing sources. `genre` and
`language` are normalized lists; their display labels may be retained in a
separate adapter only when actually provided. `metadata_confidence` is a
provenance/completeness assessment (`high`, `medium`, `low`, or null), not an
invented factual rating. Every unknown field is null or absent; arrays are
empty only when the source has established that no values exist.

## Frontend product behavior (future, no UI work in A5)

Existing cards should remain usable with their present fields. A hybrid-aware
card should display, only when present:

| Item | Display rule |
| --- | --- |
| Movie title | Always use canonical `title`; show an ambiguity chooser before a title is treated as exact. |
| Release year | Show `release_year`; do not derive it from a missing date. |
| Genre and language | Show supplied values; show “Not listed” rather than fabricate either. |
| Rating | Show source-backed rating, ideally with a source label/tooltip; hide if absent. |
| Data source | Show concise provenance such as Local dataset, OMDb enrichment, and/or Watchmode. Do not overload the current `source` string without an API migration. |
| Streaming provider | Display provider names/types only for the returned `availability_region`. |
| Region | Display the requested/verified two-letter region in human-readable UI copy. |
| Availability verification | Use one of: `Verified for IN`, `No providers returned for IN`, `Not verified — provider unavailable`, or `Not checked`. “No providers returned” is not “unavailable everywhere.” |

For OTT answers, availability should be visually distinct from recommendation
quality. For latest answers, include the date basis (for example, “release date
verified”) rather than suggesting the card is an OTT release.

## Phase A6 implementation sequence

1. Add a versioned/additive hybrid response contract and canonical intent
   parser fields, with current routes frozen behind regression tests.
2. Implement pure normalization/provenance adapters for local, OMDb, and
   Watchmode payloads, including date parsing and null handling.
3. Implement exact-title resolution with explicit ambiguity handling and a
   bounded availability lookup for `OTT_AVAILABILITY`.
4. Add deduplication and a failure-isolated candidate orchestration layer.
5. Enable freshness retrieval only after release-discovery plan, regional
   coverage, schema, credit cost, and live verification are approved.
6. Implement and test hybrid ranking behind a feature flag; preserve Model A
   baseline outputs for similarity requests.
7. Add frontend rendering only after the API version is stable.

Unresolved Watchmode limitations are regional/latest discovery access and cost,
the live details-payload verification, exact-title ambiguity rules across
localized titles/remakes, source freshness semantics, and the absence of a
verified genre/language discovery endpoint in the current integration.
