from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.telemetry import analysis


def _row(event_type: str, timestamp: str, properties: dict) -> dict:
    return {
        "event_type": event_type,
        "event_timestamp": timestamp,
        "properties": properties,
    }


def test_metrics_group_timestamps_in_utc_and_return_serializable_records(monkeypatch):
    events = [
        _row("navigation_page_viewed", "2026-01-01T23:30:00-02:00", {"route": "/"}),
        _row("api_latency_recorded", "2026-01-02T01:30:00+00:00", {
            "route": "/inventory/products", "method": "GET", "status_code": 503,
            "duration_ms": 200.0,
        }),
        _row("api_latency_recorded", "2026-01-02T05:30:00+04:00", {
            "route": "/inventory/products", "method": "GET", "status_code": 200,
            "duration_ms": 100.0,
        }),
    ]
    calls = []

    def fake_read(event_types, start, end):
        calls.append((event_types, start, end))
        return [event for event in events if event["event_type"] in event_types]

    monkeypatch.setattr(analysis, "_read_events", fake_read)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 3, tzinfo=timezone.utc)

    volume = analysis.events_per_day(start, end)
    error_rate = analysis.api_error_rate_by_day(start, end)
    latency = analysis.api_latency_by_day_route(start, end)

    assert volume == [{"day": "2026-01-02", "event_count": 3}]
    assert error_rate == [{
        "day": "2026-01-02", "request_count": 2, "error_count": 1, "error_rate": 0.5,
    }]
    assert latency == [{
        "day": "2026-01-02", "route": "/inventory/products", "request_count": 2,
        "mean_duration_ms": 150.0, "p95_duration_ms": 195.0,
    }]
    assert calls[0] == (analysis.ALL_EVENT_TYPES, start, end)


def test_report_endpoint_resolves_default_period_and_uses_cache(client, admin_account, monkeypatch):
    from services.api import telemetry as telemetry_module

    telemetry_module.report_cache.clear()
    calls = []

    def build(start, end):
        calls.append((start, end))
        return {"events_per_day": [{"day": "2026-01-01", "event_count": 1}]}

    monkeypatch.setattr("services.telemetry.analysis.build_technical_report", build)
    headers = admin_account["headers"]
    first = client.get("/api/telemetry/report?from=2026-01-01T00:00:00Z&to=2026-01-02T00:00:00Z", headers=headers)
    second = client.get("/api/telemetry/report?from=2026-01-01T00:00:00Z&to=2026-01-02T00:00:00Z", headers=headers)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["period"] == {
        "from": "2026-01-01T00:00:00+00:00", "to": "2026-01-02T00:00:00+00:00",
    }
    assert len(calls) == 1
    assert calls[0][0].tzinfo == calls[0][1].tzinfo == timezone.utc
    telemetry_module.report_cache.clear()


def test_report_rejects_invalid_or_naive_period(client, admin_account):
    headers = admin_account["headers"]
    assert client.get("/api/telemetry/report?from=not-a-date", headers=headers).status_code == 422
    assert client.get("/api/telemetry/report?from=2026-01-01T00:00:00", headers=headers).status_code == 422
    assert client.get(
        "/api/telemetry/report?from=2026-01-02T00:00:00Z&to=2026-01-01T00:00:00Z", headers=headers
    ).status_code == 422


def test_report_requires_manager_or_admin(client, create_user, monkeypatch):
    account = create_user()
    response = client.post(
        "/auth/login", data={"username": account["email"], "password": account["password"]}
    )
    token = response.json()["access_token"]
    denied = client.get("/api/telemetry/report", headers={"Authorization": f"Bearer {token}"})
    assert denied.status_code == 403


def test_report_default_period_is_seven_days(client, admin_account, monkeypatch):
    from services.api import telemetry as telemetry_module

    telemetry_module.report_cache.clear()
    observed = []
    monkeypatch.setattr(
        "services.telemetry.analysis.build_technical_report",
        lambda start, end: observed.append((start, end)) or {},
    )
    first = client.get("/api/telemetry/report", headers=admin_account["headers"])
    second = client.get("/api/telemetry/report", headers=admin_account["headers"])
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert len(observed) == 1
    assert observed[0][1] - observed[0][0] == timedelta(days=7)
    assert observed[0][1].second == observed[0][1].microsecond == 0
    telemetry_module.report_cache.clear()