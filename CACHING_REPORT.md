# TrackFlow Caching Optimisation

## Scope and Method

Implemented on the existing `feature/caching` branch, targeting the logistics
backoffice and existing FastAPI service, not the recruitment reference app.
Measurements below are local synthetic experiments, **not production telemetry**.
Production request frequency is unknown; estimates are explicitly labelled.
Backoffice typechecking passed before edits. The backend runner was initially
unavailable (`uv` and pytest missing); a disposable Python environment was used
for isolated API startup, profiling and regression checks. A pre-change live
frontend/backend smoke test was not captured; production UI checks were performed
after implementation. No production database was seeded or modified.

Timing middleware emits method, matched route template, status and elapsed ms
for each request, including failures. Query strings, tokens, payloads and actual
path identifiers are deliberately excluded. Repeated identical URLs are generated
by the profiling script, rather than inferred from privacy-sensitive log values.

### Reproduction

Use the repository Python environment with API requirements and test dependencies
(`httpx<0.28`, pytest, pytest-cov, freezegun). In this container the working runner
was `/tmp/trackflow-caching-venv/bin/python` instead of `uv run python`.

```bash
python scripts/profile_caching.py --uncached --repeats 20
python scripts/profile_caching.py --repeats 20
python -m pytest -q --no-cov --disable-warnings
npm --prefix uis/backoffice test -- --runInBand
npm --prefix uis/backoffice run typecheck
npm --prefix uis/backoffice run build
npm --prefix uis/backoffice run start -- --port 3101
# With Playwright and its Chromium browser installed:
PLAYWRIGHT_MODULE=/tmp/trackflow-caching-browser/node_modules/playwright node scripts/check_caching_ui.cjs
python scripts/check_memory_bank.py
```

The Python script sets `DATABASE_URL` to temporary SQLite before importing the
application and redirects TinyDB and incident storage into the same disposable
directory. It seeds valid foreign keys, three product categories, two warehouses,
40 clients, varied quantities, references, dispatch/loss movements and dates,
plus incidents spanning every allowed category/status/origin/branch. Review
`seed_load` before running. Temporary storage is deleted on exit. No artificial
sleep or injected query delay is used. It also prints every registered route.

### Dataset and Results

| Table | Before | After |
| --- | ---: | ---: |
| Inventory SKUs | 6 | 2,006 |
| Stock entries | 4 | 20,004 |
| Stock exits | 3 | 20,003 |
| Incidents | 0 | 20,000 |

20 identical sequential requests per route, FastAPI TestClient, local SQLite,
Python 3.14; timings include middleware, auth where required and response encoding.

| Read | Small-data uncached median | Seeded uncached median | Seeded cache-miss first request | Seeded cached median |
| --- | ---: | ---: | ---: | ---: |
| GET /inventory/products | 2.98 ms | 107.14 ms | 122.88 ms | 2.01 ms |
| GET /api/incidents/summary | 2.34 ms | 28.27 ms | 28.64 ms | 1.88 ms |

The first pre-cache experiment recorded 168.49 ms / 27.44 ms seeded medians;
the reproducible `--uncached` rerun recorded 107.14 ms / 28.27 ms. Catalog timings
vary with runtime warmup and contention, so use the lower baseline for comparison:
approximately 98% / 93% lower local warm latency. Cached medians include one miss
and 19 hits; expiry and write-heavy traffic reduce this benefit. Response sizes
are 293,012 bytes for catalog and 483 bytes for summary. No claim is made about
Supabase network latency, concurrent throughput, production p95 or TTI gains.

## Frontend Decisions

### Two Conditional Lazy Loads

1. `IncidentAnalysisReport` uses `next/dynamic` with `ssr: false`, mounted only
   after successful CSV analysis. Uploading is the initial workflow; the five
   report sections and label mapping cannot be useful before a result exists.
   Actual separate production chunk: **3,080 bytes uncompressed**. Browser checks
   confirm it is absent initially and fetched after successful analysis. Small
   absolute savings are acknowledged; no chart library or exaggerated bundle
   reduction is claimed. Upload, error and export state remain in the page.
