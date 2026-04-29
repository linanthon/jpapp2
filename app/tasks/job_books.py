import redis.asyncio as aioredis
from fastapi import UploadFile

from app.config import DB_USER, DB_PASS, REDIS_URL
from app.handlers.insert import handle_insert_file_stream, handle_insert_str_stream
from app.handlers.view import delete_book_helper
from app.taskiq_broker import broker
from utils.db import DBHandling
from utils.process_data import ProcessData
from utils.storage import get_file_from_minio_as_stream


async def _bootstrap_runtime() -> tuple[DBHandling, aioredis.Redis, ProcessData]:
	db = DBHandling()
	await db.connect_2_db(username=DB_USER, password=DB_PASS)
	redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
	pdata = ProcessData()
	return db, redis, pdata


async def _cleanup_runtime(db: DBHandling | None, redis: aioredis.Redis | None):
	if redis is not None:
		await redis.close()
	if db is not None:
		await db.close_db()


@broker.task(task_name="jobbook.process_insert_str")
async def process_insert_str_job(job_id: str, book_id: int, data: str) -> None:
	"""Process string insert in worker and persist workflow state for retries/rollback."""
	db: DBHandling | None = None
	redis: aioredis.Redis | None = None

	try:
		db, redis, pdata = await _bootstrap_runtime()
		await db.update_job_book_status(job_id, "PROCESSING", attempts_inc=1)

		await handle_insert_str_stream(pdata, db, redis, book_id, data)
		await db.insert_book_finished(book_id)
		await db.update_job_book_status(job_id, "FINISHED")

	except Exception as e:
		if db is not None:
			await db.update_job_book_status(job_id, "ROLLING_BACK", error=str(e))
			book = await db.get_exact_book(book_id=book_id)
			rolled_back = await delete_book_helper(db, book_id, (book or {}).get("object_name", ""))
			if rolled_back:
				await db.update_job_book_status(job_id, "ROLLED_BACK", error=str(e))
			else:
				await db.update_job_book_status(job_id, "FAILED_ROLLBACK", error=str(e))
		raise
	finally:
		await _cleanup_runtime(db, redis)


@broker.task(task_name="jobbook.process_insert_file")
async def process_insert_file_job(job_id: str, book_id: int, object_name: str,
								  filename: str, file_size: int | None = None) -> None:
	"""Process file insert in worker from MinIO object and persist workflow state."""
	db: DBHandling | None = None
	redis: aioredis.Redis | None = None

	try:
		db, redis, pdata = await _bootstrap_runtime()
		await db.update_job_book_status(job_id, "PROCESSING", attempts_inc=1)

		file_stream = get_file_from_minio_as_stream(object_name)
		upload = UploadFile(file=file_stream, filename=filename, size=file_size)
		await handle_insert_file_stream(pdata, db, redis, book_id, upload)
		await db.insert_book_finished(book_id)
		await db.update_job_book_status(job_id, "FINISHED")

	except Exception as e:
		if db is not None:
			await db.update_job_book_status(job_id, "ROLLING_BACK", error=str(e))
			book = await db.get_exact_book(book_id=book_id)
			rolled_back = await delete_book_helper(db, book_id, (book or {}).get("object_name", ""))
			if rolled_back:
				await db.update_job_book_status(job_id, "ROLLED_BACK", error=str(e))
			else:
				await db.update_job_book_status(job_id, "FAILED_ROLLBACK", error=str(e))
		raise
	finally:
		await _cleanup_runtime(db, redis)


@broker.task(task_name="jobbook.process_delete")
async def process_delete_job_book(job_id: str, book_id: int, object_name: str = "") -> None:
	"""Delete a book in worker with workflow status updates."""
	db: DBHandling | None = None
	redis: aioredis.Redis | None = None

	try:
		db, redis, _ = await _bootstrap_runtime()
		await db.update_job_book_status(job_id, "PROCESSING", attempts_inc=1)

		deleted = await delete_book_helper(db, book_id, object_name)
		if not deleted:
			await db.update_job_book_status(job_id, "FAILED", error="Failed to delete book")
			raise RuntimeError("Failed to delete book")

		await db.update_job_book_status(job_id, "FINISHED")
	except Exception as e:
		if db is not None:
			await db.update_job_book_status(job_id, "FAILED", error=str(e))
		raise
	finally:
		await _cleanup_runtime(db, redis)
