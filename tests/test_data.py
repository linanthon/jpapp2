"""Tests for utils/data.py — data utility functions."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from utils.data import (
    is_japanese_word,
    is_english_word,
    is_word_or_number,
    str_2_int,
    get_quiz_distractors,
    bootstrap_stopwords_from_redis,
    read_jlpt_from_db,
    get_jlpt_level,
    is_stop_word,
    JLPT_REDIS_KEY,
    STOPWORDS_REDIS_KEY,
)


class TestIsJapaneseWord:
    @pytest.mark.parametrize("word", ["日本語", "かな", "カタカナ", "食べる", "東京ー"])
    def test_valid_jp(self, word):
        assert is_japanese_word(word) is True

    @pytest.mark.parametrize("word", ["hello", "123", "日本語!", "", " "])
    def test_invalid_jp(self, word):
        assert is_japanese_word(word) is False


class TestIsEnglishWord:
    @pytest.mark.parametrize("word", ["hello", "Word", "ABC"])
    def test_valid_en(self, word):
        assert is_english_word(word) is True

    @pytest.mark.parametrize("word", ["hello123", "two words", "日本", "", "hello!"])
    def test_invalid_en(self, word):
        assert is_english_word(word) is False


class TestIsWordOrNumber:
    @pytest.mark.parametrize("inp", ["abc", "123", "abc123", "_underscore", "a_1"])
    def test_valid(self, inp):
        assert is_word_or_number(inp) is True

    @pytest.mark.parametrize("inp", ["", "hello world", "a-b", "a!"])
    def test_invalid(self, inp):
        assert is_word_or_number(inp) is False


class TestStr2Int:
    def test_valid_int(self):
        assert str_2_int("42") == 42

    def test_invalid(self):
        from schemas.constants import DEFAULT_LIMIT
        assert str_2_int("abc") == DEFAULT_LIMIT

    def test_empty(self):
        from schemas.constants import DEFAULT_LIMIT
        assert str_2_int("") == DEFAULT_LIMIT


class TestRedisBackedHelpers:
    @pytest.mark.asyncio
    async def test_bootstrap_stopwords_seeds_when_missing(self, tmp_path):
        f = tmp_path / "stopwords.txt"
        f.write_text("の\nは\n", encoding="utf-8")

        redis = AsyncMock()
        redis.exists.return_value = 0

        await bootstrap_stopwords_from_redis(redis, str(f))

        redis.exists.assert_awaited_once_with(STOPWORDS_REDIS_KEY)
        redis.sadd.assert_awaited_once_with(STOPWORDS_REDIS_KEY, "の", "は")

    @pytest.mark.asyncio
    async def test_bootstrap_stopwords_no_seed_if_exists(self, tmp_path):
        f = tmp_path / "stopwords.txt"
        f.write_text("の\nは\n", encoding="utf-8")

        redis = AsyncMock()
        redis.exists.return_value = 1

        await bootstrap_stopwords_from_redis(redis, str(f))

        redis.exists.assert_awaited_once_with(STOPWORDS_REDIS_KEY)
        redis.sadd.assert_not_called()

    @pytest.mark.asyncio
    async def test_read_jlpt_from_db_writes_redis_hash(self):
        db = AsyncMock()
        db.list_jlpt_levels.return_value = {"食べる": "N5", "走る": "N4"}

        redis = MagicMock()
        lock = AsyncMock()
        lock.acquire.return_value = True
        redis.lock.return_value = lock
        pipeline = MagicMock()
        pipeline.execute = AsyncMock()
        redis.pipeline.return_value = pipeline

        await read_jlpt_from_db(db, redis)

        db.list_jlpt_levels.assert_awaited_once()
        pipeline.delete.assert_called_once_with(JLPT_REDIS_KEY)
        pipeline.hset.assert_called_once_with(JLPT_REDIS_KEY, mapping={"食べる": "N5", "走る": "N4"})
        pipeline.execute.assert_awaited_once()
        lock.release.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_jlpt_level_from_redis(self):
        redis = AsyncMock()
        redis.hget.return_value = "N3"

        result = await get_jlpt_level("勉強", redis)

        assert result == "N3"
        redis.hget.assert_awaited_once_with(JLPT_REDIS_KEY, "勉強")

    @pytest.mark.asyncio
    async def test_get_jlpt_level_default_when_missing(self):
        redis = AsyncMock()
        redis.hget.return_value = None

        result = await get_jlpt_level("未知語", redis)

        assert result == "N0"

    @pytest.mark.asyncio
    async def test_is_stop_word_true_false(self):
        redis = AsyncMock()
        redis.sismember.side_effect = [1, 0]

        assert await is_stop_word("の", redis) is True
        assert await is_stop_word("食べる", redis) is False


# -- get_quiz_distractors -----------------------------------------------------
class TestGetQuizDistractors:
    @pytest.mark.asyncio
    async def test_no_word_returns_none(self):
        result = await get_quiz_distractors(MagicMock(), AsyncMock(), jp_word="", en_word="")
        assert result is None

    @pytest.mark.asyncio
    async def test_from_db_enough(self):
        mock_db = AsyncMock()
        mock_db.get_distractors.return_value = [
            {"jp": "飲む", "en": "to drink"},
            {"jp": "走る", "en": "to run"},
            {"jp": "寝る", "en": "to sleep"},
        ]
        result = await get_quiz_distractors(MagicMock(), mock_db, jp_word="食べる", en_word="to eat")
        assert len(result.jp) == 3
        assert len(result.en) == 3
        assert "飲む" in result.jp

    @pytest.mark.asyncio
    async def test_from_jamdict_fallback(self):
        mock_db = AsyncMock()
        mock_db.get_distractors.return_value = []
        mock_pdata = MagicMock()

        mock_entry = MagicMock()
        mock_entry.kanji_forms = [MagicMock(text="走る")]
        mock_sense = MagicMock()
        mock_sense.text.return_value = "to run"
        mock_entry.senses = [mock_sense]
        mock_pdata.get_random_jamdict_entries.return_value = [mock_entry] * 3

        result = await get_quiz_distractors(mock_pdata, mock_db, jp_word="食べる", en_word="to eat", distractor_count=3)
        assert len(result.jp) == 3
        assert result.jp[0] == "走る"

    @pytest.mark.asyncio
    async def test_from_jamdict_kana_only(self):
        mock_db = AsyncMock()
        mock_db.get_distractors.return_value = []
        mock_pdata = MagicMock()

        mock_entry = MagicMock()
        mock_entry.kanji_forms = []
        mock_entry.kana_forms = [MagicMock(text="ビール")]
        mock_sense = MagicMock()
        mock_sense.text.return_value = "beer"
        mock_entry.senses = [mock_sense]
        mock_pdata.get_random_jamdict_entries.return_value = [mock_entry]

        result = await get_quiz_distractors(mock_pdata, mock_db, jp_word="食べる", en_word="to eat", distractor_count=1)
        assert result.jp[0] == "ビール"
