import logging

import pytest

from services.api import cache


def test_ttl_expiry_and_clear(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(cache, "monotonic", lambda: clock[0])
    values = iter([b"first", b"expired", b"cleared"])
    cached = cache.TTLCache(15, 2, 100)
    assert cached.get_or_load("key", lambda: next(values)) == b"first"
    clock[0] = 114.9
    assert cached.get_or_load("key", lambda: next(values)) == b"first"
    clock[0] = 115
    assert cached.get_or_load("key", lambda: next(values)) == b"expired"
    cached.clear()
    assert cached.get_or_load("key", lambda: next(values)) == b"cleared"


def test_cache_is_bounded_and_does_not_cache_failures():
    cached = cache.TTLCache(15, 1, 3)
    cached.get_or_load("one", lambda: b"one")
    cached.get_or_load("two", lambda: b"two")
    assert cached.get_or_load("one", lambda: b"new") == b"new"
    assert cached.get_or_load("large", lambda: b"large") == b"large"
    assert cached.get_or_load("large", lambda: b"new") == b"new"
    with pytest.raises(ValueError):
        cached.get_or_load("bad", lambda: (_ for _ in ()).throw(ValueError("failure")))
    assert cached.get_or_load("bad", lambda: b"ok") == b"ok"


def test_catalog_hit_and_write_invalidation(client, auth_headers, monkeypatch):
    from services.api.routes import inventory
    original = inventory.list_skus_with_stock
    calls = []
    monkeypatch.setattr(inventory, "list_skus_with_stock", lambda session: (calls.append(1), original(session))[1])
    headers, _ = auth_headers
    first = client.get("/inventory/products")
    assert first.headers["cache-control"] == "no-store"
    assert client.get("/inventory/products").json() == first.json()
    assert len(calls) == 1
    sku = first.json()[0]
    response = client.post("/inventory/orders/inbound", headers=headers, json={
        "sku_id": sku["id"], "quantity": 5, "reference": "CACHE-RECEIPT", "warehouse": sku["warehouse"],
    })
    assert response.status_code == 201
    updated = next(row for row in client.get("/inventory/products").json() if row["id"] == sku["id"])
    assert updated["current_stock"] == sku["current_stock"] + 5
    assert len(calls) == 2
    assert client.post("/inventory/orders/outbound", headers=headers, json={
        "sku_id": sku["id"], "quantity": 1, "exit_type": "loss", "warehouse": sku["warehouse"],
    }).status_code == 201
    updated = next(row for row in client.get("/inventory/products").json() if row["id"] == sku["id"])
    assert updated["current_stock"] == sku["current_stock"] + 4
    assert len(calls) == 3
    assert client.post("/inventory/products", headers=headers, json={
        "name": "New serum", "sku": "CACHE-SERUM", "client_name": "Synthetic brand",
        "category": "cosmetics", "warehouse": "ZGZ",
    }).status_code == 201
    assert len(client.get("/inventory/products").json()) == len(first.json()) + 1
    assert len(calls) == 4


def test_summary_scoped_and_invalidated(client, auth_headers, create_user, monkeypatch):
    from services.api import incidents
    from services.api.auth import create_access_token
    original = incidents.summary
    calls = []
    monkeypatch.setattr(incidents, "summary", lambda: (calls.append(1), original())[1])
    headers, _ = auth_headers
    assert client.get("/api/incidents/summary", headers=headers).json()["total"] == 0
    client.get("/api/incidents/summary", headers=headers)
    assert len(calls) == 1
    assert client.get("/api/incidents/summary").status_code == 401
    account = create_user()
    other = {"Authorization": f"Bearer {create_access_token({'sub': str(account['user']['id'])})}"}
    client.get("/api/incidents/summary", headers=other)
    assert len(calls) == 2
    created = client.post("/api/incidents", headers=headers, json={
        "title": "Delay", "description": "Synthetic delivery delay", "category": "carrier_issue",
        "status": "open", "origin": "branch", "branch": "la_office",
    })
    assert created.status_code == 201
    assert client.get("/api/incidents/summary", headers=headers).json()["total"] == 1
    assert client.patch(f"/api/incidents/{created.json()['id']}/status", headers=headers, json={"status": "in_progress"}).status_code == 200
    assert client.get("/api/incidents/summary", headers=headers).json()["by_status"]["in_progress"] == 1
    assert len(calls) == 4


def test_request_timing_omits_query_values(client, caplog):
    with caplog.at_level(logging.INFO, logger="api.timing"):
        response = client.get("/inventory/products?secret=never-log-this")
    assert response.status_code == 200
    messages = [record.getMessage() for record in caplog.records if record.name == "api.timing"]
    assert len(messages) == 1
    assert "GET /inventory/products status=200 duration_ms=" in messages[0]
    assert "never-log-this" not in messages[0]