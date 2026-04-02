"""
Shared pytest fixtures for the jpapp2 test suite.

All DB, Redis, and ProcessData dependencies are mocked so tests
run without any external services.
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

from fastapi import FastAPI
from app.routes import router
from app.config import bpv1_url_prefix
from utils.auth import create_access_token, hash_password


# ── Mock DB ───────────────────────────────────────────────────────────────────
@pytest.fixture
def mock_db():
    """Return a MagicMock that mimics DBHandling with async helpers."""
    db = MagicMock()
    # Make all public methods async by default
    for attr in [
        "connect_2_db", "migrate", "close_db",
        "create_user", "get_user_by_id", "get_user_by_username",
        "user_exists", "user_exists_by_email",
        "insert_book", "update_book", "get_exact_book", "list_books",
        "count_books", "update_book_star", "delete_book",
        "insert_word", "update_word_occurrence", "update_word_jlpt",
        "update_words_known", "update_word_star",
        "query_like_word", "get_exact_word", "query_word_sense",
        "get_word_occurence", "get_user_word_quized",
        "list_words", "count_words",
        "insert_update_sentence", "get_sentences_containing_word_by_id",
        "query_like_sentence", "query_random_sentences", "get_exact_sentence",
        "insert_word_book_ref", "insert_word_sentence_ref", "insert_sentence_book_ref",
        "get_quiz", "update_quized_prio_ts", "get_distractors",
        "get_meanings_from_db",
    ]:
        setattr(db, attr, AsyncMock())

    # Synchronous helpers
    db.get_meanings = MagicMock(return_value=["meaning1", "meaning2"])
    db._extract_meanings = MagicMock(return_value=["meaning1"])
    db._priority_formula = MagicMock(return_value=1.0)
    db._priority_softcap_formula = MagicMock(return_value=0.5)
    db._parse_quiz = MagicMock()
    db._parse_word = MagicMock()
    db._parse_book = MagicMock()
    db._get_rowcount = MagicMock(return_value=1)

    # transaction context manager
    db.transaction = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(), __aexit__=AsyncMock()
    ))

    return db


# ── Mock Redis ────────────────────────────────────────────────────────────────
@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    redis.setex = AsyncMock()
    redis.delete = AsyncMock()
    redis.incr = AsyncMock()
    redis.expire = AsyncMock()
    redis.ping = AsyncMock()
    return redis


# ── Mock ProcessData ──────────────────────────────────────────────────────────
@pytest.fixture
def mock_pdata():
    pdata = MagicMock()
    pdata.process_sentence = AsyncMock(return_value=[])
    pdata.stream_sentences_file = MagicMock(return_value=iter([]))
    pdata.stream_sentences_str = MagicMock(return_value=iter([]))
    pdata.get_random_jamdict_entries = MagicMock(return_value=[])
    return pdata


# ── Test users ────────────────────────────────────────────────────────────────
ADMIN_USER = {
    "id": 1,
    "username": "admin",
    "email": "admin@test.com",
    "password_hash": hash_password("adminpass"),
    "is_admin": True,
    "created_at": "2025-01-01T00:00:00",
}

NORMAL_USER = {
    "id": 2,
    "username": "user",
    "email": "user@test.com",
    "password_hash": hash_password("userpass"),
    "is_admin": False,
    "created_at": "2025-01-01T00:00:00",
}


@pytest.fixture
def admin_token():
    return create_access_token(ADMIN_USER["id"])


@pytest.fixture
def user_token():
    return create_access_token(NORMAL_USER["id"])


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── FastAPI test app ──────────────────────────────────────────────────────────
@pytest.fixture
def app(mock_db, mock_redis, mock_pdata):
    """
    Build a fresh FastAPI app per test with mocked state.
    Templates are loaded from actual template dir so route signatures stay valid,
    but we mostly test JSON API endpoints.
    """
    import os
    from fastapi.templating import Jinja2Templates

    test_app = FastAPI()
    test_app.state.db = mock_db
    test_app.state.redis = mock_redis
    test_app.state.pdata = mock_pdata

    test_app.include_router(router, prefix=bpv1_url_prefix)

    # Static files not needed for API tests
    return test_app


@pytest_asyncio.fixture
async def client(app):
    """Async httpx test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
