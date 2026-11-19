from __future__ import annotations

import json
import logging
import math
import os
import re
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ValidationError, root_validator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])
MAX_BATCH_EVENTS = 20
MAX_BATCH_BYTES = 64 * 1024
SCHEMA_VERSION = "1.0.0"

# The receiver is deliberately an in-memory capture stub. It validates and
# acknowledges telemetry without persisting it or logging event properties.
EVENT_PROPERTIES: dict[str, tuple[set[str], set[str]]] = {
    "inbound_order_created": ({"warehouse", "client_id", "product_id", "product_category", "quantity"}, {"warehouse", "client_id", "product_id", "product_category", "quantity"}),
    "outbound_order_created": ({"warehouse", "client_id", "product_id", "product_category", "quantity"}, {"warehouse", "client_id", "product_id", "product_category", "quantity"}),
    "stock_threshold_triggered": ({"warehouse", "client_id", "product_id", "product_category", "quantity", "minimum_stock"}, {"warehouse", "client_id", "product_id", "product_category", "quantity", "minimum_stock"}),
    "direct_stock_edit_rejected": ({"warehouse", "client_id", "product_id", "product_category", "quantity", "rejection_code"}, {"warehouse", "client_id", "product_id", "product_category", "quantity", "rejection_code"}),
    "inventory_discrepancy_detected": ({"warehouse", "client_id", "product_id", "product_category", "quantity", "system_quantity", "physical_quantity"}, {"warehouse", "client_id", "product_id", "product_category", "quantity", "system_quantity", "physical_quantity"}),
    "inventory_validation_failed": ({"operation", "validation_code", "warehouse", "product_id"}, {"operation", "validation_code", "warehouse", "product_id", "product_category"}),
    "inventory_products_viewed": (set(), {"warehouse", "product_category", "result_count"}),
    "login_succeeded": (set(), {"auth_method"}),
    "login_failed": ({"reason"}, {"reason"}),
    "session_expired": ({"reason"}, {"reason"}),
    "navigation_page_viewed": ({"route"}, {"route"}),
    "flow_abandoned": ({"flow", "last_step"}, {"flow", "last_step"}),
    "api_latency_recorded": ({"route", "method", "status_code", "duration_ms"}, {"route", "method", "status_code", "duration_ms"}),
    "frontend_error_captured": ({"error_kind", "error_code", "route"}, {"error_kind", "error_code", "route"}),
    "web_vital_recorded": ({"metric_name", "value", "route"}, {"metric_name", "value", "route"}),
    "supplier_action_completed": ({"action", "result"}, {"action", "result"}),
    "incident_action_completed": ({"action", "result"}, {"action", "result"}),
}

ROUTES = {"/", "/inventory/products", "/inventory/orders", "/inventory/orders/inbound", "/inventory/orders/outbound", "/suppliers", "/incidents", "/incident-file-analyzer", "/account/profile"}
API_ROUTES = {"/auth/login", "/auth/me", "/users", "/profiles/me", "/inventory/products", "/inventory/orders", "/suppliers", "/api/incidents"}
ENUMS: dict[tuple[str, str], set[str]] = {
    ("*", "warehouse"): {"los_angeles", "zaragoza"},
    ("*", "product_category"): {"fashion", "electronics", "cosmetics"},
    ("inventory_validation_failed", "operation"): {"inbound", "outbound", "product"},
    ("inventory_validation_failed", "validation_code"): {"quantity_invalid", "sku_unknown", "warehouse_mismatch", "insufficient_stock", "missing_tracking_number", "duplicate_sku", "required_field_missing"},
    ("login_succeeded", "auth_method"): {"password"},
    ("login_failed", "reason"): {"invalid_credentials", "network_error", "rate_limited"},
    ("session_expired", "reason"): {"unauthorized_response"},
    ("flow_abandoned", "flow"): {"inbound_order", "outbound_order", "supplier_create", "incident_create"},
    ("flow_abandoned", "last_step"): {"form_opened", "form_started", "validation_failed", "submission_started"},
    ("api_latency_recorded", "method"): {"GET", "POST", "PATCH", "DELETE"},
    ("frontend_error_captured", "error_kind"): {"window_error", "unhandled_rejection", "render_error"},
    ("web_vital_recorded", "metric_name"): {"CLS", "FCP", "INP", "LCP", "TTFB"},
    ("supplier_action_completed", "action"): {"created", "rate_updated", "status_updated", "deleted"},
    ("incident_action_completed", "action"): {"created", "status_updated"},
    ("*", "result"): {"success", "failure"},
}


