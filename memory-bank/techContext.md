# Technical Context

## Current repository baseline

This repository now combines three active implementation layers:

- repo-level agent governance and memory-bank rules
- Milestone 2 logistics utilities and test interface in `src/`
- Next.js UI surfaces in `uis/website` and `uis/backoffice`

## Existing implementation surfaces

### 1. Milestone 2 TypeScript utility layer in src

The `src/` folder now includes a substantial Milestone 2 implementation, not only static prototype files.

Core modules:

- `src/types/models.ts`: domain types for products, shipments, carriers, inventory movements, and sample datasets.
- `src/utils/collections.ts`: filtering and sorting utilities for product and carrier operations.
- `src/utils/search.ts`: linear search and binary search utilities.
- `src/utils/transformations.ts`: shipping-cost calculation, carrier scoring/selection, and aggregation utilities.
- `src/utils/validations.ts`: validation helpers for product, shipment, and carrier entities.
- `src/index.ts`: central export barrel.
- `src/demo.ts`: demo runner that exercises all major utility functions.

Milestone UI/test surface:

- `src/index.html`: browser testing console for Milestone 2 operations.
- `src/testing-interface.js`: event handlers and in-browser operation orchestration for filters, search, sorting, carrier scoring, reports, and validations.
- `src/milestone2-output.js`: shared Milestone 2 output helper that powers dummy-order output generation for both browser testing and Node scripts.
- `scripts/generate_milestone2_output.cjs` now reads `products`, `carriers`, `shipments`, and optional `milestone2OrderContext` directly from `src/testing-interface.js`, making the sync artifacts source-aligned with the UI test dataset.
- `scripts/generate_milestone2_output.cjs` supports `--shipment=<shipmentId>` to force output generation for a specific testing-interface shipment.
- `scripts/generate_milestone2_output.cjs` also supports `TRACKFLOW_SHIPMENT_ID=<shipmentId>` as an environment override when no `--shipment` argument is passed.
- `src/milestone2-output.js` now supports `selectedShipmentId`, enabling generation from the shipment currently selected in `src/testing-interface.js`.
- `src/testing-interface.js` now maintains an `activeShipmentId` context updated by user operations and passes it to milestone output generation.
- `src/TrackFlow.html` includes anchor-based top navigation links targeting `#header`, `#site-nav-target`, `#contact`, and `#footer`, with `Apply` linking to `application.html`.

Implication:

- Milestone 2 logic currently has a concrete home in `src/` and can be manually exercised from the test interface.
- This logic is not yet packaged for direct reuse from `packages/shared`.

### 2. Public website app

`uis/website` is now a TypeScript Next.js app with Milestone 1 section parity restored.

Observed characteristics:

- App Router files use TypeScript (`layout.tsx`, `page.tsx`).
- `package.json` includes `typecheck` and TypeScript dev dependencies.
- `tsconfig.json` and `next-env.d.ts` are present.
- The page includes header/nav, hero, benefits/services, contact section, and footer.

### 3. Backoffice app

`uis/backoffice` is now a TypeScript Next.js app and no longer computes carrier mapping inline in the page component.

Observed characteristics:

- App Router files use TypeScript (`layout.tsx`, `page.tsx`).
- `package.json` includes `typecheck` and TypeScript dev dependencies.
- `tsconfig.json` and `next-env.d.ts` are present.
- Route `/` is now an Operations Home launcher with a dropdown for available internal pages.
- `uis/backoffice/lib/milestone2.ts` parses `.trackflow-dummy-order.txt` and returns structured values.
- `uis/backoffice/lib/milestone2.ts` reads `.trackflow-milestone2-output.json` as the single source for rendered Milestone 2 output.
- `uis/backoffice/app/milestone-2-output/page.tsx` renders imported Milestone 2 output on screen.
- `uis/backoffice/package.json` now runs `milestone2:sync` automatically before `dev` and `build`.

Implication:

- Backoffice depends on a file-based integration path to generated output, which is good for milestone visibility but can become stale without regeneration.

### 4. Legacy/internal reference app

`uis/talent-pipeline-tracker` remains a functional TypeScript Next.js app but is domain-misaligned (recruitment rather than logistics). It should be treated as reference or migration candidate, not as the business source-of-truth UI.

### 5. Shared package

`packages/shared` still provides minimal placeholder shared types (`Id`, `BaseEntity`) and has not yet absorbed Milestone 2 domain models.

### 6. Auth/API service layer

The API service now includes a TinyDB-backed identity layer for TrackFlow users and profiles. Relevant implementation details:

- `services/api/auth.py` centralizes JWT creation, decoding, and bearer-token validation via `OAuth2PasswordBearer` and `python-jose`.
- `services/api/database.py` persists user and profile records in `services/api/data/users.json` with a one-to-one profile mapping on `user_id`.
- `services/api/routes/auth.py`, `services/api/routes/users.py`, and `services/api/routes/profiles.py` expose the login and protected CRUD flow.
- `main.py` protects the internal API routes and seeds an admin user by default so the service can authenticate staff requests with a bearer token.

### 7. Frontend auth layer (AUTH-02)

The backoffice and talent-pipeline-tracker apps now implement a complete JWT-based authentication flow:

**Auth library** (`uis/backoffice/lib/auth.ts`):
- Token storage in `localStorage` under key `trackflow_access_token`.
- `getToken()` / `setToken()` / `clearToken()` — safe localStorage access with try/catch fallback.
- `isAuthenticated()` — boolean check for existing token.
- `redirectToLogin()` / `redirectToHome()` — window-level redirects.
- `apiFetch<T>(path, options?)` — generic fetch wrapper that attaches `Authorization: Bearer <token>`, auto-sets `Content-Type: application/json` (skipped for `FormData` bodies), and handles 401 responses by clearing the token and redirecting to `/login`. Parses structured error responses (string `detail` or array of validation errors).
- `API_BASE` sourced from `NEXT_PUBLIC_INCIDENTS_API_BASE_URL` env var (default `http://localhost:8000`).

