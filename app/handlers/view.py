import math
import re
from typing import List, Tuple, Dict, Any, TYPE_CHECKING

from app.config import WORD_CORE_CACHE_EXPIRE_SECONDS, WORD_SENTENCE_EXPIRE_SECONDS
from app.dependencies import (word_core_cache_key, word_sentence_cache_key,
    redis_get_json, redis_get_json_sliding, redis_set_json, get_word_sentence_cache_version,
    extract_word_core_payload)
from utils.logger import get_logger
from utils.storage import get_file_download_link, delete_storage_file
from schemas.constants import DEFAULT_LIMIT

if TYPE_CHECKING:
    from utils.db import DBHandling
    import redis.asyncio as aioredis 

log = get_logger(__name__)

# cache word count for /view/word
view_count_cache = {}


def _strip_storage_prefix(name: str) -> str:
    """Strip generated UUID prefix from storage object names, if present."""
    if not name:
        return ""
    # Keep only basename if object_name includes folders like uploads/{user}/{batch}/...
    base = name.split("/")[-1].split("\\")[-1]
    # Remove '<32 hex chars>_' prefix used by insert endpoints.
    if re.match(r"^[0-9a-fA-F]{32}_.+", base):
        return base[33:]
    return base

def reset_view_word_count():
    """call this when insert new book/word"""
    view_count_cache.clear()


async def _paginated_query(cache_key: tuple, count_fn, list_fn,
                           limit: int, page: int) -> Tuple[list, int]:
    """Shared pagination: cache the total count, compute page_count, guard out-of-range pages."""
    if cache_key not in view_count_cache:
        view_count_cache[cache_key] = await count_fn()

    page_count = int(math.ceil(view_count_cache[cache_key] / limit))
    if page > page_count:
        return [], page_count
    return await list_fn(limit, limit * (page - 1)), page_count


async def toggle_star_helper(db: "DBHandling", user_id: int, obj_id: int, obj_type: str, star: int) -> bool:
    """Turn star on or off. Return true if success, false otherwise."""
    star_stt = True if star == 1 else False
    if obj_type == "word":
        return await db.update_word_star(user_id=user_id, word_id=obj_id, new_star_status=star_stt)
    elif obj_type == "book":
        return await db.update_book_star(user_id=user_id, book_id=obj_id, new_star_status=star_stt)
    else:
        return False

async def delete_book_helper(db: "DBHandling", book_id: int, object_name: str = "") -> bool:
    """Delete DB record, if success then delete storage file.
    Return True if all success, False otherwise."""
    async with db.transaction():
        deleted = await db.delete_book(book_id=book_id)

    if not deleted:
        return False

    # Best effort: DB is source of truth; storage cleanup failures are logged.
    if object_name:
        try:
            if not delete_storage_file(object_name):
                log.warning(f"Deleted book_id={book_id} in DB but failed to delete object '{object_name}'")
        except Exception as e:
            log.warning(f"Deleted book_id={book_id} in DB but storage cleanup raised error: {e}")

    return True

async def get_all_book_name_and_id(db: "DBHandling"):
    """call db.list_books with no star, 0 offset, query all"""
    return await db.list_books(star=None, limit=None, offset=0)


async def handle_search_word(db: "DBHandling", word: str, limit: int, bp_prefix: str) -> Dict[str, Any]:
    """
    Search a JP or EN word, return max number of found result (`limit`).
    Returns empty list if word not found.
    
    Output: {"result": [list of word dicts]}
    """
    res: List[dict] = []
    res = await db.query_search_word(word, limit)
    
    # Modify senses to only have the first meaning for UI
    for w in res:
        w["senses"] = db.get_meanings(w["word"], w["senses"])[0]
    return {"results": res, "bpPrefix": bp_prefix}

