"""Reporting API endpoints — business-facing, separate from services/telemetry/.

These endpoints expose the output of the business performance pipeline and
allow manual triggering. They import pipeline logic from data/pipelines/ —
no ETL logic lives here.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from services.reporting.database import query_reporting_kpis as _query_kpis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reporting", tags=["reporting"])


@router.get("/pipeline-runs/latest")
def get_latest_run() -> dict[str, Any]:
    """Return metadata for the most recent pipeline run.

    Response includes run_id, week_start, started_at, completed_at, status,
    records_extracted, records_loaded, and triggered_by.
    """
    # Import here to avoid circular imports and keep ETL logic in data/pipelines/
    from data.pipelines.pipeline import get_latest_pipeline_run as _get_latest_run

    result = _get_latest_run()
    if result is None:
        raise HTTPException(status_code=404, detail="No pipeline runs found yet.")
    return result


@router.post("/pipeline-runs")
def trigger_manual_run(week_start: str | None = None) -> dict[str, Any]:
    """Trigger a manual pipeline run for the given ISO week.

    If ``week_start`` is omitted, the pipeline runs for the last completed
    ISO week. Returns the run summary with status.
    """
    from data.pipelines.pipeline import trigger_pipeline_run as _trigger_run

    result = _trigger_run(week_start=week_start)
    if result.get("status") == "failed":
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline run failed: {result.get('error', 'Unknown error')}",
        )
    return result


@router.get("/weekly-warehouse-client-performance")
def get_weekly_performance(
    week_start: str | None = Query(
        default=None,
        description="ISO week Monday date (YYYY-MM-DD). Defaults to the most recent computed week.",
    ),
) -> dict[str, Any]:
    """Return KPI rows for the given week.

    Response shape matches the company-BRIEFING.md contract:
    {
        "week_start": "2026-07-13",
        "entries": [
            {
                "warehouse": "los_angeles",
                "client_id": "fashion-co",
                "inbound_units_count": 4200,
                "outbound_orders_count": 980,
                "stockout_events_count": 3,
                "discrepancy_events_count": 2,
                "discrepancy_rate": 0.002
            }
        ]
    }
    """
    result = _query_kpis(week_start=week_start)
    if result["week_start"] is None:
        raise HTTPException(status_code=404, detail="No reporting data found yet.")
    return result