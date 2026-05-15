import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks.job_scrape import (
    process_delete_job_book,
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