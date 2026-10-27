# API Configuration

The password recovery flow sends reset links through Resend. Copy the root `.env.example` to `.env`, then set `RESEND_API_KEY` and `RESEND_FROM_EMAIL` to credentials for a verified sender in your Resend account. Never commit `.env` or put provider keys in source code.

The API loads the root `.env` at startup. `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES` defaults to 30, and `BACKOFFICE_URL` defaults to `http://localhost:3000`; the generated reset link points to the backoffice app. `NEXT_PUBLIC_INCIDENTS_API_BASE_URL` configures the backoffice API address.

For local development, Resend delivery failures (missing config, blocked network, rejected sender) automatically fall back to printing the reset link in the API console. This keeps the forgot/reset flow usable without a reachable email provider; real mail delivery still requires a verified Resend sender.

Run the API from the repository root with:

```powershell
uvicorn services.api.main:app --reload
```

The forgot-password endpoint always returns the same confirmation for known and unknown email addresses. Email delivery errors are logged server-side without exposing whether an account exists. Reset tokens are signed, expire at the configured interval, and are recorded as used after a successful password update.

## Centralized Incident Manager

The manager follows `trackflow-BRIEFING.en.md`. Incident persistence is transactional SQLite at `services/api/data/incidents.sqlite3` (git-ignored). Existing user and supplier persistence remains unchanged. Python's standard library provides SQLite; no extra service or credential is needed.

From the repository root, seed historical customer incidents:

```powershell
.\.venv\Scripts\python.exe scripts/seed_incidents.py
```

The default input is `scripts/incidents-trackflow.csv`; an optional path may be passed as the first argument. The initial result is 95 inserted and 5 invalid rows. Running it again skips the 95 duplicates. Existing CSV IDs are tracked in a separate import ledger, not exposed on the incident model; missing IDs use a hashed title/timestamp key. Rejected rows are reported by row number and reason, never by customer email. The database is not automatically reseeded on server startup.

Shared CSV validation lives in `packages/shared/incident_validation.py`, used by the existing analyzer and the seed script. Manager field constraints and briefing mappings live in `packages/shared/incidents.py`, imported by the API and seed path. Seed descriptions are copied verbatim; title, date, status, category, origin, and branch are transformed as the briefing specifies.

All manager endpoints require the existing bearer token:

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/incidents` | Create an incident (201) |
| GET | `/api/incidents` | List; optional status, origin, branch, category filters |
| GET | `/api/incidents/options` | Shared allowed values, labels, transitions for the UI |
| GET | `/api/incidents/summary` | Global totals by status, category, origin, branch |
| GET | `/api/incidents/{id}` | Detail or 404 |
| PATCH | `/api/incidents/{id}/status` | Valid lifecycle transition or 400 |

Validation failures return 400 with `message` and an `errors` object keyed by field. Missing incidents return 404. Unexpected failures return a generic 500 response, never a stack trace. Empty databases return an empty list and zero-filled summary. The existing analyzer and CSV-export endpoints are retained.

For a database containing only the historical seed, expected totals are:

- Total 95; customer origin 95.
- Status: open 29, in_progress 0, resolved 52, discarded 14.
- Category: lost_parcel 14, carrier_issue 45, delivery_failure 19, returns_issue 17; other categories 0.
- Branch: la_office 50, zaragoza_office 45; other branches 0.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_incidents_api.py -q
```

The incident tests use isolated temporary databases, including seed idempotency, exact transformed counts, field errors, all status transitions, empty results, authentication, and generic failure handling. Do not delete the live database to run these tests.