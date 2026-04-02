"""Tests for utils/auth.py — password hashing and JWT tokens."""
import pytest
from datetime import timedelta
from utils.auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_token,
)


class TestPasswordHashing:
    def test_hash_returns_string(self):
        h = hash_password("test123")
        assert isinstance(h, str)
        assert h != "test123"

    def test_verify_correct_password(self):
        h = hash_password("mypassword")
        assert verify_password("mypassword", h) is True

    def test_verify_wrong_password(self):
        h = hash_password("mypassword")
        assert verify_password("wrongpassword", h) is False

    def test_different_hashes(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        # bcrypt produces different salts each time
        assert h1 != h2
        # But both verify correctly
        assert verify_password("same", h1)
        assert verify_password("same", h2)


class TestAccessToken:
    def test_create_and_verify(self):
        token = create_access_token(user_id=42)
        uid = verify_token(token, token_type="access")
        assert uid == 42

    def test_custom_expiry(self):
        token = create_access_token(user_id=7, expires_delta=timedelta(minutes=5))
        assert verify_token(token, token_type="access") == 7

    def test_wrong_type_returns_none(self):
        token = create_access_token(user_id=1)
        assert verify_token(token, token_type="refresh") is None


class TestRefreshToken:
    def test_create_and_verify(self):
        token = create_refresh_token(user_id=99)
        uid = verify_token(token, token_type="refresh")
        assert uid == 99

    def test_wrong_type_returns_none(self):
        token = create_refresh_token(user_id=1)
        assert verify_token(token, token_type="access") is None


class TestInvalidToken:
    def test_garbage_token(self):
        assert verify_token("not.a.jwt") is None

    def test_empty_token(self):
        assert verify_token("") is None
