import random
from schemas.constants import DEFAULT_LIMIT

from handlers.helpers import get_dbhandling, get_processdata
from utils.data import get_quiz_distractors

def get_word_jp_quizes(jlpt_level: str = None, star: bool = False, book_id: int = 0, limit: int = DEFAULT_LIMIT,
                       use_priority: bool = True, get_distractors_from_db: bool = True):
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
    """
    db = get_dbhandling()
    pdata = get_processdata()

    res = {}
    tests = db.get_quiz(limit=limit, jlpt_filter=jlpt_level, star_only=star, book_id=book_id,
                        use_priority=use_priority)
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
            "occurrence": test_case.occurrence
        }
    return res


def update_word_prio_after_answering(word_id: int = 0, is_correct: bool = False,
                                     quized: int = 0, occurrence: int = 0) -> bool:
    """Update answered quiz's word priority calculation.
    Return true if success, false otherwise"""
    db = get_dbhandling()
    new_quized = quized + 1 if is_correct else max(0, quized - 1)
    return db.update_quized_prio_ts(word_id=word_id, occurrence=occurrence, quized=new_quized)
