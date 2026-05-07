import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks.job_books import (
    process_delete_job_book,
    process_insert_file_job,
    process_insert_str_job,
)


def _make_runtime():
    db = MagicMock()
    db.claim_job_book_batch_item_for_processing = AsyncMock(return_value=True)
    db.update_job_book_batch_item_status = AsyncMock(return_value=True)
    db.update_insert_book_status_finished = AsyncMock(return_value=True)
    db.get_exact_book = AsyncMock(return_value={"object_name": "obj_1"})
    db.get_job_book_batch_item = AsyncMock(
        return_value={
            "id": "item-x",
            "batch_id": "batch-x",
            "user_id": 1,
            "book_id": 1,
            "action": "INSERT_STR",
            "status": "FAILED",
            "attempts": 1,
            "max_attempts": 3,
        }
    )

    redis = AsyncMock()
    pdata = MagicMock()
    return db, redis, pdata


class TestJobBookTasks:
    @pytest.mark.asyncio
    async def test_insert_str_success(self):
        db, redis, pdata = _make_runtime()

        with patch("app.tasks.job_books._bootstrap_runtime", new=AsyncMock(return_value=(db, redis, pdata))), \
            patch("app.tasks.job_books._cleanup_runtime", new=AsyncMock()) as cleanup_mock, \
            patch("app.tasks.job_books.handle_insert_str_stream", new=AsyncMock()) as insert_mock:
            await process_insert_str_job.original_func("item-1", 10, "abc")

        insert_mock.assert_awaited_once_with(pdata, db, redis, 10, "abc")
        db.update_insert_book_status_finished.assert_awaited_once_with(10)
        db.claim_job_book_batch_item_for_processing.assert_awaited_once_with("item-1")
        db.update_job_book_batch_item_status.assert_any_await("item-1", "FINISHED")
        cleanup_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_insert_str_failure_rolls_back(self):
        db, redis, pdata = _make_runtime()

        with patch("app.tasks.job_books._bootstrap_runtime", new=AsyncMock(return_value=(db, redis, pdata))), \
            patch("app.tasks.job_books._cleanup_runtime", new=AsyncMock()) as cleanup_mock, \
            patch("app.tasks.job_books.handle_insert_str_stream", new=AsyncMock(side_effect=RuntimeError("boom"))), \
            patch("app.tasks.job_books.delete_book_helper", new=AsyncMock(return_value=True)) as rollback_mock:
            with pytest.raises(RuntimeError, match="boom"):
                await process_insert_str_job.original_func("item-2", 11, "abc")

        db.update_job_book_batch_item_status.assert_any_await("item-2", "FAILED_PROCESS", error="boom")
        rollback_mock.assert_awaited_once()
        cleanup_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_insert_file_success(self):
        db, redis, pdata = _make_runtime()

        with patch("app.tasks.job_books._bootstrap_runtime", new=AsyncMock(return_value=(db, redis, pdata))), \
            patch("app.tasks.job_books._cleanup_runtime", new=AsyncMock()) as cleanup_mock, \
            patch("app.tasks.job_books.get_file_from_minio_as_stream", return_value=io.BytesIO(b"x")) as stream_mock, \
            patch("app.tasks.job_books.handle_insert_file_stream", new=AsyncMock()) as insert_mock:
            await process_insert_file_job.original_func(
                "item-3", 12, "obj_file", "book.txt", 1
            )

        stream_mock.assert_called_once_with("obj_file")
        insert_mock.assert_awaited_once()
        db.claim_job_book_batch_item_for_processing.assert_awaited_once_with("item-3")
        db.update_job_book_batch_item_status.assert_any_await("item-3", "FINISHED")
        cleanup_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_failure_marks_failed(self):
        db, redis, _ = _make_runtime()

        with patch("app.tasks.job_books._bootstrap_runtime", new=AsyncMock(return_value=(db, redis, MagicMock()))), \
            patch("app.tasks.job_books._cleanup_runtime", new=AsyncMock()) as cleanup_mock, \
            patch("app.tasks.job_books.delete_book_helper", new=AsyncMock(return_value=False)):
            with pytest.raises(RuntimeError, match="Failed to delete book"):
                await process_delete_job_book.original_func("", 13, "obj", "item-4")

        db.update_job_book_batch_item_status.assert_any_await("item-4", "FAILED_PROCESS", error="Failed to delete book")
        cleanup_mock.assert_awaited_once()
        redis.xadd.assert_not_called()

    @pytest.mark.asyncio
    async def test_insert_file_failed_rollback_publishes_dlq_when_attempts_exhausted(self):
        db, redis, pdata = _make_runtime()
        db.get_job_book_batch_item.return_value = {
            "id": "item-5",
            "batch_id": "batch-5",
            "user_id": 1,
            "book_id": 12,
            "action": "INSERT_FILE",
            "status": "FAILED_ROLLBACK",
            "attempts": 3,
            "max_attempts": 3,
        }

        with patch("app.tasks.job_books._bootstrap_runtime", new=AsyncMock(return_value=(db, redis, pdata))), \
            patch("app.tasks.job_books._cleanup_runtime", new=AsyncMock()) as cleanup_mock, \
            patch("app.tasks.job_books.get_file_from_minio_as_stream", return_value=io.BytesIO(b"x")), \
            patch("app.tasks.job_books.handle_insert_file_stream", new=AsyncMock(side_effect=RuntimeError("boom"))), \
            patch("app.tasks.job_books.delete_book_helper", new=AsyncMock(return_value=False)):
            with pytest.raises(RuntimeError, match="boom"):
                await process_insert_file_job.original_func(
                    "item-5", 12, "obj_file", "book.txt", 1
                )

        redis.xadd.assert_awaited_once()
        cleanup_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_insert_file_missing_batch_item_id_fails_fast(self):
        with patch("app.tasks.job_books._bootstrap_runtime", new=AsyncMock()) as bootstrap_mock:
            with pytest.raises(ValueError, match="Missing required batch_item_id"):
                await process_insert_file_job.original_func("", 12, "obj_file", "book.txt", 1)

        bootstrap_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_insert_str_missing_batch_item_id_fails_fast(self):
        with patch("app.tasks.job_books._bootstrap_runtime", new=AsyncMock()) as bootstrap_mock:
            with pytest.raises(ValueError, match="Missing required batch_item_id"):
                await process_insert_str_job.original_func("", 12, "abc")

        bootstrap_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_insert_str_duplicate_delivery_is_noop_when_claim_fails(self):
        db, redis, pdata = _make_runtime()
        db.claim_job_book_batch_item_for_processing = AsyncMock(return_value=False)

        with patch("app.tasks.job_books._bootstrap_runtime", new=AsyncMock(return_value=(db, redis, pdata))), \
            patch("app.tasks.job_books._cleanup_runtime", new=AsyncMock()) as cleanup_mock, \
            patch("app.tasks.job_books.handle_insert_str_stream", new=AsyncMock()) as insert_mock:
            await process_insert_str_job.original_func("item-dup", 10, "abc")

        db.claim_job_book_batch_item_for_processing.assert_awaited_once_with("item-dup")
        insert_mock.assert_not_awaited()
        db.update_insert_book_status_finished.assert_not_awaited()
        db.update_job_book_batch_item_status.assert_not_awaited()
        cleanup_mock.assert_awaited_once()
