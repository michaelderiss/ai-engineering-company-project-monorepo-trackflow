from __future__ import annotations

from datetime import date
from types import ModuleType
import sys

from fastapi.testclient import TestClient

from services.reporting import routes, store


def test_weekly_report_requires_manager(client: TestClient, auth_headers):
    response = client.get(
        "/reporting/weekly-warehouse-client-performance",
        headers=auth_headers[0],
    )

    assert response.status_code == 403


def test_weekly_report_returns_expected_business_kpis(
    client: TestClient, manager_account, monkeypatch
):
    expected = {
        "week_start": date(2026, 11, 2),
        "entries": [
            {
                "warehouse": "los_angeles",
                "client_id": "fashion-co",
                "inbound_units_count": 4200,
                "outbound_orders_count": 980,
                "stockout_events_count": 3,
                "discrepancy_events_count": 2,
                "discrepancy_rate": 2 / 980,
            }
        ],
    }
    monkeypatch.setattr(store, "weekly_performance", lambda week: expected)

    response = client.get(
        "/reporting/weekly-warehouse-client-performance?week_start=2026-11-02",
        headers=manager_account["headers"],
    )

    assert response.status_code == 200
    assert response.json() == {
        "week_start": "2026-11-02",
        "entries": [
            {
                "warehouse": "los_angeles",
                "client_id": "fashion-co",
                "inbound_units_count": 4200,
                "outbound_orders_count": 980,
                "stockout_events_count": 3,
                "discrepancy_events_count": 2,
                "discrepancy_rate": 2 / 980,
            }
        ],
    }


def test_weekly_report_rejects_non_monday(client: TestClient, manager_account):
    response = client.get(
        "/reporting/weekly-warehouse-client-performance?week_start=2026-11-03",
        headers=manager_account["headers"],
    )

    assert response.status_code == 422


def test_pipeline_status_returns_latest_run(
    client: TestClient, manager_account, monkeypatch
):
    expected = {
        "run_id": "run-123",
        "week_start": date(2026, 11, 2),
        "queued_at": "2026-11-09T06:00:00+00:00",
        "start_time": "2026-11-09T06:00:01+00:00",
        "end_time": "2026-11-09T06:00:05+00:00",
        "records_processed": 17,
        "rows_written": 2,
        "status": "COMPLETED",
        "errors": [],
    }
    monkeypatch.setattr(store, "latest_pipeline_run", lambda: expected)

    response = client.get(
        "/reporting/pipeline-runs/latest",
        headers=manager_account["headers"],
    )

    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETED"
    assert response.json()["records_processed"] == 17


def test_manual_run_calls_pipeline_launcher(
    client: TestClient, manager_account, monkeypatch
):
    package = ModuleType("data")
    package.__path__ = []
    pipelines = ModuleType("data.pipelines")
    pipelines.__path__ = []
    pipeline = ModuleType("data.pipelines.pipeline")
    pipeline.trigger_pipeline = lambda week_start: "run-456"
    monkeypatch.setitem(sys.modules, "data", package)
    monkeypatch.setitem(sys.modules, "data.pipelines", pipelines)
    monkeypatch.setitem(sys.modules, "data.pipelines.pipeline", pipeline)

    response = client.post(
        "/reporting/pipeline-runs?week_start=2026-11-02",
        headers=manager_account["headers"],
    )

    assert response.status_code == 202
    assert response.json() == {"run_id": "run-456", "status": "QUEUED"}
