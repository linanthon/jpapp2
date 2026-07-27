from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import redis.asyncio as aioredis
import asyncio
import os
import uvicorn
import uuid

from utils.db import DBHandling
from utils.process_data import ProcessData
from utils.data import read_jlpt_from_db
from app.config import (DB_USER, DB_PASS, REDIS_URL, bpv1_url_prefix, JLPT_CACHE_RELOAD_STREAM,
                        JLPT_CACHE_RELOAD_GROUP, JLPT_CACHE_RELOAD_BLOCK_MS, SEARCH_WORD_VERSION_KEY)
from app.dependencies import redis_get_json
from app.routes import router
from utils.logger import get_logger


log = get_logger(__name__)


def _build_cors_allow_origins() -> list[str]:
    """Parse optional CORS_ALLOW_ORIGINS env var (comma-separated)."""
    raw = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


async def _jlpt_cache_reload_listener(app: FastAPI) -> None:
    """Listen for JLPT cache-reload stream events and refresh in-memory cache.
    Use Redis built-in pub/sub for this job (not taskiq bg job)"""
    if not hasattr(app.state, "redis"):
        return

    while True:
        # Redis blocks the call and wakes it only `new msg` or `block timeout`
        fetched = await app.state.redis.xreadgroup(
            groupname=JLPT_CACHE_RELOAD_GROUP,
            consumername=app.state.jlpt_reload_consumer,
            streams={JLPT_CACHE_RELOAD_STREAM: ">"},
            block=max(JLPT_CACHE_RELOAD_BLOCK_MS, 1),
            count=10,
        )
        for stream_name, msg_list in fetched:
            for msg_id, msg in msg_list:
                # Read then ack
                await read_jlpt_from_db(app.state.db, app.state.redis)
                await app.state.redis.xack(stream_name, JLPT_CACHE_RELOAD_GROUP, msg_id)
                log.info(f"Reloaded JLPT cache from DB via stream event: {msg}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup ----------------------------
    # Connect DB, migrate tables
    app.state.db = DBHandling()
    await app.state.db.connect_2_db(
        username=DB_USER,
        password=DB_PASS
    )
    if not await app.state.db.migrate():
        raise Exception("Error: DB migration error, please check the tables script. Shutting down.")

    # Connect Redis for caching, sessions, rate limiting
    try:
        app.state.redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
        await app.state.redis.ping()  # Test connection
        # Set initial word search version if not found
        search_version = await redis_get_json(app.state.redis, SEARCH_WORD_VERSION_KEY)
        if not search_version:
            await app.state.redis.set(SEARCH_WORD_VERSION_KEY, "1")
    except Exception as e:
        raise Exception(f"Error: Failed to connect to Redis: {e}")

    # Setup Redis Stream consumer group for JLPT cache reload notifications.
    app.state.jlpt_reload_consumer = f"api-{uuid.uuid4().hex}"
    try:
        await app.state.redis.xgroup_create(
            JLPT_CACHE_RELOAD_STREAM,
            JLPT_CACHE_RELOAD_GROUP,
            id="$",
            mkstream=True,
        )
    except Exception as e:
        if "BUSYGROUP" not in str(e):
            raise

    # Shoule be very light overhead but note that all API nodes will connect to Redis to consume the read jlpt task
    app.state.jlpt_listener_task = asyncio.create_task(_jlpt_cache_reload_listener(app))

    # Bootstrap JLPT mapping only when DB table is empty.
    # Startup only enqueues the scrape job and continues serving.
    jlpt_count = await app.state.db.count_jlpt_levels()
    if jlpt_count == 0:
        from app.tasks.job_scrape import process_scrape_jlpt_job, ScrapeSources

        startup_idem_key = f"startup-jlpt-bootstrap:{uuid.uuid4().hex}"
        job_id, is_new = await app.state.db.create_job_scrape(
            user_id=None,
            idempotency_key=startup_idem_key,
            trigger_type="STARTUP",
            source=ScrapeSources.WIKIPEDIA.value,
        )
        if job_id and is_new:
            try:
                await process_scrape_jlpt_job.kiq(
                    job_id=job_id,
                    source=ScrapeSources.WIKIPEDIA.value,
                )
                log.info(f"Queued startup JLPT bootstrap job: {job_id}")
            except Exception as e:
                await app.state.db.update_job_scrape_status(job_id, "FAILED", error=str(e))
                log.error(f"Failed to enqueue startup JLPT bootstrap: {e}")
        else:
            log.error("Failed to initialize startup JLPT bootstrap job")
    else:
        # Just load JLPT from DB only when data existed.
        # No background job or redis stream related
        await read_jlpt_from_db(app.state.db, app.state.redis)

    # Load fugashi tagger and jamdict
    app.state.pdata = ProcessData()
    
    # Serve
    yield
    
    # Shutdown ---------------------------
    if hasattr(app.state, "jlpt_listener_task") and app.state.jlpt_listener_task:
        app.state.jlpt_listener_task.cancel()
        try:
            await app.state.jlpt_listener_task
        except asyncio.CancelledError:
            pass
    if hasattr(app.state, "redis"):
        await app.state.redis.aclose()
    if hasattr(app.state, "db"):
        await app.state.db.close_db()

def create_app():
    """
    Create FastAPI app with lifespan, connect with DB, load dictionaries.
    Read stop words, JLPT levels / Scrape if no JLPT levels yet.
    """
    app = FastAPI(lifespan=lifespan)
    allow_origins = _build_cors_allow_origins()
    app.add_middleware(
        CORSMiddleware,
        # Cover local frontend dev/preview ports (5173, 4173, and any other local port)
        # so preflight OPTIONS requests with Authorization/Idempotency-Key pass.
        allow_origins=allow_origins,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app

app = create_app()

# Add the router with prefix
app.include_router(router, prefix=bpv1_url_prefix)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
