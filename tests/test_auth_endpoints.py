"""Endpoint-level tests for the authentication routes (services/api/routes/auth.py).

These tests drive the real HTTP endpoints through TestClient and assert on the
*business outcome* (was a token issued? was the password changed? was an invalid
token rejected?) — not on HTTP plumbing or serialisation. The pure unit-level
logic is covered separately in test_auth_token.py / test_auth_password.py.
"""

from __future__ import annotations

from datetime import timedelta
from urllib.parse import unquote

import pytest
from freezegun import freeze_time

from services.api import auth as auth_module
from services.api.database import delete_user, update_user
from services.api.models import UserUpdate


class TestLoginEndpoint:
    def test_happy_path_returns_bearer_token(self, client, create_user):
        account = create_user()
        response = client.post(
            "/auth/login",
            data={"username": account["email"], "password": account["password"]},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]
        # The token must actually represent this user — decode it and check the id.
        token_data = auth_module.decode_access_token(body["access_token"])
        assert token_data.user_id == account["user"]["id"]

    def test_login_works_for_user_with_profile(self, client, create_user):
        account = create_user(
            role="manager",
            profile={"display_name": "Alex Manager", "phone": "555-1000", "address": "Los Angeles"},
        )
        response = client.post(
            "/auth/login",
            data={"username": account["email"], "password": account["password"]},
        )
        assert response.status_code == 200, response.text

    def test_wrong_password_is_rejected(self, client, create_user):
        account = create_user()
        response = client.post(
            "/auth/login",
            data={"username": account["email"], "password": "WrongPassword!"},
        )
        assert response.status_code == 401

    def test_unknown_email_is_rejected_without_enumeration(self, client, make_email):
        """Unknown and wrong-password logins must return the identical response."""
        known = client.post(
            "/auth/login",
            data={"username": make_email("nobody"), "password": "Whatever123!"},
        )
        assert known.status_code == 401
        # The message must not reveal whether the email exists.
        assert known.json()["detail"] == "Incorrect email or password"

    def test_inactive_user_cannot_login(self, client, create_user):
        account = create_user()
        update_user(account["user"]["id"], UserUpdate(is_active=False))
        response = client.post(
            "/auth/login",
            data={"username": account["email"], "password": account["password"]},
        )
        assert response.status_code == 401


