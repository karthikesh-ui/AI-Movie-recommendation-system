# Model A Hybrid Retrieval Design

## Scope

This is the implementation design for a later Phase A6. It does not implement
or alter ranking in Phase A5. The frozen baseline is the 48,599-record local
dataset plus its existing TF-IDF matrix and NearestNeighbors model.

## Design principles

- Keep local Model A operational when Watchmode is absent, slow, rate-limited,
  malformed, or unavailable.
- Use Watchmode only for an operation its currently available capabilities can
  support: title resolution, details by ID, and sources by ID/region.
- Treat query mode as an explicit routing decision. “Latest” changes ranking
  only when the user requested it and reliable relevant dates exist.
- Do not treat a recent theatrical date as an OTT date.
- Preserve explicit genre and language relevance before quality/popularity or
  freshness tie-breakers.
- Normalize missing metadata to null/empty collections at the boundary; rankers
  must never call string/date/numeric operations on missing values.

## Proposed orchestration

```text
request
  -> intent parsing + validation
  -> mode router
     -> SIMILARITY: existing local TF-IDF/NearestNeighbors
     -> GENERAL: existing local structured retrieval/ranking
     -> LATEST: local dated records (+ future verified discovery candidates)
     -> OTT_AVAILABILITY: exact title resolution -> Watchmode sources by ID
  -> source adapters normalize candidates and record provenance
  -> conservative deduplication
  -> mode-specific ranking/presentation assembly
  -> response with availability/freshness verification state
```

Watchmode calls belong behind a small timeout-bound adapter. The adapter returns
a typed outcome (`ok`, `timeout`, `rate_limited`, `unavailable`,
`malformed_response`) rather than raising into local retrieval. Provider errors
are represented in response metadata for requests that asked for provider data;
they do not turn a successful local recommendation into an error.

## Candidate collection by mode

### Similarity

Run `recommend_titles` equivalent logic against the unchanged saved artifacts.
The seed title must resolve in the local dataset. Its current exclusion and
title-level deduplication behavior are retained. Watchmode can enrich a
resolved movie or supply a separately verified availability panel, but cannot
be injected into the TF-IDF nearest-neighbor ordering without a newly designed
feature space.

### General

Use existing local intent retrieval as the baseline candidate set. Explicit
genre/language filters are eligibility filters when local values exist; mood
and audience remain soft signals as they are today. Do not call Watchmode title
search as a pseudo-discovery API. Future Watchmode discovery candidates are
allowed only if an approved, verified endpoint provides the requested facets.

### Latest

Require `freshness_kind` and an `as_of_date`. Form candidate pools from records
with a parseable release date. Apply explicit genre/language constraints before
freshness sorting. `latest_released` sorts release date descending; `upcoming`
filters dates after `as_of_date`; `recently_released` applies the configured
date window. Records with only a year are retained outside date-qualified
claims or put after date-qualified candidates, depending on response policy.

No comprehensive “latest Telugu action” claim is possible from current
Watchmode title search. A later release-discovery implementation must pass
provider plan, India coverage, schema, date-type, and cost validation first.

### OTT availability

Resolve a title to a Watchmode ID using exact normalized title and, where
available, year/external IDs. If multiple viable results remain, return a
disambiguation list rather than pick a remake by title alone. Fetch sources
only after resolution and normalize provider name/type/region values actually
returned. A zero-source successful reply means only “no qualifying sources
returned by Watchmode for this title and requested region at lookup time.”

## Conservative deduplication

Each normalized candidate has a `dedupe_evidence` record internally; this is
not necessarily exposed to clients.

1. Merge candidates with the same non-null IMDb ID.
2. Else merge candidates with the same non-null TMDb ID.
3. Else merge candidates with the same non-null Watchmode ID.
4. Else consider normalized title plus the same known release year.
5. If title matches but either side has no year, or the years differ, keep both
   unless another strong identifier establishes equivalence.

The fallback deliberately avoids merging remakes, same-title films, translated
titles, and ambiguous records. Merging combines non-conflicting provenance and
provider availability; it never manufactures a missing ID/date/language. On
field conflicts, retain source-specific values internally and choose a display
value only under a documented precedence rule, rather than overwrite silently.

## Ranking contract for A6

Ranking must be mode-specific rather than a single score that obscures user
intent.

