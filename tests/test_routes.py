"""Tests for API routes via FastAPI TestClient.

Tests the actual HTTP endpoints with mocked DB/Redis/ProcessData.
Focuses on auth routes (no template rendering needed) and JSON API endpoints.
"""
import pytest

from tests.conftest import ADMIN_USER, NORMAL_USER, _auth_header
from utils.auth import hash_password, create_refresh_token


# ── Auth: Register ────────────────────────────────────────────────────────────
class TestRegister:
    @pytest.mark.asyncio
    async def test_register_success(self, client, mock_db):
        mock_db.user_exists.return_value = False
        mock_db.user_exists_by_email.return_value = False
        mock_db.create_user.return_value = 1
        mock_db.get_user_by_id.return_value = {
            "id": 1, "username": "newuser", "email": "new@test.com", "is_admin": False
        }
        resp = await client.post("/v1/register", json={
            "username": "newuser", "email": "new@test.com", "password": "pass123"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "newuser"
        assert data["id"] == 1

    @pytest.mark.asyncio
    async def test_register_duplicate_username(self, client, mock_db):
        mock_db.user_exists.return_value = True
        resp = await client.post("/v1/register", json={
            "username": "taken", "email": "e@e.com", "password": "pw"
        })
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, client, mock_db):
        mock_db.user_exists.return_value = False
        mock_db.user_exists_by_email.return_value = True
        resp = await client.post("/v1/register", json={
            "username": "new", "email": "taken@e.com", "password": "pw"
        })
        assert resp.status_code == 409


# ── Auth: Login ───────────────────────────────────────────────────────────────
class TestLogin:
    @pytest.mark.asyncio
    async def test_login_success(self, client, mock_db, mock_redis):
        mock_redis.get.return_value = None  # no failed attempts
        username = "user"
        correct_password = "correct"
        mock_db.get_user_by_username.return_value = {
            "id": 1,
            "username": username,
            "password_hash": hash_password(correct_password),
            "is_admin": False,
        }
        resp = await client.post("/v1/login", json={
            "username": username, "password": correct_password
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client, mock_db, mock_redis):
        mock_redis.get.return_value = None
        mock_db.get_user_by_username.return_value = {
            "id": 1,
            "username": "user",
            "password_hash": hash_password("correct"),
            "is_admin": False,
        }
        resp = await client.post("/v1/login", json={
            "username": "user", "password": "wrong"
        })
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client, mock_db, mock_redis):
        mock_redis.get.return_value = None
        mock_db.get_user_by_username.return_value = None
        resp = await client.post("/v1/login", json={
            "username": "ghost", "password": "pw"
        })
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_rate_limited(self, client, mock_db, mock_redis):
        mock_redis.get.return_value = "10"  # exceeds limit
        resp = await client.post("/v1/login", json={
            "username": "user", "password": "pw"
        })
        assert resp.status_code == 429


# ── Auth: Logout ──────────────────────────────────────────────────────────────
class TestLogout:
    @pytest.mark.asyncio
    async def test_logout_success(self, client, mock_redis, user_token):
        mock_redis.get.return_value = None  # not blacklisted
        resp = await client.post("/v1/logout", headers=_auth_header(user_token))
        assert resp.status_code == 200
        assert resp.json()["message"] == "Logged out successfully"

    @pytest.mark.asyncio
    async def test_logout_no_token(self, client):
        resp = await client.post("/v1/logout")
        assert resp.status_code == 401


# ── Auth: Refresh ─────────────────────────────────────────────────────────────
class TestRefreshToken:
    @pytest.mark.asyncio
    async def test_refresh_success(self, client, mock_redis):
        refresh = create_refresh_token(user_id=2)
        mock_redis.get.return_value = refresh  # stored token matches
        resp = await client.post("/v1/refresh", json={"refresh_token": refresh})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    @pytest.mark.asyncio
    async def test_refresh_invalid_token(self, client, mock_redis):
        mock_redis.get.return_value = None
        resp = await client.post("/v1/refresh", json={"refresh_token": "bad.token.here"})
        assert resp.status_code == 401


# ── Search Word ───────────────────────────────────────────────────────────────
class TestSearchWordRoute:
    @pytest.mark.asyncio
    async def test_search_jp_word(self, client, mock_db, mock_redis, user_token):
        mock_redis.get.return_value = None
        mock_db.query_like_word.return_value = [
            {"word": "食べる", "senses": "to eat ([verb])"}
        ]
        mock_db.get_meanings.return_value = ["to eat"]
        resp = await client.get(
            "/v1/api/search-word", params={"word": "食べる"},
            headers=_auth_header(user_token)
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data

    @pytest.mark.asyncio
    async def test_search_en_word(self, client, mock_db, mock_redis, user_token):
        mock_redis.get.return_value = None
        mock_db.query_word_sense.return_value = [
            {"word": "食べる", "senses": "to eat ([verb])"}
        ]
        mock_db.get_meanings.return_value = ["to eat"]
        resp = await client.get(
            "/v1/api/search-word", params={"word": "eat"},
            headers=_auth_header(user_token)
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_search_invalid_word(self, client, mock_db, mock_redis, user_token):
        mock_redis.get.return_value = None
        resp = await client.get(
            "/v1/api/search-word", params={"word": "123!"},
            headers=_auth_header(user_token)
        )
        assert resp.status_code == 400


# ── Toggle Star ───────────────────────────────────────────────────────────────
class TestToggleStar:
    @pytest.mark.asyncio
    async def test_toggle_star_word(self, client, mock_db, mock_redis, user_token):
        mock_redis.get.return_value = None  # not blacklisted
        mock_db.update_word_star.return_value = True
        resp = await client.post(
            "/v1/toggle-star",
            json={"id": 1, "objType": "word", "star": True},
            headers=_auth_header(user_token),
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @pytest.mark.asyncio
    async def test_toggle_star_invalid_type(self, client, mock_db, mock_redis, user_token):
        mock_redis.get.return_value = None
        resp = await client.post(
            "/v1/toggle-star",
            json={"id": 1, "objType": "invalid", "star": True},
            headers=_auth_header(user_token),
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_toggle_star_no_auth(self, client):
        resp = await client.post("/v1/toggle-star", json={"id": 1, "objType": "word", "star": True})
        assert resp.status_code == 401


# ── Delete Book ───────────────────────────────────────────────────────────────
class TestDeleteBook:
    @pytest.mark.asyncio
    async def test_delete_requires_admin(self, client, mock_db, mock_redis, user_token):
        """Normal (non-admin) user should get 403."""
        mock_redis.get.return_value = None
        mock_db.get_user_by_id.return_value = NORMAL_USER
        resp = await client.post(
            "/v1/del/book",
            json={"id": 1},
            headers=_auth_header(user_token),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_by_admin(self, client, mock_db, mock_redis, admin_token):
        """Admin user should get 200."""
        mock_redis.get.return_value = None
        mock_db.get_user_by_id.return_value = ADMIN_USER
        mock_db.delete_book.return_value = True
        resp = await client.post(
            "/v1/del/book",
            json={"id": 1},
            headers=_auth_header(admin_token),
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_no_auth(self, client):
        resp = await client.post("/v1/del/book", json={"id": 1})
        assert resp.status_code == 401


# ── Word Priority (Quiz support) ──────────────────────────────────────────────
class TestWordPrioRoute:
    @pytest.mark.asyncio
    async def test_update_prio(self, client, mock_db, mock_redis, user_token):
        mock_redis.get.return_value = None
        mock_db.update_quized_prio_ts.return_value = True
        resp = await client.post(
            "/v1/word/prio",
            json={"word_id": 1, "is_correct": True, "quized": 5, "occurrence": 10},
            headers=_auth_header(user_token),
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @pytest.mark.asyncio
    async def test_update_prio_no_auth(self, client):
        resp = await client.post("/v1/word/prio", json={"word_id": 1})
        assert resp.status_code == 401


# ── Word Known (Quiz support) ─────────────────────────────────────────────────
class TestWordKnownRoute:
    @pytest.mark.asyncio
    async def test_mark_as_known(self, client, mock_db, mock_redis, user_token):
        mock_redis.get.return_value = None
        mock_db.update_words_known.return_value = True
        resp = await client.post(
            "/v1/word/known",
            json={"word_id": 1, "update_to_known": True},
            headers=_auth_header(user_token),
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @pytest.mark.asyncio
    async def test_reset_known(self, client, mock_db, mock_redis, user_token):
        mock_redis.get.return_value = None
        mock_db.get_word_occurence.return_value = (1, 10)
        mock_db.update_quized_prio_ts.return_value = True
        resp = await client.post(
            "/v1/word/known",
            json={"word_id": 1, "update_to_known": False, "quized": 5, "occurrence": 10},
            headers=_auth_header(user_token),
        )
        assert resp.status_code == 200


# ── Progress (stub) ───────────────────────────────────────────────────────────
class TestProgressRoute:
    @pytest.mark.asyncio
    async def test_progress(self, client, mock_redis, user_token):
        mock_redis.get.return_value = None
        resp = await client.get("/v1/progress", headers=_auth_header(user_token))
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_progress_no_auth(self, client):
        resp = await client.get("/v1/progress")
        assert resp.status_code == 401