class TestMeEndpoint:
    def test_happy_path_returns_current_user(self, client, create_user):
        account = create_user()
        token = client.post(
            "/auth/login",
            data={"username": account["email"], "password": account["password"]},
        ).json()["access_token"]
        response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["email"] == account["email"]
        assert response.json()["id"] == account["user"]["id"]

    def test_me_works_for_user_with_profile(self, client, create_user):
        account = create_user(profile={"display_name": "Sam User"})
        token = client.post(
            "/auth/login",
            data={"username": account["email"], "password": account["password"]},
        ).json()["access_token"]
        response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["profile"]["display_name"] == "Sam User"

    def test_missing_token_is_rejected(self, client):
        assert client.get("/auth/me").status_code == 401

    def test_malformed_token_is_rejected(self, client):
        response = client.get("/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
        assert response.status_code == 401

    def test_token_for_deleted_user_is_rejected(self, client, create_user):
        account = create_user()
        token = client.post(
            "/auth/login",
            data={"username": account["email"], "password": account["password"]},
        ).json()["access_token"]
        assert delete_user(account["user"]["id"]) is True
        assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401

    def test_token_for_inactive_user_is_rejected(self, client, create_user):
        account = create_user()
        token = client.post(
            "/auth/login",
            data={"username": account["email"], "password": account["password"]},
        ).json()["access_token"]
        update_user(account["user"]["id"], UserUpdate(is_active=False))
        response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
        assert "inactive" in response.json()["detail"].lower()


class TestForgotPasswordEndpoint:
    @pytest.fixture
    def capture_reset_delivery(self, monkeypatch):
        """Intercept email delivery and return the reset URL that was produced."""
        deliveries: list[str] = []

        def fake_send(recipient, reset_url):
            deliveries.append(reset_url)

        monkeypatch.setattr("services.api.routes.auth.send_password_reset_email", fake_send)
        return deliveries

    def test_happy_path_schedules_reset_email(self, client, create_user, capture_reset_delivery):
        account = create_user()
        response = client.post("/auth/forgot-password", json={"email": account["email"]})
        assert response.status_code == 200
        assert len(capture_reset_delivery) == 1
        assert "reset-password?token=" in capture_reset_delivery[0]

    def test_email_delivery_failure_does_not_break_request(self, client, create_user, monkeypatch):
        """A failing email provider must never fail the forgot-password request.

        The route schedules delivery in a background task and swallows delivery
        errors, so the user still gets the generic "check your inbox" response
        (and no internal error details leak).
        """
        account = create_user()

        def failing_send(recipient, reset_url):
            raise OSError("provider down")

        monkeypatch.setattr("services.api.routes.auth.send_password_reset_email", failing_send)
        response = client.post("/auth/forgot-password", json={"email": account["email"]})
        assert response.status_code == 200
        assert "message" in response.json()

    def test_unknown_email_gets_identical_generic_response(
        self, client, create_user, make_email, capture_reset_delivery
    ):
        account = create_user()
        known = client.post("/auth/forgot-password", json={"email": account["email"]})
        unknown = client.post("/auth/forgot-password", json={"email": make_email("ghost")})
        assert known.status_code == unknown.status_code == 200
        # Anti-enumeration: both responses are byte-for-byte identical.
        assert known.json() == unknown.json()
        # And no email is scheduled for the unknown address.
        assert len(capture_reset_delivery) == 1

    def test_too_short_email_is_rejected(self, client):
        """ForgotPasswordRequest enforces a minimum length; shorter input is a 4xx.

        (A longer, malformed-looking address is intentionally accepted and given
        the generic response to avoid user enumeration — asserted above.)
        """
        response = client.post("/auth/forgot-password", json={"email": "ab"})
        assert response.status_code in (400, 422)


class TestResetPasswordEndpoint:
    def _obtain_token(self, client, email, capture_reset_delivery):
        response = client.post("/auth/forgot-password", json={"email": email})
        assert response.status_code == 200
        assert capture_reset_delivery
        return unquote(capture_reset_delivery[0].split("token=", 1)[1])

    @pytest.fixture
    def capture_reset_delivery(self, monkeypatch):
        deliveries: list[str] = []

        def fake_send(recipient, reset_url):
            deliveries.append(reset_url)

        monkeypatch.setattr("services.api.routes.auth.send_password_reset_email", fake_send)
        return deliveries

    def test_happy_path_resets_password(self, client, create_user, capture_reset_delivery):
        account = create_user()
        token = self._obtain_token(client, account["email"], capture_reset_delivery)
        response = client.post(
            "/auth/reset-password",
            json={"token": token, "new_password": "NewPassword123!"},
        )
        assert response.status_code == 200
        # Old password must no longer work; the new one must.
        assert client.post(
            "/auth/login",
            data={"username": account["email"], "password": account["password"]},
        ).status_code == 401
        assert client.post(
            "/auth/login",
            data={"username": account["email"], "password": "NewPassword123!"},
        ).status_code == 200

    def test_expired_token_is_rejected(self, client, create_user, capture_reset_delivery, frozen_now):
        """REG RESSION GUARD: an expired reset token must be rejected end-to-end."""
        account = create_user()
        with freeze_time(frozen_now):
            token = self._obtain_token(client, account["email"], capture_reset_delivery)
        # Advance past the 30-minute reset window and try to use the token.
        with freeze_time(frozen_now + timedelta(minutes=31)):
            response = client.post(
                "/auth/reset-password",
                json={"token": token, "new_password": "NewPassword123!"},
            )
        assert response.status_code == 400
        # The original password must be untouched.
        assert client.post(
            "/auth/login",
            data={"username": account["email"], "password": account["password"]},
        ).status_code == 200

    def test_garbage_token_is_rejected(self, client):
        response = client.post(
            "/auth/reset-password",
            json={"token": "garbage-token", "new_password": "NewPassword123!"},
        )
        assert response.status_code == 400

    def test_single_use_token_is_rejected_on_replay(
        self, client, create_user, capture_reset_delivery
    ):
        account = create_user()
        token = self._obtain_token(client, account["email"], capture_reset_delivery)
        first = client.post(
            "/auth/reset-password",
            json={"token": token, "new_password": "FirstPass123!"},
        )
        replay = client.post(
            "/auth/reset-password",
            json={"token": token, "new_password": "SecondPass123!"},
        )
        assert first.status_code == 200
        assert replay.status_code == 400

    def test_short_new_password_is_rejected(self, client, create_user, capture_reset_delivery):
        account = create_user()
        token = self._obtain_token(client, account["email"], capture_reset_delivery)
        response = client.post(
            "/auth/reset-password",
            json={"token": token, "new_password": "short"},
        )
        assert response.status_code in (400, 422)


class TestChangePasswordEndpoint:
    def test_happy_path_changes_password(self, client, auth_headers):
        headers, account = auth_headers
        response = client.post(
            "/auth/change-password",
            headers=headers,
            json={"current_password": account["password"], "new_password": "ChangedPass123!"},
        )
        assert response.status_code == 200
        assert client.post(
            "/auth/login",
            data={"username": account["email"], "password": "ChangedPass123!"},
        ).status_code == 200

    def test_wrong_current_password_is_rejected(self, client, auth_headers):
        headers, account = auth_headers
        response = client.post(
            "/auth/change-password",
            headers=headers,
            json={"current_password": "WrongPass123!", "new_password": "ChangedPass123!"},
        )
        assert response.status_code == 400
        # Original password still works because nothing was overwritten.
        assert client.post(
            "/auth/login",
            data={"username": account["email"], "password": account["password"]},
        ).status_code == 200

    def test_requires_authentication(self, client):
        response = client.post(
            "/auth/change-password",
            json={"current_password": "Whatever123!", "new_password": "ChangedPass123!"},
        )
        assert response.status_code == 401

    def test_empty_current_password_is_rejected(self, client, auth_headers):
        headers, _ = auth_headers
        response = client.post(
            "/auth/change-password",
            headers=headers,
            json={"current_password": "", "new_password": "ChangedPass123!"},
        )
        assert response.status_code in (400, 422)