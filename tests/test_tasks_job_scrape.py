from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks.job_scrape import (
    JLPT_CACHE_RELOAD_STREAM,
    ScrapeSources,
    _publish_jlpt_cache_reload,
    process_scrape_jlpt_job,
    process_update_words_from_jlpt_job,
    scrape_all_jlpt,
    scrape_jlpt_sensei,
    scrape_wikipedia,
)


def _make_runtime():
    db = MagicMock()
    db.claim_job_scrape = AsyncMock(return_value=True)
    db.update_job_scrape_status = AsyncMock(return_value=True)
    db.replace_jlpt_levels = AsyncMock(return_value=True)
    db.update_word_jlpt = AsyncMock(return_value=True)

    redis = AsyncMock()
    pdata = MagicMock()
    return db, redis, pdata


class TestScrapeSources:
    def test_from_source_id(self):
        assert ScrapeSources.from_source_id(1) == ScrapeSources.WIKIPEDIA
        assert ScrapeSources.from_source_id(2) == ScrapeSources.JLPT_SENSEI
        assert ScrapeSources.from_source_id(999) is None


class TestScrapeAllJlpt:
    @patch("app.tasks.job_scrape.scrape_wikipedia")
    def test_wikipedia_success(self, mock_scrape_wikipedia):
        mock_scrape_wikipedia.side_effect = [
            ({"w5"}, ""),
            ({"w4"}, ""),
            ({"w3"}, ""),
            ({"w2"}, ""),
            ({"w1"}, ""),
        ]

        mapping, err = scrape_all_jlpt(ScrapeSources.WIKIPEDIA)

        assert err == ""
        assert mapping["w5"] == "N5"
        assert mapping["w1"] == "N1"

    @patch("app.tasks.job_scrape.scrape_jlpt_sensei")
    def test_source_error_propagates(self, mock_scrape_jlpt_sensei):
        mock_scrape_jlpt_sensei.return_value = (set(), "boom")

        mapping, err = scrape_all_jlpt(ScrapeSources.JLPT_SENSEI)

        assert mapping == {}
        assert err == "boom"

    @patch("app.tasks.job_scrape.scrape_wikipedia")
    def test_empty_vocab_is_error(self, mock_scrape_wikipedia):
        mock_scrape_wikipedia.return_value = (set(), "")

        mapping, err = scrape_all_jlpt(ScrapeSources.WIKIPEDIA)

        assert mapping == {}
        assert "scraped nothing" in err


class TestScrapeWikipedia:
    def test_invalid_level(self):
        vocab, err = scrape_wikipedia(0)
        assert vocab == set()
        assert err == "invalid level"

    @patch("app.tasks.job_scrape.requests.get")
    def test_request_failure(self, mock_get):
        mock_get.side_effect = RuntimeError("network down")

        vocab, err = scrape_wikipedia(5)

        assert vocab == set()
        assert "Failed to request N5" in err

    @patch("app.tasks.job_scrape.requests.get")
    def test_http_non_200(self, mock_get):
        resp = MagicMock()
        resp.status_code = 500
        mock_get.return_value = resp

        vocab, err = scrape_wikipedia(5)

        assert vocab == set()
        assert "status code 500" in err

    @patch("app.tasks.job_scrape.requests.get")
    def test_parse_vocab(self, mock_get):
        html = """
        <html><body>
          <table class=\"wikitable\">
            <tr><td>食べる</td><td>たべる</td><td>to eat</td><td>100</td></tr>
            <tr><td></td><td>あいさつ</td><td>greeting</td><td>20</td></tr>
          </table>
        </body></html>
        """
        resp = MagicMock()
        resp.status_code = 200
        resp.text = html
        mock_get.return_value = resp

        vocab, err = scrape_wikipedia(5)

        assert err == ""
        assert "食べる" in vocab
        assert "あいさつ" in vocab


class TestScrapeJlptSensei:
    def test_not_implemented(self):
        vocab, err = scrape_jlpt_sensei(5)
        assert vocab == set()
        assert "source not implemented" in err


class TestPublishJlptCacheReload:
    @pytest.mark.asyncio
    async def test_noop_when_redis_none(self):
        await _publish_jlpt_cache_reload(None, "job-1", "wikipedia")

    @pytest.mark.asyncio
    async def test_publish_xadd(self):
        redis = AsyncMock()

        await _publish_jlpt_cache_reload(redis, "job-1", "wikipedia")

        redis.xadd.assert_awaited_once()
        args, kwargs = redis.xadd.await_args
        assert args[0] == JLPT_CACHE_RELOAD_STREAM
        assert args[1]["event"] == "jlpt_cache_reload"
        assert args[1]["job_id"] == "job-1"
        assert args[1]["source"] == "wikipedia"
        assert "ts" in args[1]
        assert kwargs["approximate"] is True


