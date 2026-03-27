from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import redis.asyncio as aioredis
import os
import uvicorn

from utils.db import DBHandling
from utils.process_data import ProcessData
from utils.data import read_stop_words, read_jlpt, scrape_all_jlpt
from app.config import DB_USER, DB_PASS, REDIS_URL, bpv1_url_prefix
from app.routes import router


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
    except Exception as e:
        raise Exception(f"Error: Failed to connect to Redis: {e}")

    # Load fugashi tagger and jamdict
    app.state.pdata = ProcessData()
    
    yield
    
    # Shutdown ---------------------------
    if hasattr(app.state, "redis"):
        await app.state.redis.close()
    if hasattr(app.state, "db"):
        await app.state.db.close_db()

def create_app():
    """
    Create FastAPI app with lifespan, connect with DB, load dictionaries.
    Read stop words, JLPT levels / Scrape if no JLPT levels yet.
    """
    app = FastAPI(lifespan=lifespan)
    read_stop_words()
    scrape_all_jlpt()
    read_jlpt()
    return app

app = create_app()

# Add the router with prefix
app.include_router(router, prefix=bpv1_url_prefix)

# Add static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
