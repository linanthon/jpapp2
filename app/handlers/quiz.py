import random
from typing import TYPE_CHECKING, Dict, Any

from app.config import WORD_CORE_CACHE_EXPIRE_SECONDS
from app.dependencies import (word_core_cache_key,
                        redis_get_json_sliding, redis_set_json, extract_word_core_payload)
from schemas.constants import DEFAULT_LIMIT
from utils.data import get_quiz_distractors
from utils.helpers import parse_bool_param

if TYPE_CHECKING:
    from utils.process_data import ProcessData
    from utils.db import DBHandling
    import redis.asyncio as aioredis

async def build_quizes(mode: str, pdata: "ProcessData", db: "DBHandling", user_id: int = None,
                       limit: int = DEFAULT_LIMIT, jlpt_level: str = None, star: bool = False,
                       book_id: int = None, use_priority: bool = True,
                       is_known: bool = False, get_distractors_from_db: bool = True,
                       redis: "aioredis" = None) -> Dict[int, Dict[str, Any]]:
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
        if redis is not None:
            core_key = word_core_cache_key(test_case["word_id"])
            cached_core = await redis_get_json_sliding(redis, core_key, WORD_CORE_CACHE_EXPIRE_SECONDS)
            if not cached_core:
                core_from_db = await db.get_exact_word(word_id=test_case["word_id"])
                core_payload = extract_word_core_payload(core_from_db)
                if core_payload:
                    await redis_set_json(
                        redis, core_key, core_payload, WORD_CORE_CACHE_EXPIRE_SECONDS,
                    )

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
                                     is_correct: bool = False, quized: int = None, occurrence: int = None) -> bool:
    """Update answered quiz's word priority calculation.
    Return true if success, false otherwise"""
    if not word_id:
        return False

    # Fallback to DB state when client did not send current values.
    if occurrence is None or quized is None:
        _, occurrence_db = await db.get_word_occurence(word_id=word_id)
        if not occurrence_db:
            return False
        occurrence = occurrence_db
        quized = await db.get_user_word_quized(user_id=user_id, word_id=word_id)

    new_quized = quized + 1 if is_correct else max(0, quized - 1)
    return await db.update_quized_prio_ts(user_id=user_id, word_id=word_id, occurrence=occurrence, quized=new_quized)


async def update_word_prio_after_session(db: "DBHandling", user_id: int,
                                         answers: list[dict[str, Any]]) -> dict[str, int]:
    """Apply quiz priority updates in one request after a session.

    `answers` expects items with at least:
      - word_id: int
      - is_correct: bool
    Optional per item:
      - occurrence: int
      - quized: int

    Multiple answers for the same word are aggregated into one DB update.
    Returns stats: total, updated, failed.
    """
    if not answers:
        return {"total": 0, "updated": 0, "failed": 0}

    # word_id -> {delta, occurrence, quized}
    # `delta` is for the same word showed up multiple times in 1 quiz
    grouped: dict[int, dict[str, Any]] = {}
    for answer in answers:
        try:
            word_id = int(answer.get("word_id", 0))
        except Exception:
            continue
        if not word_id:
            continue

        is_correct = parse_bool_param(answer.get("is_correct", False))
        delta = 1 if is_correct else -1

        item = grouped.setdefault(word_id, {"delta": 0, "occurrence": None, "quized": None})
        item["delta"] += delta

        if answer.get("occurrence", None) is not None:
            try:
                item["occurrence"] = int(answer.get("occurrence"))
            except Exception:
                pass
        if answer.get("quized", None) is not None:
            try:
                item["quized"] = int(answer.get("quized"))
            except Exception:
                pass

    total = len(grouped)
    updated = 0

    # Collect words missing either occurrence or quized and fetch them in one DB query.
    missing_word_ids = {
        word_id for word_id, item in grouped.items()
        if item["occurrence"] is None or item["quized"] is None
    }
    missing_word_data = {}
    if missing_word_ids:
        missing_word_data = await db.get_words_occurrence_quized_batch(
            user_id=user_id,
            word_ids=list(missing_word_ids),
        )

    for word_id, item in grouped.items():
        occurrence = item["occurrence"]
        current_quized = item["quized"]

        if occurrence is None or current_quized is None:
            meta = missing_word_data.get(word_id, {})
            occurrence_db = meta.get("occurrence", 0)
            if not occurrence_db:
                continue
            occurrence = occurrence_db
            current_quized = meta.get("quized", 0)

        new_quized = max(0, current_quized + item["delta"])
        success = await db.update_quized_prio_ts(
            user_id=user_id,
            word_id=word_id,
            occurrence=occurrence,
            quized=new_quized,
        )
        if success:
            updated += 1

    return {"total": total, "updated": updated, "failed": max(0, total - updated)}

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
        _, occurrence_db = await db.get_word_occurence(word_id=word_id)
        if not occurrence_db:
            return False
        occurrence = occurrence_db
        quized = await db.get_user_word_quized(user_id=user_id, word_id=word_id)
    # quized can = 0 but not occurrence
    if not occurrence:
        return False
    # call calculate prio
    return await db.update_quized_prio_ts(user_id=user_id, word_id=word_id, occurrence=occurrence, quized=quized)