2. `InventoryHistoryTable` uses `next/dynamic` with `ssr: false`, mounted only
   after nonempty history arrives. Navigation, refresh and loading/error/empty
   states do not require table rendering or date preparation. Actual separate
   production chunk: **2,450 bytes uncompressed**. Browser interception holds the
   API response and verifies the chunk is absent until that boundary resolves.
   This introduces a small extra chunk roundtrip when data arrives, acceptable
   for a secondary read-only history view, not a critical dispatch form.

Both boundaries provide accessible loading feedback. Next.js already splits
routes, so these changes defer work *within* routes instead of claiming existing
route splitting as a new optimisation.

### Non-Trivial useMemo

History previously localized every movement timestamp inside rendering.
A five-run Node/V8 microbenchmark on 40,007 varied timestamps measured
459.10 / 70.13 / 72.33 / 72.31 / 67.27 ms (median **72.31 ms**). This isolates
computation, not total React render duration or a React DevTools trace.

`InventoryHistoryTable` now memoizes date formatting and display-row preparation
with **`[orders]`**: every derived field depends only on immutable API order data.
Page changes leave that array unchanged; refresh supplies a new array and
recalculates. Browser instrumentation of `Date.prototype.toLocaleString` confirms
40,007 calls on mount, **zero additional calls on page change**, and 40,007 new
calls after refresh, at both 1440x1000 and 390x844. There is no claim that useMemo
prevents rendering itself. A 50-row page bounds DOM work; this is client-side
pagination, not reduced API transfer size. The first calculation and all-row
download remain O(n); server pagination/virtualisation is future work.

The memo stores one derived array for the mounted component and can temporarily
increase browser memory. It is not a time-based server-data cache: data freshness
still depends on the existing refresh/fetch lifecycle. No persistent browser
response cache is added. Removed the analyzer's trivial nine-label `useMemo`.

## Backend Decisions

### GET /inventory/products

- Cost: aggregates stock by SKU/warehouse and constructs the entire catalog;
  measured 107.14 ms seeded median and about 286 KiB response.
- Frequency assumption: 30 identical reads/minute across operations users and
  product selectors; scenario estimate, not observed production traffic.
- Key: SQLAlchemy engine identity, with no filters because this endpoint accepts
  none. Response is already public and identical for all callers. No token,
  movement creator, tracking number or user profile is added to the cache.
- TTL: **15 seconds**. Same-process successful SKU creation, inbound receipts
  and outbound dispatch/loss commits clear the catalog cache before returning.
- Storage: at most four entries, each at most 1 MiB; oversized responses are served
  uncached. Immutable, validated JSON bytes avoid repeated ORM/Pydantic encoding.
- Expected best-case no-write load: about four full computations/minute instead
  of 30. Writes, eviction and worker count reduce the hit ratio.

### GET /api/incidents/summary

- Cost: count plus four grouped scans over incident rows; measured 28.27 ms
  seeded median. Small 483-byte aggregate makes storage cheap relative to scans.
- Frequency assumption: 15 staff checking twice/minute = 30 reads/minute, normally
  about two per user/minute. No polling was introduced to manufacture demand.
- Key: **`(incident database path, authenticated user ID)`**. Authentication runs
  on hits as well as misses; another user's request cannot reuse this entry.
  Summary currently contains global aggregates, not descriptions or identities.
  Future tenant/role-specific queries must include their visibility scope too.
- TTL: **30 seconds**. Store-level create and status-update functions clear all
  users' summaries only after a successful transaction, including direct seeding
  in this process. Failed writes leave valid cached values alone.
- Storage: at most 128 entries, each at most 16 KiB. Per-user scoping intentionally
  sacrifices cross-user hits for isolation; a user's two reads within 30 seconds
  can share a scan, but evenly spaced 30-second reads may have no hits.

