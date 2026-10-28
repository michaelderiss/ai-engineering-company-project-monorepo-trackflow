# TrackFlow — Testing Guide

This document is the test plan and reference for the TrackFlow monorepo's automated
test suites. It was created to close ticket **AUTH-088 (Unit test coverage for the
authentication API)**, and also closes the backlog tickets **API-042** (backoffice
endpoint unit tests) and **FE-019** (frontend utility function tests).

> **Motivation.** Last week a small refactor broke token expiration logic in the
> authentication API. No test caught it and real users were locked out for two hours.
> The CTO's rule is now: *"Untested code is not production code."* This suite exists
> to prove the authentication business logic behaves correctly under normal
> conditions, edge cases, and failure scenarios — not to test HTTP serialisation or
> framework plumbing.

---

## 1. How to run the tests

### Backend — FastAPI + pytest (project root)

```bash
# Install runtime + dev dependencies (first time)
uv sync --dev

# Run the whole suite with coverage (pytest.ini/tool config applies coverage)
uv run pytest

# Run only the authentication tests
uv run pytest tests/test_auth_token.py tests/test_auth_password.py tests/test_auth_endpoints.py

# Coverage report focused on the auth module
uv run pytest --cov=services.api.auth --cov-report=term-missing tests/
```

The `pyproject.toml` `[tool.pytest.ini_options]` block sets `pythonpath = ["."]`
(so `services` / `packages` resolve) and `testpaths = ["tests"]`. Coverage is
configured to track `services.api` only (application code, not test helpers or
stored data files).

### Frontend — Jest (backoffice app)

```bash
cd uis/backoffice
npm install          # installs jest + ts-jest (devDependencies)
npx jest --coverage  # runs uis/backoffice/__tests__/ + packages/shared
```

`uis/backoffice/jest.config.ts` is configured with `rootDir` set to the monorepo
root so that both `uis/backoffice/lib/*` and `packages/shared/http.ts` are
compiled by ts-jest and attributed to coverage. Coverage is scoped via
`collectCoverageFrom` to the three modules under test.

### Shared TypeScript logic (Node built-in runner)

The `packages/shared/http.ts` client and `uis/backoffice/lib/milestone2.ts` loader
are exercised through a lightweight CommonJS harness:

```bash
node --test tests/http-errors.test.cjs
```

---

## 2. Test plan — authentication API (AUTH-088)

The authentication surface lives in `services/api/auth.py` (pure business logic),
`services/api/routes/auth.py` (endpoint wiring) and `services/api/database.py`
(persistence, including password-reset token consumption).

Three pillars are applied to **every** endpoint/function: a **happy path** (valid
input → expected behaviour), an **edge case** (boundary or unusual-but-valid
input), and a **failure mode** (invalid input → graceful rejection). No test
asserts HTTP serialisation details — every test asserts what the code *does*.

### 2.1 `POST /auth/login` — `login_user` / `authenticate_user`

| Pillar | Case | Why it matters |
|---|---|---|
| Happy path | Correct email + password returns a `Token` with a non-empty `access_token` and `token_type == "bearer"` | Core contract of the API |
| Happy path | Token decodes back to the correct `sub` (user id) | Confirms the token actually encodes the user identity |
| Edge case | Login works when the user was created with a `profile` (registration with profile) | Profiles must not interfere with auth |
| Edge case | Email addresses are matched exactly (case-sensitive) | Prevent ambiguous login with case variants |
| Failure | Wrong password → `401`, `authenticate_user` returns `None` | Invalid credentials must be rejected |
| Failure | Unknown email → `401` with identical message | No user enumeration |
| Failure | Inactive (suspended) user → rejected even with a valid password | Suspended accounts must not log in |

### 2.2 `GET /auth/me` — `get_current_user`

| Pillar | Case | Why it matters |
|---|---|---|
| Happy path | Valid token for an existing, active user returns that user | The bearer token proves identity |
| Edge case | User created via registration (with profile) is returned fully | `/me` must work for normal sign-up users |
| Failure | No `Authorization` header → `401` | Unauthenticated requests rejected |
| Failure | Malformed / garbage token → `401` | Bad tokens rejected gracefully |
| Failure | Token for a deleted (unknown) user → `401` | Orphan tokens must not grant access |
| Failure | Token for an inactive user → `401` with "inactive" message | Suspended users lose access |

