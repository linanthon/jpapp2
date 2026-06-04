"""Tests for DBHandling helper/parsing methods that don't need a real DB."""
import pytest
import math
from unittest.mock import AsyncMock
from utils.db import DBHandling
from schemas.constants import (DEFAULT_FORMULA_K, DEFAULT_MULTI_PENALTY, QUIZ_SOFT_CAP,
                               DEFAULT_DISTRACTOR_COUNT, QUIZ_HARD_CAP, DEFAULT_LIMIT)


class TestPriorityFormulas:
    """Test the priority calculation math."""

    def setup_method(self):
        self.db = DBHandling.__new__(DBHandling)

    def test_expodecay_basic(self):
        # occurrence=10, quized=0 → priority = 10 * exp(0) = 10
        result = self.db._priority_expodecay(10, 0)
        assert result == pytest.approx(10.0)

    def test_expodecay_with_quized(self):
        result = self.db._priority_expodecay(10, 2, k=DEFAULT_FORMULA_K)
        expected = 10 * math.exp(-DEFAULT_FORMULA_K * 2)
        assert result == pytest.approx(expected)

    def test_expodecay_high_quized(self):
        result = self.db._priority_expodecay(5, 100)
        assert result < 0.01  # very small

    def test_priority_formula_delegates(self):
        result = self.db._priority_formula(10, 5)
        expected = self.db._priority_expodecay(10, 5)
        assert result == pytest.approx(expected)

    def test_softcap_formula(self):
        quized = QUIZ_SOFT_CAP + 5
        result = self.db._priority_softcap_formula(10, quized)
        base = self.db._priority_expodecay(10, quized)
        expected = base / (1 + DEFAULT_MULTI_PENALTY * (quized - QUIZ_SOFT_CAP))
        assert result == pytest.approx(expected)

    def test_softcap_lower_than_normal(self):
        occ, quized = 10, QUIZ_SOFT_CAP + 3
        normal = self.db._priority_formula(occ, quized)
        softcap = self.db._priority_softcap_formula(occ, quized)
        assert softcap < normal


class TestGetRowcount:
    def test_update_1(self):
        assert DBHandling._get_rowcount("UPDATE 1") == 1

    def test_delete_3(self):
        assert DBHandling._get_rowcount("DELETE 3") == 3

    def test_insert_0(self):
        assert DBHandling._get_rowcount("INSERT 0 1") == 1

    def test_empty(self):
        assert DBHandling._get_rowcount("") == 0

    def test_none(self):
        assert DBHandling._get_rowcount(None) == 0


class TestParseWord:
    def setup_method(self):
        self.db = DBHandling.__new__(DBHandling)

    def test_parse_word_with_progress(self):
        record = {
            "id": 1, "word": "食べる", "senses": "to eat", "spelling": "タベル",
            "forms": "", "jlpt_level": "N5", "audio_mapping": ["ta", "be", "ru"],
            "occurrence": 10,
        }
        progress = {"star": True, "quized": 5, "priority": 2.0}
        result = self.db._parse_word(record, progress)
        assert result["word_id"] == 1
        assert result["star"] is True
        assert result["quized"] == 5

    def test_parse_word_no_progress(self):
        record = {
            "id": 2, "word": "飲む", "senses": "to drink", "spelling": "ノム",
            "forms": "", "jlpt_level": "N4", "audio_mapping": [],
            "occurrence": 3,
        }
        result = self.db._parse_word(record, {})
        assert result["star"] is False
        assert result["quized"] == 0
        assert result["priority"] == 0

    def test_parse_word_senses_override(self):
        record = {
            "id": 3, "word": "走る", "senses": "to run; to dash",
            "spelling": "ハシル", "forms": "", "jlpt_level": "N4",
            "audio_mapping": [], "occurrence": 1,
        }
        result = self.db._parse_word(record, {}, senses_override="to run")
        assert result["senses"] == "to run"


class TestParseBook:
    def setup_method(self):
        self.db = DBHandling.__new__(DBHandling)

    def test_parse_book(self):
        record = {"id": 1, "created_at": "2025-01-01", "name": "Test", "content": "text"}
        result = self.db._parse_book(record, star=True)
        assert result["book_id"] == 1
        assert result["star"] is True
        assert result["content"] == "text"

    def test_parse_book_no_content(self):
        record = {"id": 2, "created_at": "2025-01-01", "name": "NoContent"}
        result = self.db._parse_book(record, star=False)
        assert result["content"] == ""