**Route-level auth guard** (`uis/backoffice/app/layout.tsx` and `uis/talent-pipeline-tracker/app/layout.tsx`):
- Inline `<AuthGuardScript />` in the `<head>` that runs before any page content.
- Public paths (`/login`, `/register`, `/logout`) are exempt from auth checks.
- All other paths redirect to `/login` if no token is found in localStorage.
- Talent pipeline tracker uses the same shared token for route protection (no login UI — users are redirected to the backoffice login page).

**Auth pages** (all under `uis/backoffice/app/`):
- `/login` — email/password form → POST `/auth/login` (form-urlencoded) → stores JWT → redirects to `/`.
- `/register` — email/password + optional profile fields → POST `/users` (JSON) → POST `/auth/login` → stores JWT → redirects to `/`.
- `/account/profile` — loads user from GET `/auth/me` and profile from GET `/profiles/me` → editable form for display_name/phone/address → saves via PATCH `/profiles/me`.
- `/logout` — calls `clearToken()` → redirects to `/login`.

**Protected page updates** (existing pages that now send Bearer tokens):
- `uis/backoffice/app/suppliers/page.tsx` — all 4 API calls use local `authFetch()` wrapper with token injection and 401 handling.
- `uis/backoffice/app/incident-file-analyzer/page.tsx` — POST to analysis endpoint uses `authFetch()`, correctly handling FormData (no Content-Type override).

**API endpoint added** (`services/api/routes/profiles.py`):
- `PATCH /profiles/me` — creates profile if missing (via `create_profile_for_user`), updates if existing (via `update_profile_for_user`). Accepts `ProfileCreate` payload, returns `Profile` response model.

**Scope**:
- `uis/website/` — completely unaffected (no auth guard, no changes).

### 8. Password recovery and change (AUTH-03)

- `POST /auth/forgot-password` looks up active users, issues a signed JWT with a `password_reset` purpose and configured expiry, persists a hashed token ID in the TinyDB `password_reset_tokens` table, and queues reset email delivery through FastAPI background tasks. Its response is identical for registered and unknown emails; delivery failures are logged without changing that response or waiting on Resend latency.
- `POST /auth/reset-password` validates signature, expiry, token purpose, matching server-side state, and unused status. It stores the new bcrypt hash and marks the token used. The token record stores no raw reset token.
- `POST /auth/change-password` requires a valid bearer token and verifies the current password before calling the existing user update path.
- Token expiry is configured with `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES` (default 30). The email link base is `BACKOFFICE_URL` (default `http://localhost:3000`). Resend uses `RESEND_API_KEY` and `RESEND_FROM_EMAIL`; `services/api/main.py` loads the root `.env` (not `uis/.env`) through `python-dotenv` before importing auth settings. `JWT_SECRET_KEY` is also loaded from the environment; the development fallback is generated per process, so deployments must configure one stable value shared by API instances. Reset email delivery falls back to printing the reset link in the API console when Resend is unconfigured, blocked by the network, or rejects the sender, so the local flow works without real mail delivery.
- Backoffice reads the API base from `uis/backoffice/.env.local` (`NEXT_PUBLIC_INCIDENTS_API_BASE_URL`, git-ignored); that value is baked in at build/start time, so it must stay in sync with the root `.env` when the API URL changes.
- Backoffice routes: `/forgot-password` and `/reset-password` are public; `/account/change-password` remains behind the existing auth guard. Login and profile pages link to the respective workflows.
- Root `.env.example` documents required settings; `.gitignore` excludes `.env` and other local env files while permitting examples. `services/api/README.md` documents Resend setup and API startup.
- TinyDB reset-token consumption is serialized within one API process. For multi-worker production deployments, move identity/token persistence to a transactional database to guarantee race-free one-time consumption across processes.

## Feedback-related status

- Website section parity issue: resolved in `uis/website`.
- JavaScript vs TypeScript issue for website/backoffice: resolved.
- Backoffice inline logic issue: resolved by importing generated output based on `src/testing-interface.js` data.
- Milestone output consistency is now driven by `scripts/generate_milestone2_output.cjs`, which writes both `.trackflow-dummy-order.txt` and `.trackflow-milestone2-output.json` from the shared helper using `src/testing-interface.js` data as input.
- The shared TrackFlow website surface was restored to the componentized state expected by the review: reusable `Header` and `FeatureCard` components, a shared content file in `src/trackflow-website/content.ts`, and the public/backoffice apps both rendering the same screen.
- The Next.js 16 app boundary issue was fixed by aliasing the source content with `@trackflow-content` and adding the matching webpack/Turbopack config in both app folders so the root-level content file resolves correctly without breaking the build.
- Final validation status: both `uis/website` and `uis/backoffice` pass `npm run build` in the current restored baseline.

## Technical constraints and assumptions

- Work must preserve monorepo structure and remain Windows-friendly.
- Milestone 2 logic in `src/` is currently authoritative for local utility behavior and demo coverage.
- A future decision is needed on consolidation: keep `src/` as milestone playground vs move reusable logic to `packages/shared`.

## Validation and working practices

- Website and backoffice have local validation commands: `npm run typecheck` and `npm run build`.
- Memory updates remain mandatory when architecture, milestone output, or workflow interpretation changes.
- Git hygiene from earlier GH001 issue remains relevant: generated artifacts (`node_modules`, `.next`, `out`) must stay untracked.
