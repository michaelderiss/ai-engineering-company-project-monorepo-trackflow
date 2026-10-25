from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from services.api.main import app

client = TestClient(app)


def _make_email(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}@trackflow.test"


def test_user_and_login_flow():
    email = _make_email("user")
    password = "StrongPass123!"

    response = client.post(
        "/users",
        json={
            "email": email,
            "password": password,
            "role": "manager",
            "profile": {"display_name": "Alex Manager", "phone": "555-1000", "address": "Los Angeles"},
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["email"] == email
    assert payload["hashed_password"] != password
    assert payload["role"] == "manager"
    assert payload["profile"]["display_name"] == "Alex Manager"

    login = client.post(
        "/auth/login",
        data={"username": email, "password": password},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    assert token

    protected = client.get(f"/users/{payload['id']}", headers={"Authorization": f"Bearer {token}"})
    assert protected.status_code == 200, protected.text
    assert protected.json()["email"] == email

    other_email = _make_email("other")
    other_user = client.post(
        "/users",
        json={
            "email": other_email,
            "password": "OtherPass123!",
            "role": "user",
        },
    )
    assert other_user.status_code == 201, other_user.text
    other_id = other_user.json()["id"]

    forbidden = client.get(f"/users/{other_id}", headers={"Authorization": f"Bearer {token}"})
    assert forbidden.status_code == 403, forbidden.text

    missing = client.get("/users/999999", headers={"Authorization": f"Bearer {token}"})
    assert missing.status_code == 404, missing.text

    unauthenticated = client.get("/users/999999")
    assert unauthenticated.status_code == 401, unauthenticated.text
