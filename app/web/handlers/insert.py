from typing import TYPE_CHECKING
import os

from app.common import do_insert_word_sentence_book_2_db
from handlers.helpers import do_insert_book, str_2_byte, reset_view_word_count
from utils.logger import get_logger

if TYPE_CHECKING:
    from utils.data import ProcessData
    from utils.db import DBHandling

log = get_logger(__name__)

def handle_insert_file(pdata: "ProcessData", db: "DBHandling", filename: str, saved_tmp_path: str, is_api_call: bool = False):
    """
    Handle input-ing a file, check file exist, insert as book (the book name is the file name),
    sentences, words to DB and link word-book, word-sentence, sentence-book IDs.

    Input:
    - pdata: ProcessData instance
    - db: DBHandling instance
    - filename: the filename to be use as book's name, only the name, no path.
    - saved_tmp_path: the full path of the saved tmp file if use UI, or the og file if use API calls

    Output: if is_api_call, return dict. Otherwise, yield bytes to show on UI.
    """
    if not filename or not saved_tmp_path:
        if is_api_call:
            return {"error": "No file selected"}
        yield str_2_byte("Error: No file selected")
        return
    
    reset_view_word_count()
    
    book_id, resp = int(0), None
    content_len = os.path.getsize(saved_tmp_path)
    
    progress = 0
    # Does not strip now to keep originality for book insertion
    for sentence in pdata.stream_sentences_file(saved_tmp_path, auto_strip=False):
        # Insert book sentence by sentence
        if not progress:
            # First time will create new row
            book_id, resp = do_insert_book(db, filename, sentence)
            if resp:
                if is_api_call:
                    return resp
                yield str_2_byte(str(resp))
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
        return {"message": f"Processed and inserted {filename}"}
    yield str_2_byte(f"Processed and inserted {filename}")

def handle_insert_str(pdata: "ProcessData", db: "DBHandling", name: str, data: str, is_api_call: bool = False):
    """
    Handle input-ing a string, insert as book, sentences, words to DB
    and link word-book, word-sentence, sentence-book IDs.

    Input:
    - pdata: ProcessData instance
    - db: DBHandling instance
    - name: the name to be use as book's name.
    - data: the JP text to be processed and inserted.

    Output: return dict for API or yield bytes for UI
    """
    if not name or not data:
        return {"error": "Missing name or text"}

    reset_view_word_count()

    content_len = len(data)
    book_id, resp = do_insert_book(db, name, data)
    if resp:
        if is_api_call:
            return resp
        yield str_2_byte(str(resp))
        return
    
    progress = 0
    for sentence in pdata.stream_sentences_str(data):
        do_insert_word_sentence_book_2_db(pdata, db, sentence, book_id)
        progress += len(sentence)
        # use "data: " to mark the progress display for JS
        if not is_api_call:
            yield str_2_byte(f"data: Processing... {((progress/content_len)*100):.2f}%\n\n")
    
    if is_api_call:
        return {"message": "Processed and inserted text"}
    yield str_2_byte(f"Processed and inserted text")
