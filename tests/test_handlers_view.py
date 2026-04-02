"""Tests for app/handlers/view.py — view logic with mocked DB."""
import pytest
from app.handlers.view import (
    toggle_star_helper,
    delete_book_helper,
    get_all_book_name_and_id,
    handle_search_word,
    handle_view_specific_word,
    handle_view_words,
    handle_view_books,
    handle_view_specific_book,
    reset_view_word_count,
    view_count_cache,
)


# ── toggle_star_helper ────────────────────────────────────────────────────────
class TestToggleStarHelper:
    @pytest.mark.asyncio
    async def test_star_word(self, mock_db):
        mock_db.update_word_star.return_value = True
        result = await toggle_star_helper(mock_db, user_id=1, obj_id=10, obj_type="word", star=1)
        assert result is True
        mock_db.update_word_star.assert_called_once_with(user_id=1, word_id=10, new_star_status=True)

    @pytest.mark.asyncio
    async def test_unstar_word(self, mock_db):
        mock_db.update_word_star.return_value = True
        result = await toggle_star_helper(mock_db, user_id=1, obj_id=10, obj_type="word", star=0)
        assert result is True
        mock_db.update_word_star.assert_called_once_with(user_id=1, word_id=10, new_star_status=False)

    @pytest.mark.asyncio
    async def test_star_book(self, mock_db):
        mock_db.update_book_star.return_value = True
        result = await toggle_star_helper(mock_db, user_id=1, obj_id=5, obj_type="book", star=1)
        assert result is True
        mock_db.update_book_star.assert_called_once_with(user_id=1, book_id=5, new_star_status=True)

    @pytest.mark.asyncio
    async def test_invalid_type(self, mock_db):
        result = await toggle_star_helper(mock_db, user_id=1, obj_id=5, obj_type="sentence", star=1)
        assert result is False


# ── delete_book_helper ────────────────────────────────────────────────────────
class TestDeleteBookHelper:
    @pytest.mark.asyncio
    async def test_delete_success(self, mock_db):
        mock_db.delete_book.return_value = True
        result = await delete_book_helper(mock_db, book_id=1)
        assert result is True


# ── get_all_book_name_and_id ──────────────────────────────────────────────────
class TestGetAllBookNameAndId:
    @pytest.mark.asyncio
    async def test_returns_books(self, mock_db):
        mock_db.list_books.return_value = [{"book_id": 1, "name": "Book A"}]
        result = await get_all_book_name_and_id(mock_db)
        assert len(result) == 1
        mock_db.list_books.assert_called_once_with(star=None, limit=None, offset=0)


# ── handle_search_word ────────────────────────────────────────────────────────
class TestHandleSearchWord:
    @pytest.mark.asyncio
    async def test_japanese_word(self, mock_db):
        mock_db.query_like_word.return_value = [
            {"word": "食べる", "senses": "to eat ([verb])"}
        ]
        mock_db.get_meanings.return_value = ["to eat"]
        result = await handle_search_word(mock_db, "食べる", 10, "/v1")
        assert "results" in result
        assert result["bpPrefix"] == "/v1"

    @pytest.mark.asyncio
    async def test_english_word(self, mock_db):
        mock_db.query_word_sense.return_value = [
            {"word": "食べる", "senses": "to eat ([verb])"}
        ]
        mock_db.get_meanings.return_value = ["to eat"]
        result = await handle_search_word(mock_db, "eat", 10, "/v1")
        assert "results" in result

    @pytest.mark.asyncio
    async def test_invalid_word(self, mock_db):
        result = await handle_search_word(mock_db, "123!", 10, "/v1")
        assert "error" in result


# ── handle_view_specific_word ─────────────────────────────────────────────────
class TestHandleViewSpecificWord:
    @pytest.mark.asyncio
    async def test_returns_word_and_sentences(self, mock_db):
        mock_db.get_exact_word.return_value = {
            "word_id": 1, "word": "食べる", "senses": "to eat; to consume",
        }
        mock_db.get_sentences_containing_word_by_id.return_value = ["食べてください"]
        word, sentences = await handle_view_specific_word(mock_db, user_id=1, word_id=1, sentence_limit=5)
        assert word["word"] == "食べる"
        assert "meanings" in word
        assert len(sentences) == 1


# ── handle_view_words ─────────────────────────────────────────────────────────
class TestHandleViewWords:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        reset_view_word_count()
        yield
        reset_view_word_count()

    @pytest.mark.asyncio
    async def test_returns_words_and_page_count(self, mock_db):
        mock_db.count_words.return_value = 25
        mock_db.list_words.return_value = [{"word": "test"}]
        words, pages = await handle_view_words(mock_db, user_id=1, limit=10, page=1)
        assert pages == 3  # ceil(25/10)
        assert len(words) == 1

    @pytest.mark.asyncio
    async def test_page_beyond_count_returns_empty(self, mock_db):
        mock_db.count_words.return_value = 5
        words, pages = await handle_view_words(mock_db, user_id=1, limit=10, page=5)
        assert words == []
        assert pages == 1

    @pytest.mark.asyncio
    async def test_caches_count(self, mock_db):
        mock_db.count_words.return_value = 10
        mock_db.list_words.return_value = []
        await handle_view_words(mock_db, user_id=1, limit=10, page=1)
        await handle_view_words(mock_db, user_id=1, limit=10, page=1)
        # count_words should only be called once due to caching
        assert mock_db.count_words.call_count == 1


# ── handle_view_books ─────────────────────────────────────────────────────────
class TestHandleViewBooks:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        reset_view_word_count()
        yield
        reset_view_word_count()

    @pytest.mark.asyncio
    async def test_returns_books_and_page_count(self, mock_db):
        mock_db.count_books.return_value = 15
        mock_db.list_books.return_value = [{"name": "Book1"}]
        books, pages = await handle_view_books(mock_db, user_id=1, limit=10, page=1)
        assert pages == 2
        assert len(books) == 1


# ── handle_view_specific_book ─────────────────────────────────────────────────
class TestHandleViewSpecificBook:
    @pytest.mark.asyncio
    async def test_returns_book(self, mock_db):
        mock_db.get_exact_book.return_value = {"book_id": 1, "name": "Test Book"}
        result = await handle_view_specific_book(mock_db, user_id=1, book_id=1)
        assert result["name"] == "Test Book"


# ── reset_view_word_count ─────────────────────────────────────────────────────
class TestResetViewWordCount:
    def test_clears_cache(self):
        view_count_cache["key"] = 42
        reset_view_word_count()
        assert view_count_cache == {}
