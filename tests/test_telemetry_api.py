from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from services.api import telemetry as telemetry_module


@pytest.fixture(autouse=True)
def mock_telemetry_storage(monkeypatch):
    monkeypatch.setenv("TELEMETRY_ENABLED", "true")
    monkeypatch.setattr(telemetry_module, "persist_events", lambda _events: None)

def _event(event_type: str = "navigation_page_viewed", properties: dict | None = None) -> dict:
    return {
        "eventId": str(uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sessionId": str(uuid4()),
        "userId": str(uuid4()),
        "event_type": event_type,
        "schemaVersion": "1.0.0",
        "requestId": str(uuid4()),
        "properties": properties if properties is not None else {"route": "/"},
    }


def test_accepts_valid_event_batch(client):
    response = client.post("/api/telemetry/events", json={"events": [_event()]})
    assert response.status_code == 202
    assert response.json() == {"accepted": 1}


def test_maps_validated_event_to_supabase_columns():
    event = telemetry_module.TelemetryEvent.parse_obj(_event())

    row = telemetry_module._storage_rows([event])[0]

    assert set(row) == {
        "event_id", "event_type", "event_timestamp", "properties",
        "session_id", "user_id", "schema_version", "request_id",
    }
    assert row["event_id"] == event.eventId
    assert row["event_timestamp"] == event.timestamp
    assert row["session_id"] == event.sessionId
    assert row["user_id"] == event.userId
    assert row["request_id"] == event.requestId
    assert row["properties"] == '{"route": "/"}'


def test_does_not_acknowledge_batch_when_persistence_fails(client, monkeypatch):
    monkeypatch.setattr(
        telemetry_module,
        "persist_events",
        lambda _events: (_ for _ in ()).throw(RuntimeError("sensitive db detail")),
    )

    response = client.post("/api/telemetry/events", json={"events": [_event()]})

    assert response.status_code == 503
    assert response.json() == {"detail": "Telemetry batch could not be stored."}
    assert "sensitive db detail" not in response.text


def test_rejects_unknown_properties(client):
    response = client.post(
        "/api/telemetry/events",
        json={"events": [_event(properties={"route": "/", "email": "private@example.test"})]},
    )
    assert response.status_code == 422
    assert "private@example.test" not in response.text


def test_rejects_wrong_event_properties(client):
    response = client.post(
        "/api/telemetry/events",
        json={"events": [_event("login_failed", {"route": "/"})]},
    )
    assert response.status_code == 422


def test_rejects_unhashable_enum_value_without_server_error(client):
    response = client.post(
        "/api/telemetry/events",
        json={"events": [_event("login_failed", {"reason": ["invalid_credentials"]})]},
    )
    assert response.status_code == 422


def test_rejects_timestamp_without_timezone(client):
    event = _event()
    event["timestamp"] = "2026-11-09T12:00:00"
    response = client.post("/api/telemetry/events", json={"events": [event]})
    assert response.status_code == 422


def test_rejects_batches_over_event_limit(client):
    response = client.post("/api/telemetry/events", json={"events": [_event() for _ in range(21)]})
    assert response.status_code == 422


def test_disables_receiver_with_environment_toggle(client, monkeypatch):
    monkeypatch.setenv("TELEMETRY_ENABLED", "false")
    response = client.post("/api/telemetry/events", json={"events": [_event()]})
    assert response.status_code == 404


def test_accepts_consistent_discrepancy_math(client):
    event = _event("inventory_discrepancy_detected", {
        "warehouse": "zaragoza", "client_id": "client_1", "product_id": "SKU-1",
        "product_category": "fashion", "quantity": 2, "system_quantity": 8,
        "physical_quantity": 10,
    })
    response = client.post("/api/telemetry/events", json={"events": [event]})
    assert response.status_code == 202


def test_rejects_inconsistent_discrepancy_math(client):
    event = _event("inventory_discrepancy_detected", {
        "warehouse": "zaragoza", "client_id": "client_1", "product_id": "SKU-1",
        "product_category": "fashion", "quantity": 2, "system_quantity": 8,
        "physical_quantity": 9,
    })
    response = client.post("/api/telemetry/events", json={"events": [event]})
    assert response.status_code == 422
def test_rejects_inconsistent_discrepancy_math(client):
    event = _event("inventory_discrepancy_detected", {
        "warehouse": "zaragoza", "client_id": "client_1", "product_id": "SKU-1",
        "product_category": "fashion", "quantity": 2, "system_quantity": 8,
        "physical_quantity": 9,
    })
    response = client.post("/api/telemetry/events", json={"events": [event]})
    assert response.status_code == 422
