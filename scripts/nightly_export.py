#!/usr/bin/env python3
"""Export yesterday's telemetry and trigger the TrackFlow data pipeline.

The worker is an independent CLI process. It does not import the FastAPI app
or register work in an API lifecycle hook.
"""

from __future__ import annotations

import csv
import logging
import os
import subprocess
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from services.job_runner import (
    JOB_NAME,
    create_job_run,
    has_completed_for_date,
    update_job_run,
)

ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = ROOT / "data" / "raw"
CSV_COLUMNS = (
    "event_id",
    "event_type",
    "event_timestamp",
    "session_id",
    "user_id",
    "schema_version",
    "request_id",
    "properties",
)
EXPORT_EVENTS_SQL = text("""
    SELECT event_id, event_type, event_timestamp, session_id, user_id,
           schema_version, request_id, properties::text AS properties
    FROM public.telemetry_events
    WHERE event_timestamp >= :start_at AND event_timestamp < :end_at
    ORDER BY event_timestamp, event_id
""")
logger = logging.getLogger("nightly_export")


def resolve_target_date(value: str | None = None, *, now: datetime | None = None) -> date:
    """Resolve TARGET_DATE, defaulting to yesterday's UTC calendar date."""
    override = value if value is not None else os.getenv("TARGET_DATE")
    if override:
        try:
            return date.fromisoformat(override)
        except ValueError as exc:
            raise ValueError("TARGET_DATE must use YYYY-MM-DD format.") from exc
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("The current time must be timezone-aware.")
    return current.astimezone(timezone.utc).date() - timedelta(days=1)


def export_telemetry(target_date: date, *, output_dir: Path = RAW_DATA_DIR) -> Path:
    """Write a stable CSV snapshot for the UTC calendar day unless it exists."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"telemetry_{target_date.isoformat()}.csv"
    if output_path.exists():
        logger.info(
            "job_name=%s status=export_skipped_existing target_date=%s path=%s",
            JOB_NAME,
            target_date,
            output_path,
        )
        return output_path

    from services.api.telemetry_database import get_telemetry_engine

    start_at = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    end_at = start_at + timedelta(days=1)
    engine = get_telemetry_engine()
    with engine.connect() as connection:
        rows = connection.execute(
            EXPORT_EVENTS_SQL, {"start_at": start_at, "end_at": end_at}
        ).mappings().all()

    # Write atomically so a crash cannot leave a partial CSV that looks complete.
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    try:
        with temporary_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    key: _csv_value(row.get(key)) for key in CSV_COLUMNS
                })
        os.replace(temporary_path, output_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()

    logger.info(
        "job_name=%s status=exported target_date=%s rows=%d path=%s",
        JOB_NAME,
        target_date,
        len(rows),
        output_path,
    )
    return output_path


def _csv_value(value: object) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()  # type: ignore[no-any-return]
    return str(value)


def run_pipeline(target_date: date, *, project_root: Path = ROOT) -> None:
    """Trigger the existing Milestone 6 pipeline in an isolated subprocess."""
    week_start = (target_date - timedelta(days=target_date.weekday())).isoformat()
    command: Sequence[str] = (
        sys.executable,
        "-m",
        "data.pipelines.pipeline",
        "--week-start",
        week_start,
    )
    logger.info(
        "job_name=%s status=pipeline_started target_date=%s command=%s",
        JOB_NAME,
        target_date,
        " ".join(command),
    )
    subprocess.run(command, cwd=project_root, check=True)


def execute(
    target_date: date,
    *,
    export: Callable[[date], Path] = export_telemetry,
    pipeline: Callable[[date], None] = run_pipeline,
) -> str:
    """Run one date's export and pipeline under the database processing lock."""
    if has_completed_for_date(target_date, JOB_NAME):
        logger.info(
            "job_name=%s status=skipped_duplicate target_date=%s",
            JOB_NAME,
            target_date,
        )
        return "skipped_duplicate"

    run = create_job_run(target_date, JOB_NAME)
    if run is None:
        # Another process may have completed this exact target after our first
        # idempotency read but before we claimed it.
        if has_completed_for_date(target_date, JOB_NAME):
            logger.info(
                "job_name=%s status=skipped_duplicate target_date=%s",
                JOB_NAME,
                target_date,
            )
            return "skipped_duplicate"
        logger.info(
            "job_name=%s status=blocked_processing target_date=%s",
            JOB_NAME,
            target_date,
        )
        return "blocked_processing"

    run_id = str(run["id"])
    logger.info(
        "job_name=%s status=processing target_date=%s run_id=%s",
        JOB_NAME,
        target_date,
        run_id,
    )
    try:
        export(target_date)
        pipeline(target_date)
        update_job_run(run_id, "completed")
    except Exception as exc:
        try:
            update_job_run(run_id, "failed", error_message=str(exc))
        except Exception:
            logger.exception(
                "job_name=%s status=failed_record_update_error target_date=%s run_id=%s",
                JOB_NAME,
                target_date,
                run_id,
            )
        logger.exception(
            "job_name=%s status=failed target_date=%s run_id=%s error=%s",
            JOB_NAME,
            target_date,
            run_id,
            exc,
        )
        raise

    logger.info(
        "job_name=%s status=completed target_date=%s run_id=%s",
        JOB_NAME,
        target_date,
        run_id,
    )
    return "completed"


def main() -> int:
    # Local setup convenience: keep credentials in ignored .env.worker and
    # load them into this worker process before opening the database.
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env.worker", override=False)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        target_date = resolve_target_date()
        logger.info("job_name=%s status=started target_date=%s", JOB_NAME, target_date)
        result = execute(target_date)
        logger.info("job_name=%s status=%s target_date=%s", JOB_NAME, result, target_date)
        return 0
    except Exception:
        logger.exception("job_name=%s status=failed", JOB_NAME)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
