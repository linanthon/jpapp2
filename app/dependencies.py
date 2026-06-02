import asyncpg
import json
import re
from http import HTTPStatus
from fastapi import Request, Depends, HTTPException
import redis.asyncio as aioredis

from utils.data import is_english_word, is_japanese_word
from utils.db import DBHandling
from utils.process_data import ProcessData
from utils.auth import verify_token
from app.config import (bpv1_url_prefix, WORD_CORE_CACHE_EXPIRE_SECONDS,
                    WORD_SENTENCE_EXPIRE_SECONDS, WORD_SENTENCE_VERSION_KEY,
                    TTS_MAX_TEXT_LEN)


# ===== FastAPI Dependency Injection =====
def get_db(request: Request) -> DBHandling:
    """Get DB connection from app state"""
    return request.app.state.db

def get_pdata(request: Request) -> ProcessData:
    """Get ProcessData instance from app state"""
    return request.app.state.pdata

async def get_redis(request: Request) -> aioredis.Redis:
    """Get Redis connection from app state"""
    return request.app.state.redis

async def get_current_user_id(
    request: Request,
    redis: aioredis.Redis = Depends(get_redis)
) -> int:
    """
    Dependency to get current user from JWT token in Authorization header.
    Validates token and checks if it's blacklisted.
    Raises HTTPException if token is invalid, expired, or blacklisted.

    Output: user id if found
    """
    # Get token from authorization header
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )
    token = auth_header.split(" ")[1]
    
    # Check if token is blacklisted
    is_blacklisted = await redis.get(f"blacklist:{token}")
    if is_blacklisted:
        raise HTTPException(status_code=HTTPStatus.UNAUTHORIZED, detail="Token has been revoked")
    
    # Verify token and get user_id
    user_id = verify_token(token, token_type="access")
    if not user_id:
        raise HTTPException(status_code=HTTPStatus.UNAUTHORIZED, detail="Invalid or expired token")
    return user_id

async def get_current_user(
    request: Request,
    db: DBHandling = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis)
) -> asyncpg.Record:
    """
    Dependency to get current user from JWT token in Authorization header.
    Validates token and checks if it's blacklisted.
    Raises HTTPException if token is invalid, expired, or blacklisted.

    Output: dict containing id, username, email, is_admin, created_at
    """
    user_id = await get_current_user_id(request, redis)
    user = await db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=HTTPStatus.UNAUTHORIZED, detail="User not found")
    return user

async def get_current_admin_user(
    current_user: asyncpg.Record = Depends(get_current_user)
) -> asyncpg.Record:
    """
    Dependency to ensure current user is an admin.
    Raises 403 Forbidden if user is not admin.
    
    Output: dict containing id, username, email, is_admin, created_at
    """
    if not current_user['is_admin']:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Admin access required")
    return current_user

def rate_limiter(max_calls: int, period_seconds: int):
    """
    Factory that returns a FastAPI dependency enforcing a fixed-window rate limit per IP.

    Uses Redis as the shared counter so the limit is consistent across multiple workers.
    Key format: "rl:{route_path}:{client_ip}"
    On first request the key is created with a TTL of `period_seconds`.
    Raises HTTP 429 once `max_calls` is exceeded within that window.

    Usage:
        @router.post("/login", dependencies=[Depends(rate_limiter(10, 60))])
    """
    async def _check(request: Request, redis: aioredis.Redis = Depends(get_redis)):
        ip = request.client.host
        key = f"rl:{request.url.path}:{ip}"
        count = await redis.incr(key)
        if count == 1:
            # First hit - set expiry to define the window
            await redis.expire(key, period_seconds)
        if count > max_calls:
            raise HTTPException(
                status_code=HTTPStatus.TOO_MANY_REQUESTS,
                detail=f"Too many requests. Limit: {max_calls} per {period_seconds}s."
            )
    return _check


# ===== Redis cache helpers =====
def word_core_cache_key(word_id: int) -> str:
    """Make word ID cache key for storing to Redis.
    The value should be the word value from DB, unrelated to user data."""
    return f"word_core:{word_id}"

def word_sentence_cache_key(word_id: int, sentence_limit: int, version: int) -> str:
    """Make word's sentence example (shows in view feature) cache key
    for storing to Redis, requires version for old ver to eventually die out
    after inserting/deleting file/string/book."""
    return f"word_sentence:v{version}:{word_id}:l{max(1, sentence_limit)}"


def extract_word_core_payload(word_data: dict | None) -> dict:
    """Return only cache-safe, user-agnostic fields from a word payload."""
    if not isinstance(word_data, dict):
        return {}
    core_fields = (
        "word_id",
        "word",
        "senses",
        "spelling",
        "forms",
        "jlpt_level",
        "audio_mapping",
        "occurrence",
    )
    return {field: word_data.get(field) for field in core_fields}


