"""Tests for app/handlers/insert.py — insert logic with mocked DB/pdata."""
import pytest
import os
from http import HTTPStatus
from unittest.mock import MagicMock, AsyncMock

from app.handlers.insert import (
    do_insert_word_sentence_book_2_db,
    handle_insert_str_stream,
    handle_insert_file_stream,
)
from schemas.word import Word


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
def _make_upload_file(filename="testbook.txt", content=b"", size=None):
    """Helper: create a mock UploadFile with .file, .filename, .size."""
    upload = MagicMock()
    upload.filename = filename
    upload.size = size if size is not None else len(content)
    upload.file = MagicMock()
    return upload


class TestHandleInsertFileStream:
    @pytest.mark.asyncio
    async def test_successful_file_insert(self, mock_pdata, mock_db, mock_redis):
        upload = _make_upload_file("testbook.txt", size=100)
        mock_pdata.stream_sentences_file.return_value = iter(["文一。", "文二。"])
        mock_pdata.process_sentence.return_value = []

        await handle_insert_file_stream(mock_pdata, mock_db, mock_redis, book_id=1, submittedFile=upload)

        mock_pdata.stream_sentences_file.assert_called_once_with(upload, auto_strip=True)
        # Two sentences → two progress updates + one final
        assert mock_redis.set.call_count == 3
        # Final call should contain the filename
        final_call = mock_redis.set.call_args_list[-1]
        assert "testbook.txt" in final_call.args[1]

    @pytest.mark.asyncio
    async def test_progress_written_to_redis(self, mock_pdata, mock_db, mock_redis):
        upload = _make_upload_file("book.txt", size=10)
        mock_pdata.stream_sentences_file.return_value = iter(["12345", "67890"])
        mock_pdata.process_sentence.return_value = []

        await handle_insert_file_stream(mock_pdata, mock_db, mock_redis, book_id=42, submittedFile=upload)

        # Check redis key uses book_id
        progress_calls = [c for c in mock_redis.set.call_args_list if "book_progress:42" in str(c)]
        assert len(progress_calls) >= 2

    @pytest.mark.asyncio
    async def test_no_sentences(self, mock_pdata, mock_db, mock_redis):
        upload = _make_upload_file("empty.txt", size=0)
        mock_pdata.stream_sentences_file.return_value = iter([])

        await handle_insert_file_stream(mock_pdata, mock_db, mock_redis, book_id=1, submittedFile=upload)
        # Only the final "Processed and inserted" message
        assert mock_redis.set.call_count == 1

    @pytest.mark.asyncio
    async def test_inserts_words_and_refs(self, mock_pdata, mock_db, mock_redis):
        """When process_sentence returns words, refs should be inserted for each."""
        word = Word(word="食べる", senses="to eat", spelling="タベル")
        upload = _make_upload_file("book.txt", size=50)
        mock_pdata.stream_sentences_file.return_value = iter(["食べてください。"])
        mock_pdata.process_sentence.return_value = [word]
        mock_db.insert_update_sentence.return_value = 100
        mock_db.insert_word.return_value = 200

        await handle_insert_file_stream(mock_pdata, mock_db, mock_redis, book_id=3, submittedFile=upload)

        mock_db.insert_update_sentence.assert_called_once()
        mock_db.insert_word.assert_called_once_with(word)
        mock_db.insert_word_book_ref.assert_called_once_with(200, 3)
        mock_db.insert_word_sentence_ref.assert_called_once_with(200, 100)
        mock_db.insert_sentence_book_ref.assert_called_once_with(100, 3)

    @pytest.mark.asyncio
    async def test_no_words_skipped(self, mock_pdata, mock_db):
        """When pdata returns 0 words, refs should not be inserted."""
        mock_db.insert_update_sentence.return_value = 100
        mock_pdata.process_sentence.return_value = []

        await do_insert_word_sentence_book_2_db(mock_pdata, mock_db, "empty sentence", book_id=1)

        mock_db.insert_update_sentence.assert_called_once()
        mock_db.insert_word.assert_not_called()
