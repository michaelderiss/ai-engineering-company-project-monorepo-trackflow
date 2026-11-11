from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import Engine, text

from services.api.telemetry_database import get_telemetry_engine


def _engine() -> Engine:
    return get_telemetry_engine()


def _table_name(engine: Engine, table: str) -> str:
    return f"reporting.{table}" if engine.dialect.name == "postgresql" else table


def ensure_reporting_tables() -> None:
    engine = _engine()
    performance_table = _table_name(engine, "weekly_warehouse_client_performance")
    runs_table = _table_name(engine, "pipeline_runs")
    schema_statement = (
        "CREATE SCHEMA IF NOT EXISTS reporting"
        if engine.dialect.name == "postgresql"
        else None
    )
    with engine.begin() as connection:
        if schema_statement:
            connection.execute(text(schema_statement))
        connection.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {performance_table} (
                    id { 'UUID PRIMARY KEY DEFAULT gen_random_uuid()' if engine.dialect.name == 'postgresql' else 'INTEGER PRIMARY KEY AUTOINCREMENT' },
                    warehouse TEXT NOT NULL,
                    client_id TEXT NOT NULL,
                    week_start DATE NOT NULL,
                    inbound_units_count INTEGER NOT NULL DEFAULT 0,
                    outbound_orders_count INTEGER NOT NULL DEFAULT 0,
                    stockout_events_count INTEGER NOT NULL DEFAULT 0,
                    discrepancy_events_count INTEGER NOT NULL DEFAULT 0,
                    discrepancy_rate NUMERIC NOT NULL DEFAULT 0,
                    computed_at { 'TIMESTAMPTZ NOT NULL DEFAULT now()' if engine.dialect.name == 'postgresql' else 'TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP' },
                    UNIQUE (warehouse, client_id, week_start)
                )
                """
            )
        )
        connection.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {runs_table} (
                    run_id TEXT PRIMARY KEY,
                    week_start DATE,
                    queued_at TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    records_processed INTEGER NOT NULL DEFAULT 0,
                    rows_written INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    errors TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT NOT NULL
                )
                """
            )
        )


def record_pipeline_run(record: dict[str, Any]) -> None:
    ensure_reporting_tables()
    engine = _engine()
    table = _table_name(engine, "pipeline_runs")
    now = datetime.now(timezone.utc).isoformat()
    values = {
        "run_id": record["run_id"],
        "week_start": record.get("week_start"),
        "queued_at": record.get("queued_at"),
        "start_time": record.get("start_time"),
        "end_time": record.get("end_time"),
        "records_processed": record.get("records_processed", 0),
        "rows_written": record.get("rows_written", 0),
        "status": record["status"],
        "errors": record.get("errors", "[]"),
        "updated_at": now,
    }
    for field in ("queued_at", "start_time", "end_time"):
        if isinstance(values[field], datetime):
            if values[field].tzinfo is None or values[field].utcoffset() is None:
                raise ValueError(f"{field} must include a timezone.")
            values[field] = values[field].astimezone(timezone.utc).isoformat()
    if not isinstance(values["errors"], str):
        values["errors"] = json.dumps(values["errors"], allow_nan=False)

    statement = text(
        f"""
        INSERT INTO {table}
          (run_id, week_start, queued_at, start_time, end_time, records_processed,
           rows_written, status, errors, updated_at)
        VALUES
          (:run_id, :week_start, :queued_at, :start_time, :end_time, :records_processed,
           :rows_written, :status, :errors, :updated_at)
        ON CONFLICT (run_id) DO UPDATE SET
          week_start = excluded.week_start,
          queued_at = excluded.queued_at,
          start_time = excluded.start_time,
          end_time = excluded.end_time,
          records_processed = excluded.records_processed,
          rows_written = excluded.rows_written,
          status = excluded.status,
          errors = excluded.errors,
          updated_at = excluded.updated_at
        """
    )
    with engine.begin() as connection:
        connection.execute(statement, values)


def latest_pipeline_run() -> dict[str, Any] | None:
    ensure_reporting_tables()
    engine = _engine()
    table = _table_name(engine, "pipeline_runs")
    with engine.connect() as connection:
        row = connection.execute(
            text(f"SELECT * FROM {table} ORDER BY updated_at DESC LIMIT 1")
        ).mappings().first()
    if row is None:
        return None
    record = dict(row)
    if isinstance(record["errors"], str):
        record["errors"] = json.loads(record["errors"])
    return record


def weekly_performance(week_start: date | None = None) -> dict[str, Any] | None:
    ensure_reporting_tables()
    engine = _engine()
    table = _table_name(engine, "weekly_warehouse_client_performance")
    with engine.connect() as connection:
        selected_week = week_start or connection.execute(
            text(f"SELECT MAX(week_start) FROM {table}")
        ).scalar_one()
        if selected_week is None:
            return None
        rows = connection.execute(
            text(
                f"""
                SELECT warehouse, client_id, week_start, inbound_units_count,
                       outbound_orders_count, stockout_events_count,
                       discrepancy_events_count, discrepancy_rate
                FROM {table}
                WHERE week_start = :week_start
                ORDER BY warehouse, client_id
                """
            ),
            {"week_start": selected_week},
        ).mappings().all()
    return {
        "week_start": selected_week,
        "entries": [
            {
                **dict(row),
                "discrepancy_rate": float(row["discrepancy_rate"]),
            }
            for row in rows
        ],
    }


def upsert_weekly_performance(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    ensure_reporting_tables()
    engine = _engine()
    table = _table_name(engine, "weekly_warehouse_client_performance")
    computed_at = datetime.now(timezone.utc)
    statement = text(
        f"""
        INSERT INTO {table}
          (warehouse, client_id, week_start, inbound_units_count, outbound_orders_count,
           stockout_events_count, discrepancy_events_count, discrepancy_rate, computed_at)
        VALUES
          (:warehouse, :client_id, :week_start, :inbound_units_count, :outbound_orders_count,
           :stockout_events_count, :discrepancy_events_count, :discrepancy_rate, :computed_at)
        ON CONFLICT (warehouse, client_id, week_start) DO UPDATE SET
          inbound_units_count = excluded.inbound_units_count,
          outbound_orders_count = excluded.outbound_orders_count,
          stockout_events_count = excluded.stockout_events_count,
          discrepancy_events_count = excluded.discrepancy_events_count,
          discrepancy_rate = excluded.discrepancy_rate,
          computed_at = excluded.computed_at
        """
    )
    values = [{**row, "computed_at": computed_at} for row in rows]
    with engine.begin() as connection:
        connection.execute(statement, values)
    return len(rows)
