from flask import Response, jsonify
import math
import os
from typing import TYPE_CHECKING, List, Tuple

from handlers.helpers import str_2_byte, get_dbhandling, view_word_count_cache
from utils.data import is_japanese_word, is_english_word
from utils.logger import get_logger
from schemas.constants import DEFAULT_LIMIT
from schemas.word import Word

if TYPE_CHECKING:
    from utils.data import ProcessData
    from utils.db import DBHandling

log = get_logger(__name__)

def handle_search_word(word: str, limit: int, bp_prefix: str, is_api_call: bool = False):
    """
    Search a JP or EN word, return max number of found result (`limit`).
    Returns empty list if word not found.
    
    Output: jsonify the list of `Word`s
    """
    res: List[dict] = []
    db = get_dbhandling()

    if is_japanese_word(word):
        res = db.query_like_word(word, limit, parse_dict=True)
    elif is_english_word(word):
        res = db.query_word_sense(word, limit, parse_dict=True)
    else:
        return jsonify(error="Only accept Japanese or English word"), 400

    # For API, just return
    if is_api_call:
        return jsonify(results=res, bpPrefix=bp_prefix), 200
    
    # Modify senses to only have the first meaning for UI
    for w in res:
        w["senses"] = db.get_meanings(w["word"], w["senses"])[0]
    return jsonify(results=res, bpPrefix=bp_prefix)

def handle_view_specific_word(word: str, sentence_limit: int) -> Tuple[dict, List[str]]:
    """
    Handle viewing a JP word with `sentence_limit` amount of sentence examples.
    """
    db = get_dbhandling()
    res: dict = db.get_exact_word(word, parse_dict=True)
    res["meanings"] = [chunk.strip() for chunk in res["senses"].split(";") if chunk.strip()]
    sentence_examples = db.get_sentences_containing_word(word, sentence_limit)
    return res, sentence_examples

def handle_view_words(jlpt_level: str = "", star: bool = False, limit: int = DEFAULT_LIMIT,
                      page: int = 1) -> Tuple[List[dict], int]:
    """
    Handle viewing a list of `limit` JP words with their 1st EN meaning.
    
    Output: a list containing dicts with below format:
        - word: the JP word
        - spelling: the Kata spelling
        - senses: the 1st EN meaning. Still make the key as `senses` to line up
        with handle_search_word()
    """
    db = get_dbhandling()
    # Save count to cache until insert endpoint
    key = tuple(f"{jlpt_level}::{star}")
    if key not in view_word_count_cache:
        view_word_count_cache[key] = db.count_words(jlpt_level, star)

    page_count = int(math.ceil(view_word_count_cache[key] / limit))
    if page > page_count:
        return [], page_count
    return db.list_words(jlpt_level, star, limit, limit*(page-1)), page_count
