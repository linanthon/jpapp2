from flask import Response, jsonify
from typing import TYPE_CHECKING, List, Tuple
import os

from handlers.helpers import str_2_byte, get_dbhandling
from schemas.word import Word
from utils.data import is_japanese_word, is_english_word
from utils.logger import get_logger


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

def handle_view_word(word: str, sentence_limit: int) -> Tuple[dict, List[str]]:
    """
    Handle viewing a JP word with `sentence_limit` amount of sentence examples.
    """
    db = get_dbhandling()
    res: dict = db.get_exact_word(word, parse_dict=True)
    res["meanings"] = [chunk.strip() for chunk in res["senses"].split(";") if chunk.strip()]
    sentence_examples = db.get_sentences_containing_word(word, sentence_limit)
    return res, sentence_examples
