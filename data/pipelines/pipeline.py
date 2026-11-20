"""Weekly Warehouse & Client Performance Pipeline.

Reads from telemetry_events (read-only) and produces business KPIs in
the reporting schema. Built with Prefect for resilience, observability,
and recoverability.

The main flow orchestrates three subflows:
  1. extraction_subflow  — reads events from telemetry_events
  2. transformation_subflow — computes KPI aggregates
  3. load_subflow        — upserts results and saves optional snapshot

Run: python data/pipelines/pipeline.py
Schedule: Monday 01:00 UTC (cron: ``0 1 * * 1``)

This module is part of the TrackFlow Business Performance Pipeline.
It does NOT modify services/telemetry/analysis.py or the GET /telemetry/report endpoint.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from prefect import flow, task
from prefect.logging import get_run_logger
from sqlalchemy import text

# Allow running as a script from the repo root
_HERE = Path(__file__).resolve().parent  # data/pipelines/
_PROJECT = _HERE.parent.parent  # repo root
if str(_PROJECT) not in sys.path:
    sys.path.insert(0, str(_PROJECT))

from services.api.telemetry_database import get_telemetry_engine
from services.reporting.database import (
    complete_pipeline_run,
    create_pipeline_run,
    ensure_reporting_schema,
    upsert_weekly_performance,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────

ALLOWED_EVENT_TYPES = (
    "inbound_order_created",
    "outbound_order_created",
    "stock_threshold_triggered",
    "inventory_discrepancy_detected",
)

EVENT_TYPE_TO_KPI = {
    "inbound_order_created": "inbound_units_count",
    "outbound_order_created": "outbound_orders_count",
    "stock_threshold_triggered": "stockout_events_count",
    "inventory_discrepancy_detected": "discrepancy_events_count",
}

BRIEFING_KPI_LABELS = {
    "inbound_units_count": "Inbound Volume",
    "outbound_orders_count": "Outbound Throughput",
    "stockout_events_count": "Stockout Frequency",
    "discrepancy_events_count": "Discrepancy Events (supporting)",
    "discrepancy_rate": "Discrepancy Rate",
}

# ──────────────────────────────────────────────────────────────────────
# Helper: compute the Monday of the ISO week for a given date
# ──────────────────────────────────────────────────────────────────────

def _iso_week_start(task_run, input_mapping: dict) -> str:
    """Return the Monday date string of the ISO week from the input mapping.

    Prefect 2.x calls cache_key_fn with ``(task_run, input_mapping)``.
    The input mapping contains the keyword arguments passed to the task,
    so we extract the target week from whichever parameter is present.
    """
    week_val = input_mapping.get("week_start")
    if week_val is not None:
        dt = datetime.strptime(week_val, "%Y-%m-%d") if isinstance(week_val, str) else week_val
    else:
        dt = datetime.now(timezone.utc)
    days_since_monday = dt.weekday() if hasattr(dt, "weekday") else 0
    monday = dt - timedelta(days=days_since_monday) if hasattr(dt, "weekday") else dt
    return monday.strftime("%Y-%m-%d") if hasattr(monday, "strftime") else str(monday)


def _last_completed_iso_week() -> str:
    """Return the Monday of the most recently completed ISO week.

    If today is Monday, last week ended yesterday (Sunday).
    Otherwise, it's the previous Monday.
    """
    now = datetime.now(timezone.utc)
    days_since_monday = now.weekday()
    offset = days_since_monday + 7 if days_since_monday == 0 else days_since_monday
    last_monday = now - timedelta(days=offset)
    return last_monday.strftime("%Y-%m-%d")


# ──────────────────────────────────────────────────────────────────────
# Task definitions (leaf tasks used by subflows)
# ──────────────────────────────────────────────────────────────────────

@task(retries=3, retry_delay_seconds=30)
def extract_events(week_start: str) -> pd.DataFrame:
    """Extract mandatory telemetry events for the given ISO week.

    Retries: 3 attempts with 30-second delays.
    Justification: The database connection may be transiently unavailable
    (network blip, pool exhaustion, replica failover). Three retries with
    30-second gaps cover common transient failures within a ~2-minute window
    without blocking the pipeline for too long.
    """
    run_logger = get_run_logger(__name__)
    run_logger.info("Extracting events for week starting %s", week_start)

    week_end = (
        datetime.strptime(week_start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        + timedelta(days=7)
    )

    engine = get_telemetry_engine()
    query = text("""
        SELECT
            event_id,
            event_type,
            event_timestamp,
            properties::text AS properties_json
        FROM public.telemetry_events
        WHERE event_type IN :event_types
          AND event_timestamp >= :week_start
          AND event_timestamp < :week_end
        ORDER BY event_timestamp ASC
    """)

    with engine.connect() as connection:
        rows = connection.execute(
            query,
            {
                "event_types": tuple(ALLOWED_EVENT_TYPES),
                "week_start": week_start,
                "week_end": week_end,
            },
        ).mappings().all()

    run_logger.info("Extracted %d raw events", len(rows))
    return pd.DataFrame([dict(row) for row in rows])


# ──────────────────────────────────────────────────────────────────────
# Pure KPI computation logic (no Prefect dependency)
# ──────────────────────────────────────────────────────────────────────

def compute_kpis_logic(events_df: pd.DataFrame) -> list[dict[str, Any]]:
    """Compute KPI rows from a DataFrame of telemetry events.

    This is a pure function with no Prefect or database dependency.
    It can be tested in isolation with in-memory fixtures.

    Parameters
    ----------
    events_df : pd.DataFrame
        Must contain columns: event_id, event_type, event_timestamp,
        properties_json (JSON string).

    Returns
    -------
    list[dict[str, Any]]
        KPI rows with warehouse, client_id, week_start, and the four
        KPI fields (inbound_units_count, outbound_orders_count,
        stockout_events_count, discrepancy_events_count,
        discrepancy_rate).
    """
    if events_df.empty:
        return []

    df = events_df.copy()

    # Parse properties JSON
    df["properties"] = df["properties_json"].map(
        lambda x: json.loads(x) if isinstance(x, str) else {}
    )

    # Parse timestamps
    df["event_timestamp"] = pd.to_datetime(
        df["event_timestamp"], utc=True, errors="coerce"
    )
    df = df.dropna(subset=["event_timestamp"]).copy()

    if df.empty:
        return []

    # Derive week_start from event_timestamp
    df["week_start"] = df["event_timestamp"].map(
        lambda ts: ts.strftime("%Y-%m-%d")
    )

    # Only process the first (and expected only) week in the data
    target_week = df["week_start"].iloc[0]
    df = df[df["week_start"] == target_week]

    if df.empty:
        return []

    # Flatten properties
    df["warehouse"] = df["properties"].map(
        lambda p: p.get("warehouse") if isinstance(p, dict) else None
    )
    df["client_id"] = df["properties"].map(
        lambda p: p.get("client_id") if isinstance(p, dict) else None
    )
    df["quantity"] = df["properties"].map(
        lambda p: p.get("quantity", 0) if isinstance(p, dict) else 0
    )
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0).astype(int)

    # Drop rows with missing warehouse/client_id
    df = df.dropna(subset=["warehouse", "client_id"])

    if df.empty:
        return []

    # Group by warehouse x client_id x week_start
    groups = df.groupby(["warehouse", "client_id", "week_start"])

    results: list[dict[str, Any]] = []
    for (warehouse, client_id, week_start), group in groups:
        inbound = int(group[group["event_type"] == "inbound_order_created"]["quantity"].sum())
        outbound = int((group["event_type"] == "outbound_order_created").sum())
        stockout = int((group["event_type"] == "stock_threshold_triggered").sum())
        discrepancy = int((group["event_type"] == "inventory_discrepancy_detected").sum())
        disc_rate = round(discrepancy / outbound, 6) if outbound > 0 else 0.0

        results.append({
            "warehouse": warehouse,
            "client_id": client_id,
            "week_start": week_start,
            "inbound_units_count": inbound,
            "outbound_orders_count": outbound,
            "stockout_events_count": stockout,
            "discrepancy_events_count": discrepancy,
            "discrepancy_rate": disc_rate,
        })

    return results


@task(cache_key_fn=_iso_week_start, cache_expiration=timedelta(hours=1))
def compute_kpis(events_df: pd.DataFrame) -> list[dict[str, Any]]:
    """Prefect task: group events by warehouse x client x week and compute KPI aggregates.

    Delegates the pure computation to ``compute_kpis_logic``.

    Caching: cache key is the week_start string (derived from _iso_week_start).
    Cache expires after 1 hour.
    Justification: If the pipeline is re-run within the same hour for the same
    week (e.g., due to a manual trigger after a failed run), the transformation
    result is reused without re-computing. This is safe because the extract
    layer always re-reads from the database, so any new events are picked up on
    the next cache miss. One hour matches the typical delay between re-runs.
    """
    run_logger = get_run_logger(__name__)
    run_logger.info("Starting KPI computation on %d events", len(events_df))
    result = compute_kpis_logic(events_df)
    run_logger.info("Computed %d KPI rows", len(result))
    return result


@task(retries=2, retry_delay_seconds=15)
def load_reporting_rows(kpi_rows: list[dict[str, Any]]) -> int:
    """Upsert computed KPI rows into reporting.weekly_warehouse_client_performance.

    Retries: 2 attempts with 15-second delays.
    Justification: The load touches the database and may hit transient
    connection issues. Two retries with short delays are sufficient because
    the upsert is idempotent -- partial writes from a failed attempt are
    overwritten on retry.
    """
    run_logger = get_run_logger(__name__)
    if not kpi_rows:
        run_logger.info("No KPI rows to load -- skipping")
        return 0

    count = upsert_weekly_performance(kpi_rows)
    run_logger.info("Upserted %d KPI rows into reporting schema", count)
    return count


@task
def snapshot_eval(kpi_rows: list[dict[str, Any]], week_start: str) -> str | None:
    """Save a snapshot of computed KPI rows to data/eval/ for validation.

    This is an optional/non-critical step. A failure here must not block
    the main pipeline execution.
    """
    run_logger = get_run_logger(__name__)
    if not kpi_rows:
        run_logger.info("No KPI rows to snapshot -- skipping")
        return None

    eval_dir = _PROJECT / "data" / "eval"
    eval_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    filename = f"weekly_kpis_{week_start}_{timestamp}.json"
    filepath = eval_dir / filename

    try:
        with open(filepath, "w") as f:
            json.dump(
                {
                    "week_start": week_start,
                    "computed_at": timestamp,
                    "rows": kpi_rows,
                },
                f,
                indent=2,
            )
        run_logger.info("Snapshot saved to %s", filepath)
        return str(filepath)
    except OSError as exc:
        run_logger.warning("Failed to save eval snapshot: %s", exc)
        return None


# ──────────────────────────────────────────────────────────────────────
# Subflow 1: Extraction
# ──────────────────────────────────────────────────────────────────────

@flow(name="Extraction Subflow")
def extraction_subflow(week_start: str) -> pd.DataFrame:
    """Extract telemetry events for the given ISO week.

    This subflow ensures the reporting schema exists, then runs the
    extract task. It can be executed independently for debugging or
    ad-hoc extraction.
    """
    run_logger = get_run_logger(__name__)
    run_logger.info("Extraction subflow: week_start=%s", week_start)

    # Ensure the reporting schema exists before proceeding
    ensure_reporting_schema()

    events_df = extract_events(week_start)
    return events_df


# ──────────────────────────────────────────────────────────────────────
# Subflow 2: Transformation
# ──────────────────────────────────────────────────────────────────────

@flow(name="Transformation Subflow")
def transformation_subflow(events_df: pd.DataFrame) -> list[dict[str, Any]]:
    """Transform extracted events into KPI rows.

    This subflow wraps the compute_kpis task with caching. It can be
    executed independently with in-memory fixtures for testing.
    """
    run_logger = get_run_logger(__name__)
    run_logger.info("Transformation subflow: %d events received", len(events_df))

    kpi_rows = compute_kpis(events_df)
    return kpi_rows


# ──────────────────────────────────────────────────────────────────────
# Subflow 3: Load
# ──────────────────────────────────────────────────────────────────────

@flow(name="Load Subflow")
def load_subflow(kpi_rows: list[dict[str, Any]], week_start: str) -> dict[str, Any]:
    """Load KPI rows into the reporting schema and save an optional snapshot.

    The load is idempotent (upsert). The snapshot step is optional and
    its failure does not block the overall result.

    Returns a dict with ``records_loaded`` and ``snapshot_saved`` keys.
    """
    run_logger = get_run_logger(__name__)
    run_logger.info("Load subflow: %d KPI rows, week=%s", len(kpi_rows), week_start)

    # Stage 3a: Idempotent upsert
    records_loaded = load_reporting_rows(kpi_rows)

    # Stage 3b: Optional snapshot (non-critical)
    snapshot_result = snapshot_eval.with_options(return_state=True)(
        kpi_rows, week_start
    )
    snapshot_saved = (
        snapshot_result.result.is_completed()
        if hasattr(snapshot_result, "result")
        and hasattr(snapshot_result.result, "is_completed")
        and snapshot_result.result.is_completed()
        else False
    )

    return {
        "records_loaded": records_loaded,
        "snapshot_saved": snapshot_saved,
    }


# ──────────────────────────────────────────────────────────────────────
# Main flow — orchestrates the pipeline via subflows
# ──────────────────────────────────────────────────────────────────────

@flow(name="Weekly Warehouse and Client Performance")
def weekly_warehouse_client_performance_flow(
    week_start: str | None = None,
    triggered_by: str = "manual",
) -> dict[str, Any]:
    """Main pipeline flow: extraction_subflow -> transformation_subflow -> load_subflow.

    Each phase is an independent subflow with explicit inputs and outputs.
    The main flow handles orchestration, run tracking, and error handling.

    Args:
        week_start: ISO week Monday date (YYYY-MM-DD). Defaults to the last
            completed ISO week.
        triggered_by: Source of the trigger -- ``scheduler`` or ``manual``.

    Returns:
        Dict with run summary: run_id, week_start, status, records counts.
    """
    if week_start is None:
        week_start = _last_completed_iso_week()

    logger.info("Starting pipeline for week %s (triggered by: %s)", week_start, triggered_by)

    # Record the run in the pipeline log
    run_id = create_pipeline_run(week_start, triggered_by=triggered_by)

    try:
        # Subflow 1: Extraction
        events_df = extraction_subflow(week_start)
        records_extracted = len(events_df)

        # Subflow 2: Transformation
        kpi_rows = transformation_subflow(events_df)

        # Subflow 3: Load (idempotent upsert + optional snapshot)
        load_result = load_subflow(kpi_rows, week_start)
        records_loaded = load_result["records_loaded"]
        snapshot_saved = load_result["snapshot_saved"]

        # Record successful completion
        complete_pipeline_run(
            run_id,
            status="completed",
            records_extracted=records_extracted,
            records_loaded=records_loaded,
        )

        summary = {
            "run_id": run_id,
            "week_start": week_start,
            "status": "completed",
            "records_extracted": records_extracted,
            "records_loaded": records_loaded,
            "snapshot_saved": snapshot_saved,
        }
        logger.info("Pipeline completed: %s", summary)
        return summary

    except Exception as exc:
        logger.error("Pipeline failed: %s", exc)
        try:
            complete_pipeline_run(
                run_id,
                status="failed",
                records_extracted=locals().get("records_extracted", 0),
                records_loaded=locals().get("records_loaded", 0),
                error_message=str(exc),
            )
        except Exception:
            logger.exception("Failed to record pipeline failure status")
        return {
            "run_id": run_id,
            "week_start": week_start,
            "status": "failed",
            "error": str(exc),
        }


# ──────────────────────────────────────────────────────────────────────
# CLI entrypoint — allows running as a script
# ──────────────────────────────────────────────────────────────────────

def trigger_pipeline_run(week_start: str | None = None) -> dict[str, Any]:
    """Trigger a pipeline run, returning the summary dict.

    This is the function imported by services/reporting/ endpoints.
    It wraps the flow so callers don't need to import Prefect directly.
    """
    return weekly_warehouse_client_performance_flow(week_start=week_start)


def get_latest_pipeline_run() -> dict[str, Any] | None:
    """Return the latest pipeline run metadata from the reporting schema.

    Delegates to services.reporting.database.get_latest_pipeline_run().
    """
    from services.reporting.database import get_latest_pipeline_run as _get_latest
    return _get_latest()


# ──────────────────────────────────────────────────────────────────────
# When run directly as a script
# ──────────────────────────────────────────────────────────────────────
# Command: python data/pipelines/pipeline.py
# Schedule: Monday 01:00 UTC (cron: ``0 1 * * 1``)

if __name__ == "__main__":
    # Configure basic logging for CLI use
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    result = weekly_warehouse_client_performance_flow()
    print(f"\nPipeline result: {json.dumps(result, indent=2, default=str)}")
    if result.get("status") == "failed":
        sys.exit(1)