from __future__ import annotations

import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError

from services.api.auth import get_current_user
from services.api.models import Role, User
from services.reporting import store
from services.reporting.schemas import (
    PipelineRunResponse,
    PipelineTriggerResponse,
    WeeklyPerformanceResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reporting", tags=["reporting"], dependencies=[Depends(get_current_user)])


def _require_manager(current_user: User) -> None:
    if current_user.role not in {Role.ADMIN, Role.MANAGER}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions.")


@router.get(
    "/weekly-warehouse-client-performance",
    response_model=WeeklyPerformanceResponse,
)
def get_weekly_warehouse_client_performance(
    week_start: date | None = Query(default=None),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _require_manager(current_user)
    if week_start is not None and week_start.weekday() != 0:
        raise HTTPException(status_code=422, detail="week_start must be a Monday.")
    try:
        report = store.weekly_performance(week_start)
    except (SQLAlchemyError, RuntimeError, ValueError) as exc:
        logger.error("Warehouse performance report could not be read: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Warehouse performance report is unavailable.") from None
    if report is None:
        raise HTTPException(status_code=404, detail="No weekly warehouse performance report is available.")
    return report


@router.get("/pipeline-runs/latest", response_model=PipelineRunResponse)
def get_latest_pipeline_run(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _require_manager(current_user)
    try:
        run = store.latest_pipeline_run()
    except (SQLAlchemyError, RuntimeError, ValueError) as exc:
        logger.error("Pipeline run status could not be read: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Pipeline run status is unavailable.") from None
    if run is None:
        raise HTTPException(status_code=404, detail="No pipeline run has been recorded.")
    return run


@router.post(
    "/pipeline-runs",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PipelineTriggerResponse,
)
def trigger_pipeline_run(
    week_start: date | None = Query(default=None),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    _require_manager(current_user)
    if week_start is not None and week_start.weekday() != 0:
        raise HTTPException(status_code=422, detail="week_start must be a Monday.")
    try:
        from data.pipelines.pipeline import trigger_pipeline

        run_id = trigger_pipeline(week_start)
    except ModuleNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="The Prefect pipeline runtime is not installed or available.",
        ) from None
    except RuntimeError as exc:
        logger.error("Pipeline runtime could not be started: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="The pipeline runtime is unavailable.") from None
    except OSError:
        logger.error("Pipeline process could not be started.")
        raise HTTPException(status_code=503, detail="The pipeline could not be started.") from None
    return {"run_id": run_id, "status": "QUEUED"}