### 2.3 `POST /auth/forgot-password`

| Pillar | Case | Why it matters |
|---|---|---|
| Happy path | Known, active email → 200, a signed reset token is issued and stored server-side | Reset flow works end-to-end |
| Edge case | Unknown email → same generic 200 message, no token stored | Anti-enumeration; identical response |
| Edge case | Token issued is a signed JWT with `purpose == "password_reset"` | Reset tokens are scoped and cannot be used as access tokens |
| Failure | Empty/malformed email body → 4xx validation | Bad input rejected |

### 2.4 `POST /auth/reset-password` — `reset_user_password`

| Pillar | Case | Why it matters |
|---|---|---|
| Happy path | Valid, unexpired, unused token resets the password and old password stops working | Core reset contract |
| Edge case | Token is single-use: replaying it fails with 400 | One-time tokens prevent replay attacks |
| Edge case | Token with wrong `purpose` (e.g. an access token) is rejected | Tokens are scoped to their purpose |
| Edge case | Short new password (e.g. 7 chars) → 4xx validation | Minimum strength enforced |
| Failure | Expired token → 400, password unchanged | **This is the exact regression from last week** |
| Failure | Unknown/garbage token → 400, password unchanged | Malformed tokens rejected |
| Failure | Already-used token → 400 | Replay protection |

### 2.5 `POST /auth/change-password`

| Pillar | Case | Why it matters |
|---|---|---|
| Happy path | Correct current password + valid new password updates the account | Core self-service flow |
| Edge case | New password differs from current and passes min length | Boundary of acceptable input |
| Failure | Wrong current password → 400 and password unchanged | Must never overwrite with bad credentials |
| Failure | No bearer token → 401 | Authenticated endpoint |
| Failure | Empty current password / short new password → 4xx validation | Input boundaries |

### 2.6 Token & password helpers (unit level)

Covered directly in `tests/test_auth_token.py` and `tests/test_auth_password.py`:

- `create_access_token`: happy path (decodes, correct `sub`, correct `exp` delta),
  edge (custom payload fields preserved), failure (never encodes `None` subject).
- `decode_access_token`: happy path (round-trips), edge (`sub` missing), failure
  (expired token → 401 HTTPException), failure (malformed token → 401), failure
  (non-integer `sub` → 401).
- `verify_password` / `get_password_hash`: hash round-trips, wrong password false.
- `change_user_password`: correct current password updates, wrong current password
  returns `False` without touching the stored hash.
