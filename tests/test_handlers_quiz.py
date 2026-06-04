"""Tests for app/handlers/quiz.py — quiz logic with mocked DB."""
import pytest
from unittest.mock import patch
from app.handlers.quiz import (
    build_quizes,
    update_word_prio_after_answering,
    update_word_prio_after_session,
    change_word_prio_to_negative,
    reset_word_prio,
)


# ── update_word_prio_after_answering ──────────────────────────────────────────
class TestUpdateWordPrioAfterAnswering:
    @pytest.mark.asyncio
    async def test_correct_answer_increments_quized(self, mock_db):
        mock_db.update_quized_prio_ts.return_value = True
        result = await update_word_prio_after_answering(
            mock_db, user_id=1, word_id=10, is_correct=True, quized=5, occurrence=10
        )
        assert result is True
        mock_db.update_quized_prio_ts.assert_called_once_with(
            user_id=1, word_id=10, occurrence=10, quized=6
        )

    @pytest.mark.asyncio
    async def test_wrong_answer_decrements_quized(self, mock_db):
        mock_db.update_quized_prio_ts.return_value = True
        await update_word_prio_after_answering(
            mock_db, user_id=1, word_id=10, is_correct=False, quized=3, occurrence=10
        )
        mock_db.update_quized_prio_ts.assert_called_once_with(
            user_id=1, word_id=10, occurrence=10, quized=2
        )

    @pytest.mark.asyncio
    async def test_wrong_answer_floors_at_zero(self, mock_db):
        mock_db.update_quized_prio_ts.return_value = True
        await update_word_prio_after_answering(
            mock_db, user_id=1, word_id=10, is_correct=False, quized=0, occurrence=10
        )
        mock_db.update_quized_prio_ts.assert_called_once_with(
            user_id=1, word_id=10, occurrence=10, quized=0
        )

    @pytest.mark.asyncio
    async def test_fallback_to_db_values_when_missing_counts(self, mock_db):
        mock_db.get_word_occurence.return_value = (10, 12)
        mock_db.get_user_word_quized.return_value = 4
        mock_db.update_quized_prio_ts.return_value = True

        result = await update_word_prio_after_answering(
            mock_db, user_id=1, word_id=10, is_correct=True
        )

        assert result is True
        mock_db.get_word_occurence.assert_called_once_with(word_id=10)
        mock_db.get_user_word_quized.assert_called_once_with(user_id=1, word_id=10)
        mock_db.update_quized_prio_ts.assert_called_once_with(
            user_id=1, word_id=10, occurrence=12, quized=5
        )


# ── change_word_prio_to_negative ──────────────────────────────────────────────
class TestChangeWordPrioToNegative:
    @pytest.mark.asyncio
    async def test_calls_update_words_known(self, mock_db):
        mock_db.update_words_known.return_value = True
        result = await change_word_prio_to_negative(mock_db, user_id=1, word_id=5)
        assert result is True
        mock_db.update_words_known.assert_called_once_with(user_id=1, word_ids=[5])


# ── reset_word_prio ───────────────────────────────────────────────────────────
class TestResetWordPrio:
    @pytest.mark.asyncio
    async def test_with_values(self, mock_db):
        mock_db.update_quized_prio_ts.return_value = True
        result = await reset_word_prio(mock_db, user_id=1, word_id=5, occurrence=10, quized=3)
        assert result is True
        mock_db.update_quized_prio_ts.assert_called_once_with(
            user_id=1, word_id=5, occurrence=10, quized=3
        )

    @pytest.mark.asyncio
    async def test_queries_when_values_none(self, mock_db):
        mock_db.get_word_occurence.return_value = (5, 12)
        mock_db.get_user_word_quized.return_value = 3
        mock_db.update_quized_prio_ts.return_value = True
        result = await reset_word_prio(mock_db, user_id=1, word_id=5)
        assert result is True
        mock_db.get_word_occurence.assert_called_once_with(word_id=5)
        mock_db.get_user_word_quized.assert_called_once_with(user_id=1, word_id=5)
        mock_db.update_quized_prio_ts.assert_called_once_with(
            user_id=1, word_id=5, occurrence=12, quized=3
        )

    @pytest.mark.asyncio
    async def test_returns_false_when_no_occurrence(self, mock_db):
        mock_db.get_word_occurence.return_value = (0, 0)
        result = await reset_word_prio(mock_db, user_id=1, word_id=5)
        assert result is False


class TestUpdateWordPrioAfterSession:
    @pytest.mark.asyncio
    async def test_aggregates_same_word_and_updates_once(self, mock_db):
        mock_db.get_words_occurrence_quized_batch.return_value = {
            7: {"occurrence": 9, "quized": 4}
        }
        mock_db.update_quized_prio_ts.return_value = True

        result = await update_word_prio_after_session(
            mock_db,
            user_id=1,
            answers=[
                {"word_id": 7, "is_correct": True},
                {"word_id": 7, "is_correct": False},
                {"word_id": 7, "is_correct": True},
            ],
        )

        assert result == {"total": 1, "updated": 1, "failed": 0}
        mock_db.get_words_occurrence_quized_batch.assert_called_once_with(
            user_id=1, word_ids=[7]
        )
        mock_db.update_quized_prio_ts.assert_called_once_with(
            user_id=1, word_id=7, occurrence=9, quized=5
        )

    @pytest.mark.asyncio
    async def test_fetches_all_missing_words_in_one_batch(self, mock_db):
        mock_db.get_words_occurrence_quized_batch.return_value = {
            7: {"occurrence": 9, "quized": 4},
            8: {"occurrence": 12, "quized": 0},
        }
        mock_db.update_quized_prio_ts.return_value = True

        result = await update_word_prio_after_session(
            mock_db,
            user_id=1,
            answers=[
                {"word_id": 7, "is_correct": True},
                {"word_id": 8, "is_correct": False},
            ],
        )

        assert result == {"total": 2, "updated": 2, "failed": 0}
        mock_db.get_words_occurrence_quized_batch.assert_called_once()
        args, kwargs = mock_db.get_words_occurrence_quized_batch.call_args
        assert kwargs["user_id"] == 1
        assert set(kwargs["word_ids"]) == {7, 8}


