from flask import Response, jsonify
from typing import TYPE_CHECKING, List
import os

from handlers.helpers import str_2_byte, get_dbhandling
from schemas.word import Word
from utils.data import is_japanese_word, is_english_word
from utils.logger import get_logger


if TYPE_CHECKING:
    from utils.data import ProcessData
    from utils.db import DBHandling

log = get_logger(__name__)

def handle_search_word(word: str, limit: int, is_api_call: bool = False):
    """
    
    Output:
    - is api call: jsonify the list of `Word`s
    """
    res: List[Word] = []
    db = get_dbhandling()

    if is_japanese_word(word):
        res = db.query_like_word(word, limit)
    elif is_english_word(word):
        res = db.query_word_sense(word, limit)
    else:
        return jsonify(error="Only accept Japanese or English word"), 400

    if not res:
        return jsonify(error="Word not found"), 404

    # For API, just return
    if is_api_call:
        return jsonify(results=[w.to_dict() for w in res]), 200
    
    # Modify senses to only have the first meaning for UI
    for w in res:
        w.senses = db.get_meanings(w.word, w.senses)[0]
    return jsonify(results=[w.to_dict() for w in res])
    