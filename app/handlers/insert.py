from typing import TYPE_CHECKING, Tuple
import os
from http import HTTPStatus

from app.handlers.view import reset_view_word_count
from utils.helpers import str_2_byte
from utils.db import DBHandling
from utils.logger import get_logger

if TYPE_CHECKING:
    from utils.process_data import ProcessData

log = get_logger(__name__)


async def do_insert_book(db: DBHandling, name: str, data: str = "") -> Tuple[int, dict | None, int]:
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
    
    book_id = await db.insert_book(name, data)
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

async def do_insert_word_sentence_book_2_db(pdata: "ProcessData", db: "DBHandling", sentence: str, book_id: int) -> None:
    """
    Insert sentence, update occurrence if already in DB.

    Insert each word in a sentence (does not include symbols, stopwords, numbers),
    update occurrence and new priority (for quiz) if already in DB.

    Insert references of the word-book, word-sentence, sentence-book
    """
    # Insert sentence
    sentence_id = await db.insert_update_sentence(sentence)
    
    # Insert words
    words = await pdata.process_sentence(sentence, db)
    for word in words:
        word_id = await db.insert_word(word)

        # Insert references if sentece and word insert/updated successfully
        if word_id and sentence_id and book_id:
            await db.insert_word_book_ref(word_id, book_id)
            await db.insert_word_sentence_ref(word_id, sentence_id)
            await db.insert_sentence_book_ref(sentence_id, book_id)


async def handle_insert_file_stream(pdata: "ProcessData", db: "DBHandling", filename: str, saved_tmp_path: str):
    """
    Handle input-ing a file, check file exist, insert as book (the book name is the file name),
    sentences, words to DB and link word-book, word-sentence, sentence-book IDs.

    Input:
    - pdata: ProcessData instance
    - db: DBHandling instance
    - filename: the filename to be use as book's name, only the name, no path.
    - saved_tmp_path: the full path of the saved tmp file if use UI, or the og file if use API calls

    Output: bytes of response data or error dict
    """
    if not filename or not saved_tmp_path:
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
            book_id, resp, _ = await do_insert_book(db, filename, sentence)
            if resp:
                yield str_2_byte(str(resp))
                return
        else:
            # append next sentences to the created row 
            await db.update_book(book_id=book_id, append_content=sentence)

        await do_insert_word_sentence_book_2_db(pdata, db, sentence.strip("\n").strip(), book_id)
        progress += len(sentence)
        # use "data: " to mark the progress display for JS
        yield str_2_byte(f"data: Processing... {((progress/content_len)*100):.2f}%\n\n")
    
    # Remove tmp file
    os.remove(saved_tmp_path)
    yield str_2_byte(f"Processed and inserted {filename}")

async def handle_insert_str_stream(pdata: "ProcessData", db: "DBHandling", name: str, data: str):
    """
    Handle input-ing a string, insert as book, sentences, words to DB
    and link word-book, word-sentence, sentence-book IDs.

    Input:
    - pdata: ProcessData instance
    - db: DBHandling instance
    - name: the name to be use as book's name
    - data: the JP text to be processed and inserted

    Output: bytes of response data or error dict
    """
    if not name or not data:
        yield str_2_byte("Error: Missing name or text")
        return

    reset_view_word_count()

    content_len = len(data)
    book_id, resp, _ = await do_insert_book(db, name, data)
    if resp:
        yield str_2_byte(str(resp))
        return
    
    progress = 0
    for sentence in pdata.stream_sentences_str(data):
        await do_insert_word_sentence_book_2_db(pdata, db, sentence, book_id)
        progress += len(sentence)
        # use "data: " to mark the progress display for JS
        yield str_2_byte(f"data: Processing... {((progress/content_len)*100):.2f}%\n\n")
    
    yield str_2_byte(f"Processed and inserted text")