async def redis_get_json(redis: aioredis.Redis, key: str):
    """Get JSON payload from Redis without modifying TTL."""
    value = await redis.get(key)
    if value is None:
        return None
    try:
        if isinstance(value, (bytes, bytearray)):
            value = value.decode("utf-8")
        return json.loads(value)
    except (UnicodeDecodeError, TypeError, json.JSONDecodeError):
        await redis.delete(key)
        return None

async def redis_get_json_sliding(redis: aioredis.Redis, key: str, ttl_seconds: int):
    """Get redis value by key and refresh its TTL"""
    ttl_seconds = max(1, int(ttl_seconds))
    try:
        value = await redis.getex(key, ex=ttl_seconds)
    except Exception:
        value = await redis.get(key)
        if value is not None:
            await redis.expire(key, ttl_seconds)
    if value is None:
        return None
    try:
        if isinstance(value, (bytes, bytearray)):
            value = value.decode("utf-8")
        return json.loads(value)
    except (UnicodeDecodeError, TypeError, json.JSONDecodeError):
        await redis.delete(key)
        return None


async def redis_set_json(redis: aioredis.Redis, key: str, payload, ttl_seconds: int) -> None:
    """Store `payload` as json value to Redis"""
    await redis.setex(
        key,
        max(1, int(ttl_seconds)),
        json.dumps(payload, ensure_ascii=False),
    )

async def get_word_sentence_cache_version(redis: aioredis.Redis) -> int:
    """Manages word sentence example version. The version gets bumped
    when insert/delete file/string/book."""
    raw = await redis.get(WORD_SENTENCE_VERSION_KEY)
    if raw is None:
        await redis.set(WORD_SENTENCE_VERSION_KEY, 1)
        return 1
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        await redis.set(WORD_SENTENCE_VERSION_KEY, 1)
        return 1


async def bump_word_sentence_cache_version(redis: aioredis.Redis) -> int:
    """Bump sentence-example version when changes happened to books
    (insert file, insert string, and delete book), so view requests
    will add new sentence example of the words with the new version,
    the old version will eventually be timed out
    """
    return int(await redis.incr(WORD_SENTENCE_VERSION_KEY))


# ===== Others =====
def validate_tts_request(body: dict):
    text = body.get("text", "")
    lang = body.get("lang", "").lower()

    if not isinstance(text, str) or not isinstance(lang, str):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Invalid text to speech request. 'lang' can only be either 'en' or 'jp', and 'text' must be in the specified language.",
        )

    text = text.strip()
    if not text:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Invalid text to speech request. 'text' must not be empty.",
        )
    if len(text) > TTS_MAX_TEXT_LEN:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Invalid text to speech request. EN 'text' must be <= {TTS_MAX_TEXT_LEN} characters. JP 'text' must be <= {TTS_MAX_TEXT_LEN/3} characters.",
        )

    # Keep only language-relevant letters for validation and ignore symbols/noise.
    # Keep original `text` untouched for synthesis.
    normalized_text = re.sub(r"[^A-Za-z\u3040-\u30FF\u4E00-\u9FFFー]+", "", text)

    # EN stays strict. JP allows mixed JP+EN words, but must contain at least one JP character.
    if (lang == "en" and is_english_word(normalized_text)) or \
        (lang == "jp" and is_japanese_word(normalized_text, allow_mixed_english=True)):
        return text, lang

    raise HTTPException(
        status_code=HTTPStatus.BAD_REQUEST,
        detail="Invalid text to speech request. 'lang' can only be either 'en' or 'jp', and 'text' must be in the specified language."
    )

def parse_tts_voice_options(body: dict, lang: str) -> dict:
    """Parse optional voice controls for /tts request.

    Supports:
    - speed: float, allowed range [0.5, 2.0]
    - pitch or half_tone: float, allowed range [-24, 24]
    """
    if lang != "jp":
        return {}

    voice_options: dict = {}

    raw_speed = body.get("speed")
    if raw_speed is not None:
        try:
            speed = float(raw_speed)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="Invalid tts option: 'speed' must be a number in range [0.5, 2.0].",
            )
        if speed < 0.5 or speed > 2.0:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="Invalid tts option: 'speed' must be in range [0.5, 2.0].",
            )
        voice_options["speed"] = speed

    raw_half_tone = body.get("half_tone", body.get("pitch"))
    if raw_half_tone is not None:
        try:
            half_tone = float(raw_half_tone)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="Invalid tts option: 'pitch'/'half_tone' must be a number in range [-24, 24].",
            )
        if half_tone < -24 or half_tone > 24:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="Invalid tts option: 'pitch'/'half_tone' must be in range [-24, 24].",
            )
        voice_options["half_tone"] = half_tone

    return voice_options
