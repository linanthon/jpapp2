"""Tests for app/handlers/insert.py — insert logic with mocked DB/pdata."""
import pytest
import os
from http import HTTPStatus

from app.handlers.insert import (
    do_insert_book,
    do_insert_word_sentence_book_2_db,
    handle_insert_str_stream,
    handle_insert_file_stream,
)
from schemas.word import Word


# ── do_insert_book ────────────────────────────────────────────────────────────
class TestDoInsertBook:
    @pytest.mark.asyncio
    async def test_success(self, mock_db):
        mock_db.insert_book.return_value = 1
        book_id, err, status = await do_insert_book(mock_db, "test_book", "content here")
        assert book_id == 1
        assert err is None
        assert status == HTTPStatus.OK

    @pytest.mark.asyncio
    async def test_name_already_used(self, mock_db):
        mock_db.insert_book.return_value = 0
        book_id, err, status = await do_insert_book(mock_db, "dupe", "content")
        assert book_id == 0
        assert err == {"error": "Name already used"}
        assert status == HTTPStatus.CONFLICT

    @pytest.mark.asyncio
    async def test_db_failure(self, mock_db):
        mock_db.insert_book.return_value = -1
        book_id, _, status = await do_insert_book(mock_db, "book", "content")
        assert book_id == -1
        assert status == HTTPStatus.INTERNAL_SERVER_ERROR

    @pytest.mark.asyncio
    async def test_file_not_found(self, mock_db):
        mock_db.insert_book.return_value = -2
        book_id, _, status = await do_insert_book(mock_db, "book", "content")
        assert book_id == -2
        assert status == HTTPStatus.NOT_FOUND

    @pytest.mark.asyncio
    async def test_empty_name(self, mock_db):
        book_id, _, status = await do_insert_book(mock_db, "", "")
        assert book_id == -1
        assert status == HTTPStatus.BAD_REQUEST

    @pytest.mark.asyncio
    async def test_empty_data(self, mock_db):
        book_id, _, status = await do_insert_book(mock_db, "name", "")
        assert book_id == -1
        assert status == HTTPStatus.BAD_REQUEST


# ── do_insert_word_sentence_book_2_db ─────────────────────────────────────────
class TestDoInsertWordSentenceBook2DB:
    @pytest.mark.asyncio
    async def test_inserts_sentence_and_words(self, mock_db, mock_pdata):
        word = Word(word="食べる", senses="to eat", spelling="タベル")
        mock_pdata.process_sentence.return_value = [word]
        mock_db.insert_update_sentence.return_value = 100
        mock_db.insert_word.return_value = 200
        mock_db.insert_word_book_ref.return_value = True
        mock_db.insert_word_sentence_ref.return_value = True
        mock_db.insert_sentence_book_ref.return_value = True

        await do_insert_word_sentence_book_2_db(mock_pdata, mock_db, "食べてください", book_id=1)

        mock_db.insert_update_sentence.assert_called_once_with("食べてください")
        mock_db.insert_word.assert_called_once_with(word)
        mock_db.insert_word_book_ref.assert_called_once_with(200, 1)
        mock_db.insert_word_sentence_ref.assert_called_once_with(200, 100)
        mock_db.insert_sentence_book_ref.assert_called_once_with(100, 1)


# ── handle_insert_str_stream ──────────────────────────────────────────────────
class TestHandleInsertStrStream:
    @pytest.mark.asyncio
    async def test_missing_name(self, mock_pdata, mock_db):
        chunks = []
        async for chunk in handle_insert_str_stream(mock_pdata, mock_db, "", "data"):
            chunks.append(chunk)
        assert any(b"Error" in c for c in chunks)

    @pytest.mark.asyncio
    async def test_missing_data(self, mock_pdata, mock_db):
        chunks = []
        async for chunk in handle_insert_str_stream(mock_pdata, mock_db, "name", ""):
            chunks.append(chunk)
        assert any(b"Error" in c for c in chunks)

    @pytest.mark.asyncio
    async def test_successful_insert(self, mock_pdata, mock_db):
        mock_db.insert_book.return_value = 1
        mock_pdata.stream_sentences_str.return_value = iter(["sentence1", "sentence2"])
        mock_pdata.process_sentence.return_value = []

        chunks = []
        async for chunk in handle_insert_str_stream(mock_pdata, mock_db, "Book Name", "sentence1sentence2"):
            chunks.append(chunk)

        assert any(b"Processed" in c for c in chunks)

    @pytest.mark.asyncio
    async def test_duplicate_name_error(self, mock_pdata, mock_db):
        mock_db.insert_book.return_value = 0  # already exists
        chunks = []
        async for chunk in handle_insert_str_stream(mock_pdata, mock_db, "Dupe", "content"):
            chunks.append(chunk)
        assert any(b"Name already used" in c for c in chunks)


# ── handle_insert_file_stream ─────────────────────────────────────────────────
class TestHandleInsertFileStream:
    @pytest.mark.asyncio
    async def test_missing_filename(self, mock_pdata, mock_db):
        chunks = []
        async for chunk in handle_insert_file_stream(mock_pdata, mock_db, "", ""):
            chunks.append(chunk)
        assert any(b"Error" in c for c in chunks)

    @pytest.mark.asyncio
    async def test_missing_path(self, mock_pdata, mock_db):
        chunks = []
        async for chunk in handle_insert_file_stream(mock_pdata, mock_db, "name", ""):
            chunks.append(chunk)
        assert any(b"Error" in c for c in chunks)

    @pytest.mark.asyncio
    async def test_successful_file_insert(self, mock_pdata, mock_db, tmp_path):
        # Create a temp file to process
        f = tmp_path / "testbook.txt"
        f.write_text("文一。文二。", encoding="utf-8")

        mock_db.insert_book.return_value = 1
        mock_db.update_book.return_value = True
        mock_pdata.stream_sentences_file.return_value = iter(["文一。", "文二。"])
        mock_pdata.process_sentence.return_value = []

        chunks = []
        async for chunk in handle_insert_file_stream(mock_pdata, mock_db, "testbook", str(f)):
            chunks.append(chunk)

        assert any(b"Processed" in c for c in chunks)
        # Temp file should be removed after processing
        assert not os.path.exists(str(f))

    @pytest.mark.asyncio
    async def test_file_insert_duplicate_name(self, mock_pdata, mock_db, tmp_path):
        f = tmp_path / "dupe.txt"
        f.write_text("文一。", encoding="utf-8")

        mock_db.insert_book.return_value = 0  # already exists
        mock_pdata.stream_sentences_file.return_value = iter(["文一。"])

        chunks = []
        async for chunk in handle_insert_file_stream(mock_pdata, mock_db, "dupe", str(f)):
            chunks.append(chunk)

        assert any(b"Name already used" in c for c in chunks)

    @pytest.mark.asyncio
    async def test_no_words_skipped(self, mock_pdata, mock_db):
        """When pdata returns 0 words, refs should not be inserted."""
        mock_db.insert_update_sentence.return_value = 100
        mock_pdata.process_sentence.return_value = []

        await do_insert_word_sentence_book_2_db(mock_pdata, mock_db, "empty sentence", book_id=1)

        mock_db.insert_update_sentence.assert_called_once()
        mock_db.insert_word.assert_not_called()
