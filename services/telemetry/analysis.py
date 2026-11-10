"""Pandas-based technical telemetry metrics backed by bounded SQL queries."""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any

import pandas as pd
from sqlalchemy import bindparam, text


ALL_EVENT_TYPES = (
    "inbound_order_created",
    "outbound_order_created",
    "stock_threshold_triggered",
    "direct_stock_edit_rejected",
    "inventory_discrepancy_detected",
    "inventory_validation_failed",
    "inventory_products_viewed",
    "login_succeeded",
    "login_failed",
    "session_expired",
    "navigation_page_viewed",
    "flow_abandoned",
    "api_latency_recorded",
    "frontend_error_captured",
    "web_vital_recorded",
    "supplier_action_completed",
    "incident_action_completed",
)


def _read_events(
    event_types: tuple[str, ...], start: datetime, end: datetime
) -> list[dict[str, Any]]:
    """Read only selected event kinds in the half-open UTC period [start, end)."""
    from services.api.inventory_database import engine

    statement = text(
        "SELECT event_type, event_timestamp, properties "
        "FROM public.telemetry_events "
        "WHERE event_timestamp >= :start AND event_timestamp < :end "
        "AND event_type IN :event_types"
    ).bindparams(bindparam("event_types", expanding=True))
    with engine.connect() as connection:
        rows = connection.execute(
            statement,
            {"start": start, "end": end, "event_types": event_types},
        ).mappings().all()
    return [dict(row) for row in rows]


def _frame(event_types: tuple[str, ...], start: datetime, end: datetime) -> pd.DataFrame:
    rows = _read_events(event_types, start, end)
    frame = pd.DataFrame.from_records(rows)
    if frame.empty:
        return pd.DataFrame(columns=["event_type", "event_timestamp", "properties", "day"])

    # Normalize before any temporal grouping; database timestamps may arrive in
    # different offsets even though the stored contract is UTC-aware.
    frame["event_timestamp"] = pd.to_datetime(frame["event_timestamp"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["event_timestamp"]).copy()
    frame["day"] = frame["event_timestamp"].dt.strftime("%Y-%m-%d")
    frame["properties"] = frame["properties"].map(_properties_dict)
    return frame


def _properties_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def events_per_day(start: datetime, end: datetime) -> list[dict[str, Any]]:
    """Count received events by UTC calendar day (technical pipeline volume)."""
    frame = _frame(ALL_EVENT_TYPES, start, end)
    if frame.empty:
        return []
    grouped = frame.groupby("day", as_index=False).size().rename(columns={"size": "event_count"})
    return grouped.to_dict(orient="records")


def api_error_rate_by_day(start: datetime, end: datetime) -> list[dict[str, Any]]:
    """Return daily API failure ratio from instrumented API request events."""
    frame = _frame(("api_latency_recorded",), start, end)
    if frame.empty:
        return []
    frame["status_code"] = frame["properties"].map(
        lambda properties: pd.to_numeric(properties.get("status_code"), errors="coerce")
    )
    frame = frame.dropna(subset=["status_code"])
    if frame.empty:
        return []
    frame["is_error"] = frame["status_code"] >= 400
    grouped = frame.groupby("day").agg(
        request_count=("is_error", "size"), error_count=("is_error", "sum")
    ).reset_index()
    grouped["error_rate"] = (grouped["error_count"] / grouped["request_count"]).round(6)
    for column in ("request_count", "error_count"):
        grouped[column] = grouped[column].astype(int)
    return grouped.to_dict(orient="records")


def api_latency_by_day_route(start: datetime, end: datetime) -> list[dict[str, Any]]:
    """Summarize API latency by UTC day and safe route template."""
    frame = _frame(("api_latency_recorded",), start, end)
    if frame.empty:
        return []
    frame["route"] = frame["properties"].map(lambda properties: properties.get("route"))
    frame["duration_ms"] = frame["properties"].map(
        lambda properties: pd.to_numeric(properties.get("duration_ms"), errors="coerce")
    )
    frame = frame.dropna(subset=["route", "duration_ms"])
    if frame.empty:
        return []
    grouped = frame.groupby(["day", "route"])["duration_ms"].agg(
        request_count="size", mean_duration_ms="mean", p95_duration_ms=lambda values: values.quantile(0.95)
    ).reset_index()
    grouped["request_count"] = grouped["request_count"].astype(int)
    for column in ("mean_duration_ms", "p95_duration_ms"):
        grouped[column] = grouped[column].round(3)
    return grouped.to_dict(orient="records")


def build_technical_report(start: datetime, end: datetime) -> dict[str, list[dict[str, Any]]]:
    """Build report metrics for one already-resolved reporting period."""
    return {
        "events_per_day": events_per_day(start, end),
        "api_error_rate_by_day": api_error_rate_by_day(start, end),
        "api_latency_by_day_route": api_latency_by_day_route(start, end),
    }