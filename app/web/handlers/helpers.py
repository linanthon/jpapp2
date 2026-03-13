from fastapi import FastAPI, Request, Depends, HTTPException
from contextlib import asynccontextmanager
from typing import Tuple
from http import HTTPStatus
import redis.asyncio as aioredis

from utils.db import DBHandling
from utils.process_data import ProcessData
from utils.data import read_stop_words, read_jlpt, scrape_all_jlpt
from utils.auth import verify_token
from handlers.config import DB_USER, DB_PASS, REDIS_URL, bpv1_url_prefix
from schemas.user import UserResponse, UserLogin

# cache word count for /view/word
view_count_cache = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup ----------------------------
    # Connect DB, migrate tables
    app.state.db = DBHandling()
    app.state.db.connect_2_db(
        username=DB_USER,
        password=DB_PASS
    )
    if not app.state.db.migrate():
        raise Exception("Error: DB migration error, please check the tables script. Shutting down.")

    # Connect Redis for caching, sessions, rate limiting
    try:
        app.state.redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
        await app.state.redis.ping()  # Test connection
    except Exception as e:
        raise Exception(f"Error: Failed to connect to Redis: {e}")

    # Load fugashi tagger and jamdict
    app.state.pdata = ProcessData()
    
    yield
    
    # Shutdown ---------------------------
    if hasattr(app.state, "redis"):
        await app.state.redis.close()
    if hasattr(app.state, "db"):
        app.state.db.close_db()

def create_app():
    """
    Create FastAPI app with lifespan, connect with DB, load dictionaries.
    Read stop words, JLPT levels / Scrape if no JLPT levels yet.
    """
    app = FastAPI(lifespan=lifespan)
    read_stop_words()
    scrape_all_jlpt()
    read_jlpt()
    return app

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
            'logout': f'{url_prefix}/logout',
            'insert': f'{url_prefix}/insert',
            'upload_file': f'{url_prefix}/insert/file',
            'upload_string': f'{url_prefix}/insert/str',
            'view': f'{url_prefix}/view',
            'search_word': f'{url_prefix}/view/search-word',
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
        }
        
        if endpoint == 'static':
            return f'/static/{filename}'
        return routes.get(endpoint, '#')
    
    return {'url': url, 'url_prefix': url_prefix}

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
    # Get toekn from authorization header
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
) -> dict:
    """
    Dependency to get current user from JWT token in Authorization header.
    Validates token and checks if it's blacklisted.
    Raises HTTPException if token is invalid, expired, or blacklisted.

    Output: dict containing id, username, email, is_admin, created_at
    """
    user_id = await get_current_user_id(request, redis)
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

def get_filename_from_path(fullpath: str):
    """Get filename from full path, i.e.: c:/a/path/the_file.123.txt -> the_file.123"""
    if not fullpath:
        return ""
    
    temp = fullpath.strip()
    if "/" in fullpath:
        temp = temp.split("/")[-1]
    elif "\\" in fullpath:
        temp = temp.split("\\")[-1]
    temp = temp.split(".")

    return ".".join(temp[:-1])

def do_insert_book(db: DBHandling, name: str, data: str = "") -> Tuple[int, dict | None, int]:
    """Call DB to insert book.
    
    Input:
    - db
    - name: the name to be inserted, should have no path, no extension
    - data (optional): the file's content, will read file if this is empty

    Output:
    - int: the inserted book_id if success. Otherwise,
        + 0: name already used
        + -1: if DB failed
        + -2: if file not found
    - dict: error response dict, or None if success
    - int: HTTP status code
    """
    if not name or not data:
        return -1, {"error": "No content"}, HTTPStatus.BAD_REQUEST
    
    book_id = db.insert_book(name, data)
    error_resp = None
    status_code = HTTPStatus.OK
    
    if book_id == 0:
        error_resp = {"error": "Name already used"}
        status_code = HTTPStatus.CONFLICT
    elif book_id == -1:
        error_resp = {"error": "Failed to insert"}
        status_code = HTTPStatus.INTERNAL_SERVER_ERROR
    elif book_id == -2:
        error_resp = {"error": "File not found"}
        status_code = HTTPStatus.NOT_FOUND
    
    return book_id, error_resp, status_code

def str_2_byte(input_str: str):
    return input_str.encode("utf-8")

def toggle_star_helper(db: DBHandling, obj_id: int, obj_type: str, star: int) -> bool:
    """Turn star on or off. Return true if success, false otherwise."""
    star_stt = True if star == 1 else False
    if obj_type == "word":
        return db.update_word_star(word_id=obj_id, new_star_status=star_stt)
    elif obj_type == "book":
        return db.update_book_star(book_id=obj_id, new_star_status=star_stt)
    else:
        return False

def validate_jlpt_level(jlpt_level: str) -> str:
    """Return upper cased jlpt_level if appropriate. Otherwise, return empty string"""
    jlpt_level = jlpt_level.upper()
    if jlpt_level in ["N0", "N5", "N4", "N3", "N2", "N1"]:
        return jlpt_level
    return ""

def validate_star(star_param) -> int:
    """
    Parse the star param obtained from frontend into integer:
        * 1: to star
        * 0: remove star
        * -1: invalid
    """
    if isinstance(star_param, bool):
        star = 1 if star_param else 0
    elif isinstance(star_param, (int, float)):
        star = 1 if int(star_param) != 0 else 0
    elif isinstance(star_param, str):
        s = star_param.strip().lower()
        if s in ["1", "true", "t", "yes", "y", "on"]:
            star = 1
        elif s in ["0", "false", "f", "no", "n", "off"]:
            star = 0
        else:
            star = -1
    else:
        star = -1
    return star

def parse_bool_param(val) -> bool:
    """Return True for common truthy query/JSON values, else False."""
    if isinstance(val, bool):
        return val
    if val is None:
        return False
    s = str(val).strip().lower()
    return s in ("1", "true", "t", "yes", "y", "on")

def reset_view_word_count():
    """call this when insert new book/word"""
    view_count_cache.clear()

def delete_book_helper(db: DBHandling, book_id: int) -> bool:
    with db.transaction():
        return db.delete_book(book_id=book_id)
    return False

def get_all_book_name_and_id(db: DBHandling):
    """call db.list_books with no star, 0 offset, query all"""
    return db.list_books(star=None, limit=None, offset=0)

def do_insert_word_sentence_book_2_db(pdata: "ProcessData", db: "DBHandling", sentence: str, book_id: int) -> None:
    """
    Insert sentence, update occurrence if already in DB.

    Insert each word in a sentence (does not include symbols, stopwords, numbers),
    update occurrence and new priority (for quiz) if already in DB.

    Insert references of the word-book, word-sentence, sentence-book
    """
    # Insert sentence
    sentence_id = db.insert_update_sentence(sentence)
    
    # Insert words
    words = pdata.process_sentence(sentence, db)
    for word in words:
        word_id = db.insert_word(word)

        # Insert references if sentece and word insert/updated successfully
        if word_id and sentence_id and book_id:
            db.insert_word_book_ref(word_id, book_id)
            db.insert_word_sentence_ref(word_id, sentence_id)
            db.insert_sentence_book_ref(sentence_id, book_id)
            