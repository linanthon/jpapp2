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
        - correct - the EN (first meaning in senses)
        - choices - a list of all 4 choices (shuffled)
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
            "choices": choices
        }
    return res

def aaa():
    # ans = input(f"{i+1}. '{test_case.jp}' meaning is? ({random_choices}): ")
    # # Update quized and priority if correct
    # if ans == test_case.en:
    #     print("Correct!")
    #     db.update_quized_prio_ts(test_case.jp, test_case.occurrence, test_case.quized+1)
    # else:
    #     print(f"Wrong! The correct meaning should be: {test_case.en}")
    #     if test_case.quized > 0:
    #         decr_prio = test_case.quized-1
    #         db.update_quized_prio_ts(test_case.jp, test_case.occurrence, decr_prio)
    pass