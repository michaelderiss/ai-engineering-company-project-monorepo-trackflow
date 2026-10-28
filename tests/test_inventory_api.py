from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from services.api import inventory_database
from services.api.inventory_database import EXIT_SEED, ENTRY_SEED, SKU_SEED
from services.api.inventory_models import StockEntry, StockExit


def _sku_by_code(client, code: str) -> dict:
    response = client.get("/inventory/products")
    assert response.status_code == 200
    return next(item for item in response.json() if item["sku"] == code)


def test_seeded_inventory_has_briefing_records_and_computed_stock(client):
    response = client.get("/inventory/products")

    assert response.status_code == 200
    products = response.json()
    assert len(products) == len(SKU_SEED) == 6
    assert len(ENTRY_SEED) == 4
    assert len(EXIT_SEED) == 3
    sneaker_la = next(item for item in products if item["sku"] == "CLT-SNK-W-42")
    sneaker_zgz = next(item for item in products if item["sku"] == "CLT-SNK-W-42-Z")
    assert (sneaker_la["warehouse"], sneaker_la["current_stock"]) == ("LA", 25)
    assert (sneaker_zgz["warehouse"], sneaker_zgz["current_stock"]) == ("ZGZ", 14)
    assert all("current_stock" in item for item in products)


def test_inventory_seed_is_idempotent(client):
    assert inventory_database.seed_inventory_data() == {
        "skus": 0,
        "stock_entries": 0,
        "stock_exits": 0,
    }


def test_get_product_returns_stock_for_its_warehouse(client):
    product = _sku_by_code(client, "TEC-EAR-001")

    response = client.get(f"/inventory/products/{product['id']}")

    assert response.status_code == 200
    assert response.json()["current_stock"] == 11
    assert response.json()["warehouse"] == "LA"


def test_create_product_requires_authentication(client):
    response = client.post(
        "/inventory/products",
        json={
            "name": "Test product",
            "sku": "TEST-001",
            "client_name": "Test client",
            "category": "fashion",
            "warehouse": "LA",
        },
    )

    assert response.status_code == 401


def test_create_product_returns_sku_with_zero_computed_stock(client, auth_headers):
    headers, _account = auth_headers
    response = client.post(
        "/inventory/products",
        headers=headers,
        json={
            "name": "Test product",
            "sku": "TEST-001",
            "client_name": "Test client",
            "category": "fashion",
            "warehouse": "LA",
        },
    )

    assert response.status_code == 201
    assert response.json()["current_stock"] == 0
    assert response.json()["warehouse"] == "LA"


def test_create_product_rejects_duplicate_sku_code(client, auth_headers):
    headers, _account = auth_headers
    response = client.post(
        "/inventory/products",
        headers=headers,
        json={
            "name": "Duplicate product",
            "sku": "CLT-SNK-W-42",
            "client_name": "PureStep Footwear",
            "category": "fashion",
            "warehouse": "LA",
        },
    )

    assert response.status_code == 409


def test_stock_movement_writes_require_authentication(client):
    product = _sku_by_code(client, "TEC-EAR-001")
    inbound = client.post(
        "/inventory/orders/inbound",
        json={
            "sku_id": product["id"],
            "quantity": 1,
            "reference": "PO-UNAUTH-001",
            "warehouse": "LA",
        },
    )
    outbound = client.post(
        "/inventory/orders/outbound",
        json={
            "sku_id": product["id"],
            "quantity": 1,
            "exit_type": "dispatch",
            "tracking_number": "TRACK-UNAUTH-001",
            "warehouse": "LA",
        },
    )

    assert inbound.status_code == 401
    assert outbound.status_code == 401


def test_inbound_order_increases_computed_stock_and_records_user(client, auth_headers):
    headers, account = auth_headers
    product = _sku_by_code(client, "TEC-EAR-001")
    response = client.post(
        "/inventory/orders/inbound",
        headers=headers,
        json={
            "sku_id": product["id"],
            "quantity": 5,
            "reference": "PO-TEST-1001",
            "warehouse": "LA",
        },
    )

    assert response.status_code == 201
    assert response.json()["user_uuid"] == str(account["user"]["id"])
    assert _sku_by_code(client, "TEC-EAR-001")["current_stock"] == 16


