import math
from typing import List, Tuple, Dict, Any

from utils.data import is_japanese_word, is_english_word
from utils.db import DBHandling
from utils.logger import get_logger
from utils.storage import get_file_download_link
from schemas.constants import DEFAULT_LIMIT

log = get_logger(__name__)

# cache word count for /view/word
view_count_cache = {}

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


async def toggle_star_helper(db: DBHandling, user_id: int, obj_id: int, obj_type: str, star: int) -> bool:
    """Turn star on or off. Return true if success, false otherwise."""
    star_stt = True if star == 1 else False
    if obj_type == "word":
        return await db.update_word_star(user_id=user_id, word_id=obj_id, new_star_status=star_stt)
    elif obj_type == "book":
        return await db.update_book_star(user_id=user_id, book_id=obj_id, new_star_status=star_stt)
    else:
        return False

async def delete_book_helper(db: DBHandling, book_id: int) -> bool:
    async with db.transaction():
        return await db.delete_book(book_id=book_id)

async def get_all_book_name_and_id(db: DBHandling):
    """call db.list_books with no star, 0 offset, query all"""
    return await db.list_books(star=None, limit=None, offset=0)


async def handle_search_word(db: "DBHandling", word: str, limit: int, bp_prefix: str) -> Dict[str, Any]:
    """
    Search a JP or EN word, return max number of found result (`limit`).
    Returns empty list if word not found.
    
    Output: {"result": [list of word dicts]}
    """
    res: List[dict] = []

    if is_japanese_word(word):
        res = await db.query_like_word(word, limit)
    elif is_english_word(word):
        res = await db.query_word_sense(word, limit)
    else:
        return {"error": "Only accept Japanese or English word"}
    
    # Modify senses to only have the first meaning for UI
    for w in res:
        w["senses"] = db.get_meanings(w["word"], w["senses"])[0]
    return {"results": res, "bpPrefix": bp_prefix}

async def handle_view_specific_word(db: "DBHandling", user_id: int, word_id: int, sentence_limit: int) -> Tuple[dict, List[str]]:
    """
    Handle viewing a JP word with `sentence_limit` amount of sentence examples.
    """
    res: dict = await db.get_exact_word(user_id=user_id, word_id=word_id)
    res["meanings"] = [chunk.strip() for chunk in res["senses"].split(";") if chunk.strip()]
    sentence_examples = await db.get_sentences_containing_word_by_id(res["word_id"], sentence_limit)
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
        book["download_url"] = get_file_download_link(object_name)
    else:
        book["download_url"] = ""

    return book