class TestParseJobTTS:
    def setup_method(self):
        self.db = DBHandling.__new__(DBHandling)

    def test_parse_job_tts_with_json_string_voice_options(self):
        row = {
            "id": "00000000-0000-0000-0000-000000000001",
            "text": "今日はテストです",
            "lang": "jp",
            "voice_options": '{"speed": 1.1, "half_tone": -1.0}',
            "status": "QUEUED",
            "error": "",
            "attempts": 0,
            "created_at": "2026-05-24 11:00:00",
            "modified_at": "2026-05-24 11:00:00",
        }

        parsed = self.db._parse_job_tts(row)
        assert isinstance(parsed["voice_options"], dict)
        assert parsed["voice_options"]["speed"] == pytest.approx(1.1)


class TestExtractMeanings:
    def setup_method(self):
        self.db = DBHandling.__new__(DBHandling)

    def test_single_meaning(self):
        result = self.db._extract_meanings("to eat ([verb])")
        assert result == ["to eat"]

    def test_multiple_meanings(self):
        result = self.db._extract_meanings("to eat ([verb]); food ([noun])")
        assert len(result) == 2
        assert result[0] == "to eat"
        assert result[1] == "food"

    def test_empty_senses(self):
        result = self.db._extract_meanings("")
        assert result == []

    def test_meaning_with_commas(self):
        result = self.db._extract_meanings("to receive, to get, to accept ([verb])")
        assert len(result) == 1
        # Only first 2 synonyms kept
        assert "to receive" in result[0]
        assert "to get" in result[0]


class TestGetMeanings:
    def setup_method(self):
        self.db = DBHandling.__new__(DBHandling)

    def test_with_senses(self):
        result = self.db.get_meanings("食べる", "to eat ([verb])")
        assert result == ["to eat"]

    def test_no_senses_no_word(self):
        result = self.db.get_meanings("", "")
        assert result == []

    def test_no_senses_with_word(self):
        result = self.db.get_meanings("test", "")
        assert result == []


# ── ParseSentence ─────────────────────────────────────────────────────────────
class TestParseSentence:
    def setup_method(self):
        self.db = DBHandling.__new__(DBHandling)

    def test_parse_sentence(self):
        record = {"id": 1, "sentence": "食べてください", "star": True, "occurrence": 3, "quized": 1}
        result = self.db._parse_sentence(record)
        assert result["sen_id"] == 1
        assert result["sentence"] == "食べてください"
        assert result["star"] is True
        assert result["occurrence"] == 3
        assert result["quized"] == 1


# ── ParseQuiz ─────────────────────────────────────────────────────────────────
class TestParseQuiz:
    def setup_method(self):
        self.db = DBHandling.__new__(DBHandling)

    def test_parse_quiz(self):
        record = {
            "id": 1, "word": "食べる", "senses": "to eat ([verb])",
            "spelling": "タベル", "jlpt_level": "N5",
            "audio_mapping": ["ta", "be", "ru"], "occurrence": 10,
            "quized": 3, "star": False,
        }
        result = self.db._parse_quiz(record)
        assert result["word_id"] == 1
        assert result["jp"] == "食べる"
        assert result["en"] == "to eat"
        assert result["spelling"] == "タベル"
        assert result["jlpt_level"] == "N5"

    def test_parse_quiz_n0_clears_jlpt(self):
        record = {
            "id": 2, "word": "テスト", "senses": "test ([noun])",
            "spelling": "テスト", "jlpt_level": "N0",
            "audio_mapping": [], "occurrence": 1, "quized": 0, "star": False,
        }
        result = self.db._parse_quiz(record)
        assert result["jlpt_level"] == ""


# ── Build Distractors SQL ─────────────────────────────────────────────────────
class TestBuildDistractorsSql:
    def setup_method(self):
        self.db = DBHandling.__new__(DBHandling)

    def test_without_exclude_en(self):
        sql, params = self.db._build_distractors_sql("食べる")
        assert "word != $1" in sql
        assert "senses NOT LIKE $2" in sql  # dash exclusion
        assert "LIMIT $3" in sql
        assert params == ["食べる", "%-%", DEFAULT_DISTRACTOR_COUNT]

    def test_with_exclude_en(self):
        sql, params = self.db._build_distractors_sql("食べる", "to eat")
        assert "word != $1" in sql
        assert "senses NOT LIKE $2" in sql  # dash exclusion
        assert "senses NOT LIKE $3" in sql
        assert "LIMIT $4" in sql
        assert params == ["食べる", "%-%", "%to eat%", DEFAULT_DISTRACTOR_COUNT]


