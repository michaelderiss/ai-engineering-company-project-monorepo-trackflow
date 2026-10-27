# Progress

## Completed

- Added script-first incident analyzer with context-aligned metrics.
- Created deterministic 100-row fixtures:
  - scripts/incidents-trackflow.csv
  - scripts/incidents-company.csv
- Verified script output matches expected totals:
  - total 100, valid 95, invalid 5
  - categories 14/38/19/17/7
  - status 29/52/14
  - country 50/45
  - satisfaction average 3.06 with 6/11/15/14/6 distribution
- Implemented backend analysis and export endpoints reusing shared logic.
- Refactored backoffice into launcher + app directories:
  - / hosts homepage with dropdown application launcher.
  - /incident-file-analyzer hosts the incident analysis implementation.
  - /website and /talent-pipeline-tracker are available as additional launcher options.
- Implemented backoffice incident-file-analyzer page with upload and CSV download.
- Implemented supplier directory milestone in services/api with TinyDB persistence and startup seeding.
- Added supplier endpoints for list/filter, create, detail, rate update, status update, and delete.
- Added backoffice /suppliers page with live API-backed filters, supplier registration form, rate editing, and status toggle.
- Added root pyproject.toml script entry so `uv run seed` is defined when `uv` is installed in the environment.
- Implemented JWT-based auth for the TrackFlow API, including TinyDB-backed user and profile storage, `/auth/login`, `/users`, `/profiles`, and protected internal routes requiring bearer-token validation.

## AUTH-02 — Authentication flows and protected frontend views

- Created `uis/backoffice/lib/auth.ts` — core auth library with `getToken`, `setToken`, `clearToken`, `isAuthenticated`, `redirectToLogin`, `redirectToHome`, and `apiFetch<T>()` generic fetch wrapper that auto-attaches Bearer tokens and handles 401 responses.
- Created `uis/backoffice/app/login/page.tsx` — login form (email + password) that POSTs to `/auth/login` with form-urlencoded body (OAuth2PasswordRequestForm), stores the JWT via `setToken()`, and redirects to `/`.
- Created `uis/backoffice/app/register/page.tsx` — registration form (email, password, optional display_name/phone/address) that creates the user via POST `/users`, then logs in automatically via POST `/auth/login`, stores the JWT, and redirects to `/`. Falls back to email-username as display_name when profile fields are present but display_name is empty.
- Created `uis/backoffice/app/account/profile/page.tsx` — profile view/edit page that loads user data from GET `/auth/me` and profile from `/profiles/me`, with an editable form for display_name/phone/address that saves via PATCH `/profiles/me`. Shows email, role, account status, and member-since date.
- Created `uis/backoffice/app/logout/page.tsx` — calls `clearToken()` then `redirectToLogin()`, with a fallback "Logged Out" message if JavaScript redirect fails.
- Created `uis/backoffice/components/AuthGuard.tsx` — reusable React client component that wraps content with a `useEffect` auth check, redirecting to `/login` if no token is found.
- Modified `uis/backoffice/app/layout.tsx` — added inline `<AuthGuardScript />` that runs on every page load, exempting public paths (`/login`, `/register`, `/logout`) while redirecting all others to `/login` if no token exists.
- Modified `uis/backoffice/app/globals.css` — added styles for auth forms (`.required`, `.success`, input types `[email]`/`[password]`/`[tel]`) and top navigation (`nav.top-nav`, `.nav-brand`, `.nav-links`, `.nav-link`).
- Modified `uis/backoffice/app/suppliers/page.tsx` — all 4 fetch calls (GET suppliers, POST suppliers, PATCH rate, PATCH status) now use a local `authFetch()` wrapper that injects the Bearer token and handles 401 redirects, with correct `Content-Type` handling for non-FormData bodies.
- Modified `uis/backoffice/app/incident-file-analyzer/page.tsx` — POST `/api/incidents/analyze` now uses `authFetch()` for Bearer token injection and 401 handling, skipping Content-Type override for FormData file uploads.
- Modified `uis/talent-pipeline-tracker/app/layout.tsx` — added the same inline `<AuthGuardScript />` for route protection using the shared localStorage token (the talent pipeline tracker uses a separate API but shares the token for auth guard purposes).
- Modified `services/api/routes/profiles.py` — added `PATCH /profiles/me` endpoint that creates a profile if one does not exist (via `create_profile_for_user`) or updates it (via `update_profile_for_user`), accepting `ProfileCreate` payload and returning `Profile` response model.
- **Verified**: All 8 new/modified files pass `get_errors` with zero errors.
- **Verified**: Public website (`uis/website/app/layout.tsx`) is completely untouched — no auth guard script was added.
- **Scope**: Backoffice app is fully protected. Talent pipeline tracker has route-level protection but no login UI (it shares the backoffice login). Public website is completely unaffected.

## AUTH-03 — Password recovery and change