| Mode | Primary ordering | Mandatory guards |
| --- | --- | --- |
| Similarity | Existing nearest-neighbor distance/order | No Watchmode score may reorder Model A baseline candidates. |
| General | Existing deterministic local ranking after genre/language retrieval | Missing Watchmode metadata cannot penalize local candidates or crash ranking. |
| Latest released/recent/upcoming | Eligibility by genre/language and date type/window, then release date descending, then deterministic local quality/popularity tie-breakers | Unknown dates cannot be claimed fresh; upcoming and released never mix without explicit user wording. |
| Latest OTT | Eligibility by provider-confirmed OTT event + requested region/window, then OTT event date descending | Theatrical dates cannot substitute for provider OTT dates. |
| Available now | Provider-confirmed sources for requested region; provider data is an availability filter/presentation dimension, not an inferred recency score | Failed/omitted lookup is `not_verified`, not negative availability. |

A future scoring implementation may quantify genre/language match, quality,
popularity, freshness, and availability, but it must make the eligibility gates
above deterministic and testable. It should be feature-flagged and record a
non-user-facing decision trace: source candidate IDs, rejected reason, merge
evidence, available fields, and ranking components. This makes regressions
auditable without exposing provider internals or API keys.

## Proposed additive response envelope

Do not replace any current route payload during rollout. A new hybrid endpoint
or explicit `v=2` negotiation should return an additive envelope such as:

```json
{
  "mode": "OTT_AVAILABILITY",
  "query": "Where can I watch RRR in India?",
  "intent": {
    "seed_title": "RRR",
    "region": "IN",
    "availability_requested": true
  },
  "results": [],
  "verification": {
    "availability": "verified",
    "freshness": "not_requested",
    "providers": ["watchmode"]
  },
  "degraded": false
}
```

This is illustrative only: the empty `results` deliberately avoids fabricated
movie facts. `degraded` is true when an optional external operation needed for
the selected mode failed but a safe local answer remains. A timeout/rate limit
can include a controlled `provider_status` category; it must not leak upstream
payloads, credentials, or stack traces.

## Configuration and operational safeguards

- Centralize windows (`recently_released_days`, `upcoming_horizon_days`,
  `latest_ott_days`) and source timeouts; test them with an injected clock.
- Keep Watchmode’s current 10-second client timeout subject to an A6 latency
  budget decision. A hybrid request should make at most the bounded calls
  necessary for its mode and never fan out one sources call per broad result.
- Respect client rate-limit backoff and surface retry information already
  normalized by the Watchmode client.
- Cache only according to approved TTLs and provider terms. Cache keys must
  include Watchmode ID, region, and relevant freshness date.
- Never log API keys or raw provider error bodies.

## A6 test plan

All Watchmode cases use mocks/fixtures by default; no paid calls are needed.

| Scenario | Assertions |
| --- | --- |
| Latest Telugu action | Intent is `LATEST`; language/genre precede recency; only valid released dates qualify; status says local-only if discovery is disabled. |
| Latest Hindi comedy | Same gates; deterministic tie-breaking and configurable date window. |
| Telugu OTT movie | Requires region and provider-confirmed source data; does not infer language or OTT date from theatrical metadata. |
| Where to watch a known movie | Exact resolved ID calls sources with `IN`; response contains provider/region and verified state. |
| Similar movies | Baseline Model A order/exclusion remains unchanged with Watchmode success, failure, and no configuration. |
| Unknown title | No false title resolution; return controlled not-found or ambiguity response, not arbitrary first search result. |
| Watchmode timeout | Local fallback survives; availability is `not_verified`; no exception or 5xx from hybrid orchestration when local data exists. |
| Watchmode rate limit | Backoff/error category is surfaced safely; Model A remains available. |
| Duplicate from two sources | Same external ID merges provenance; title/year fallback merges only when both match; missing/different year remains separate. |
| Missing release date | Not freshness-qualified; no date conversion crash; may appear only according to documented fallback ordering. |
| Missing language | No crash; cannot satisfy an explicit language filter by assumption. |
| Existing Model A fallback | With Watchmode disabled/unconfigured, `/api/recommend`, `/api/recommend-text`, `/api/search`, and `/api/movie` preserve their current status codes and response structures. |

Add contract tests for every current route before implementation, unit tests for
normalizers/deduplication/date policy, mocked adapter tests for status handling,
and end-to-end tests for each mode. Run the existing Model A verifier unchanged
as a release gate.

## Acceptance gates before enabling hybrid ranking

1. Current API regression suite and Model A verifier pass unchanged.
2. The new schema normalizers preserve missing data and provenance correctly.
3. Deduplication tests cover remakes/same-title cases and all ID precedence.
4. Failure-isolation tests prove Watchmode cannot break local retrieval.
5. Latest/OTT claims have a date type, region, and source-backed verification
   state.
6. Watchmode advanced discovery access/cost and India coverage are explicitly
   approved and live-verified before it contributes discovery candidates.
