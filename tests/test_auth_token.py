"""Unit tests for the JWT access-token helpers in services/api/auth.py.

These tests assert the *business logic* of token generation and decoding:
what the token contains, how long it lives, and which malformed/expired tokens
are rejected. They deliberately avoid HTTP serialisation concerns.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import HTTPException
from jose import jwt

from services.api import auth

ALGORITHM = "HS256"


class TestCreateAccessToken:
    def test_happy_path_token_decodes_to_subject_and_expiry(self, frozen_now):
        """A token minted now must carry the subject and a future expiry."""
        token = auth.create_access_token({"sub": "42"})
        payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[ALGORITHM])

        assert payload["sub"] == "42"
        # exp is stored as a Unix timestamp; it must be exactly 60 minutes ahead
        # of the frozen clock (frozen_now is already UTC-aware).
        expected_exp = (frozen_now + timedelta(minutes=60)).timestamp()
        assert payload["exp"] == int(expected_exp)
        # The token must contain the HS256 algorithm header.
        assert jwt.get_unverified_header(token)["alg"] == ALGORITHM

    def test_custom_claims_are_preserved(self):
        """Extra payload fields survive encoding and decoding."""
        token = auth.create_access_token({"sub": "7", "role": "admin"})
        payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["role"] == "admin"

    def test_different_subjects_produce_different_tokens(self):
        """Tokens for different users must never collide."""
        token_a = auth.create_access_token({"sub": "1"})
        token_b = auth.create_access_token({"sub": "2"})
        assert token_a != token_b


class TestDecodeAccessToken:
    def test_happy_path_round_trip(self):
        """A valid token decodes back to the same user id."""
        token = auth.create_access_token({"sub": "99"})
        token_data = auth.decode_access_token(token)
        assert token_data.user_id == 99

    def test_missing_sub_is_rejected(self):
        """A token without a subject carries no identity and must be rejected."""
        token = auth.create_access_token({"foo": "bar"})
        with pytest.raises(HTTPException) as exc_info:
            auth.decode_access_token(token)
        assert exc_info.value.status_code == 401

    def test_expired_token_is_rejected(self):
        """REG RESSION GUARD: an expired token must raise 401.

        This is the exact failure class from last week's refactor that locked
        real users out. A token whose `exp` is in the past is invalid, period.
        """
        token = auth.create_access_token({"sub": "1"})
        # Rewrite the exp claim to a timestamp in the past.
        expired = jwt.encode(
            {"sub": "1", "exp": 1},  # Unix epoch ~1970, always expired.
            auth.SECRET_KEY,
            algorithm=ALGORITHM,
        )
        with pytest.raises(HTTPException) as exc_info:
            auth.decode_access_token(expired)
        assert exc_info.value.status_code == 401
        assert token  # the fresh token exists but is unused here

    def test_malformed_token_is_rejected(self):
        """Garbage that is not a JWT must raise 401, not crash."""
        with pytest.raises(HTTPException) as exc_info:
            auth.decode_access_token("not-a-jwt")
        assert exc_info.value.status_code == 401

    def test_token_signed_with_wrong_secret_is_rejected(self):
        """A token from another secret (e.g. another deployment) is invalid."""
        foreign = jwt.encode({"sub": "1", "exp": 9999999999}, "other-secret", algorithm=ALGORITHM)
        with pytest.raises(HTTPException) as exc_info:
            auth.decode_access_token(foreign)
        assert exc_info.value.status_code == 401

    def test_non_integer_sub_is_rejected(self):
        """A non-numeric subject cannot map to a user id and must be rejected.

        (AI-assisted edge case: subjects that decode to strings/lists could
        previously slip through into the id conversion and crash.)
        """
        for bad_sub in ("abc", ["1"]):
            token = auth.create_access_token({"sub": bad_sub})
            with pytest.raises(HTTPException) as exc_info:
                auth.decode_access_token(token)
            assert exc_info.value.status_code == 401