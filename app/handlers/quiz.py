import random
from typing import TYPE_CHECKING, Dict, Any

from schemas.constants import DEFAULT_LIMIT
from utils.data import get_quiz_distractors

if TYPE_CHECKING:
    from utils.process_data import ProcessData
    from utils.db import DBHandling

async def build_quizes(mode: str, pdata: "ProcessData", db: "DBHandling", user_id: int = None,
                       limit: int = DEFAULT_LIMIT, jlpt_level: str = None, star: bool = False,
                       book_id: int = None, use_priority: bool = True,
                       is_known: bool = False, get_distractors_from_db: bool = True) -> Dict[int, Dict[str, Any]]:
    """Quiz builder. `mode` is 'jp' (JP->EN) or 'en' (EN->JP).

    Returns a dict keyed by word_id, each value containing:
    - question, spelling, audio_mapping, correct, choices, quized, occurrence, star
    For 'jp' mode: question=JP, correct=EN, includes spelling/audio.
    For 'en' mode: question=EN, correct=JP, spelling/audio are empty.
    """
    res = {}
    tests = await db.get_quiz(user_id=user_id, limit=limit, jlpt_filter=jlpt_level, star_only=star,
                        book_id=book_id, use_priority=use_priority, is_known=is_known)
    for test_case in tests:
        distractors = await get_quiz_distractors(pdata, db, test_case["jp"], test_case["en"], get_distractors_from_db)
        if mode == "jp":
            question, correct = test_case["jp"], test_case["en"]
            choices = [test_case["en"]] + list(distractors.en)
            spelling, audio = test_case["spelling"], test_case["audio_mapping"]
        else:
            question, correct = test_case["en"], test_case["jp"]
            choices = [test_case["jp"]] + list(distractors.jp)
            spelling, audio = "", []
        random.shuffle(choices)
        res[test_case["word_id"]] = {
            "question": question,
            "spelling": spelling,
            "audio_mapping": audio,
            "correct": correct,
            "choices": choices,
            "quized": test_case["quized"],
            "occurrence": test_case["occurrence"],
            "star": test_case["star"]
        }
    return res

async def update_word_prio_after_answering(db: "DBHandling", user_id: int = 0, word_id: int = 0,
                                     is_correct: bool = False, quized: int = 0, occurrence: int = 0) -> bool:
    """Update answered quiz's word priority calculation.
    Return true if success, false otherwise"""
    new_quized = quized + 1 if is_correct else max(0, quized - 1)
    return await db.update_quized_prio_ts(user_id=user_id, word_id=word_id, occurrence=occurrence, quized=new_quized)

async def change_word_prio_to_negative(db: "DBHandling", user_id: int = 0, word_id: int = 0) -> bool:
    """Update the word priority value to -1 (to fail the > 0.0 check when query for quiz).
    Returns true if success, false otherwise"""
    return await db.update_words_known(user_id=user_id, word_ids=[word_id])

async def reset_word_prio(db: "DBHandling", user_id: int = 0, word_id: int = 0,
                    occurrence: int = None, quized: int = None) -> bool:
    """Re-calculate priority for the word.
    `quized` and `occurrence` are optional. Will query to get if they are None.
    Returns true if success, false otherwise"""
    if occurrence is None or quized is None:
        occurrence, quized = await db.get_word_occurence(word_id=word_id)
    # quized can = 0 but not occurrence
    if not occurrence:
        return False
    # call calculate prio
    return await db.update_quized_prio_ts(user_id=user_id, word_id=word_id, occurrence=occurrence, quized=quized)