### Expiry, Safety and Invalidation

`TTLCache` uses monotonic deadlines, lazy expiry cleanup, least-recently-used
bounded eviction and a per-cache reentrant lock. Miss computations are serialized
inside that lock to suppress same-process stampedes and prevent an older load
from repopulating after invalidation. Exceptions are never cached. Serializing
misses can block unrelated keys; summary keys make that a deliberate small-scale
tradeoff. JSON responses use `Cache-Control: no-store` so browser/proxy caches do
not bypass application expiry/invalidation. Cache keys never contain raw tokens.

**Freshness tradeoff:** a warehouse catalog is an advisory overview, not stock
reservation. Up to 15 seconds of cross-worker/external-write staleness is acceptable
for scanning; individual SKU reads and outbound availability checks still read
the database, and dispatch validation/locking remains authoritative. Incident
counts are monitoring data, so up to 30 seconds of cross-worker staleness is
acceptable, whereas a committed status change is reflected immediately on the
same process. A refresh on another worker may still show the older value.

In-process invalidation is **not distributed coherence**. Each worker/replica has
its own cache; external SQL and a separate seed process cannot clear another
process's memory. TTL bounds that window but does not guarantee read-your-writes
across replicas. Use one API worker if immediate UI read-your-writes is required;
before scaling that guarantee, migrate these keys and invalidation to Redis or
another coordinated generation mechanism. Process restart simply starts cold.

## Complete Endpoint Assessment

Costs except the two measured reads are code-path estimates. Frequency figures
below are workload assumptions per active user unless explicitly aggregate.
Change frequency describes source data, not request frequency. Combined rows
explicitly enumerate every method on each path. Framework documentation routes
are included to make the inventory complete.

| Method and path | Cost | Estimated calls | Data changes / decision |
| --- | --- | --- | --- |
| POST /auth/login | High bcrypt | 1/session | Session-specific; never cache |
| GET /auth/me | Small identity lookup | 1-3/session | Identity/access can change; private, no cache |
| POST /auth/forgot-password | Lookup/sign/email queue | Occasional | Sensitive token side effects; no cache |
| POST /auth/reset-password | Verify/hash/write | Occasional | One-use token/password change; no cache |
| POST /auth/change-password | Two bcrypt operations/write | Occasional | Sensitive mutation; no cache |
| POST /users | Hash/write | Registration | Mutation; no cache |
| GET /users | TinyDB scan | <1/min | Private user directory; no cache |
| GET /users/{user_id} | Identity lookup | <1/min | Private/access-sensitive; no cache |
| PATCH /users/{user_id} | Hash or identity write | Occasional | Mutation; no cache |
| DELETE /users/{user_id} | Identity write | Rare | Mutation; no cache |
| POST /profiles | TinyDB write | Once/account | Private mutation; no cache |
| GET /profiles | TinyDB scan | <1/min | Private directory; no cache |
| GET /profiles/me | Lookup | 1/profile view | Personal data; no cache |
| PATCH /profiles/me | Write | Occasional | Personal mutation; no cache |
| GET /profiles/{profile_id} | Lookup | <1/min | Private data; no cache |
| PATCH /profiles/{profile_id} | Write | Occasional | Private mutation; no cache |
| POST /suppliers | Validate/TinyDB write | Occasional | Mutation; no cache |
| GET /suppliers | TinyDB filter/scan | 1-5/min | Rates/status change during editing; no measured need, no cache |
| GET /suppliers/{supplier_id} | Lookup | <1/min | Contact/rate details; cheap, no cache |
| PATCH /suppliers/{supplier_id}/rate | Write | Occasional | Pricing mutation; no cache |
| PATCH /suppliers/{supplier_id}/status | Write | Occasional | Availability mutation; no cache |
| DELETE /suppliers/{supplier_id} | Write | Rare | Mutation; no cache |
| GET /inventory/products | Grouped stock aggregation | 30/min aggregate | Movement-driven; 15s cache + invalidation |
| POST /inventory/products | SQL insert | Occasional | Mutation; invalidates catalog |
| GET /inventory/products/{sku_id} | Lookup/two stock sums | 1-5/min | Fresh pre-dispatch stock required; no cache |
| POST /inventory/orders/inbound | Validate/insert | Operational | Mutation; invalidates catalog |
| POST /inventory/orders/outbound | Lock/sums/insert | Operational | Correctness-critical; never use cache, invalidates catalog |
| GET /inventory/orders | Two joins/model mapping/sort | 1-2/min | Changes every movement; creator/tracking fields, no shared cache |
| GET /health | Constant state check | 12/min/monitor | Immediate readiness required; no cache |
| POST /api/incidents/analyze | CSV parse/validation/aggregation | 1/upload | File-specific side effect; no new cache |
| GET /api/incidents/results/export | CSV formatting | 1/analysis | Uploaded result workflow; no new cache |
| GET /api/incidents/options | Constant dictionaries | 1/view | Cheap constants; no added TTL machinery |
| GET /api/incidents/summary | Five aggregate queries | 30/min aggregate estimate | Create/status-driven; user-scoped 30s cache |
| POST /api/incidents | Transactional insert | Operational | Mutation; invalidates summaries |
| GET /api/incidents | Filtered scan/record mapping | 1-5/min | Descriptions/filter combinations; no measured shared-cache justification |
| GET /api/incidents/{incident_id} | Single-row lookup | 1/detail view | Must reflect edits; no cache |
| PATCH /api/incidents/{incident_id}/status | Transaction/read/write | Operational | Mutation; invalidates summaries |
| GET, HEAD /openapi.json | Schema generation (framework-managed) | Developer use | Framework behaviour unchanged |
| GET, HEAD /docs | Small HTML | Developer use | Not business load; unchanged |
| GET, HEAD /docs/oauth2-redirect | Small HTML | Developer login | Auth tooling; unchanged |
| GET, HEAD /redoc | Small HTML | Developer use | Not business load; unchanged |

