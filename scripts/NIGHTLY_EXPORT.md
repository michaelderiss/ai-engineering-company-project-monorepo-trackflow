# Nightly telemetry export worker

`scripts/nightly_export.py` is a standalone process; it does not run in FastAPI or on an API request thread. It uses `TELEMETRY_DATABASE_URL`, just like telemetry storage and the Milestone 6 pipeline.

## One-time database setup

Apply `services/telemetry/job_runs.sql` to the PostgreSQL database configured by `TELEMETRY_DATABASE_URL`. It creates the orchestration table and the partial unique index that makes `processing` the cross-process lock. `reporting.pipeline_runs` remains owned by the ETL pipeline and is not replaced by `job_runs`.

## Run manually

From the repository root in the configured Python environment:

```sh
python scripts/nightly_export.py
TARGET_DATE=2025-01-15 python scripts/nightly_export.py
```

The default target is yesterday's UTC calendar date. The CSV backup is written to `data/raw/telemetry_YYYY-MM-DD.csv`; existing files are kept and not overwritten. The existing Milestone 6 entry point runs as a checked subprocess (`python -m data.pipelines.pipeline --week-start YYYY-MM-DD`), processing the ISO week containing the target date. Its weekly aggregation is intentionally preserved; the CSV remains the exact daily backup. A nonzero pipeline exit marks the orchestration record failed.

## Production trigger: host crontab

Keep scheduling outside FastAPI. Install this entry in the service account's crontab, replacing the paths and environment-file location with the deployment's actual values:

```cron
# 02:15 UTC nightly; set process timezone explicitly on hosts not configured for UTC
CRON_TZ=UTC
15 2 * * * cd /srv/trackflow && set -a && . /etc/trackflow/worker.env && set +a && /srv/trackflow/.venv/bin/python /srv/trackflow/scripts/nightly_export.py >> /var/log/trackflow/nightly-export.log 2>&1
```

The worker environment file must provide `TELEMETRY_DATABASE_URL`; do not place credentials in the crontab or repository. For local development, the script also loads the ignored repository-root `.env.worker` file when present; an already-exported environment variable takes precedence. The worker logs timestamp, job name, and status. The cron schedule is intentionally host-managed rather than embedded in the API or a framework scheduler: it remains independently deployable and cannot consume FastAPI's main thread. `CRON_TZ` availability depends on the host cron implementation; configure the host timezone as UTC if unsupported.

The local WSL crontab used for development is `15 2 * * *` without `CRON_TZ`, because the installed Ubuntu cron does not support per-crontab timezone scheduling. The user elected to keep the WSL timezone at Pacific local time, so this local entry runs at 02:15 PST/PDT, not at a fixed UTC time. Production deployments should use a UTC-configured host (or cron implementation that supports `CRON_TZ=UTC`) to honor the 02:15 UTC example above. WSL must be running for its local cron job to execute.

## State and retries

Each execution creates a `pending` row and immediately attempts to claim it as `processing`. A PostgreSQL partial unique index permits at most one processing row per job name; a simultaneous invocation quietly exits. Completed target dates are skipped. Success transitions to `completed`; caught errors record `failed`, `finished_at`, and the exception message before the exception is logged. A failed date can be retried; the export is not duplicated and the existing ETL's reporting writes are upserts.

Example log lines:

```text
2026-11-21 02:15:00,001 INFO nightly_export job_name=nightly_export status=processing target_date=2026-11-20 run_id=...
2026-11-21 02:15:04,120 INFO nightly_export job_name=nightly_export status=completed target_date=2026-11-20 run_id=...
2026-11-22 02:15:00,001 INFO nightly_export job_name=nightly_export status=skipped_duplicate target_date=2026-11-20
2026-11-22 02:15:00,001 INFO nightly_export job_name=nightly_export status=blocked_processing target_date=2026-11-21
```

Inspect the first CSV rows with `head -n 5 data/raw/telemetry_YYYY-MM-DD.csv` (or `Get-Content ... -TotalCount 5` on Windows). This file is an audit/recovery backup only; the ETL continues to read telemetry from PostgreSQL.
