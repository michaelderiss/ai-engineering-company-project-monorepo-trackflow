from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, text

from scripts import nightly_export
from scripts.nightly_export import execute, export_telemetry, resolve_target_date
from services import job_runner


@pytest.fixture
def job_engine():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("ATTACH DATABASE ':memory:' AS public"))
        connection.execute(text("""
            CREATE TABLE public.job_runs (
                id TEXT PRIMARY KEY,
                job_name TEXT NOT NULL,
                target_date DATE NOT NULL,
                status TEXT NOT NULL,
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                error_message TEXT,
                created_at TIMESTAMP NOT NULL
            )
        """))
        connection.execute(text("""
            CREATE UNIQUE INDEX public.uq_job_runs_processing_job_name
            ON job_runs (job_name) WHERE status = 'processing'
        """))
    yield engine
    engine.dispose()


def test_target_date_uses_previous_utc_day_and_override():
    instant = datetime(2026, 11, 21, 1, 0, tzinfo=timezone.utc)
    assert resolve_target_date(now=instant) == date(2026, 11, 20)
    assert resolve_target_date("2025-01-15", now=instant) == date(2025, 1, 15)
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        resolve_target_date("15-01-2025", now=instant)


def test_job_runner_claim_completes_and_is_idempotent_by_date(job_engine):
    target = date(2025, 1, 15)
    run = job_runner.create_job_run(target, engine=job_engine)
    assert run is not None
    assert run["status"] == "processing"
    assert job_runner.has_processing_lock(engine=job_engine)

    job_runner.update_job_run(run["id"], "completed", engine=job_engine)
    assert not job_runner.has_processing_lock(engine=job_engine)
    assert job_runner.has_completed_for_date(target, engine=job_engine)
    assert not job_runner.has_completed_for_date(date(2025, 1, 16), engine=job_engine)


def test_job_runner_does_not_claim_parallel_processing_run(job_engine):
    first = job_runner.create_job_run(date(2025, 1, 15), engine=job_engine)
    second = job_runner.create_job_run(date(2025, 1, 16), engine=job_engine)
    assert first is not None
    assert second is None
    with job_engine.connect() as connection:
        statuses = connection.execute(text("SELECT status FROM public.job_runs")).scalars().all()
    assert statuses == ["processing"]


def test_execute_logs_and_skips_when_another_run_is_processing(monkeypatch, caplog):
    monkeypatch.setattr(nightly_export, "has_completed_for_date", lambda *args: False)
    monkeypatch.setattr(nightly_export, "create_job_run", lambda *args: None)

    with caplog.at_level("INFO", logger=nightly_export.logger.name):
        assert execute(date(2025, 1, 15)) == "blocked_processing"
    assert "status=blocked_processing" in caplog.text


def test_duplicate_execution_skips_export_and_pipeline(job_engine, monkeypatch):
    target = date(2025, 1, 15)
    run = job_runner.create_job_run(target, engine=job_engine)
    assert run is not None
    job_runner.update_job_run(run["id"], "completed", engine=job_engine)
    monkeypatch.setattr(nightly_export, "has_completed_for_date", lambda *args: job_runner.has_completed_for_date(target, engine=job_engine))
    monkeypatch.setattr(nightly_export, "create_job_run", lambda *args: job_runner.create_job_run(target, engine=job_engine))
    export = Mock()
    pipeline = Mock()
    assert execute(target, export=export, pipeline=pipeline) == "skipped_duplicate"
    export.assert_not_called()
    pipeline.assert_not_called()


def test_failed_run_is_terminal_with_error_and_releases_lock(job_engine, monkeypatch):
    target = date(2025, 1, 15)
    monkeypatch.setattr(nightly_export, "has_completed_for_date", lambda *args: False)
    monkeypatch.setattr(
        nightly_export,
        "create_job_run",
        lambda *args: job_runner.create_job_run(target, engine=job_engine),
    )
    monkeypatch.setattr(
        nightly_export,
        "update_job_run",
        lambda run_id, status, **kwargs: job_runner.update_job_run(
            run_id, status, engine=job_engine, **kwargs
        ),
    )

    def fail_pipeline(_):
        raise RuntimeError("pipeline exploded")

    with pytest.raises(RuntimeError, match="pipeline exploded"):
        execute(target, export=lambda _: Path("snapshot.csv"), pipeline=fail_pipeline)

    assert not job_runner.has_processing_lock(engine=job_engine)
    with job_engine.connect() as connection:
        row = connection.execute(text("SELECT status, error_message, finished_at FROM public.job_runs")).one()
    assert row.status == "failed"
    assert row.error_message == "pipeline exploded"
    assert row.finished_at is not None


def test_export_existing_file_does_not_query_database(tmp_path: Path, monkeypatch):
    target = date(2025, 1, 15)
    path = tmp_path / f"telemetry_{target.isoformat()}.csv"
    path.write_text("already exported", encoding="utf-8")
    monkeypatch.setattr("services.api.telemetry_database.get_telemetry_engine", Mock(side_effect=AssertionError("must not query")))
    assert export_telemetry(target, output_dir=tmp_path) == path
    assert path.read_text(encoding="utf-8") == "already exported"
