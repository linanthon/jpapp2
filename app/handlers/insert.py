from typing import TYPE_CHECKING, Tuple
import os
from http import HTTPStatus

from app.handlers.view import reset_view_word_count
from utils.helpers import str_2_byte
from utils.db import DBHandling
from utils.logger import get_logger

if TYPE_CHECKING:
    from fastapi import UploadFile
    from utils.process_data import ProcessData
    import redis.asyncio as aioredis

log = get_logger(__name__)

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


async def handle_insert_file_stream(pdata: "ProcessData", db: "DBHandling", redis: "aioredis.Redis", book_id: int, submittedFile: "UploadFile"):
    """
    Handle input-ing a file, check file exist, insert as book (the book name is the file name),
    sentences, words to DB and link word-book, word-sentence, sentence-book IDs.

    Input:
    - pdata: ProcessData instance
    - db: DBHandling instance
    - book_id: the book ID
    - filename: the filename to be use as book's name, only the name, no path.

    Output: bytes of response data or error dict
    """    
    reset_view_word_count()
    content_len = submittedFile.size or 1
    
    progress = 0
    for sentence in pdata.stream_sentences_file(submittedFile, auto_strip=True):
        await do_insert_word_sentence_book_2_db(pdata, db, sentence.strip("\n").strip(), book_id)
        progress += len(sentence)
        # use "data: " to mark the progress display for JS
        await redis.set(f"book_progress:{book_id}", f"data: Processing... {((progress/content_len)*100):.2f}%\n\n")
    
    await redis.set(f"book_progress:{book_id}", f"Processed and inserted {submittedFile.filename}")

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
    book_id, resp, _ = await do_insert_book(db, name, data) #TODO: fix later
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