class TestProcessScrapeJlptJob:
    @pytest.mark.asyncio
    async def test_missing_job_id(self):
        with pytest.raises(ValueError):
            await process_scrape_jlpt_job("", ScrapeSources.WIKIPEDIA.value)

    @pytest.mark.asyncio
    async def test_claim_failed_returns(self):
        db, redis, pdata = _make_runtime()
        db.claim_job_scrape.return_value = False

        with patch("app.tasks.job_scrape.bootstrap_runtime", new=AsyncMock(return_value=(db, redis, pdata))), \
             patch("app.tasks.job_scrape.cleanup_runtime", new=AsyncMock()) as mock_cleanup:
            await process_scrape_jlpt_job("job-1", ScrapeSources.WIKIPEDIA.value)

        db.claim_job_scrape.assert_awaited_once_with("job-1")
        db.replace_jlpt_levels.assert_not_called()
        mock_cleanup.assert_awaited_once_with(db, redis)

    @pytest.mark.asyncio
    async def test_success_flow(self):
        db, redis, pdata = _make_runtime()

        with patch("app.tasks.job_scrape.bootstrap_runtime", new=AsyncMock(return_value=(db, redis, pdata))), \
             patch("app.tasks.job_scrape.cleanup_runtime", new=AsyncMock()) as mock_cleanup, \
             patch("app.tasks.job_scrape.scrape_all_jlpt", return_value=({"食べる": "N5"}, "")), \
             patch("app.tasks.job_scrape._publish_jlpt_cache_reload", new=AsyncMock()) as mock_publish:
            await process_scrape_jlpt_job("job-1", ScrapeSources.WIKIPEDIA.value)

        db.claim_job_scrape.assert_awaited_once_with("job-1")
        db.replace_jlpt_levels.assert_awaited_once_with({"食べる": "N5"})
        db.update_word_jlpt.assert_awaited_once()
        db.update_job_scrape_status.assert_any_await("job-1", "UPDATING_WORDS")
        db.update_job_scrape_status.assert_any_await("job-1", "FINISHED")
        mock_publish.assert_awaited_once_with(redis, "job-1", ScrapeSources.WIKIPEDIA.value)
        mock_cleanup.assert_awaited_once_with(db, redis)

    @pytest.mark.asyncio
    async def test_invalid_source_marks_failed(self):
        db, redis, pdata = _make_runtime()

        with patch("app.tasks.job_scrape.bootstrap_runtime", new=AsyncMock(return_value=(db, redis, pdata))), \
             patch("app.tasks.job_scrape.cleanup_runtime", new=AsyncMock()):
            with pytest.raises(ValueError):
                await process_scrape_jlpt_job("job-1", "invalid")

        assert db.update_job_scrape_status.await_count >= 1
        first_call = db.update_job_scrape_status.await_args_list[0]
        assert first_call.args[0] == "job-1"
        assert first_call.args[1] == "FAILED"


class TestProcessUpdateWordsFromJlptJob:
    @pytest.mark.asyncio
    async def test_missing_job_id(self):
        with pytest.raises(ValueError):
            await process_update_words_from_jlpt_job("")

    @pytest.mark.asyncio
    async def test_success_flow(self):
        db, redis, pdata = _make_runtime()

        with patch("app.tasks.job_scrape.bootstrap_runtime", new=AsyncMock(return_value=(db, redis, pdata))), \
             patch("app.tasks.job_scrape.cleanup_runtime", new=AsyncMock()) as mock_cleanup, \
             patch("app.tasks.job_scrape._publish_jlpt_cache_reload", new=AsyncMock()) as mock_publish:
            await process_update_words_from_jlpt_job("job-2")

        db.claim_job_scrape.assert_awaited_once_with("job-2")
        db.update_job_scrape_status.assert_any_await("job-2", "UPDATING_WORDS")
        db.update_word_jlpt.assert_awaited_once()
        db.update_job_scrape_status.assert_any_await("job-2", "FINISHED")
        mock_publish.assert_awaited_once_with(redis, "job-2", "jlpt_levels")
        mock_cleanup.assert_awaited_once_with(db, redis)

    @pytest.mark.asyncio
    async def test_update_words_failed_marks_failed(self):
        db, redis, pdata = _make_runtime()
        db.update_word_jlpt.return_value = False

        with patch("app.tasks.job_scrape.bootstrap_runtime", new=AsyncMock(return_value=(db, redis, pdata))), \
             patch("app.tasks.job_scrape.cleanup_runtime", new=AsyncMock()):
            with pytest.raises(RuntimeError):
                await process_update_words_from_jlpt_job("job-2")

        # Last status call should be FAILED from exception handling path.
        assert db.update_job_scrape_status.await_count >= 2
        assert db.update_job_scrape_status.await_args_list[-1].args[1] == "FAILED"
