import redis.asyncio as aioredis

from app.taskiq_broker import broker
from app.tasks.helpers import bootstrap_runtime, cleanup_runtime
from utils.db import DBHandling
from utils.tts import TTSService, TTSAdapterError


tts_service = TTSService()


@broker.task(task_name="jobtts.process_tts")
async def process_tts_job(job_id: str) -> None:
    """Process one async TTS job.

    Flow:
    1) Claim job (QUEUED -> PROCESSING)
    2) Generate from cache/model
    3) Persist FINISHED metadata or FAILED error
    """
    if not job_id:
        raise ValueError("Missing required job_id")

    db: DBHandling | None = None
    redis: aioredis.Redis | None = None

    try:
        db, redis, _ = await bootstrap_runtime()
        if not await db.claim_job_tts(job_id):
            return

        job = await db.get_job_tts(job_id)
        if not job:
            return

        text = job.get("text", "")
        lang = job.get("lang", "")
        voice_options = job.get("voice_options", {}) or {}

        try:
            await tts_service.synthesize(text, lang, redis, voice_options=voice_options)
            await db.update_job_tts_finished(job_id)
        except TTSAdapterError as exc:
            fallback = await tts_service.build_statica_fallback(text, lang, str(exc), db)
            if fallback is not None:
                await db.update_job_tts_finished(job_id)
            else:
                await db.update_job_tts_failed(job_id, error=str(exc))
    except Exception as e:
        if db is not None:
            await db.update_job_tts_failed(job_id, error=str(e))
        raise
    finally:
        await cleanup_runtime(db, redis)