# ── Build Sort/Filter/Prio SQL ────────────────────────────────────────────────
class TestBuildSortFilterPrioSql:
    def setup_method(self):
        self.db = DBHandling.__new__(DBHandling)

    def test_basic_priority_query(self):
        sql, params = self.db._build_sort_filter_prio_sql(user_id=1, limit=10)
        assert "LEFT JOIN" in sql
        assert "b.user_id = $1" in sql
        assert "COALESCE(b.priority, w.occurrence::double precision) > 0.0" in sql
        assert "ORDER BY COALESCE(b.priority, w.occurrence::double precision) DESC" in sql
        assert "LIMIT $2" in sql
        assert params == [1, 10]

    def test_with_jlpt_filter(self):
        sql, params = self.db._build_sort_filter_prio_sql(user_id=1, limit=5, jlpt_filter="N3")
        assert "b.user_id = $1" in sql
        assert "w.jlpt_level = $2" in sql
        assert "COALESCE(b.priority, w.occurrence::double precision) > 0.0" in sql
        assert "ORDER BY COALESCE(b.priority, w.occurrence::double precision) DESC" in sql
        assert "LIMIT $3" in sql
        assert params == [1, "N3", 5]

    def test_star_only(self):
        sql, params = self.db._build_sort_filter_prio_sql(user_id=1, limit=5, star_only=True)
        assert "b.user_id = $1" in sql
        assert "COALESCE(b.star, false) = true" in sql
        assert "COALESCE(b.priority, w.occurrence::double precision) > 0.0" in sql
        assert "ORDER BY COALESCE(b.priority, w.occurrence::double precision) DESC" in sql
        assert "LIMIT $2" in sql
        assert params == [1, 5]

    def test_book_filter(self):
        sql, params = self.db._build_sort_filter_prio_sql(user_id=1, limit=5, book_id=3)
        assert "JOIN" in sql and "word_book" in sql
        assert "b.user_id = $1" in sql
        assert "r.book_id = $2" in sql
        assert "COALESCE(b.priority, w.occurrence::double precision) > 0.0" in sql
        assert "ORDER BY COALESCE(b.priority, w.occurrence::double precision) DESC" in sql
        assert "LIMIT $3" in sql
        assert params == [1, 3, 5]

    def test_is_known_mode(self):
        sql, params = self.db._build_sort_filter_prio_sql(user_id=1, limit=5, is_known=True)
        assert "b.user_id = $1" in sql
        assert f"COALESCE(b.priority, w.occurrence::double precision) <= 0.0 OR COALESCE(b.quized, 0) > {QUIZ_HARD_CAP}" in sql
        assert "ORDER BY COALESCE(b.priority, w.occurrence::double precision) DESC" in sql
        assert "LIMIT $2" in sql
        assert params == [1, 5]

    def test_sort_without_priority(self):
        sql, params = self.db._build_sort_filter_prio_sql(
            user_id=1, limit=5, sorts=[("occurrence", "desc")], use_priority=False
        )
        assert "b.user_id = $1" in sql
        assert "COALESCE(b.priority, w.occurrence::double precision) > 0.0" in sql
        assert "ORDER BY w.occurrence desc" in sql
        assert "LIMIT $2" in sql
        assert params == [1, 5]

    def test_sort_and_priority_returns_none(self):
        sql, params = self.db._build_sort_filter_prio_sql(
            user_id=1, limit=5, sorts=[("occurrence", "desc")], use_priority=True
        )
        assert sql is None
        assert params == []

    def test_no_sort_no_priority(self):
        sql, params = self.db._build_sort_filter_prio_sql(
            user_id=1, limit=5, sorts=[], use_priority=False
        )
        assert "b.user_id = $1" in sql
        assert "COALESCE(b.priority, w.occurrence::double precision) > 0.0" in sql
        assert "ORDER BY COALESCE(b.last_tested, TO_TIMESTAMP(0)) ASC" in sql
        assert "LIMIT $2" in sql
        assert params == [1, 5]

    def test_exclude_jp_and_en(self):
        sql, params = self.db._build_sort_filter_prio_sql(
            user_id=1, limit=5, exclude_jp=["食べる"], exclude_en=["to eat"]
        )
        assert "b.user_id = $1" in sql
        assert "w.word != ALL($2)" in sql
        assert "w.senses NOT LIKE $3" in sql
        assert "COALESCE(b.priority, w.occurrence::double precision) > 0.0" in sql
        assert "ORDER BY COALESCE(b.priority, w.occurrence::double precision) DESC" in sql
        assert "LIMIT $4" in sql
        assert params == [1, ["食べる"], "%to eat%", 5]

    def test_avoid_dash_sense(self):
        sql, params = self.db._build_sort_filter_prio_sql(
            user_id=1, limit=5, avoid_dash_sense=True
        )
        assert "b.user_id = $1" in sql
        assert "COALESCE(b.priority, w.occurrence::double precision) > 0.0" in sql
        assert "w.senses NOT LIKE $2" in sql
        assert "ORDER BY COALESCE(b.priority, w.occurrence::double precision) DESC" in sql
        assert "LIMIT $3" in sql
        assert params == [1, "%-%", 5]


