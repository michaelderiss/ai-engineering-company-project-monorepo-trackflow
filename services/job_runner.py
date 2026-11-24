"""Database-backed lifecycle and processing lock for scheduled jobs.

The ``processing`` status is the only lock. A PostgreSQL partial unique index
on ``job_name`` for processing rows makes the check-and-transition race-safe
across independent processes and hosts.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

JOB_NAME = "nightly_export"

HAS_PROCESSING_LOCK_SQL = text(
    "SELECT 1 FROM public.job_runs "
    "WHERE job_name = :job_name AND status = 'processing' LIMIT 1"
)
HAS_COMPLETED_FOR_DATE_SQL = text(
    "SELECT 1 FROM public.job_runs "
    "WHERE job_name = :job_name AND target_date = :target_date "
    "AND status = 'completed' LIMIT 1"
)
CREATE_PENDING_SQL = text(
    "INSERT INTO public.job_runs "
    "(id, job_name, target_date, status, created_at) "
    "VALUES (:id, :job_name, :target_date, 'pending', :created_at)"
)
CLAIM_JOB_SQL = text(
    "UPDATE public.job_runs SET status = 'processing', started_at = :started_at "
    "WHERE id = :id AND status = 'pending' "
    "AND NOT EXISTS (SELECT 1 FROM public.job_runs "
    "WHERE job_name = :job_name AND status = 'processing') "
    "AND NOT EXISTS (SELECT 1 FROM public.job_runs "
    "WHERE job_name = :job_name AND target_date = "
    "(SELECT target_date FROM public.job_runs WHERE id = :id) "
    "AND status = 'completed')"
)
DELETE_UNCLAIMED_SQL = text("DELETE FROM public.job_runs WHERE id = :id AND status = 'pending'")
FINISH_JOB_SQL = text(
    "UPDATE public.job_runs SET status = :status, finished_at = :finished_at, "
    "error_message = :error_message WHERE id = :id AND status = 'processing'"
)


def _engine(engine: Engine | None = None) -> Engine:
    if engine is not None:
        return engine
    # Import lazily: the standalone worker shares only the database connector,
    # and never imports FastAPI or its application lifecycle.
    from services.api.telemetry_database import get_telemetry_engine

    return get_telemetry_engine()


def has_processing_lock(job_name: str = JOB_NAME, *, engine: Engine | None = None) -> bool:
    """Whether any execution of this job currently owns the processing state."""
    with _engine(engine).connect() as connection:
        return connection.execute(HAS_PROCESSING_LOCK_SQL, {"job_name": job_name}).first() is not None


def has_completed_for_date(
    target_date: date, job_name: str = JOB_NAME, *, engine: Engine | None = None
) -> bool:
    """Whether this job has already completed for the requested calendar day."""
    with _engine(engine).connect() as connection:
        return connection.execute(
            HAS_COMPLETED_FOR_DATE_SQL,
            {"job_name": job_name, "target_date": target_date},
        ).first() is not None


def create_job_run(
    target_date: date, job_name: str = JOB_NAME, *, engine: Engine | None = None
) -> dict[str, Any] | None:
    """Create pending then atomically claim processing, or return ``None`` if busy.

    The partial unique index in ``services/telemetry/job_runs.sql`` is the
    cross-process arbiter. If two distinct target dates race, exactly one can
    transition to processing; the losing pending insert is rolled back.
    """
    database = _engine(engine)
    run_id = str(uuid4())
    now = datetime.now(timezone.utc)
    try:
        with database.begin() as connection:
            if connection.execute(
                HAS_PROCESSING_LOCK_SQL, {"job_name": job_name}
            ).first() is not None:
                return None
            if connection.execute(
                HAS_COMPLETED_FOR_DATE_SQL,
                {"job_name": job_name, "target_date": target_date},
            ).first() is not None:
                return None
            connection.execute(
                CREATE_PENDING_SQL,
                {
                    "id": run_id,
                    "job_name": job_name,
                    "target_date": target_date,
                    "created_at": now,
                },
            )
            claimed = connection.execute(
                CLAIM_JOB_SQL,
                {"id": run_id, "job_name": job_name, "started_at": now},
            )
            if claimed.rowcount != 1:
                # Remove pending records that never entered execution; otherwise
                # they would look like zombies despite never owning the lock.
                connection.execute(DELETE_UNCLAIMED_SQL, {"id": run_id})
                return None
    except IntegrityError:
        return None
    return {"id": run_id, "job_name": job_name, "target_date": target_date, "status": "processing"}


class _JobAlreadyProcessing(Exception):
    """Internal signal to roll back a job claim that lost a race."""


def update_job_run(
    run_id: str,
    status: str,
    *,
    error_message: str | None = None,
    engine: Engine | None = None,
) -> None:
    """Finish an active run; only completed/failed are legal terminal states."""
    if status not in {"completed", "failed"}:
        raise ValueError("A job run can only be finished as completed or failed.")
    with _engine(engine).begin() as connection:
        result = connection.execute(
            FINISH_JOB_SQL,
            {
                "id": run_id,
                "status": status,
                "finished_at": datetime.now(timezone.utc),
                "error_message": error_message if status == "failed" else None,
            },
        )
        if result.rowcount != 1:
            raise RuntimeError(f"Job run {run_id} is not in processing status.")
