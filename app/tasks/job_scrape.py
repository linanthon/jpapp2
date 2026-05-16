from enum import Enum
from typing import Dict, Tuple
import time
import random

import redis.asyncio as aioredis
import requests
from bs4 import BeautifulSoup

from app.taskiq_broker import broker
from app.config import JLPT_CACHE_RELOAD_STREAM, JLPT_CACHE_RELOAD_STREAM_MAXLEN
from app.tasks.helpers import bootstrap_runtime, cleanup_runtime
from utils.db import DBHandling
from utils.logger import get_logger


log = get_logger(__name__)

WIKIPEDIA_REQUEST_TIMEOUT_SEC = 20
WIKIPEDIA_REQUEST_RETRIES = 3
WIKIPEDIA_BACKOFF_BASE_SEC = 0.5
WIKIPEDIA_BACKOFF_MAX_SEC = 5.0

WIKIPEDIA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


async def _publish_jlpt_cache_reload(redis: aioredis.Redis | None, job_id: str, source: str) -> None:
    """Notify API process(es) to reload in-memory JLPT cache from DB (Redis Stream event)."""
    if redis is None:
        return
    try:
        await redis.xadd(
            JLPT_CACHE_RELOAD_STREAM,
            {
                "event": "jlpt_cache_reload",
                "job_id": job_id,
                "source": source,
                "ts": str(int(time.time())),
            },
            maxlen=max(JLPT_CACHE_RELOAD_STREAM_MAXLEN, 1),
            approximate=True,
        )
    except Exception as e:
        # Do not fail the job on cache-notify problems.
        log.warning(f"Failed to publish JLPT cache reload signal: {e}")


class ScrapeSources(str, Enum):
    WIKIPEDIA = "wikipedia"
    JLPT_SENSEI = "jlpt_sensei"

    @classmethod
    def from_source_id(cls, source_id: int) -> "ScrapeSources | None":
        mapping = {
            1: cls.WIKIPEDIA,
            2: cls.JLPT_SENSEI,
        }
        return mapping.get(source_id)


def scrape_all_jlpt(source: ScrapeSources) -> Tuple[Dict[str, str], str]:
    """Scrape all N1-N5 levels and return a word -> level mapping."""
    jlpt_map: Dict[str, str] = {}

    for level in range(5, 0, -1):
        if source == ScrapeSources.WIKIPEDIA:
            vocab, err = scrape_wikipedia(level)
        else:
            vocab, err = scrape_jlpt_sensei(level)

        if err:
            return {}, err
        if not vocab:
            return {}, f"scraped nothing for N{level} from source: {source.value}"

        tier = f"N{level}"
        for word in vocab:
            if word:
                jlpt_map[word] = tier

    return jlpt_map, ""


def scrape_wikipedia(level: int) -> Tuple[set[str], str]:
    """Scrape vocab from Wiktionary JLPT appendix pages."""
    if level < 1 or level > 5:
        return set(), "invalid level"

    vocab: set[str] = set()
    url = f"https://en.wiktionary.org/wiki/Appendix:JLPT/N{level}"
    log.info(f"Scraping JLPT N{level} from {url}")

    response = None
    err = ""
    for attempt in range(WIKIPEDIA_REQUEST_RETRIES):
        try:
            response = requests.get(
                url,
                headers=WIKIPEDIA_HEADERS,
                timeout=WIKIPEDIA_REQUEST_TIMEOUT_SEC,
            )
            if response.status_code == 200:
                break

            err = f"Failed to request N{level}: status code {response.status_code}"
            if attempt < WIKIPEDIA_REQUEST_RETRIES - 1:
                # Exponential backoff with jitter to reduce burst retries.
                backoff = min(WIKIPEDIA_BACKOFF_BASE_SEC * (2 ** attempt), WIKIPEDIA_BACKOFF_MAX_SEC)
                time.sleep(backoff + random.uniform(0, backoff * 0.25))
        except Exception as e:
            err = f"Failed to request N{level}: {e}"
            if attempt < WIKIPEDIA_REQUEST_RETRIES - 1:
                backoff = min(WIKIPEDIA_BACKOFF_BASE_SEC * (2 ** attempt), WIKIPEDIA_BACKOFF_MAX_SEC)
                time.sleep(backoff + random.uniform(0, backoff * 0.25))

    if response is None or response.status_code != 200:
        return set(), err or f"Failed to request N{level}: unknown request failure"

    try:
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception as e:
        return set(), f"Failed to parse N{level} page: {e}"

    # === Pattern for the word:
    # <table class="wikitable ...">
    #   ...
    #   <body>
    #       <tr>
    #           <td> <span ...> <a ...> KANJI </a> </span> </td>
    #           <td> <span ...> <a ...> FURIGANA </a> </span> </td>
    #           <td> <span ...> <a ...> MEANING </a> </span> </td>
    #           <td> FREQUENCY </td>
    #       </tr>
    #   </body>
    #   ...
    # </table>
    # Important Some word has only Furigana form and no Kanji
    tables = soup.find_all("table", attrs={"class": lambda x: x and "wikitable" in x})
    for table in tables:
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) > 0:
                kanji = tds[0].text.strip()
                furigana = tds[1].text.strip()
                vocab.add(kanji) if kanji != "" else vocab.add(furigana)
    return vocab, ""