- `create_password_reset_token`: happy (returns token + future expiry, stores a
  server-side record keyed by the token's `jti`), edge (respects configured expiry).

---

## 3. Test plan — backoffice endpoints (API-042, extra)

Three non-authentication endpoint groups receive the same three-tier treatment,
with a 60% coverage target on the modules under test.

### 3.1 Users — `services/api/routes/users.py`

- **Happy path:** admin creates a user (201, password hashed, profile attached),
  gets a user, lists users.
- **Edge case:** duplicate email → 400 "already exists"; email validation rejects
  addresses without `@` or `.`.
- **Failure mode:** unauthenticated list → 401; non-admin user reading another
  user → 403; missing user → 404.

### 3.2 Profiles — `services/api/routes/profiles.py`

- **Happy path:** create a profile for the current user, read it back via `/me`,
  patch it (create-or-update semantics).
- **Edge case:** creating a second profile → 400 (one profile per user).
- **Failure mode:** no profile yet → `GET /profiles/me` 404; non-admin listing all
  profiles → 403; accessing another user's profile → 403.

### 3.3 Suppliers — `services/api/routes/suppliers.py`

- **Happy path:** create a supplier (201), list with filters, read by id, update
  rate and status.
- **Edge case:** country/currency mismatch (USA + EUR) rejected by model;
  invalid category filter → 422.
- **Failure mode:** missing supplier by id → 404; delete missing supplier → 404.

---

## 4. Test plan — frontend utilities (FE-019, extra)

`uis/backoffice/lib/` helpers are tested with Jest in `uis/backoffice/__tests__/`.
Each function gets at least one happy-path and one failure-mode test.

### 4.1 `lib/auth.ts` — token storage helpers

- **Happy path:** `setToken`/`getToken`/`clearToken` round-trip; `isAuthenticated`
  reflects presence of the token.
- **Failure mode:** `getToken` returns `null` when `localStorage` is unavailable;
  `setToken` throws a friendly error when storage is blocked.

### 4.2 `packages/shared/http.ts` — API response handling

- **Happy path:** `requestResponse` returns the response for a successful fetch;
  `requestJson` parses valid JSON.
- **Failure mode:** network error → `RequestError` with a safe, connection-focused
  message (no internal details); 401/5xx map to friendly messages; unreadable JSON
  → `RequestError`.

### 4.3 `lib/incidents.ts` — incident response parser

- **Happy path:** `incidentRequest`'s validator accepts a well-formed incident
  object / list.
- **Failure mode:** the validator rejects malformed payloads (missing `id`, wrong
  field types), so `apiFetch` refuses incomplete data.

---

## 5. Cases identified with AI assistance / bugs caught

Per the AI-assisted workflow requirement, these were the concrete wins:

1. **Expired-token regression (AUTH-088 core).** The teammate's refactor last week
   broke token expiration. `tests/test_auth_token.py::test_expired_token_rejected`
   locks the behaviour: a token encoded with a past `exp` must raise
   `HTTPException(401)`. The original regression would be caught by this exact test.

2. **Purpose-scoped reset tokens.** Prompting the AI agent with
   `create_password_reset_token` / `reset_user_password` surfaced the `purpose`
   claim and `jti`/server-side record design. Tests assert that an **access token
   cannot be used as a reset token** (wrong `purpose` → rejected), and that a reset
   token is **single-use** (server-side record consumed after first use). This
   cross-token scoping is easy to miss.

3. **`PASSWORD_RESET_TOKEN_EXPIRE_MINUTES` is read at import time.** The AI agent
   flagged that the expiry constant is captured at module import, so tests must
   `monkeypatch` `services.api.auth.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES` **and**
   freeze the clock via `freezegun` to exercise "expired reset token" deterministically.
   Without the frozen clock, a freshly minted token can never appear expired.

4. **Non-integer `sub` payload.** The AI agent suggested testing `sub = "abc"` /
   `sub` as a list, which the code handles by converting to `int` inside
   `TokenData`. Tested as a failure mode (401) to prevent a crash-level regression.

5. **Inactive users are rejected at login AND at `/me`.** The agent cross-checked
   `authenticate_user` and `get_current_user`, catching that both enforce
   `is_active`. Covered as failure modes on both paths.

6. **Empty-string `jti` on a reset token (AI-identified gap).** When writing the
   single-use reset-token tests, the agent probed the app's own guard in
   `reset_user_password` (`if not isinstance(reset_id, str) or not reset_id`). It
   discovered that a **non-string** `jti` never reaches that guard (the JWT
   library rejects it at decode time with `JWTError`), and a **missing** `jti`
   raises `KeyError` earlier — so the only input that actually exercises the
   guard is an **empty-string** `jti`. The test `test_reset_token_with_empty_jti_is_rejected`
   pins this and pushed `auth.py` to 100% line coverage. This insight (which
   input reaches which line) is exactly what a purely mechanical coverage chase
   would have missed.

No bugs were uncovered in the current code by the suite — the recent regression
was already fixed by the time this milestone started, and these tests now guard it.
The findings above document *why* certain tests exist, which is the real value of
the AI-assisted workflow.

---

## 6. Coverage results

### Backend (pytest)

Run with `uv run pytest` from the repo root (coverage is configured in
`pyproject.toml`; `addopts = "--cov --cov-report=term-missing"` applies it
automatically). Reference results (last full run):

```
=============================== tests coverage ================================
Name                               Stmts   Miss  Cover   Missing
services\api\auth.py                  85      0   100%
services\api\database.py             246     14    94%
services\api\incidents.py             61      0   100%
services\api\main.py                 115     29    75%
services\api\models.py               108      1    99%
services\api\routes\auth.py           42      0   100%
services\api\routes\incidents.py      33      1    97%
services\api\routes\profiles.py       54      4    93%
services\api\routes\suppliers.py      38      0   100%
services\api\routes\users.py          46      2    96%
services\api\email.py                 36      7    81%
services\api\seed.py                  13      3    77%
TOTAL                                877     61    93%
================ 152 passed ================
```

Key numbers vs. the ticket targets:

| Module | Target | Actual |
|---|---|---|
| `services/api/auth.py` | **AUTH-088: ≥70%** | **100%** |
| `services/api/routes/auth.py` | (auth routes) | **100%** |
| `services/api/routes/users.py` | API-042: ≥60% | **96%** |
| `services/api/routes/profiles.py` | API-042: ≥60% | **93%** |
| `services/api/routes/suppliers.py` | API-042: ≥60% | **100%** |
| `services/api/database.py` | (supporting) | **94%** |
| **Overall `services.api`** | — | **93%** |

> Coverage is a floor, not a goal: the intent and the failure-mode coverage matter
> more than the number. A well-reasoned 70% beats a mechanical 95%. The whole
> suite (**152 tests**) passes with `uv run pytest`.

### Frontend (Jest)

Run with `npx jest --coverage` from `uis/backoffice`. Reference results (last
full run):

```
File                | % Stmts | % Branch | % Funcs | % Lines
packages/shared/http.ts    |   85.45 |    66.1  |   100   |  89.47
uis/backoffice/lib/auth.ts |   79.54 |    61.53 |  66.66  |  81.08
uis/backoffice/lib/incidents.ts |  100  |   95.83 |   100   |  100
All files                  |   85.59 |    72.91 |  85.29  |  86.74
```

FE-019 requires one happy-path + one failure-mode test per function — all 25
tests pass across 3 suites. `incidents.ts` is fully covered; `http.ts` and
`auth.ts` have healthy branch coverage, with the remaining gaps being defensive
branches (e.g. `SAFE_MESSAGES` fallback mappings) that are intentionally
unreachable from the exercised inputs.

---

## 7. Test suite layout

```
TESTING.md                         ← this document
pyproject.toml                     ← pytest + coverage configuration, dev deps
tests/
  conftest.py                      ← shared fixtures (isolated TinyDB, client, clock)
  test_auth_token.py               ← create_access_token / decode_access_token
  test_auth_password.py            ← hashing, change/reset password helpers
  test_auth_endpoints.py           ← endpoint-level auth (login, me, forgot/reset/change)
  test_users_api.py                ← API-042
  test_profiles_api.py             ← API-042
  test_suppliers_api.py            ← API-042
  test_error_handling.py           ← pre-existing (email safety, CLI, CSV)
  test_incidents_api.py            ← pre-existing (incident endpoints + lifecycle)
  http-errors.test.cjs             ← pre-existing shared http harness (node --test)
uis/backoffice/
  jest.config.ts                   ← Jest configuration (rootDir = monorepo root)
  __tests__/
    auth-utils.test.ts             ← FE-019 token storage helpers
    http-client.test.ts            ← FE-019 shared http client
    incidents-utils.test.ts        ← FE-019 incident response parser
```

### Test counts

| Suite | Command | Tests |
|---|---|---|
| Auth (AUTH-088) | `uv run pytest tests/test_auth_token.py tests/test_auth_password.py tests/test_auth_endpoints.py` | 51 |
| Backoffice endpoints (API-042) | `uv run pytest tests/test_users_api.py tests/test_profiles_api.py tests/test_suppliers_api.py` | 56 |
| Backend total (incl. pre-existing) | `uv run pytest` | **152 passed** |
| Frontend utilities (FE-019) | `npx jest --coverage` (in `uis/backoffice`) | **25 passed** |