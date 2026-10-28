"""Unit tests for password hashing / reset / change helpers in services/api/auth.py.

These tests exercise the pure password business logic: hashing round-trips,
current-password verification, password reset token creation/consumption, and
the change-password flow. Endpoint wiring is tested separately in
test_auth_api.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from freezegun import freeze_time
from jose import jwt

from services.api import auth
from services.api.auth import (
    change_user_password,
    create_password_reset_token,
    get_password_hash,
    reset_user_password,
    verify_password,
)
from services.api.database import (
    create_user,
    get_user_by_email,
)
from services.api.models import UserCreate


def _make_email(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}@trackflow.test"


@pytest.fixture
def stored_user():
    """Create a real user record in the isolated TinyDB."""
    def _create(password: str = "InitialPass123!") -> tuple:
        email = _make_email("pw")
        user = create_user(
            UserCreate(email=email, password=password, role="user")
        )
        return email, password, user
    return _create


class TestPasswordHashing:
    def test_hash_round_trip(self):
        """A hashed password verifies against the plaintext and never stores it."""
        hashed = get_password_hash("SuperSecret123!")
        assert hashed != "SuperSecret123!"
        assert verify_password("SuperSecret123!", hashed)

    def test_wrong_password_fails(self):
        hashed = get_password_hash("SuperSecret123!")
        assert not verify_password("WrongPassword!", hashed)


class TestChangeUserPassword:
    def test_happy_path_updates_password(self, stored_user):
        email, old_password, user = stored_user()
        assert change_user_password(user, old_password, "NewPassword456!")
        updated = get_user_by_email(email)
        assert updated is not None
        assert verify_password("NewPassword456!", updated.hashed_password)
        assert not verify_password(old_password, updated.hashed_password)

    def test_wrong_current_password_is_rejected(self, stored_user):
        _, old_password, user = stored_user()
        before = user.hashed_password
        # Wrong current password must fail and leave the stored hash untouched.
        assert change_user_password(user, "NotThePassword!", "NewPassword456!") is False
        assert get_user_by_email(user.email).hashed_password == before


class TestCreatePasswordResetToken:
    def test_happy_path_returns_token_and_future_expiry(self, stored_user, frozen_now):
        _, _, user = stored_user()
        token, expires_at = create_password_reset_token(user)
        assert isinstance(token, str) and token
        # Expiry must be ~30 minutes in the future (configured default).
        assert expires_at - frozen_now <= timedelta(minutes=31)
        assert expires_at - frozen_now >= timedelta(minutes=29)

    def test_token_carries_reset_purpose(self, stored_user):
        """Reset tokens must be purpose-scoped so they can't be used as access tokens."""
        _, _, user = stored_user()
        token, _ = create_password_reset_token(user)
        payload = jwt.decode(token, auth.SECRET_KEY, algorithms=["HS256"])
        assert payload["purpose"] == "password_reset"
        assert payload["sub"] == str(user.id)
        assert payload.get("jti")  # unique token id stored server-side

    def test_reset_token_is_single_use(self, stored_user):
        """The server-side record is consumed after the first successful reset."""
        _, _, user = stored_user()
        token, _ = create_password_reset_token(user)
        assert reset_user_password(token, "BrandNewPass123!") is True
        # Second use must fail — the token has already been consumed.
        assert reset_user_password(token, "AnotherPass123!") is False


class TestResetUserPassword:
    def test_happy_path_resets_and_old_password_stops_working(self, stored_user):
        email, old_password, user = stored_user()
        token, _ = create_password_reset_token(user)
        assert reset_user_password(token, "ResetPass999!")
        updated = get_user_by_email(email)
        assert verify_password("ResetPass999!", updated.hashed_password)
        assert not verify_password(old_password, updated.hashed_password)

    def test_expired_token_is_rejected(self, stored_user, frozen_now, monkeypatch):
        """REG RESSION GUARD: an expired reset token must not change the password.

        This is the token-expiry class of bug from last week. We mint a token,
        then fast-forward past its 30-minute lifetime and confirm the reset fails
        and the stored hash is untouched.
        """
        _, _, user = stored_user()
        token, _ = create_password_reset_token(user)
        with freeze_time(frozen_now + timedelta(minutes=31)):
            assert reset_user_password(token, "ResetPass999!") is False
        assert verify_password("InitialPass123!", get_user_by_email(user.email).hashed_password)

    def test_garbage_token_is_rejected(self, stored_user):
        _, _, user = stored_user()
        before = user.hashed_password
        assert reset_user_password("totally-not-a-token", "ResetPass999!") is False
        assert get_user_by_email(user.email).hashed_password == before

    def test_access_token_cannot_reset_password(self, stored_user):
        """A normal login token must be rejected by the reset flow (purpose guard)."""
        _, _, user = stored_user()
        access_token = auth.create_access_token({"sub": str(user.id)})
        before = user.hashed_password
        assert reset_user_password(access_token, "ResetPass999!") is False
        assert get_user_by_email(user.email).hashed_password == before

    def test_already_used_token_is_rejected(self, stored_user):
        """Consumed tokens cannot be replayed."""
        _, _, user = stored_user()
        token, _ = create_password_reset_token(user)
        assert reset_user_password(token, "FirstReset123!") is True
        assert reset_user_password(token, "SecondReset123!") is False

    def test_reset_token_with_missing_jti_is_rejected(self, stored_user):
        """A reset token whose jti is not a usable string is rejected.

        (Edge case surfaced while reviewing reset_user_password: the jti is the
        server-side lookup key. A non-string jti (e.g. an integer) is already
        rejected by python-jose's claim validation during decode, so this test
        uses an empty-string jti — which survives decode but must still be
        rejected by the isinstance/emptiness guard. It is a non-empty token
        that would otherwise slip through to the lookup.)
        """
        _, _, user = stored_user()
        bad_token = jwt.encode(
            {
                "sub": str(user.id),
                "purpose": "password_reset",
                "jti": "",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
            },
            auth.SECRET_KEY,
            algorithm="HS256",
        )
        assert reset_user_password(bad_token, "ResetPass999!") is False