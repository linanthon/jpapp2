import json

import redis.asyncio as aioredis

from app.config import (DB_USER, DB_PASS, REDIS_URL, TASKIQ_DLQ_STREAM,
						TASKIQ_MAX_ATTEMPTS, TASKIQ_STREAM_MAXLEN_DLQ)
from utils.db import DBHandling
from utils.process_data import ProcessData


async def bootstrap_runtime() -> tuple[DBHandling, aioredis.Redis, ProcessData]:
	db = DBHandling()
	await db.connect_2_db(username=DB_USER, password=DB_PASS)
	redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
	pdata = ProcessData()
	return db, redis, pdata


async def cleanup_runtime(db: DBHandling | None, redis: aioredis.Redis | None):
	if redis is not None:
		await redis.close()
	if db is not None:
		await db.close_db()


def _to_stream_value(value):
	if value is None:
		return ""
	if isinstance(value, (dict, list, tuple, set)):
		return json.dumps(value, ensure_ascii=True)
	if isinstance(value, bytes):
		return value.decode("utf-8", errors="replace")
	return str(value)


async def _publish_dlq_message(
	redis: aioredis.Redis,
	job: dict,
	task_name: str,
	error: str,
	payload: dict,
):
	"""Persist terminally failed messages to a dedicated DLQ stream."""
	message = {
		str(key): _to_stream_value(value)
		for key, value in job.items()
	}
	# Keep aliases/overrides predictable for DLQ consumers.
	message["job_id"] = _to_stream_value(job.get("id", ""))
	message["task_name"] = task_name
	message["error"] = error
	message["payload"] = json.dumps(payload, ensure_ascii=True)

	await redis.xadd(
		TASKIQ_DLQ_STREAM,
		message,
		maxlen=max(TASKIQ_STREAM_MAXLEN_DLQ, 1),
		approximate=True,
	)


async def maybe_publish_dlq(
	db: DBHandling,
	redis: aioredis.Redis | None,
	batch_item_id: str,
	task_name: str,
	error: str,
	payload: dict,
):
	"""Publish to DLQ only when retry attempts reach configured maximum."""
	if redis is None:
		return

	item = await db.get_job_book_batch_item(batch_item_id)
	if not item:
		return

	attempts = int(item.get("attempts", 0) or 0)
	if TASKIQ_MAX_ATTEMPTS > 0 and attempts >= TASKIQ_MAX_ATTEMPTS:
		await _publish_dlq_message(redis, item, task_name, error, payload)
