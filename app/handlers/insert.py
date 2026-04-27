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


async def _process_sentences(pdata: "ProcessData", db: "DBHandling", redis: "aioredis.Redis",
                             book_id: int, sentences, content_len: int, done_msg: str):
    """Shared logic: iterate sentences, insert words/refs, report progress via Redis."""
    reset_view_word_count()
    progress = 0
    for sentence in sentences:
        await do_insert_word_sentence_book_2_db(pdata, db, sentence.strip("\n").strip(), book_id)
        progress += len(sentence)
        await redis.set(f"book_progress:{book_id}", f"data: Processing... {((progress/content_len)*100):.2f}%\n\n")

    await redis.set(f"book_progress:{book_id}", done_msg)


async def handle_insert_file_stream(pdata: "ProcessData", db: "DBHandling", redis: "aioredis.Redis", book_id: int, submittedFile: "UploadFile"):
    """
    Handle input-ing a file, check file exist, insert as book (the book name is the file name),
    sentences, words to DB and link word-book, word-sentence, sentence-book IDs.

    Input:
    - pdata: ProcessData instance
    - db: DBHandling instance
    - book_id: the book ID
    - submittedFile: the file user submitted in frontend

    Output: bytes of response data or error dict
    """
    await _process_sentences(
        pdata, db, redis, book_id,
        sentences=pdata.stream_sentences_file(submittedFile, auto_strip=True),
        content_len=submittedFile.size or 1,
        done_msg=f"Processed and inserted {submittedFile.filename}",
    )

async def handle_insert_str_stream(pdata: "ProcessData", db: "DBHandling", redis: "aioredis.Redis", book_id: int, data: str):
    """
    Handle input-ing a string, insert as book, sentences, words to DB
    and link word-book, word-sentence, sentence-book IDs.

    Input:
    - pdata: ProcessData instance
    - db: DBHandling instance
    - redis: Redis
    - book_id: the inserted book ID
    - data: the JP text to be processed and inserted

    Output: bytes of response data or error dict
    """
    await _process_sentences(
        pdata, db, redis, book_id,
        sentences=pdata.stream_sentences_str(data),
        content_len=len(data) or 1,
        done_msg="Processed and inserted text",
    )
