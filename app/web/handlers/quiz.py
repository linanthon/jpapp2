import random
from typing import TYPE_CHECKING, Dict, Any

from schemas.constants import DEFAULT_LIMIT
from utils.data import get_quiz_distractors

if TYPE_CHECKING:
    from utils.data import ProcessData
    from utils.db import DBHandling

def get_word_jp_quizes(pdata: "ProcessData" = None, db: "DBHandling" = None, user_id: int = None, limit: int = DEFAULT_LIMIT, 
                       jlpt_level: str = None, star: bool = False, book_id: int = None, use_priority: bool = True,
                       is_known: bool = False, get_distractors_from_db: bool = True) -> Dict[int, Dict[str, Any]]:
    """Get JP->EN quizes. Return a dict:
    - key: word ID
    - value: a dict of items:
        - question - the JP
        - spelling - the Katakana spelling
        - audio_mapping - the audio mapping list for this word
        - correct - the EN (first meaning in senses)
        - choices - a list of all 4 choices (shuffled)
        - quized - the number of correct times
        - occurrence - the total appearance count of this word in DB
        - star - the word starred or not
    """
    res = {}
    tests = db.get_quiz(user_id=user_id, limit=limit, jlpt_filter=jlpt_level, star_only=star,
                        book_id=book_id, use_priority=use_priority, is_known=is_known)
    for test_case in tests:
        # randomize correct answer location
        choices = [test_case.en]
        choices.extend(get_quiz_distractors(pdata, db, test_case.jp, test_case.en, get_distractors_from_db).en)
        random.shuffle(choices)
        # save to return
        res[test_case.word_id] = {
            "question": test_case.jp,
            "spelling": test_case.spelling,
            "audio_mapping": test_case.audio_mapping,
            "correct": test_case.en,
            "choices": choices,
            "quized": test_case.quized,
            "occurrence": test_case.occurrence,
            "star": test_case.star
        }
    return res

def update_word_prio_after_answering(db: "DBHandling", user_id: int = 0, word_id: int = 0,
                                     is_correct: bool = False, quized: int = 0, occurrence: int = 0) -> bool:
    """Update answered quiz's word priority calculation.
    Return true if success, false otherwise"""
    new_quized = quized + 1 if is_correct else max(0, quized - 1)
    return db.update_quized_prio_ts(user_id=user_id, word_id=word_id, occurrence=occurrence, quized=new_quized)

def change_word_prio_to_negative(db: "DBHandling", word_id: int = 0) -> bool:
    """Update the word priority value to -1 (to fail the > 0.0 check when query for quiz).
    Returns true if success, false otherwise"""
    return db.update_words_known(word_ids=[word_id])

def reset_word_prio(db: "DBHandling", user_id: int = 0, word_id: int = 0,
                    occurrence: int = None, quized: int = None) -> bool:
    """Re-calculate priority for the word.
    `quized` and `occurrence` are optional. Will query to get if they are None.
    Returns true if success, false otherwise"""
    if occurrence is None or quized is None:
        occurrence, quized = db.get_word_occurence_quized(word_id=word_id)
    # quized can = 0 but not occurrence
    if not occurrence:
        return False
    # call calculate prio
    return db.update_quized_prio_ts(user_id=user_id, word_id=word_id, occurrence=occurrence, quized=quized)

def get_word_en_quizes(pdata: "ProcessData" = None, db: "DBHandling" = None, user_id: int = None, limit: int = DEFAULT_LIMIT,
                       jlpt_level: str = None, star: bool = False, book_id: int = None, use_priority: bool = True,
                       is_known: bool = False, get_distractors_from_db: bool = True) -> Dict[int, Dict[str, Any]]:
    """Get EN->JP quizes. Return a dict:
    - key: word ID
    - value: a dict of items:
        - question - the EN (first meaning of the JP word)
        - correct - the JP word
        - choices - a list of all 4 choices (shuffled)
        - quized - the number of correct times
        - occurrence - the total appearance count of this word in DB
        - star - the word starred or not
    """
    res = {}
    tests = db.get_quiz(user_id=user_id, limit=limit, jlpt_filter=jlpt_level, star_only=star,
                        book_id=book_id, use_priority=use_priority, is_known=is_known)
    for test_case in tests:
        # randomize correct answer location
        choices = [test_case.jp]
        choices.extend(get_quiz_distractors(pdata, db, test_case.jp, test_case.en, get_distractors_from_db).jp)
        random.shuffle(choices)
        # save to return
        res[test_case.word_id] = {
            "question": test_case.en,
            "spelling": "",
            "audio_mapping": [],
            "correct": test_case.jp,
            "choices": choices,
            "quized": test_case.quized,
            "occurrence": test_case.occurrence,
            "star": test_case.star
        }
    return res
