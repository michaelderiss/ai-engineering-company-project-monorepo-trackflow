"""Dedicated database connection and schema for the reporting pipeline.

This module manages the reporting schema and tables that are separate from
telemetry_events. The pipeline reads from telemetry_events (read-only) and
writes results here. No ETL logic lives in this module — only schema
management and queries.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, MetaData, Table, TextClause, create_engine, text
from sqlalchemy.engine import make_url


# ──────────────────────────────────────────────────────────────
# Schema and table names
# ──────────────────────────────────────────────────────────────

REPORTING_SCHEMA = "reporting"
WEEKLY_PERFORMANCE_TABLE = "weekly_warehouse_client_performance"
PIPELINE_RUNS_TABLE = "pipeline_runs"


# ──────────────────────────────────────────────────────────────
# DDL statements for the reporting schema
# ──────────────────────────────────────────────────────────────

CREATE_SCHEMA_SQL = text(f"CREATE SCHEMA IF NOT EXISTS {REPORTING_SCHEMA}")

CREATE_PERFORMANCE_TABLE_SQL = text(f"""
CREATE TABLE IF NOT EXISTS {REPORTING_SCHEMA}.{WEEKLY_PERFORMANCE_TABLE} (
    id              uuid primary key default gen_random_uuid(),
    warehouse       text not null,
    client_id       text not null,
    week_start      date not null,
    inbound_units_count    integer not null default 0,
    outbound_orders_count  integer not null default 0,
    stockout_events_count  integer not null default 0,
    discrepancy_events_count integer not null default 0,
    discrepancy_rate        numeric not null default 0,
    computed_at     timestamptz not null default now(),
    unique (warehouse, client_id, week_start)
)
""")

CREATE_PIPELINE_RUNS_TABLE_SQL = text(f"""
CREATE TABLE IF NOT EXISTS {REPORTING_SCHEMA}.{PIPELINE_RUNS_TABLE} (
    run_id              uuid primary key default gen_random_uuid(),
    week_start          date not null,
    started_at          timestamptz not null,
    completed_at        timestamptz,
    status              text not null default 'running',
    records_extracted   integer not null default 0,
    records_loaded      integer not null default 0,
    error_message       text,
    triggered_by        text not null default 'manual'
)
""")


# ──────────────────────────────────────────────────────────────
# Connection management — uses the same TELEMETRY_DATABASE_URL
# as telemetry (they share the same PostgreSQL instance but
# the reporting schema is a separate logical namespace).
# ──────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _engine_for_url(database_url: str) -> Engine:
    """Create a cached SQLAlchemy engine for the reporting database.

    Uses the same TELEMETRY_DATABASE_URL as the telemetry system.
    The reporting schema is a separate namespace within the same
    database, not a different database.
    """
    url = make_url(database_url)
    if url.drivername == "postgres":
        url = url.set(drivername="postgresql")
    if url.drivername not in {"postgresql", "postgresql+psycopg2"}:
        raise RuntimeError("REPORTING_DATABASE_URL must use PostgreSQL.")
    query = dict(url.query)
    if query.get("sslmode") not in {"require", "verify-ca", "verify-full"}:
        query["sslmode"] = "require"
    url = url.set(query=query)
    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )


def get_reporting_engine() -> Engine:
    """Return the reporting engine, reading TELEMETRY_DATABASE_URL.

    The reporting pipeline shares the PostgreSQL instance with telemetry
    but writes into the ``reporting`` schema — never into telemetry_events.
    """
    database_url = os.getenv("TELEMETRY_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError(
            "TELEMETRY_DATABASE_URL is not configured. "
            "The reporting pipeline reads from telemetry_events (in the telemetry database) "
            "and writes its output to the reporting schema in the same database."
        )
    return _engine_for_url(database_url)


# ──────────────────────────────────────────────────────────────
# Schema initialisation
# ──────────────────────────────────────────────────────────────

def ensure_reporting_schema() -> None:
    """Create the reporting schema and all required tables if they do not exist.

    This is safe to call multiple times — each CREATE statement uses IF NOT EXISTS.
    It should be called once at startup or before the first pipeline run.
    """
    engine = get_reporting_engine()
    with engine.begin() as connection:
        connection.execute(CREATE_SCHEMA_SQL)
        connection.execute(CREATE_PERFORMANCE_TABLE_SQL)
        connection.execute(CREATE_PIPELINE_RUNS_TABLE_SQL)


# ──────────────────────────────────────────────────────────────
# Upsert helper for the weekly performance table
# ──────────────────────────────────────────────────────────────

UPSERT_PERFORMANCE_SQL = text(f"""
INSERT INTO {REPORTING_SCHEMA}.{WEEKLY_PERFORMANCE_TABLE}
    (warehouse, client_id, week_start,
     inbound_units_count, outbound_orders_count,
     stockout_events_count, discrepancy_events_count,
     discrepancy_rate, computed_at)
VALUES
    (:warehouse, :client_id, :week_start,
     :inbound_units_count, :outbound_orders_count,
     :stockout_events_count, :discrepancy_events_count,
     :discrepancy_rate, now())
ON CONFLICT (warehouse, client_id, week_start)
DO UPDATE SET
    inbound_units_count    = EXCLUDED.inbound_units_count,
    outbound_orders_count  = EXCLUDED.outbound_orders_count,
    stockout_events_count  = EXCLUDED.stockout_events_count,
    discrepancy_events_count = EXCLUDED.discrepancy_events_count,
    discrepancy_rate       = EXCLUDED.discrepancy_rate,
    computed_at            = now()
