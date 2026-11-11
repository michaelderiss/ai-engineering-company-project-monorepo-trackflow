from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class WeeklyPerformanceEntry(BaseModel):
    warehouse: Literal["los_angeles", "zaragoza"]
    client_id: str
    inbound_units_count: int = Field(ge=0)
    outbound_orders_count: int = Field(ge=0)
    stockout_events_count: int = Field(ge=0)
    discrepancy_events_count: int = Field(ge=0)
    discrepancy_rate: float = Field(ge=0)


class WeeklyPerformanceResponse(BaseModel):
    week_start: date
    entries: list[WeeklyPerformanceEntry]


class PipelineRunResponse(BaseModel):
    run_id: str
    week_start: date | None = None
    queued_at: datetime | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    records_processed: int = 0
    rows_written: int = 0
    status: str
    errors: list[str] = Field(default_factory=list)


class PipelineTriggerResponse(BaseModel):
    run_id: str
    status: Literal["QUEUED"]
