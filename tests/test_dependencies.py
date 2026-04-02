"""Tests for app/dependencies.py — FastAPI dependency functions."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from app.dependencies import (
    get_db,
    get_pdata,
    get_redis,
    get_current_user_id,
    get_current_user,
    get_current_admin_user,
    get_jinja_globals,
)


def _make_request(app_state=None, headers=None):
    """Build a mock request with given app state and headers."""
    request = MagicMock()
    request.app.state = app_state or MagicMock()
    request.headers = headers or {}
    return request


# ── get_db / get_pdata / get_redis ────────────────────────────────────────────
class TestSimpleDependencies:
    def test_get_db(self):
        state = MagicMock()
        state.db = "db_instance"
        request = _make_request(state)
        assert get_db(request) == "db_instance"

    def test_get_pdata(self):
        state = MagicMock()
        state.pdata = "pdata_instance"
        request = _make_request(state)
        assert get_pdata(request) == "pdata_instance"

    @pytest.mark.asyncio
    async def test_get_redis(self):
        state = MagicMock()
        state.redis = "redis_instance"
        request = _make_request(state)
        result = await get_redis(request)
        assert result == "redis_instance"


# ── get_current_user_id ───────────────────────────────────────────────────────
class TestGetCurrentUserId:
    @pytest.mark.asyncio
    async def test_no_auth_header(self):
        request = _make_request(headers={})
        redis = AsyncMock()
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(request, redis)
        assert exc_info.value.status_code == 401
        assert "Missing" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_invalid_auth_format(self):
        request = _make_request(headers={"Authorization": "Basic abc"})
        redis = AsyncMock()
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(request, redis)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_blacklisted_token(self):
        request = _make_request(headers={"Authorization": "Bearer sometoken"})
        redis = AsyncMock()
        redis.get.return_value = "true"  # blacklisted
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(request, redis)
        assert exc_info.value.status_code == 401
        assert "revoked" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("app.dependencies.verify_token", return_value=None)
    async def test_invalid_token(self, mock_verify):
        request = _make_request(headers={"Authorization": "Bearer badtoken"})
        redis = AsyncMock()
        redis.get.return_value = None
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(request, redis)
        assert exc_info.value.status_code == 401
        assert "Invalid" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("app.dependencies.verify_token", return_value=42)
    async def test_valid_token(self, mock_verify):
        request = _make_request(headers={"Authorization": "Bearer goodtoken"})
        redis = AsyncMock()
        redis.get.return_value = None
        user_id = await get_current_user_id(request, redis)
        assert user_id == 42


# ── get_current_user ──────────────────────────────────────────────────────────
class TestGetCurrentUser:
    @pytest.mark.asyncio
    @patch("app.dependencies.get_current_user_id", new_callable=AsyncMock, return_value=1)
    async def test_user_found(self, mock_get_id):
        request = _make_request()
        db = AsyncMock()
        redis = AsyncMock()
        db.get_user_by_id.return_value = {"id": 1, "username": "user", "is_admin": False}
        user = await get_current_user(request, db, redis)
        assert user["id"] == 1

    @pytest.mark.asyncio
    @patch("app.dependencies.get_current_user_id", new_callable=AsyncMock, return_value=99)
    async def test_user_not_found(self, mock_get_id):
        request = _make_request()
        db = AsyncMock()
        redis = AsyncMock()
        db.get_user_by_id.return_value = None
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request, db, redis)
        assert exc_info.value.status_code == 401
        assert "User not found" in exc_info.value.detail


# ── get_current_admin_user ────────────────────────────────────────────────────
class TestGetCurrentAdminUser:
    @pytest.mark.asyncio
    async def test_admin_passes(self):
        admin = {"id": 1, "username": "admin", "is_admin": True}
        result = await get_current_admin_user(admin)
        assert result["is_admin"] is True

    @pytest.mark.asyncio
    async def test_non_admin_raises_403(self):
        non_admin = {"id": 2, "username": "user", "is_admin": False}
        with pytest.raises(HTTPException) as exc_info:
            await get_current_admin_user(non_admin)
        assert exc_info.value.status_code == 403


# ── get_jinja_globals ─────────────────────────────────────────────────────────
class TestGetJinjaGlobals:
    def test_returns_url_function_and_prefix(self):
        result = get_jinja_globals()
        assert "url" in result
        assert "url_prefix" in result

    def test_url_routes(self):
        result = get_jinja_globals()
        url = result["url"]
        prefix = result["url_prefix"]
        assert url("home") == f"{prefix}/"
        assert url("login") == f"{prefix}/login"
        assert url("insert") == f"{prefix}/insert"

    def test_url_static(self):
        result = get_jinja_globals()
        url = result["url"]
        assert url("static", "css/style.css") == "/static/css/style.css"
