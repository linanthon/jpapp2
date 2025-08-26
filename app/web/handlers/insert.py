from flask import Response
from typing import TYPE_CHECKING
import os

from app.common import do_insert_word_sentence_book_2_db
from handlers.helpers import get_processdata, get_dbhandling, do_insert_book, str_2_byte
from utils.logger import get_logger

if TYPE_CHECKING:
    from utils.data import ProcessData
    from utils.db import DBHandling

log = get_logger(__name__)

def handle_insert_file(filename: str, saved_tmp_path: str, is_api_call: bool = False):
    """
    Handle input-ing a file, check file exist, insert as book (the book name is the file name),
    sentences, words to DB and link word-book, word-sentence, sentence-book IDs.

    Input:
    - filename: the filename to be use as book's name, only the name, no path.
    - saved_tmp_path: the full path of the saved tmp file if use UI, or the og file if use API calls

    Output: if is_api_call, return flask Response. Otherwise, yield bytes to show on UI.
    """
    if not filename or not saved_tmp_path:
        if is_api_call:
            return Response("Error: No file selected", 400)
        yield str_2_byte("Error: No file selected")
        return
    
    pdata, db = get_processdata(), get_dbhandling()
    book_id, resp, data = int(0), None, None
    with open(saved_tmp_path, "r", encoding="utf-8") as f:
        data = f.read()
        book_id, resp = do_insert_book(db, filename, data)
    # If has resp, something was wrong -> return
    if resp:
        if is_api_call:
            return resp
        yield str_2_byte(resp.get_data(as_text=True))
        return
    
    content_len = len(data)
    progress = 0
    for sentence in pdata.stream_sentences_file(saved_tmp_path):
        do_insert_word_sentence_book_2_db(pdata, db, sentence, book_id)
        progress += len(sentence)
        # use "data: " to mark the progress display for JS
        if not is_api_call:
            yield str_2_byte(f"data: Processing... {((progress/content_len)*100):.2f}%\n\n")

    # If is saved file (not API call), remove tmp file
    if not is_api_call:
        os.remove(saved_tmp_path)

    if is_api_call:
        return Response(f"Processed and inserted {filename}", 200)
    yield str_2_byte(f"Processed and inserted {filename}")

def handle_insert_str(name: str, data: str):
    """
    Handle input-ing a string, insert as book, sentences, words to DB
    and link word-book, word-sentence, sentence-book IDs.

    Input:
    - name: the name to be use as book's name.
    - data: the JP text to be processed and inserted.

    Output: return flask Response
    """
    if not name or not data:
        return Response("Error: Missing name or text", 400)

    pdata, db = get_processdata(), get_dbhandling()
    book_id, resp = do_insert_book(db, name, data)
    # If has resp, something was wrong -> return
    if resp:
        return resp
    
    for sentence in pdata.stream_sentences_str(data):
        do_insert_word_sentence_book_2_db(pdata, db, sentence, book_id)
    return Response(f"Processed and inserted text", 200)
