# Error-Handling Audit and Verification

## Scope

Existing TrackFlow backoffice, public website, tracker, FastAPI service, CSV analyzer, seeders, generator, memory guard, and reusable pandas script. This change adds resilience, not product features. User credentials and live records are not needed for automated failure tests.

## Audit Resolutions

| Original gap | Resolution |
| --- | --- |
| Raw fetch/JSON errors and status codes in UI | Shared `packages/shared/http.ts` normalizes failures, applies a 15-second timeout, sanitizes field messages, and guards JSON parsing. |
| Incomplete payloads crash rendering | Domain response guards reject incomplete data; all Next.js apps have error/loading routes with retry and home navigation. |
| Unhandled supplier mutations | Scoped catches and finally cleanup, disabled pending controls, success feedback and list retry. Stale filter responses cannot overwrite newer results. |
| Silent profile load failures | Only 404 is treated as absent; other failures show retry/home actions. |
| Unauthenticated CSV downloads | Authenticated fetch, CSV content-type check, pending/success/error UI, and object-URL cleanup. |
| Tracker errors lack read recovery | Detail and notes retries; mutation saving indicators; guarded candidate/note/pagination payloads. |
| Mixed plain-text/JSON API failures | Uniform safe JSON envelope; auth headers preserved; CIM 400 and other model 422 contracts preserved. |
| Broad catches expose internal exceptions | Narrow expected exceptions; conflicts have their own type; unexpected failures return generic 500 without exception details. |
| Reset tokens printed automatically | Console fallback requires explicit development opt-in and defaults off. Provider failures log no recipient, token, or provider response. |
| Missing CSV structure checks | Shared required/duplicate-column and row-width validation before processing. |
| CLI input/export/seed failures crash | Scoped file/encoding/parser/database handling, actionable stderr, and nonzero exits for critical failures. EOF skips optional export. |
| Git guard silently passes on Git failure | Guard fails closed with stderr and nonzero exit. |
| Raw dataframe samples in output | Pandas utility prints aggregate shapes/counts only and reports dependency/input errors safely. |
| Incorrect dispatch recovery command | Loader validates output and shows a safe unavailable state; documented generator command corrected. |

## Policy

- Catch errors at the dangerous operation: network request, response parsing, file access, CSV parsing, database operation, or subprocess invocation. Do not catch a whole workflow and pretend it succeeded.
- Unexpected exceptions have a final server boundary; clients get a generic actionable message, not a stack trace or arbitrary provider body.
- Successful data, loading progress, and recoverable errors remain distinct. Mutations clear busy state in `finally`; errors preserve user input when possible.
- Error messages include or sit beside an appropriate action: retry, resubmit, home navigation, or support instructions.
- API bodies use `message`, optional `detail`, and optional `errors` keyed by field. Clients do not render unrecognized server messages verbatim.
- Never log keys, passwords, customer rows, or normal reset tokens. `ALLOW_PASSWORD_RESET_CONSOLE_FALLBACK=true` is an explicit local-only exception for reset demonstration; leave it unset in production.
- Scripts report critical failures to stderr and exit nonzero. Informational totals remain on stdout. Unknown programming errors are not disguised as successful script execution.

## Automated Checks

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
node --test tests/http-errors.test.cjs
npm --prefix uis/backoffice run build
npm --prefix uis/talent-pipeline-tracker run build
npm --prefix uis/website run build
.\.venv\Scripts\python.exe scripts/check_memory_bank.py
```

Python tests isolate user, supplier, and incident storage. Failure tests use temporary files and mocked provider/database errors, not real emails or live database corruption. Node tests use mocked responses and filesystem reads. The shared helper adds no runtime package dependency; the tracker bundler root is configured to read the shared source.

## Browser Checklist

Start the API and backoffice normally in separate terminals. Sign in, then use DevTools request blocking or Offline mode; remove blocks after each check.

1. `/login`: block `/auth/login`, submit, and verify a connection message, retained inputs, and re-enabled sign-in button.
2. `/register`: fail the login request after account creation. The page must explain that the account exists and link to sign-in rather than encouraging duplicate registration.
3. `/suppliers`: block a rate/status PATCH. Verify pending controls, a readable error, unchanged saved values, and recovery controls. Reload with list requests blocked and retry after unblocking.
4. `/account/profile`: fail `/profiles/me` with 500. It must show Retry profile rather than silently presenting an empty profile. A genuine 404 still permits profile creation.
5. `/incident-file-analyzer`: upload a valid CSV, then download. Verify the export request includes Authorization and reports success. Block export and verify readable feedback without a separate raw-error tab.
6. `/incidents`: test list/summary independently with blocked requests, retry, and attempt a blocked status update. The previous status must be restored; other sections remain usable.
7. Tracker: block record or note reads and verify retries. Fail edits/status/stage/note mutations and verify feedback and controls recover.
8. Throttle requests: loading messages must remain visible and duplicate mutation controls disabled until completion.
9. With response interception, return invalid JSON or `null` from a data endpoint. The page must show an unreadable/incomplete response error, not a native parser message or render crash.

Browser automation during this change verified supplier offline updates, malformed supplier responses, profile failure/retry, authorized CSV export, and offline login using intercepted synthetic data. Live provider delivery was not part of this error-handling verification.

## CLI Checks

- Analyze a nonexistent or incorrectly encoded CSV: readable stderr and exit 1.
- Analyze a CSV with missing/duplicate headers or inconsistent row widths: input error, not a successful empty analysis.
- Export in a directory that is not writable: actionable stderr and exit 1, without a traceback.
- Run a seeder without writable database storage: a safe storage message and nonzero exit. Incident seeding remains idempotent on retry.
- Run the memory guard where Git cannot inspect the repository: fail rather than treating it as no changes.