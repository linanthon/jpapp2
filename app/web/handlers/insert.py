from flask import Response
from typing import TYPE_CHECKING
import os

from app.common import do_insert_word_sentence_book_2_db
from handlers.helpers import get_processdata, get_dbhandling, do_insert_book, str_2_byte, reset_view_word_count
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
    
    reset_view_word_count()
    
    pdata, db = get_processdata(), get_dbhandling()
    book_id, resp = int(0), None
    content_len = os.path.getsize(saved_tmp_path)
    
    progress = 0
    # Does not strip now to keep originality for book insertion
    for sentence in pdata.stream_sentences_file(saved_tmp_path, auto_strip=False):
        # Insert book appendingly
        if not progress:
            # First time will create new row
            book_id, resp = do_insert_book(db, filename, sentence)
            if resp:
                if is_api_call:
                    return resp
                yield str_2_byte(resp.get_data(as_text=True))
                return
        else:
            # append next sentences to the created row 
            db.update_book(book_id=book_id, append_content=sentence)

        do_insert_word_sentence_book_2_db(pdata, db, sentence.strip("\n").strip(), book_id)
        progress += len(sentence)
        # use "data: " to mark the progress display for JS
        if not is_api_call:
            yield str_2_byte(f"data: Processing... {((progress/content_len)*100):.2f}%\n\n")
    
    # If is saved temp file (not API call), remove tmp file
    if not is_api_call:
        os.remove(saved_tmp_path)

    if is_api_call:
        return Response(f"Processed and inserted {filename}", 200)
    yield str_2_byte(f"Processed and inserted {filename}")

def handle_insert_str(name: str, data: str, is_api_call: bool = False):
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

    reset_view_word_count()

    content_len = len(data)
    pdata, db = get_processdata(), get_dbhandling()
    book_id, resp = do_insert_book(db, name, data)
    if resp:
        if is_api_call:
            return resp
        yield str_2_byte(resp.get_data(as_text=True))
        return
    
    progress = 0
    for sentence in pdata.stream_sentences_str(data):
        do_insert_word_sentence_book_2_db(pdata, db, sentence, book_id)
        progress += len(sentence)
        # use "data: " to mark the progress display for JS
        if not is_api_call:
            yield str_2_byte(f"data: Processing... {((progress/content_len)*100):.2f}%\n\n")
    
    if is_api_call:
        return Response(f"Processed and inserted text", 200)
    yield str_2_byte(f"Processed and inserted text")