""")


def upsert_weekly_performance(rows: list[dict[str, Any]]) -> int:
    """Upsert a batch of KPI rows into the weekly performance table.

    Returns the number of rows processed. The upsert is idempotent:
    running it twice with the same data produces the same result.
    """
    if not rows:
        return 0
    engine = get_reporting_engine()
    total = 0
    with engine.begin() as connection:
        for row in rows:
            connection.execute(UPSERT_PERFORMANCE_SQL, row)
            total += 1
    return total


# ──────────────────────────────────────────────────────────────
# Pipeline run log helpers
# ──────────────────────────────────────────────────────────────

INSERT_RUN_SQL = text(f"""
INSERT INTO {REPORTING_SCHEMA}.{PIPELINE_RUNS_TABLE}
    (run_id, week_start, started_at, status, triggered_by)
VALUES
    (:run_id, :week_start, :started_at, 'running', :triggered_by)
""")


COMPLETE_RUN_SQL = text(f"""
UPDATE {REPORTING_SCHEMA}.{PIPELINE_RUNS_TABLE}
SET
    completed_at = :completed_at,
    status       = :status,
    records_extracted = :records_extracted,
    records_loaded    = :records_loaded,
    error_message     = :error_message
WHERE run_id = :run_id
""")


def create_pipeline_run(week_start: str, triggered_by: str = "manual") -> str:
    """Record the start of a pipeline run and return its run_id UUID."""
    from uuid import uuid4

    run_id = str(uuid4())
    from datetime import datetime, timezone

    engine = get_reporting_engine()
    with engine.begin() as connection:
        connection.execute(
            INSERT_RUN_SQL,
            {
                "run_id": run_id,
                "week_start": week_start,
                "started_at": datetime.now(timezone.utc),
                "triggered_by": triggered_by,
            },
        )
    return run_id


def complete_pipeline_run(
    run_id: str,
    status: str,
    records_extracted: int = 0,
    records_loaded: int = 0,
    error_message: str | None = None,
) -> None:
    """Record the completion or failure of a pipeline run."""
    from datetime import datetime, timezone

    engine = get_reporting_engine()
    with engine.begin() as connection:
        connection.execute(
            COMPLETE_RUN_SQL,
            {
                "run_id": run_id,
                "completed_at": datetime.now(timezone.utc),
                "status": status,
                "records_extracted": records_extracted,
                "records_loaded": records_loaded,
                "error_message": error_message,
            },
        )


# ──────────────────────────────────────────────────────────────
# Query helpers
# ──────────────────────────────────────────────────────────────

LATEST_RUN_SQL = text(f"""
SELECT run_id, week_start, started_at, completed_at, status,
       records_extracted, records_loaded, error_message, triggered_by
FROM {REPORTING_SCHEMA}.{PIPELINE_RUNS_TABLE}
WHERE status IN ('completed', 'failed')
ORDER BY started_at DESC
LIMIT 1
""")


def get_latest_pipeline_run() -> dict[str, Any] | None:
    """Return metadata for the most recent pipeline run (completed or failed).

    Returns None if no runs have been recorded yet.
    """
    engine = get_reporting_engine()
    with engine.connect() as connection:
        row = connection.execute(LATEST_RUN_SQL).mappings().first()
    if row is None:
        return None
    return dict(row._mapping)


QUERY_KPIS_SQL = text(f"""
SELECT warehouse, client_id, week_start,
       inbound_units_count, outbound_orders_count,
       stockout_events_count, discrepancy_events_count,
       discrepancy_rate
FROM {REPORTING_SCHEMA}.{WEEKLY_PERFORMANCE_TABLE}
WHERE week_start = :week_start
ORDER BY warehouse, client_id
""")


LATEST_WEEK_SQL = text(f"""
SELECT DISTINCT week_start
FROM {REPORTING_SCHEMA}.{WEEKLY_PERFORMANCE_TABLE}
ORDER BY week_start DESC
LIMIT 1
""")


def query_reporting_kpis(week_start: str | None = None) -> dict[str, Any]:
    """Return KPIs for a given ISO week, or the most recent computed week.

    Response shape matches the company-BRIEFING.md contract:
    {
        "week_start": "2026-07-13",
        "entries": [
            {
                "warehouse": "los_angeles",
                "client_id": "fashion-co",
                ...
            }
        ]
    }
    """
    engine = get_reporting_engine()
    with engine.connect() as connection:
        if week_start is None:
            row = connection.execute(LATEST_WEEK_SQL).first()
            if row is None:
                return {"week_start": None, "entries": []}
            week_start = str(row[0])

        rows = connection.execute(
            QUERY_KPIS_SQL, {"week_start": week_start}
        ).mappings().all()

    return {
        "week_start": week_start,
        "entries": [
            {
                "warehouse": row["warehouse"],
                "client_id": row["client_id"],
                "inbound_units_count": row["inbound_units_count"],
                "outbound_orders_count": row["outbound_orders_count"],
                "stockout_events_count": row["stockout_events_count"],
                "discrepancy_events_count": row["discrepancy_events_count"],
                "discrepancy_rate": float(row["discrepancy_rate"]),
            }
            for row in rows
        ],
    }