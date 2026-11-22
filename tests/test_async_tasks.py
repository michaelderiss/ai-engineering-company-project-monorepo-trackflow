from __future__ import annotations

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from services.api.main import app
from services.reporting import routes


def test_enqueue_reporting_run_returns_202_without_waiting(monkeypatch):
    queued = Mock(id="task-123")
    delay_calls = []
    monkeypatch.setattr(routes, "logger", Mock())
    monkeypatch.setattr(
        "services.reporting.tasks.run_reporting_pipeline.delay",
        lambda **kwargs: delay_calls.append(kwargs) or queued,
    )
    with TestClient(app) as client:
        response = client.post("/reporting/pipeline-runs?week_start=2026-11-16")

    assert response.status_code == 202
    assert response.json() == {"task_id": "task-123"}
    assert delay_calls == [{"week_start": "2026-11-16"}]


def test_task_status_includes_terminal_result(monkeypatch):
    class CompletedResult:
        state = "SUCCESS"
        result = {"status": "completed", "records_loaded": 2}

        def successful(self):
            return True

        def failed(self):
            return False

    monkeypatch.setattr("celery.result.AsyncResult", lambda task_id, app: CompletedResult())
    with TestClient(app) as client:
        response = client.get("/tasks/task-123")

    assert response.status_code == 200
    assert response.json() == {
        "task_id": "task-123",
        "status": "success",
        "result": {"status": "completed", "records_loaded": 2},
    }


def test_task_status_maps_started_state(monkeypatch):
    class StartedResult:
        state = "STARTED"

        def successful(self):
            return False

        def failed(self):
            return False

    monkeypatch.setattr("celery.result.AsyncResult", lambda task_id, app: StartedResult())
    with TestClient(app) as client:
        response = client.get("/tasks/task-started")

    assert response.json() == {"task_id": "task-started", "status": "started"}


def test_task_status_reports_failure(monkeypatch):
    class FailedResult:
        state = "FAILURE"
        result = RuntimeError("pipeline unavailable")

        def successful(self):
            return False

        def failed(self):
            return True

    monkeypatch.setattr("celery.result.AsyncResult", lambda task_id, app: FailedResult())
    with TestClient(app) as client:
        response = client.get("/tasks/task-456")

    assert response.json() == {
        "task_id": "task-456",
        "status": "failure",
        "result": {"error": "pipeline unavailable"},
    }


def test_pipeline_failure_uses_exponential_retry_delay(monkeypatch):
    from services.reporting.tasks import run_reporting_pipeline

    class RetrySignal(Exception):
        pass

    retry_calls = []

    def fail_pipeline(**_kwargs):
        return {"status": "failed", "error": "temporary database outage"}

    def request_retry(**kwargs):
        retry_calls.append(kwargs)
        raise RetrySignal()

    monkeypatch.setattr(
        "data.pipelines.pipeline.weekly_warehouse_client_performance_flow",
        fail_pipeline,
    )
    monkeypatch.setattr(run_reporting_pipeline, "retry", request_retry)

    for retry_count, expected_delay in ((0, 2), (1, 4), (2, 8)):
        run_reporting_pipeline.push_request(id="task-retry", retries=retry_count)
        try:
            with pytest.raises(RetrySignal):
                run_reporting_pipeline.run(week_start="2026-11-16")
        finally:
            run_reporting_pipeline.pop_request()
        assert retry_calls[-1]["countdown"] == expected_delay
        assert retry_calls[-1]["max_retries"] == 3


def test_celery_retry_policy_and_dlq_recording(monkeypatch):
    from services.reporting.tasks import RetryingReportingTask, record_dead_letter

    assert RetryingReportingTask.max_retries == 3
    assert RetryingReportingTask.retry_backoff is True
    assert RetryingReportingTask.acks_late is True

    from services.reporting.tasks import run_reporting_pipeline

    sends = []
    monkeypatch.setattr("services.reporting.tasks.celery_app.send_task", lambda *args, **kwargs: sends.append((args, kwargs)))
    monkeypatch.setattr("services.reporting.tasks.ensure_dlq_table", lambda: None)
    monkeypatch.setattr("services.reporting.tasks.record_dead_letter", lambda *args: None)
    run_reporting_pipeline.on_failure(RuntimeError("terminal failure"), "task-dlq", ("2026-11-16",), {}, None)
    assert sends[0][1]["queue"] == "dead_letter"
    assert sends[0][1]["args"][0] == "task-dlq"
    assert sends[0][1]["args"][4] == 4

    inserted = []

    class Connection:
        def execute(self, query, params):
            inserted.append((str(query), params))

    class Engine:
        def begin(self):
            class Context:
                def __enter__(self):
                    return Connection()

                def __exit__(self, *_args):
                    return False

            return Context()

    monkeypatch.setattr("services.reporting.tasks.get_reporting_engine", lambda: Engine())
    record_dead_letter("task-789", "reporting.run_pipeline", 4, "db unavailable")

    assert inserted[0][1]["task_id"] == "task-789"
    assert inserted[0][1]["attempt_number"] == 4
    assert inserted[0][1]["error_message"] == "db unavailable"
