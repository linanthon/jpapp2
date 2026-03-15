import math
import os
from typing import TYPE_CHECKING, List, Tuple, Dict, Any

from handlers.helpers import view_count_cache
from utils.data import is_japanese_word, is_english_word
from utils.logger import get_logger
from schemas.constants import DEFAULT_LIMIT

if TYPE_CHECKING:
    from utils.data import ProcessData
    from utils.db import DBHandling

log = get_logger(__name__)

async def handle_search_word(db: "DBHandling", word: str, limit: int, bp_prefix: str) -> Dict[str, Any]:
    """
    Search a JP or EN word, return max number of found result (`limit`).
    Returns empty list if word not found.
    
    Output: {"result": [list of `Word`s]}
    """
    res: List[dict] = []

    if is_japanese_word(word):
        res = await db.query_like_word(word, limit, parse_dict=True)
    elif is_english_word(word):
        res = await db.query_word_sense(word, limit, parse_dict=True)
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
    res: dict = await db.get_exact_word(user_id=user_id, word_id=word_id, parse_dict=True)
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
    # Save count to cache until insert endpoint
    key = tuple(f"word::{jlpt_level}::{star}")
    if key not in view_count_cache:
        view_count_cache[key] = await db.count_words(user_id, jlpt_level, star)

    page_count = int(math.ceil(view_count_cache[key] / limit))
    if page > page_count:
        return [], page_count
    return await db.list_words(user_id, jlpt_level, star, limit, limit*(page-1)), page_count

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
    # Save count to cache until insert endpoint
    key = tuple(f"book::{star}")
    if key not in view_count_cache:
        view_count_cache[key] = await db.count_books(star)

    page_count = int(math.ceil(view_count_cache[key] / limit))
    if page > page_count:
        return [], page_count
    return await db.list_books(user_id, star, limit, limit*(page-1)), page_count

async def handle_view_specific_book(db: "DBHandling", user_id: int, book_id: int) -> dict:
    """
    Handle viewing a JP word with `sentence_limit` amount of sentence examples.
    """
    return await db.get_exact_book(user_id=user_id, book_id=book_id, parse_dict=True)