# ── build_quizes ──────────────────────────────────────────────────────────────
class TestBuildQuizesJp:
    @pytest.mark.asyncio
    async def test_empty_quiz(self, mock_db, mock_pdata):
        mock_db.get_quiz.return_value = []
        res = await build_quizes("jp", mock_pdata, mock_db, user_id=1, limit=5)
        assert res == {}

    @pytest.mark.asyncio
    @patch("app.handlers.quiz.get_quiz_distractors")
    async def test_returns_shuffled_choices(self, mock_get_distractors, mock_db, mock_pdata):
        from schemas.quiz import QuizDistractors
        mock_db.get_quiz.return_value = [
            {
                "word_id": 1, "jp": "食べる", "en": "to eat", "spelling": "タベル",
                "audio_mapping": ["ta", "be", "ru"], "quized": 3, "occurrence": 10, "star": False,
            }
        ]
        mock_get_distractors.return_value = QuizDistractors(
            jp=["飲む", "走る", "寝る"], en=["to drink", "to run", "to sleep"]
        )
        res = await build_quizes("jp", mock_pdata, mock_db, user_id=1, limit=5)
        assert 1 in res
        quiz = res[1]
        assert quiz["question"] == "食べる"
        assert quiz["correct"] == "to eat"
        assert len(quiz["choices"]) == 4
        assert "to eat" in quiz["choices"]

    @pytest.mark.asyncio
    @patch("app.handlers.quiz.get_quiz_distractors")
    async def test_backfills_when_strict_filter_returns_too_few(self, mock_get_distractors, mock_db, mock_pdata):
        from schemas.quiz import QuizDistractors
        mock_db.get_quiz.side_effect = [
            [
                {
                    "word_id": 1, "jp": "食べる", "en": "to eat", "spelling": "タベル",
                    "audio_mapping": ["ta", "be", "ru"], "quized": 3, "occurrence": 10, "star": False,
                }
            ],
            [
                {
                    "word_id": 2, "jp": "飲む", "en": "to drink", "spelling": "ノム",
                    "audio_mapping": ["no", "mu"], "quized": 1, "occurrence": 5, "star": False,
                }
            ],
        ]
        mock_get_distractors.return_value = QuizDistractors(
            jp=["走る", "寝る", "読む"], en=["to run", "to sleep", "to read"]
        )

        res = await build_quizes("jp", mock_pdata, mock_db, user_id=1, limit=2)

        assert len(res) == 2
        assert set(res.keys()) == {1, 2}
        assert mock_db.get_quiz.call_count == 2

    @pytest.mark.asyncio
    @patch("app.handlers.quiz.get_quiz_distractors")
    async def test_backfills_from_non_positive_priority_when_still_short(self, mock_get_distractors, mock_db, mock_pdata):
        from schemas.quiz import QuizDistractors
        mock_db.get_quiz.side_effect = [
            [
                {
                    "word_id": 1, "jp": "食べる", "en": "to eat", "spelling": "タベル",
                    "audio_mapping": ["ta", "be", "ru"], "quized": 3, "occurrence": 10, "star": False,
                }
            ],
            [],
            [
                {
                    "word_id": 3, "jp": "読む", "en": "to read", "spelling": "ヨム",
                    "audio_mapping": ["yo", "mu"], "quized": 50, "occurrence": 2, "star": False,
                },
                {
                    "word_id": 4, "jp": "書く", "en": "to write", "spelling": "カク",
                    "audio_mapping": ["ka", "ku"], "quized": 45, "occurrence": 1, "star": False,
                },
            ],
        ]
        mock_get_distractors.return_value = QuizDistractors(
            jp=["走る", "寝る", "飲む"], en=["to run", "to sleep", "to drink"]
        )

        res = await build_quizes("jp", mock_pdata, mock_db, user_id=1, limit=3)

        assert len(res) == 3
        assert set(res.keys()) == {1, 3, 4}
        assert mock_db.get_quiz.call_count == 3


class TestBuildQuizesEn:
    @pytest.mark.asyncio
    async def test_empty_quiz(self, mock_db, mock_pdata):
        mock_db.get_quiz.return_value = []
        res = await build_quizes("en", mock_pdata, mock_db, user_id=1, limit=5)
        assert res == {}

    @pytest.mark.asyncio
    @patch("app.handlers.quiz.get_quiz_distractors")
    async def test_returns_jp_as_choices(self, mock_get_distractors, mock_db, mock_pdata):
        from schemas.quiz import QuizDistractors
        mock_db.get_quiz.return_value = [
            {
                "word_id": 2, "jp": "飲む", "en": "to drink", "spelling": "ノム",
                "audio_mapping": ["no", "mu"], "quized": 1, "occurrence": 5, "star": True,
            }
        ]
        mock_get_distractors.return_value = QuizDistractors(
            jp=["食べる", "走る", "寝る"], en=["to eat", "to run", "to sleep"]
        )
        res = await build_quizes("en", mock_pdata, mock_db, user_id=1, limit=5)
        assert 2 in res
        quiz = res[2]
        assert quiz["question"] == "to drink"
        assert quiz["correct"] == "飲む"
        assert len(quiz["choices"]) == 4
        assert "飲む" in quiz["choices"]
