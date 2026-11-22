"""Asynchronous reporting tasks and persistent dead-letter recording."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from celery import Task
from sqlalchemy import text

from services.celery_app import celery_app
from services.reporting.database import get_reporting_engine

logger = logging.getLogger(__name__)

CREATE_DLQ_TABLE_SQL = text("""
CREATE SCHEMA IF NOT EXISTS reporting;
CREATE TABLE IF NOT EXISTS reporting.task_dead_letters (
    id bigserial primary key,
    task_id text not null,
    task_name text not null,
    attempt_number integer not null,
    error_message text not null,
    failed_at timestamptz not null default now()
);
CREATE INDEX IF NOT EXISTS ix_task_dead_letters_task_id
    ON reporting.task_dead_letters (task_id)
""")
INSERT_DLQ_SQL = text("""
INSERT INTO reporting.task_dead_letters
    (task_id, task_name, attempt_number, error_message, failed_at)
VALUES (:task_id, :task_name, :attempt_number, :error_message, :failed_at)
""")


def ensure_dlq_table() -> None:
    """Create the persistent DLQ table idempotently."""
    engine = get_reporting_engine()
    with engine.begin() as connection:
        for statement in str(CREATE_DLQ_TABLE_SQL).split(";"):
            if statement.strip():
                connection.execute(text(statement))


def record_dead_letter(task_id: str, task_name: str, attempt_number: int, error: str) -> None:
    """Persist terminal task failure details in the reporting database."""
    engine = get_reporting_engine()
    with engine.begin() as connection:
        connection.execute(
            INSERT_DLQ_SQL,
            {
                "task_id": task_id,
                "task_name": task_name,
                "attempt_number": attempt_number,
                "error_message": error,
                "failed_at": datetime.now(timezone.utc),
            },
        )


class RetryingReportingTask(Task):
    """Retry reporting failures three times with exponential backoff."""

    # The task calls ``self.retry`` explicitly so every retry can log its
    # attempt and exact backoff before Celery republishes the message.
    max_retries = 3
    retry_backoff = True
    retry_backoff_max = 60
    retry_jitter = False
    acks_late = True

    def on_failure(self, exc: BaseException, task_id: str, args: tuple, kwargs: dict, einfo: Any) -> None:
        # Celery invokes on_failure after the initial attempt and all retries fail.
        attempt_number = self.max_retries + 1
        logger.exception(
            "task_id=%s attempt=%s status=failure error=%s",
            task_id,
            attempt_number,
            exc,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        try:
            ensure_dlq_table()
            record_dead_letter(task_id, self.name or "reporting.run_pipeline", attempt_number, str(exc))
        except Exception:
            logger.exception("task_id=%s status=dlq_record_failure error=%s", task_id, exc)
        try:
            celery_app.send_task(
                "reporting.dead_letter",
                args=[task_id, self.name or "reporting.run_pipeline", args, kwargs, attempt_number, str(exc)],
                task_id=f"dlq-{task_id}",
                queue="dead_letter",
                headers={
                    "original_task_id": task_id,
                    "attempt_number": attempt_number,
                    "error_message": str(exc),
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception:
            logger.exception("task_id=%s status=dlq_enqueue_failure", task_id)


@celery_app.task(
    bind=True,
    base=RetryingReportingTask,
    name="reporting.run_pipeline",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=840,
    time_limit=900,
)
def run_reporting_pipeline(self, week_start: str | None = None) -> dict[str, Any]:
    """Run one weekly pipeline; only the compact ISO date is sent in the task message."""
    task_id = self.request.id
    attempt = self.request.retries + 1
    started = time.monotonic()
    logger.info("task_id=%s attempt=%s status=started week_start=%s", task_id, attempt, week_start)
    try:
        from data.pipelines.pipeline import weekly_warehouse_client_performance_flow

        result = weekly_warehouse_client_performance_flow(week_start=week_start, triggered_by="celery")
        if result.get("status") != "completed":
            raise RuntimeError(result.get("error", "Pipeline run failed"))
        duration = time.monotonic() - started
        logger.info(
            "task_id=%s attempt=%s status=success duration_seconds=%.3f",
            task_id,
            attempt,
            duration,
        )
        return result
    except Exception as exc:
        duration = time.monotonic() - started
        if self.request.retries >= self.max_retries:
            logger.exception(
                "task_id=%s attempt=%s status=failure duration_seconds=%.3f error=%s",
                task_id,
                attempt,
                duration,
                exc,
            )
            raise

        countdown = 2 ** attempt
        logger.exception(
            "task_id=%s attempt=%s status=retrying retry_in_seconds=%s duration_seconds=%.3f error=%s",
            task_id,
            attempt,
            countdown,
            duration,
            exc,
        )
        raise self.retry(exc=exc, countdown=countdown, max_retries=self.max_retries)
