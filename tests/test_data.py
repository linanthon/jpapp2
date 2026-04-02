"""Tests for utils/data.py — data utility functions."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from utils.data import (
    is_japanese_word,
    is_english_word,
    is_word_or_number,
    str_2_int,
    read_stop_words,
    read_jlpt,
    get_quiz_distractors,
    scrape_all_jlpt,
    JLPT_DICT,
    STOP_WORDS,
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


# ── read_stop_words ───────────────────────────────────────────────────────────
class TestReadStopWords:
    @pytest.fixture(autouse=True)
    def clear_stop_words(self):
        STOP_WORDS.clear()
        yield
        STOP_WORDS.clear()

    def test_reads_file(self, tmp_path):
        assert len(STOP_WORDS) == 0
        f = tmp_path / "stops.txt"
        f.write_text("の\nは\nが\n", encoding="utf-8")
        read_stop_words(str(f))
        assert "の" in STOP_WORDS
        assert "は" in STOP_WORDS
        assert "が" in STOP_WORDS

    def test_skips_empty_lines(self, tmp_path):
        assert len(STOP_WORDS) == 0
        f = tmp_path / "stops.txt"
        f.write_text("の\n\nは\n\n", encoding="utf-8")
        read_stop_words(str(f))
        assert len(STOP_WORDS) == 2


# ── read_jlpt ────────────────────────────────────────────────────────────────
class TestReadJlpt:
    @pytest.fixture(autouse=True)
    def clear_jlpt_dict(self):
        JLPT_DICT.clear()
        yield
        JLPT_DICT.clear()

    def test_reads_jlpt_files(self, tmp_path):
        for level in ["N5", "N4", "N3", "N2", "N1"]:
            f = tmp_path / f"{level}.txt"
            f.write_text(f"word_{level}\n", encoding="utf-8")
        read_jlpt(str(tmp_path))
        assert JLPT_DICT["word_N5"] == "N5"
        assert JLPT_DICT["word_N1"] == "N1"

    def test_missing_files_skipped(self, tmp_path):
        # No files in tmp_path — should not crash
        read_jlpt(str(tmp_path))
        assert len(JLPT_DICT) == 0


# ── get_quiz_distractors ─────────────────────────────────────────────────────
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
        mock_db.get_distractors.return_value = []  # not enough from DB
        mock_pdata = MagicMock()

        mock_entry = MagicMock()
        mock_entry.kanji_forms = [MagicMock(text="走る")]
        mock_sense = MagicMock()
        mock_sense.text.return_value = "to run"
        mock_entry.senses = [mock_sense]
        mock_pdata.get_random_jamdict_entries.return_value = [mock_entry] * 3

        result = await get_quiz_distractors(mock_pdata, mock_db, jp_word="食べる",
                                            en_word="to eat", distractor_count=3)
        assert len(result.jp) == 3
        assert result.jp[0] == "走る"

    @pytest.mark.asyncio
    async def test_from_jamdict_kana_only(self):
        """When a Jamdict entry has no kanji forms, the distractor JP word
        should fall back to the kana form (used in EN->JP quiz choices)."""
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

        # jp_word/en_word are the correct-answer words being excluded from distractors
        result = await get_quiz_distractors(mock_pdata, mock_db, jp_word="食べる",
                                            en_word="to eat", distractor_count=1)
        # distractor JP word should be the kana form, not kanji
        assert result.jp[0] == "ビール"


# ── scrape_all_jlpt ──────────────────────────────────────────────────────────
class TestScrapeAllJlpt:
    def test_invalid_option(self):
        assert scrape_all_jlpt(option=-1) == "invalid option"
        assert scrape_all_jlpt(option=5) == "invalid option"

    def test_files_already_exist(self, tmp_path, monkeypatch):
        # Create a file that makes the check fail
        import os
        monkeypatch.chdir(tmp_path)
        os.makedirs("data/jlpt", exist_ok=True)
        (tmp_path / "data" / "jlpt" / "n5.txt").write_text("word\n")
        result = scrape_all_jlpt(option=0)
        assert result == "JLPT file(s) already existed"
