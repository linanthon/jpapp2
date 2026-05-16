import redis.asyncio as aioredis
from fastapi import UploadFile

from app.handlers.insert import handle_insert_file_stream, handle_insert_str_stream
from app.handlers.view import delete_book_helper
from app.taskiq_broker import broker
from app.tasks.helpers import bootstrap_runtime, cleanup_runtime, maybe_publish_dlq
from utils.db import DBHandling
from utils.storage import get_file_from_minio_as_stream


async def _rollback_process_book_data_job(
	db: DBHandling,
	redis: aioredis.Redis | None,
	batch_item_id: str,
	book_id: int,
	task_name: str,
	error: str,
	payload: dict,
) -> None:
	"""Compensating action for insert task failures using batch-item state.

	Saga step order on failure:
	1) mark item FAILED_PROCESS
	2) compensate book + storage via delete_book_helper
	3) publish DLQ when retries are exhausted and rollback fails
	"""
	await db.update_job_book_batch_item_status(batch_item_id, "FAILED_PROCESS", error=error)
	book = await db.get_exact_book(book_id=book_id)
	rolled_back = await delete_book_helper(db, book_id, (book or {}).get("object_name", ""))
	if rolled_back:
		return

	await maybe_publish_dlq(
		db,
		redis,
		batch_item_id,
		task_name,
		error,
		payload,
	)


@broker.task(task_name="jobbook.process_insert_str")
async def process_insert_str_job(batch_item_id: str, book_id: int, data: str) -> None:
	"""Process string insert in worker and persist workflow state for retries/rollback.
	
	Input:
	- batch_item_id: The job ID for 1 single item in the batch
	"""
	db: DBHandling | None = None
	redis: aioredis.Redis | None = None
	if not batch_item_id:
		raise ValueError("Missing required batch_item_id")

	try:
		db, redis, pdata = await bootstrap_runtime()
		if not await db.claim_job_book_batch_item_for_processing(batch_item_id):
			return

		await handle_insert_str_stream(pdata, db, redis, book_id, data)
		await db.update_insert_book_status_finished(book_id)
		await db.update_job_book_batch_item_status(batch_item_id, "FINISHED")

	except Exception as e:
		if db is not None:
			await _rollback_process_book_data_job(
				db,
				redis,
				batch_item_id,
				book_id,
				task_name="jobbook.process_insert_str",
				error=str(e),
				payload={"book_id": book_id, "data": data},
			)
		raise
	finally:
		await cleanup_runtime(db, redis)


@broker.task(task_name="jobbook.process_insert_file")
async def process_insert_file_job(batch_item_id: str, book_id: int, object_name: str,
								  filename: str, file_size: int | None = 0) -> None:
	"""Process file insert in worker from MinIO object and persist workflow state.
	
	Input:
	- batch_item_id: The job ID for 1 single item in the batch
	"""
	db: DBHandling | None = None
	redis: aioredis.Redis | None = None
	if not batch_item_id:
		raise ValueError("Missing required batch_item_id")

	try:
		db, redis, pdata = await bootstrap_runtime()
		if not await db.claim_job_book_batch_item_for_processing(batch_item_id):
			return

		file_stream = get_file_from_minio_as_stream(object_name)
		upload = UploadFile(file=file_stream, filename=filename, size=file_size)
		await handle_insert_file_stream(pdata, db, redis, book_id, upload)
		await db.update_insert_book_status_finished(book_id)
		await db.update_job_book_batch_item_status(batch_item_id, "FINISHED")

	except Exception as e:
		if db is not None:
			await _rollback_process_book_data_job(
				db,
				redis,
				batch_item_id,
				book_id,
				task_name="jobbook.process_insert_file",
				error=str(e),
				payload={
					"book_id": book_id,
					"object_name": object_name,
					"filename": filename,
					"file_size": file_size,
				},
			)
		raise
	finally:
		await cleanup_runtime(db, redis)


@broker.task(task_name="jobbook.process_delete")
async def process_delete_job_book(job_id: str, book_id: int, object_name: str = "", batch_item_id: str = "") -> None:
	"""Delete a book in worker with workflow status updates."""
	db: DBHandling | None = None
	redis: aioredis.Redis | None = None
	if not batch_item_id:
		raise ValueError("Missing required batch_item_id")

	try:
		db, redis, _ = await bootstrap_runtime()
		if not await db.claim_job_book_batch_item_for_processing(batch_item_id):
			return

		deleted = await delete_book_helper(db, book_id, object_name)
		if not deleted:
			await db.update_job_book_batch_item_status(batch_item_id, "FAILED_PROCESS", error="Failed to delete book")
			raise RuntimeError("Failed to delete book")

		await db.update_job_book_batch_item_status(batch_item_id, "FINISHED")
	except Exception as e:
		if db is not None:
			await db.update_job_book_batch_item_status(batch_item_id, "FAILED_PROCESS", error=str(e))
			await maybe_publish_dlq(
				db,
				redis,
				batch_item_id,
				"jobbook.process_delete",
				str(e),
				{"book_id": book_id, "object_name": object_name},
			)
		raise
	finally:
		await cleanup_runtime(db, redis)
