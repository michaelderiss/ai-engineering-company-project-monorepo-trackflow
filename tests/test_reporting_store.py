from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine, text

from services.reporting import store


def test_weekly_performance_upsert_is_idempotent(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    monkeypatch.setattr(store, "_engine", lambda: engine)
    rows = [
        {
            "warehouse": "los_angeles",
            "client_id": "fashion-co",
            "week_start": date(2026, 11, 2),
            "inbound_units_count": 4200,
            "outbound_orders_count": 980,
            "stockout_events_count": 3,
            "discrepancy_events_count": 2,
            "discrepancy_rate": 2 / 980,
        }
    ]

    assert store.upsert_weekly_performance(rows) == 1
    assert store.upsert_weekly_performance(rows) == 1
    report = store.weekly_performance(date(2026, 11, 2))
    with engine.connect() as connection:
        row_count = connection.execute(
            text("SELECT COUNT(*) FROM weekly_warehouse_client_performance")
        ).scalar_one()

    assert row_count == 1
    assert report is not None
    assert report["entries"][0]["inbound_units_count"] == 4200
    assert report["entries"][0]["discrepancy_rate"] == 2 / 980


def test_pipeline_run_metadata_round_trips_as_structured_data(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    monkeypatch.setattr(store, "_engine", lambda: engine)
    store.record_pipeline_run(
        {
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
    )

    record = store.latest_pipeline_run()

    assert record is not None
    assert record["run_id"] == "run-123"
    assert record["records_processed"] == 17
    assert record["errors"] == []