def _validate_properties(event_type: str, properties: Any) -> None:
    if event_type not in EVENT_PROPERTIES or not isinstance(properties, dict):
        raise ValueError("Invalid telemetry event.")
    required, allowed = EVENT_PROPERTIES[event_type]
    if not required.issubset(properties) or not set(properties).issubset(allowed):
        raise ValueError("Invalid telemetry event.")

    for key, value in properties.items():
        nullable_validation_field = (
            event_type == "inventory_validation_failed"
            and key in {"warehouse", "product_id", "product_category"}
            and value is None
        )
        if nullable_validation_field:
            continue
        choices = ENUMS.get((event_type, key), ENUMS.get(("*", key)))
        if choices and (not isinstance(value, str) or value not in choices):
            raise ValueError("Invalid telemetry event.")
        if key in {"client_id", "product_id"} and (
            not isinstance(value, str) or len(value) > 128 or not re.fullmatch(r"[a-zA-Z0-9._-]+", value)
        ):
            raise ValueError("Invalid telemetry event.")
        if key == "error_code" and (not isinstance(value, str) or len(value) > 80 or not re.fullmatch(r"[A-Z0-9_]+", value)):
            raise ValueError("Invalid telemetry event.")
        if key in {"route"} and value not in (ROUTES if event_type != "api_latency_recorded" else API_ROUTES):
            raise ValueError("Invalid telemetry event.")
        if key in {"quantity", "minimum_stock", "system_quantity", "physical_quantity", "result_count", "status_code"}:
            low, high = (100, 599) if key == "status_code" else (0, None)
            if type(value) is not int or value < low or (high is not None and value > high):
                raise ValueError("Invalid telemetry event.")
        if key == "duration_ms" or key == "value":
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError("Invalid telemetry event.")
    if event_type in {"inbound_order_created", "outbound_order_created"} and properties["quantity"] < 1:
        raise ValueError("Invalid telemetry event.")
    if event_type == "inventory_discrepancy_detected":
        if properties["quantity"] < 1 or abs(properties["physical_quantity"] - properties["system_quantity"]) != properties["quantity"]:
            raise ValueError("Invalid telemetry event.")


class TelemetryEvent(BaseModel):
    eventId: UUID
    timestamp: datetime
    sessionId: UUID | None
    userId: UUID | None
    event_type: str
    schemaVersion: str
    requestId: UUID
    properties: dict[str, Any]

    class Config:
        extra = "forbid"

    @root_validator
    def validate_contract(cls, values: dict[str, Any]) -> dict[str, Any]:
        if values.get("schemaVersion") != SCHEMA_VERSION:
            raise ValueError("Invalid telemetry event.")
        timestamp = values.get("timestamp")
        if timestamp is not None and (timestamp.tzinfo is None or timestamp.utcoffset() is None):
            raise ValueError("Invalid telemetry event.")
        _validate_properties(values.get("event_type", ""), values.get("properties"))
        return values


class TelemetryBatch(BaseModel):
    events: list[TelemetryEvent]

    class Config:
        extra = "forbid"


def telemetry_enabled() -> bool:
    return os.getenv("TELEMETRY_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}


@router.post("/events", status_code=status.HTTP_200_OK)
async def capture_telemetry(request: Request) -> dict[str, int]:
    if not telemetry_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    body = await request.body()
    if len(body) > MAX_BATCH_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Telemetry batch is too large.")
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported media type.")
    try:
        payload = json.loads(body)
        if not isinstance(payload, dict) or not isinstance(payload.get("events"), list) or not 1 <= len(payload["events"]) <= MAX_BATCH_EVENTS:
            raise ValueError("Invalid telemetry batch.")
        batch = TelemetryBatch.parse_obj(payload)
    except (json.JSONDecodeError, ValidationError, ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Telemetry batch rejected.") from None

    # No event properties, identities or IDs are written to logs or storage.
    logger.info("Telemetry capture accepted event_count=%d", len(batch.events))
    return {"accepted": len(batch.events)}