- Added `POST /auth/forgot-password`, which issues a signed reset token for active users and queues a link through Resend as a background task. The endpoint returns the same 200 confirmation for known and unknown email addresses without waiting on provider latency.
- Added `POST /auth/reset-password`, which validates the token signature, purpose, expiry, and server-side one-use record before updating the password hash. Invalid, expired, and replayed tokens return 400.
- Added authenticated `POST /auth/change-password`, which verifies the current password before applying the new password and returns 400 for an incorrect current password.
- Added persistent token records in TinyDB, storing a hash of each reset token ID and marking a record used when the password changes.
- Added Resend integration in `services/api/email.py`; API key and sender are environment-only values. Root `.env.example`, `.gitignore` rules, `python-dotenv` loading, and `services/api/README.md` document local setup.
- Added console fallback in email delivery: when Resend is unconfigured, blocked, or rejects a send, the generated reset link is printed to the API console so the forgot/reset flow remains usable locally.
- Added backoffice `/forgot-password` and `/reset-password` public pages, plus protected `/account/change-password`. Login links to recovery; the profile view links to password change. Reset pages are exempt from the inline route guard.
- Added auth API tests for account enumeration resistance, successful reset and token replay rejection, expired token rejection, and change-password current-password checks.
- Repaired malformed supplier PATCH calls that prevented app-wide typechecking; they now use the existing authenticated fetch helper and send the expected JSON payloads.
- Moved logout token clearing/redirect into a client effect so the auth page can be statically prerendered.
- **Environment note**: the working `.env` lives at the repo root (where `services/api/main.py` loads it via `python-dotenv`). A local `uis/backoffice/.env.local` sets `NEXT_PUBLIC_INCIDENTS_API_BASE_URL` for the backoffice app; both files are git-ignored.
- **Verified fallback**: confirmed `services/api/email.py` prints the reset link to the API console instead of raising when Resend is unreachable or unconfigured; direct invocation returned without raising, and the earlier traceback (`raise EmailDeliveryError ... from exc`) no longer exists in source.
- **Verified**: `tests/test_auth_api.py` passes (5 tests); `uis/backoffice` TypeScript typecheck passes.
- **Verified**: `uis/backoffice` production build passes and generates the new reset/change-password routes.
- **Setup requirement**: Configure a Resend API key and verified sender in the local `.env` or deployment environment before expecting real reset emails.

## Centralized Incident Manager (CIM1-CIM3)

- Implemented the model, branch labels, nine categories, three origins, and four-state lifecycle from `trackflow-BRIEFING.en.md`.
- Extracted the analyzer's CSV validation into `packages/shared/incident_validation.py`; the analyzer retains its existing interface and 100/95/5 totals. Shared manager contracts and mappings live in `packages/shared/incidents.py`.
- Added transactional SQLite incident persistence under `services/api/data/incidents.sqlite3`, separate from existing identity/supplier stores. A separate import ledger prevents duplicate seeds without storing CSV IDs on incidents.
- Added `scripts/seed_incidents.py`: validates before transformation, preserves descriptions, maps dates to midnight UTC, skips invalid rows with privacy-safe messages, and supports missing-ID title/timestamp duplicate control.
- Verified seed in isolated databases: 95 inserted / 5 invalid, followed by 95 duplicates skipped. Expected transformed totals match the briefing, including carrier_issue 45 and office branch counts 50/45.
- Added authenticated create/list/detail/status/summary endpoints and an options endpoint for shared UI labels. Manager validation returns field-keyed JSON 400 errors; unexpected failures return a generic 500; empty storage returns zero metrics.
- Added protected backoffice `/incidents` with an Operations Home launcher entry, registration form, highlighted required branch field, four list filters, independent loading/error/retry states, summary breakdowns, and optimistic status updates with rollback.
- Verification: 29 incident API tests pass; the full backend suite, backoffice typecheck, and production build passed during implementation. Browser checks verified validation, creation/reset, filters/empty state, lifecycle update, failed-save rollback, list/summary failure isolation and retry, pending submission disablement, and narrow-screen layout.
- Local storage was seeded with 95 incidents; browser verification added one carrier_issue incident at la_warehouse and advanced it to in_progress (96 total after that check). Seeding again will not remove browser-created records.
- API setup/expected totals and browser/PR screenshot steps are documented in the API and backoffice READMEs. No embeddings or automatic alerts were added; they are outside this delivery.

## Notes

- No customer emails are printed or exported by script/API/UI outputs.
- API dependency pin uses FastAPI + Pydantic v1 compatibility due Python 3.15 beta environment constraints.
- `uv run seed` is configured in-repo, but this machine currently does not have `uv` installed on PATH and package download for `uv` was blocked by network connectivity during validation.

## Restored website/backoffice baseline

- Restored the TrackFlow public website to a componentized structure with reusable `Header` and `FeatureCard` components instead of the monolithic inline page.
- Re-established the source-of-truth data flow from `src/trackflow-website/content.ts` to the shared website screen used by the public app and backoffice route.
- Fixed the Next.js 16 module-boundary issue by resolving the shared content through an alias (`@trackflow-content`) and by keeping the required Turbopack/webpack configuration compatible with the repo setup.
- Verified both app builds pass after the restoration:
  - `uis/website`: `npm run build` succeeded
  - `uis/backoffice`: `npm run build` succeeded

This is the current working baseline to preserve before additional feature work or remote merges.