# ── GetUserProgress ───────────────────────────────────────────────────────────
class TestGetUserProgress:
    def setup_method(self):
        self.db = DBHandling.__new__(DBHandling)

    def _make_row(self, jlpt_level, total, silver_count, gold_count):
        return {
            "jlpt_level": jlpt_level,
            "total": total,
            "silver_count": silver_count,
            "gold_count": gold_count,
        }

    @pytest.mark.asyncio
    async def test_single_level(self):
        self.db._fetch = AsyncMock(return_value=[
            self._make_row("N5", 100, 50, 20),
        ])
        result = await self.db.get_user_progress(1)
        assert "N5" in result
        assert result["N5"]["silver_pct"] == pytest.approx(50.0)
        assert result["N5"]["gold_pct"] == pytest.approx(20.0)
        assert result["total"]["silver_pct"] == pytest.approx(50.0)
        assert result["total"]["gold_pct"] == pytest.approx(20.0)

    @pytest.mark.asyncio
    async def test_multiple_levels(self):
        self.db._fetch = AsyncMock(return_value=[
            self._make_row("N5", 100, 60, 10),
            self._make_row("N4", 200, 40, 20),
        ])
        result = await self.db.get_user_progress(1)
        assert result["N5"]["silver_pct"] == pytest.approx(60.0)
        assert result["N5"]["gold_pct"] == pytest.approx(10.0)
        assert result["N4"]["silver_pct"] == pytest.approx(20.0)
        assert result["N4"]["gold_pct"] == pytest.approx(10.0)
        # total: (60+40)/(100+200) = 100/300 ≈ 33.3, gold: 30/300 = 10.0
        assert result["total"]["silver_pct"] == pytest.approx(33.3, abs=0.1)
        assert result["total"]["gold_pct"] == pytest.approx(10.0)

    @pytest.mark.asyncio
    async def test_no_rows_returns_empty_total(self):
        self.db._fetch = AsyncMock(return_value=[])
        result = await self.db.get_user_progress(1)
        assert result == {"total": {"silver_pct": 0.0, "gold_pct": 0.0}}

    @pytest.mark.asyncio
    async def test_zero_silver_and_gold(self):
        self.db._fetch = AsyncMock(return_value=[
            self._make_row("N3", 50, 0, 0),
        ])
        result = await self.db.get_user_progress(1)
        assert result["N3"]["silver_pct"] == 0.0
        assert result["N3"]["gold_pct"] == 0.0

    @pytest.mark.asyncio
    async def test_all_words_at_hard_cap(self):
        self.db._fetch = AsyncMock(return_value=[
            self._make_row("N2", 80, 80, 80),
        ])
        result = await self.db.get_user_progress(1)
        assert result["N2"]["silver_pct"] == pytest.approx(100.0)
        assert result["N2"]["gold_pct"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_percentages_rounded_to_one_decimal(self):
        self.db._fetch = AsyncMock(return_value=[
            self._make_row("N1", 3, 1, 0),  # 1/3 = 33.333...% → 33.3
        ])
        result = await self.db.get_user_progress(1)
        assert result["N1"]["silver_pct"] == 33.3
        assert result["N1"]["gold_pct"] == 0.0

    @pytest.mark.asyncio
    async def test_query_passes_user_id(self):
        self.db._fetch = AsyncMock(return_value=[])
        await self.db.get_user_progress(42)
        call_args = self.db._fetch.call_args
        assert call_args.args[1] == 42


# ── InsertBookInit ────────────────────────────────────────────────────────────
class TestInsertBookInit:
    def setup_method(self):
        self.db = DBHandling.__new__(DBHandling)

    @pytest.mark.asyncio
    async def test_new_insert_success(self):
        self.db._fetchrow = AsyncMock(return_value={"id": 5, "is_new": True})
        book_id, is_new = await self.db.insert_book_init(1, "mybook.txt", "key-123")
        assert book_id == 5
        assert is_new is True

    @pytest.mark.asyncio
    async def test_duplicate_insert(self):
        self.db._fetchrow = AsyncMock(return_value={"id": 5, "is_new": False})
        book_id, is_new = await self.db.insert_book_init(1, "mybook.txt", "key-123")
        assert book_id == 5
        assert is_new is False

    @pytest.mark.asyncio
    async def test_failure_returns_negative(self):
        self.db._fetchrow = AsyncMock(return_value=None)
        book_id, is_new = await self.db.insert_book_init(1, "mybook.txt", "key-123")
        assert book_id == -1
        assert is_new is False

    @pytest.mark.asyncio
    async def test_extracts_bookname_from_path(self):
        self.db._fetchrow = AsyncMock(return_value={"id": 1, "is_new": True})
        await self.db.insert_book_init(1, "/some/path/mybook.txt", "key-456")
        call_args = self.db._fetchrow.call_args
        # Second positional arg after the SQL is user_id, third is bookname
        assert call_args.args[2] == "mybook.txt"


# ── InsertBookUploaded ────────────────────────────────────────────────────────
class TestInsertBookUploaded:
    def setup_method(self):
        self.db = DBHandling.__new__(DBHandling)

    @pytest.mark.asyncio
    async def test_success(self):
        self.db._execute = AsyncMock(return_value="UPDATE 1")
        result = await self.db.update_insert_book_status_uploaded(5, "minio/path/file.txt")
        assert result is True

    @pytest.mark.asyncio
    async def test_failure(self):
        self.db._execute = AsyncMock(return_value=None)
        result = await self.db.update_insert_book_status_uploaded(5, "minio/path/file.txt")
        assert result is False


# ── InsertBookFinished ────────────────────────────────────────────────────────
class TestInsertBookFinished:
    def setup_method(self):
        self.db = DBHandling.__new__(DBHandling)

    @pytest.mark.asyncio
    async def test_success(self):
        self.db._execute = AsyncMock(return_value="UPDATE 1")
        result = await self.db.update_insert_book_status_finished(5)
        assert result is True

    @pytest.mark.asyncio
    async def test_failure(self):
        self.db._execute = AsyncMock(return_value=None)
        result = await self.db.update_insert_book_status_finished(5)
        assert result is False


# ── UpdateQuizedPrioTs ───────────────────────────────────────────────────────
class TestUpdateQuizedPrioTs:
    def setup_method(self):
        self.db = DBHandling.__new__(DBHandling)

    @pytest.mark.asyncio
    async def test_upserts_progress_when_row_missing(self):
        self.db._execute = AsyncMock(return_value="INSERT 0 1")

        result = await self.db.update_quized_prio_ts(
            user_id=11,
            word_id=22,
            occurrence=10,
            quized=3,
        )

        assert result is True
        self.db._execute.assert_awaited_once()
        call_args = self.db._execute.await_args.args
        sql = call_args[0]
        assert "INSERT INTO" in sql
        assert "ON CONFLICT (user_id, word_id)" in sql
        assert call_args[1] == 11
        assert call_args[2] == 22
        assert call_args[3] == 3

    @pytest.mark.asyncio
    async def test_fallback_values_use_upsert(self):
        self.db.get_word_occurence = AsyncMock(return_value=(22, 12))
        self.db.get_user_word_quized = AsyncMock(return_value=4)
        self.db._execute = AsyncMock(return_value="UPDATE 1")

        result = await self.db.update_quized_prio_ts(user_id=11, word_id=22)

        assert result is True
        self.db.get_word_occurence.assert_awaited_once_with(word_id=22)
        self.db.get_user_word_quized.assert_awaited_once_with(11, 22)
        self.db._execute.assert_awaited_once()
        call_args = self.db._execute.await_args.args
        # quized should be current + 1 in fallback path
        assert call_args[3] == 5


# ── QuerySearchWord ───────────────────────────────────────────────────────────
class TestQuerySearchWord:
    def setup_method(self):
        self.db = DBHandling.__new__(DBHandling)
        self.db._parse_word = lambda record, _progress: {"word": record["word"]}

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty(self):
        self.db._fetch = AsyncMock()
        result = await self.db.query_search_word("   ", 10)
        assert result == []
        self.db._fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_typo_query_enabled_for_single_term(self):
        self.db._fetch = AsyncMock(return_value=[{"word": "食べる"}])

        result = await self.db.query_search_word("taberu", 10)

        assert result == [{"word": "食べる"}]
        assert self.db._fetch.await_count == 1
        sql = self.db._fetch.await_args.args[0]
        assert "word_similarity(" in sql
        assert "exact_rank" in sql

    @pytest.mark.asyncio
    async def test_typo_disabled_for_short_query(self):
        self.db._fetch = AsyncMock(side_effect=[[]])

        result = await self.db.query_search_word("ab", 10)

        assert result == []
        assert self.db._fetch.await_count == 1
        sql = self.db._fetch.await_args.args[0]
        assert "word_similarity(" not in sql

    @pytest.mark.asyncio
    async def test_mixed_chunk_query_runs_with_typo_support(self):
        self.db._fetch = AsyncMock(return_value=[{"word": "学び"}])

        result = await self.db.query_search_word("学bi", 10)

        assert result == [{"word": "学び"}]
        assert self.db._fetch.await_count == 1
        sql = self.db._fetch.await_args.args[0]
        assert " AND " in sql
        assert "word ILIKE $1" in sql
        assert "word_similarity(" in sql

    @pytest.mark.asyncio
    async def test_mixed_with_space_uses_compact_similarity_value(self):
        self.db._fetch = AsyncMock(return_value=[{"word": "学び"}])

        result = await self.db.query_search_word("学 bi", 10)

        assert result == [{"word": "学び"}]
        assert self.db._fetch.await_count == 1
        call_args = self.db._fetch.await_args.args
        sql = call_args[0]
        assert "word_similarity(" in sql
        # compact term is passed for similarity ranking.
        assert "学bi" in call_args


# ── GetSentencesContainingWordById ───────────────────────────────────────────
class TestGetSentencesContainingWordById:
    def setup_method(self):
        self.db = DBHandling.__new__(DBHandling)

    @pytest.mark.asyncio
    async def test_invalid_word_id_returns_empty(self):
        self.db._fetch = AsyncMock()
        result = await self.db.get_sentences_containing_word_by_id(word_id=None)
        assert result == []
        self.db._fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_limit_falls_back_to_default_and_filters_empty_rows(self):
        self.db._fetch = AsyncMock(return_value=[
            {"sentence": "猫が好きです。"},
            {"sentence": ""},
            {"sentence": None},
            {"sentence": "毎日日本語を勉強します。"},
        ])

        result = await self.db.get_sentences_containing_word_by_id(word_id=7, limit=0)

        assert result == ["猫が好きです。", "毎日日本語を勉強します。"]
        self.db._fetch.assert_awaited_once()
        call_args = self.db._fetch.await_args.args
        sql = call_args[0]
        assert "WHERE ws.word_id = $1" in sql
        assert "ORDER BY RANDOM() LIMIT $2" in sql
        assert call_args[1] == 7
        assert call_args[2] == DEFAULT_LIMIT

    @pytest.mark.asyncio
    async def test_with_word_adds_min_length_filter(self):
        self.db._fetch = AsyncMock(return_value=[{"sentence": "文です。"}])

        result = await self.db.get_sentences_containing_word_by_id(
            word_id=3, limit=5, word="文",
        )

        assert result == ["文です。"]
        self.db._fetch.assert_awaited_once()
        call_args = self.db._fetch.await_args.args
        sql = call_args[0]
        assert "WHERE ws.word_id = $1" in sql
        assert "CHAR_LENGTH(s.sentence) - CHAR_LENGTH($2) > 2" in sql
        assert "ORDER BY RANDOM() LIMIT $3" in sql
        assert call_args[1] == 3
        assert call_args[2] == "文"
        assert call_args[3] == 5
