from typing import TYPE_CHECKING
from utils.logger import get_logger

if TYPE_CHECKING:
    from utils.data import ProcessData
    from utils.db import DBHandling

log = get_logger(__name__)


def do_insert_word_sentence_book_2_db(pdata: "ProcessData", db: "DBHandling", sentence: str, book_id: int) -> None:
    """
    Insert sentence, update occurrence if already in DB.

    Insert each word in a sentence (does not include symbols, stopwords, numbers),
    update occurrence and new priority (for quiz) if already in DB.

    Insert references of the word-book, word-sentence, sentence-book
    """
    # Insert sentence
    sentence_id = db.insert_update_sentence(sentence)
    
    # Insert words
    words = pdata.process_sentence(sentence, db)
    for word in words:
        word_id = db.insert_word(word)

        # Insert references
        if word_id and sentence_id and book_id:
            db.insert_word_book_ref(word_id, book_id)
            db.insert_word_sentence_ref(word_id, sentence_id)
            db.insert_sentence_book_ref(sentence_id, book_id)
