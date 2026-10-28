import csv
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from packages.shared.incidents import TRANSITIONS
from scripts.seed_incidents import seed_incidents
from services.api import incidents as store
from services.api.auth import get_current_user
from services.api.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "incidents.sqlite3")
    app.dependency_overrides[get_current_user] = lambda: object()
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.pop(get_current_user, None)


def payload(**changes):
    return {"title": "Carrier delay", "description": "Shipment delayed in Los Angeles.", "status": "open", "category": "carrier_issue", "origin": "branch", "branch": "la_warehouse", **changes}


def test_seed_exact_mapping_and_idempotency(client):
    source = Path(__file__).resolve().parents[1] / "scripts" / "incidents-trackflow.csv"
    assert seed_incidents(source) == {"inserted": 95, "skipped": 0, "invalid": 5}
    assert seed_incidents(source) == {"inserted": 0, "skipped": 95, "invalid": 5}
    summary = client.get("/api/incidents/summary").json()
    assert summary["total"] == 95
    assert summary["by_status"] == {"open": 29, "in_progress": 0, "resolved": 52, "discarded": 14}
    assert summary["by_category"] == {"lost_parcel": 14, "carrier_issue": 45, "delivery_failure": 19, "returns_issue": 17, "inventory_discrepancy": 0, "warehouse_incident": 0, "system_failure": 0, "client_complaint": 0, "other": 0}
    assert summary["by_origin"] == {"customer": 95, "branch": 0, "internal": 0}
    assert summary["by_branch"]["la_office"] == 50
    assert summary["by_branch"]["zaragoza_office"] == 45
    record = client.get("/api/incidents").json()[0]
    assert record["created_at"] == record["updated_at"]
    assert datetime.fromisoformat(record["created_at"]).hour == 0
    assert "incident_id" not in record and "customer_email" not in record


def test_empty_summary_and_list(client):
    assert client.get("/api/incidents").json() == []
    summary = client.get("/api/incidents/summary").json()
    assert summary["total"] == 0
    assert all(value == 0 for key, counts in summary.items() if key != "total" for value in counts.values())


def test_create_detail_filters_and_missing(client):
    response = client.post("/api/incidents", json=payload())
    assert response.status_code == 201
    record = response.json()
    assert client.get(f"/api/incidents/{record['id']}").json() == record
    assert len(client.get("/api/incidents?status=open&origin=branch&branch=la_warehouse&category=carrier_issue").json()) == 1
    assert client.get("/api/incidents?branch=central").json() == []
    assert client.get("/api/incidents/999999").status_code == 404
    assert client.patch("/api/incidents/999999/status", json={"status": "discarded"}).status_code == 404


@pytest.mark.parametrize("field,value", [("title", "  "), ("description", "  "), ("category", "invalid"), ("status", "invalid"), ("origin", "invalid"), ("branch", "invalid")])
def test_field_errors(client, field, value):
    response = client.post("/api/incidents", json=payload(**{field: value}))
    assert response.status_code == 400
    assert field in response.json()["errors"]


def test_required_fields_and_invalid_filter(client):
    response = client.post("/api/incidents", json={})
    assert response.status_code == 400
    assert set(response.json()["errors"]) == {"title", "description", "category", "status", "origin", "branch"}
    assert client.get("/api/incidents?status=wrong").status_code == 400


@pytest.mark.parametrize("before,after", [(before, after) for before in TRANSITIONS for after in TRANSITIONS])
def test_lifecycle(client, before, after):
    record = client.post("/api/incidents", json=payload(status=before)).json()
    response = client.patch(f"/api/incidents/{record['id']}/status", json={"status": after})
    allowed = after in TRANSITIONS[before]
    assert response.status_code == (200 if allowed else 400)
    current = client.get(f"/api/incidents/{record['id']}").json()
    assert current["status"] == (after if allowed else before)
    if allowed:
        assert current["updated_at"] >= record["updated_at"]


def test_unexpected_error_is_generic(client, monkeypatch):
    def fail():
        raise RuntimeError("Private database failure")
    monkeypatch.setattr(store, "summary", fail)
    response = client.get("/api/incidents/summary")
    assert response.status_code == 500
    assert "Private" not in response.text
    assert response.json()["message"] == "Something went wrong. Please try again."


def test_seed_preserves_description_and_skips_bad_dates(client, tmp_path, capsys):
    source = tmp_path / "historical.csv"
    row = {
        "date": "2026-08-01", "country": "US", "carrier": "UPS", "tracking_number": "TRACK123456",
        "category": "DAMAGE", "description": "  Historical description with spaces.  ", "status": "OPEN",
        "customer_email": "private@example.test", "satisfaction_score": "",
    }
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
        writer.writerow(row)
        writer.writerow({**row, "date": "not-a-date"})
    assert seed_incidents(source) == {"inserted": 1, "skipped": 1, "invalid": 1}
    record = client.get("/api/incidents").json()[0]
    assert record["title"] == row["description"][:120].strip()
    assert record["description"] == row["description"]
    assert record["category"] == "carrier_issue"
    assert "private@example.test" not in capsys.readouterr().out


def test_bearer_authentication_required(client):
    app.dependency_overrides.pop(get_current_user, None)
    assert client.get("/api/incidents").status_code == 401
    assert client.post("/api/incidents", json=payload()).status_code == 401


def test_error_contract_outside_manager(client):
    response = client.get("/suppliers?category=unavailable")
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["message"]
    response = client.post("/suppliers", json={})
    assert response.status_code == 422
    assert "name" in response.json()["errors"]
    app.dependency_overrides.pop(get_current_user, None)
    response = client.get("/suppliers")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_analysis_unexpected_failure_does_not_leak(client, monkeypatch):
    def fail(_):
        raise RuntimeError("PRIVATE_AUDIT_MARKER")
    monkeypatch.setattr("services.api.main.analyze_incidents_text", fail)
    response = client.post("/api/incidents/analyze", files={"file": ("audit.csv", b"x,y\n1,2\n", "text/csv")})
    assert response.status_code == 500
    assert "PRIVATE_AUDIT_MARKER" not in response.text
    assert response.json()["message"] == "Something went wrong. Please try again."


def test_wrong_csv_headers_return_safe_error(client):
    response = client.post("/api/incidents/analyze", files={"file": ("audit.csv", b"wrong,columns\nx,y\n", "text/csv")})
    assert response.status_code == 400
    assert "CSV" in response.json()["message"]