## What Was Not Cached and Why

Stock detail/outbound computation deliberately remains uncached even though it
repeats: stale availability must never authorize an oversell. User/profile data
is private and cheap relative to the added invalidation/access-control risk.
Supplier reads lack measured expensive work; neither stable options nor the
small analyzer label lookup justifies more cache machinery. The initial upload
controls and stock-exit form are not lazy-loaded because they are primary tasks.

Pre-existing risk outside this change: the analyzer/export workflow still uses
the existing process-global `_LAST_ANALYSIS`. It is not part of the new caches;
its cross-user ownership should be fixed in a separate authorization change
before using uploaded private data in a multi-user deployment. This milestone
does not claim to resolve that legacy issue or other existing access policies.

## Validation and Remaining Limits

- Full backend: **172 passed**; existing frontend utilities: **32 passed**.
- Five focused cache tests cover expiry at the deadline, hits, explicit clears,
  capacity/oversize bypass, failed loader recovery, user separation, unauthenticated
  rejection, all catalog writes, incident creation/status invalidation, and logs.
- Backoffice typecheck and production build pass; both dynamic chunks emitted.
- Chromium at desktop/mobile sizes verifies conditional loading, 50 rendered
  history rows, next-page memo reuse, refresh recomputation and analyzer rendering;
  no page exceptions. Synthetic responses exercise UI, not live API authorization.
- Screenshots inspected at `/tmp/trackflow-{history,analyzer}-{1440,390}.png`;
  history keeps the existing horizontally scrollable table on small screens.
- Browser scripts require separately installed Playwright/Chromium; no runtime
  dependency or lockfile change was needed. No React DevTools trace was captured;
  measured computation plus actual browser call counts are the frontend evidence.
- No production load trace, distributed invalidation, real email or Supabase
  performance check was claimed. No commit/push/PR is made before final approval.