def test_inbound_order_rejects_a_different_sku_warehouse(client, auth_headers):
    headers, _account = auth_headers
    product = _sku_by_code(client, "TEC-EAR-001")
    response = client.post(
        "/inventory/orders/inbound",
        headers=headers,
        json={
            "sku_id": product["id"],
            "quantity": 5,
            "reference": "PO-TEST-1002",
            "warehouse": "ZGZ",
        },
    )

    assert response.status_code == 400


def test_outbound_order_cannot_reduce_stock_below_zero(client, auth_headers):
    headers, _account = auth_headers
    product = _sku_by_code(client, "TEC-EAR-001")
    before = product["current_stock"]
    response = client.post(
        "/inventory/orders/outbound",
        headers=headers,
        json={
            "sku_id": product["id"],
            "quantity": before + 1,
            "exit_type": "dispatch",
            "tracking_number": "TRACK-TOO-MANY",
            "warehouse": "LA",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        f"Insufficient stock for SKU '{product['sku']}'. Available: {before}, "
        f"requested: {before + 1}."
    )
    assert _sku_by_code(client, "TEC-EAR-001")["current_stock"] == before


def test_dispatch_requires_tracking_number(client, auth_headers):
    headers, _account = auth_headers
    product = _sku_by_code(client, "TEC-EAR-001")
    response = client.post(
        "/inventory/orders/outbound",
        headers=headers,
        json={
            "sku_id": product["id"],
            "quantity": 1,
            "exit_type": "dispatch",
            "warehouse": "LA",
        },
    )

    assert response.status_code == 422


def test_loss_requires_null_tracking_number(client, auth_headers):
    headers, _account = auth_headers
    product = _sku_by_code(client, "TEC-EAR-001")
    response = client.post(
        "/inventory/orders/outbound",
        headers=headers,
        json={
            "sku_id": product["id"],
            "quantity": 1,
            "exit_type": "loss",
            "tracking_number": "NOT-ALLOWED",
            "warehouse": "LA",
        },
    )

    assert response.status_code == 422


def test_valid_loss_decreases_stock_without_tracking_number(client, auth_headers):
    headers, _account = auth_headers
    product = _sku_by_code(client, "CLT-SNK-W-42-Z")
    response = client.post(
        "/inventory/orders/outbound",
        headers=headers,
        json={
            "sku_id": product["id"],
            "quantity": 1,
            "exit_type": "loss",
            "tracking_number": None,
            "warehouse": "ZGZ",
        },
    )

    assert response.status_code == 201
    assert response.json()["tracking_number"] is None
    assert _sku_by_code(client, "CLT-SNK-W-42-Z")["current_stock"] == 13


def test_movement_foreign_keys_are_enforced_by_database(client):
    invalid_entry = StockEntry(
        sku_id=999999,
        quantity=1,
        reference="PO-INVALID-SKU",
        warehouse="LA",
        user_uuid="test-user",
    )
    invalid_exit = StockExit(
        sku_id=999999,
        quantity=1,
        exit_type="loss",
        tracking_number=None,
        warehouse="LA",
        user_uuid="test-user",
    )

    with Session(inventory_database.engine) as session:
        for movement in (invalid_entry, invalid_exit):
            session.add(movement)
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()


def test_valid_outbound_and_orders_list_include_sku_details(client, auth_headers):
    headers, account = auth_headers
    product = _sku_by_code(client, "TEC-EAR-001")
    response = client.post(
        "/inventory/orders/outbound",
        headers=headers,
        json={
            "sku_id": product["id"],
            "quantity": 2,
            "exit_type": "dispatch",
            "tracking_number": "TRACK-VALID-1001",
            "warehouse": "LA",
        },
    )

    assert response.status_code == 201
    assert response.json()["user_uuid"] == str(account["user"]["id"])
    assert _sku_by_code(client, "TEC-EAR-001")["current_stock"] == 9

    orders = client.get("/inventory/orders")
    assert orders.status_code == 200
    created = next(
        item for item in orders.json() if item.get("tracking_number") == "TRACK-VALID-1001"
    )
    assert created["order_type"] == "outbound"
    assert created["sku"]["sku"] == "TEC-EAR-001"
    assert created["warehouse"] == "LA"