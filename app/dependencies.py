from fastapi import Request, Depends, HTTPException
import asyncpg
import redis.asyncio as aioredis

from utils.db import DBHandling
from utils.process_data import ProcessData
from utils.auth import verify_token
from app.config import bpv1_url_prefix


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
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = auth_header.split(" ")[1]
    
    # Check if token is blacklisted
    is_blacklisted = await redis.get(f"blacklist:{token}")
    if is_blacklisted:
        raise HTTPException(status_code=401, detail="Token has been revoked")
    
    # Verify token and get user_id
    user_id = verify_token(token, token_type="access")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
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
        raise HTTPException(status_code=401, detail="User not found")
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
        raise HTTPException(status_code=403, detail="Admin access required")
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
                status_code=429,
                detail=f"Too many requests. Limit: {max_calls} per {period_seconds}s."
            )
    return _check


# ===== Template Helpers =====
def get_jinja_globals():
    """Return URL helper function and url_prefix for Jinja2 templates.
    
    Usage in templates, example using /v1 url prefix:
    - {{ url('static', 'css/style.css') }} -> /static/css/style.css
    - {{ url('insert') }} -> /v1/insert
    - {{ url_prefix }} -> /v1 (accessible as data attribute in HTML)
    """
    url_prefix = bpv1_url_prefix

    def url(endpoint: str, filename: str = None) -> str:
        """Generate URLs for templates."""
        routes = {
            'home': f'{url_prefix}/',
            'login': f'{url_prefix}/login',
            'register': f'{url_prefix}/register',
            'refresh': f'{url_prefix}/refresh',
            'logout': f'{url_prefix}/logout',
            'insert': f'{url_prefix}/insert',
            'upload_file': f'{url_prefix}/insert/file',
            'upload_string': f'{url_prefix}/insert/str',
            'view': f'{url_prefix}/view',
            'search_word': f'{url_prefix}/view/search-word',
            'api_search_word': f'{url_prefix}/api/search-word',
            'view_words': f'{url_prefix}/view/word',
            'view_specific_word': f'{url_prefix}/view/word/',
            'toggle_star': f'{url_prefix}/toggle-star',
            'serve_audio': f'{url_prefix}/audio/',
            'view_books': f'{url_prefix}/view/book',
            'view_specific_book': f'{url_prefix}/view/book/',
            'delete_book': f'{url_prefix}/del/book',
            'progress': f'{url_prefix}/progress',
            'quiz': f'{url_prefix}/quiz',
            'quiz_jp': f'{url_prefix}/quiz/jp',
            'quiz_known': f'{url_prefix}/quiz/known',
            'quiz_en': f'{url_prefix}/quiz/en',
            'quiz_sentence': f'{url_prefix}/quiz/sentence',
            'update_word_prio': f'{url_prefix}/word/prio',
            'toggle_word_known': f'{url_prefix}/word/known',
            'progress': f'{url_prefix}/progress',
        }
        
        if endpoint == 'static':
            return f'/static/{filename}'
        return routes.get(endpoint, '#')
    
    return {'url': url, 'url_prefix': url_prefix}
