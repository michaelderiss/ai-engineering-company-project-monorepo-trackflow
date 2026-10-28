from __future__ import annotations

from uuid import uuid4
import pytest

from fastapi.testclient import TestClient

from services.api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_identity_storage(tmp_path, monkeypatch):
    monkeypatch.setattr("services.api.database.USER_DB_PATH", tmp_path / "users.json")
    monkeypatch.setattr("services.api.database.DB_PATH", tmp_path / "suppliers.json")


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


def test_forgot_password_does_not_enumerate_users(monkeypatch):
    email = _make_email("recovery")
    client.post("/users", json={"email": email, "password": "StrongPass123!"})
    deliveries: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "services.api.routes.auth.send_password_reset_email",
        lambda recipient, reset_url: deliveries.append((recipient, reset_url)),
    )

    existing = client.post("/auth/forgot-password", json={"email": email})
    unknown = client.post(
        "/auth/forgot-password",
        json={"email": _make_email("unknown")},
    )

    assert existing.status_code == unknown.status_code == 200
    assert existing.json() == unknown.json()
    assert deliveries[0][0] == email
    assert "/reset-password?token=" in deliveries[0][1]


def test_reset_password_token_is_single_use(monkeypatch):
    email = _make_email("reset")
    old_password = "OldPassword123!"
    new_password = "NewPassword123!"
    client.post("/users", json={"email": email, "password": old_password})
    deliveries: list[str] = []
    monkeypatch.setattr(
        "services.api.routes.auth.send_password_reset_email",
        lambda recipient, reset_url: deliveries.append(reset_url),
    )

    forgot = client.post("/auth/forgot-password", json={"email": email})
    assert forgot.status_code == 200
    token = deliveries[0].split("token=", 1)[1]

    reset = client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": new_password},
    )
    replay = client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "AnotherPassword123!"},
    )

    assert reset.status_code == 200, reset.text
    assert replay.status_code == 400
    assert client.post(
        "/auth/login",
        data={"username": email, "password": old_password},
    ).status_code == 401
    assert client.post(
        "/auth/login",
        data={"username": email, "password": new_password},
    ).status_code == 200


def test_expired_reset_token_is_rejected(monkeypatch):
    email = _make_email("expired")
    client.post("/users", json={"email": email, "password": "StrongPass123!"})
    deliveries: list[str] = []
    monkeypatch.setattr(
        "services.api.routes.auth.send_password_reset_email",
        lambda recipient, reset_url: deliveries.append(reset_url),
    )
    monkeypatch.setattr("services.api.auth.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES", -1)

    client.post("/auth/forgot-password", json={"email": email})
    token = deliveries[0].split("token=", 1)[1]
    response = client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "NewPassword123!"},
    )

    assert response.status_code == 400


def test_change_password_requires_current_password():
    email = _make_email("change")
    old_password = "OldPassword123!"
    new_password = "NewPassword123!"
    created = client.post("/users", json={"email": email, "password": old_password})
    token = client.post(
        "/auth/login",
        data={"username": email, "password": old_password},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    wrong_current = client.post(
        "/auth/change-password",
        headers=headers,
        json={"current_password": "WrongPassword!", "new_password": new_password},
    )
    changed = client.post(
        "/auth/change-password",
        headers=headers,
        json={"current_password": old_password, "new_password": new_password},
    )

    assert created.status_code == 201
    assert wrong_current.status_code == 400
    assert changed.status_code == 200
    assert client.post(
        "/auth/login",
        data={"username": email, "password": new_password},
    ).status_code == 200