async def handle_view_specific_word(
    db: "DBHandling",
    user_id: int,
    word_id: int,
    sentence_limit: int,
    redis: "aioredis" = None,
) -> Tuple[dict, List[str]]:
    """
    Handle viewing a JP word with `sentence_limit` amount of sentence examples.
    """
    res: dict | None = None

    # Word core cache is shared across users and uses sliding expiration.
    core_key = word_core_cache_key(word_id)
    if redis is not None:
        cached_core = await redis_get_json_sliding(redis, core_key, WORD_CORE_CACHE_EXPIRE_SECONDS)
        if isinstance(cached_core, dict) and cached_core.get("word_id"):
            res = cached_core

    # If no cache, get from DB, purposely not getting user related info
    if res is None:
        res = await db.get_exact_word(word_id=word_id)
        if redis is not None and res:
            core_payload = extract_word_core_payload(res)
            await redis_set_json(redis, core_key, core_payload, WORD_CORE_CACHE_EXPIRE_SECONDS)

    if not res:
        return {}, []

    progress = await db.get_user_word_progress(user_id=user_id, word_id=word_id)
    res.update(progress)
    res["meanings"] = [chunk.strip() for chunk in res["senses"].split(";") if chunk.strip()]

    sentence_examples = []
    if redis is not None:
        version = await get_word_sentence_cache_version(redis)
        sen_key = word_sentence_cache_key(res["word_id"], sentence_limit, version)
        sentence_examples = await redis_get_json(redis, sen_key)
        if not sentence_examples:
            sentence_examples = await db.get_sentences_containing_word_by_id(
                res["word_id"], sentence_limit, res["word"],
            )
            await redis_set_json(
                redis, sen_key, sentence_examples, WORD_SENTENCE_EXPIRE_SECONDS,
            )
    else:
        sentence_examples = await db.get_sentences_containing_word_by_id(
            res["word_id"], sentence_limit, res["word"],
        )
    return res, sentence_examples

async def handle_view_words(db: "DBHandling" = None, user_id: int = None, jlpt_level: str = "", star: bool = False,
                      limit: int = DEFAULT_LIMIT, page: int = 1) -> Tuple[List[dict], int]:
    """
    Handle viewing a list of `limit` JP words with their 1st EN meaning.
    
    Output: a list containing dicts with below format:
        - word: the JP word
        - spelling: the Kata spelling
        - senses: the 1st EN meaning. Still make the key as `senses` to line up
        with handle_search_word()
    """
    key = tuple(f"word::{jlpt_level}::{star}")
    return await _paginated_query(
        key,
        lambda: db.count_words(user_id, jlpt_level, star),
        lambda lim, off: db.list_words(user_id, jlpt_level, star, lim, off),
        limit, page
    )

async def handle_view_books(db: "DBHandling" = None, user_id: int = None, star: bool = False,
                      limit: int = DEFAULT_LIMIT, page: int = 1) -> Tuple[List[dict], int]:
    """
    Handle viewing a list of `limit` JP books with their 1st EN meaning.
    
    Output:
    - list: containing dicts with below format:
        - name: the book name
        - created_at: the book insert timestamp
        - star: star status of the book
    - int: page count
    """
    key = tuple(f"book::{star}")
    return await _paginated_query(
        key,
        lambda: db.count_books(star),
        lambda lim, off: db.list_books(user_id, star, lim, off),
        limit, page
    )

async def handle_view_specific_book(db: "DBHandling", user_id: int, book_id: int) -> dict:
    """
    Handle viewing a specific book and attach a short-lived download link if available.
    """
    book = await db.get_exact_book(user_id=user_id, book_id=book_id)
    if not book:
        return {}

    object_name = book.get("object_name", "")
    if object_name:
        download_name = _strip_storage_prefix(object_name) or book.get("name", "download")
        book["download_url"] = get_file_download_link(object_name, download_name=download_name)
        book["download_name"] = download_name
    else:
        book["download_url"] = ""
        book["download_name"] = ""

    return book