def scrape_jlpt_sensei(level: int) -> Tuple[set[str], str]:
    """Placeholder source. JLPT sensei is not very good.
    Currently act as a template for additional option when scrape."""
    return set(), f"source not implemented: {ScrapeSources.JLPT_SENSEI.value} (N{level})"


@broker.task(task_name="jobscrape.process_jlpt")
async def process_scrape_jlpt_job(job_id: str, source: str) -> None:
    """Run JLPT scrape, replace JLPT mapping table, then update all words' JLPT levels."""
    db: DBHandling | None = None
    redis: aioredis.Redis | None = None
    if not job_id:
        raise ValueError("Missing required job_id")

    try:
        db, redis, _ = await bootstrap_runtime()
        if not await db.claim_job_scrape(job_id):
            return

        try:
            source_enum = ScrapeSources(source)
        except ValueError:
            await db.update_job_scrape_status(job_id, "FAILED", error=f"invalid source: {source}")
            raise

        jlpt_map, err = scrape_all_jlpt(source_enum)
        if err:
            await db.update_job_scrape_status(job_id, "FAILED", error=err)
            raise RuntimeError(err)

        if not await db.replace_jlpt_levels(jlpt_map):
            await db.update_job_scrape_status(job_id, "FAILED", error="failed to replace jlpt_levels")
            raise RuntimeError("failed to replace jlpt_levels")

        if not await db.update_job_scrape_status(job_id, "UPDATING_WORDS"):
            await db.update_job_scrape_status(job_id, "FAILED", error="failed to set UPDATING_WORDS status")
            raise RuntimeError("failed to set UPDATING_WORDS status")

        if not await db.update_word_jlpt():
            await db.update_job_scrape_status(job_id, "FAILED", error="failed to update words.jlpt_level")
            raise RuntimeError("failed to update words.jlpt_level")

        await db.update_job_scrape_status(job_id, "FINISHED")
        await _publish_jlpt_cache_reload(redis, job_id, source_enum.value)

    except Exception as e:
        if db is not None:
            await db.update_job_scrape_status(job_id, "FAILED", error=str(e))
        raise
    finally:
        await cleanup_runtime(db, redis)


@broker.task(task_name="jobscrape.update_words_from_jlpt")
async def process_update_words_from_jlpt_job(job_id: str) -> None:
    """Update words.jlpt_level from existing jlpt_levels values only (no scraping)."""
    db: DBHandling | None = None
    redis: aioredis.Redis | None = None
    if not job_id:
        raise ValueError("Missing required job_id")

    try:
        db, redis, _ = await bootstrap_runtime()
        if not await db.claim_job_scrape(job_id):
            return

        if not await db.update_job_scrape_status(job_id, "UPDATING_WORDS"):
            await db.update_job_scrape_status(job_id, "FAILED", error="failed to set UPDATING_WORDS status")
            raise RuntimeError("failed to set UPDATING_WORDS status")

        if not await db.update_word_jlpt():
            await db.update_job_scrape_status(job_id, "FAILED", error="failed to update words.jlpt_level")
            raise RuntimeError("failed to update words.jlpt_level")

        await db.update_job_scrape_status(job_id, "FINISHED")
        await _publish_jlpt_cache_reload(redis, job_id, "jlpt_levels")

    except Exception as e:
        if db is not None:
            await db.update_job_scrape_status(job_id, "FAILED", error=str(e))
        raise
    finally:
        await cleanup_runtime(db, redis)

