# DEV-53 submission evidence

Evidence captured from the local WSL worker on 2026-11-21. This is a local WSL schedule, not a production-host deployment. Ubuntu cron is active and uses Pacific local time (`PST -0800` at capture); the installed expression `15 2 * * *` therefore fires at 02:15 local time, with the usual daylight-time shift. WSL must be running.

## Successful worker execution

A fresh run was executed for `TARGET_DATE=2026-11-20`; it exported the daily snapshot, invoked the weekly pipeline subprocess, and completed. The pipeline had no eligible events for that target week, so it correctly loaded zero KPI rows.

```text
2026-11-21 15:26:56,281 INFO nightly_export job_name=nightly_export status=started target_date=2026-11-20
2026-11-21 15:26:59,460 INFO nightly_export job_name=nightly_export status=processing target_date=2026-11-20 run_id=a8e0b54c-e375-4e3a-ba7b-531875acda11
2026-11-21 15:26:59,648 INFO nightly_export job_name=nightly_export status=exported target_date=2026-11-20 rows=0 path=data/raw/telemetry_2026-11-20.csv
2026-11-21 15:26:59,648 INFO nightly_export job_name=nightly_export status=pipeline_started target_date=2026-11-20 command=python -m data.pipelines.pipeline --week-start 2026-11-16
Pipeline result: {"run_id": "e988d30d-fbab-466c-9b50-a9bcb34b7a1c", "week_start": "2026-11-16", "status": "completed", "records_extracted": 0, "records_loaded": 0, "snapshot_saved": false}
2026-11-21 15:27:58,956 INFO nightly_export job_name=nightly_export status=completed target_date=2026-11-20 run_id=a8e0b54c-e375-4e3a-ba7b-531875acda11
2026-11-21 15:27:58,957 INFO nightly_export job_name=nightly_export status=completed target_date=2026-11-20
```

A second invocation for the same completed date produced a real `skipped_duplicate` result and did not rerun the pipeline.

## Blocked execution

With a temporary processing row held for a different date, the worker was launched for `2026-11-19`. It exited successfully without doing export or pipeline work; the temporary lock was transitioned to `failed` and released after capture.

```text
2026-11-21 15:28:35,950 INFO nightly_export job_name=nightly_export status=started target_date=2026-11-19
2026-11-21 15:28:38,132 INFO nightly_export job_name=nightly_export status=blocked_processing target_date=2026-11-19
worker_exit_code=0
```

## CSV excerpt

The fresh `2026-11-20` snapshot was header-only because there were no telemetry events that day. The earlier database-backed `2026-11-10` export contains 20 event rows. First rows:

```csv
event_id,event_type,event_timestamp,session_id,user_id,schema_version,request_id,properties
[redacted],login_succeeded,2026-11-10T06:44:11.470000+00:00,[redacted],[redacted],1.0.0,[redacted],"{""auth_method"": ""password""}"
[redacted],navigation_page_viewed,2026-11-10T06:44:13.856000+00:00,[redacted],[redacted],1.0.0,[redacted],"{""route"": ""/""}"
[redacted],navigation_page_viewed,2026-11-10T06:45:23.451000+00:00,[redacted],[redacted],1.0.0,[redacted],"{""route"": ""/inventory/products""}"
```

CSV rows contain telemetry identifiers and properties; review/redact them if repository policy requires avoiding test-record identifiers before publishing the PR.

## Tests

```text
Full suite after the blocked-path test was added: 211 passed, 175 warnings (156.40 seconds)
Focused worker suite: 7 passed
```
