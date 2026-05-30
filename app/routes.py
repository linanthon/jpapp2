from fastapi import APIRouter, Request, File, UploadFile, Form, Depends, HTTPException, Response, Body
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from http import HTTPStatus
import os
import io
import redis.asyncio as aioredis
import uuid

from app.config import (bpv1_url_prefix, FAILED_LOGIN_LIMIT, REFRESH_TOKEN_EXPIRE_DAYS,
                        FAILED_LOGIN_BLOCK_MINUTES, ACCESS_TOKEN_EXPIRE_MINUTES,
                        SEARCH_WORD_EXPIRE_MINUTES, MAX_INSERT_STRING_BYTES)
from app.handlers.insert import compensate_insert_saga
from app.handlers.progress import handle_progress
from app.handlers.view import (handle_search_word, handle_view_specific_word, handle_view_words,
                               handle_view_books, handle_view_specific_book,
                               toggle_star_helper, get_all_book_name_and_id)
from app.dependencies import (
    get_db, get_pdata, get_redis, get_current_user_id, get_current_user, get_current_admin_user,
    rate_limiter, redis_get_json, redis_set_json, validate_tts_request, parse_tts_voice_options
)
from app.handlers.quiz import (build_quizes, update_word_prio_after_answering,
                               update_word_prio_after_session, change_word_prio_to_negative, reset_word_prio)
from app.tasks.job_books import process_insert_file_job, process_insert_str_job, process_delete_job_book
from app.tasks.job_tts import process_tts_job
from app.tasks.job_scrape import (
    process_scrape_jlpt_job,
    process_update_words_from_jlpt_job,
    ScrapeSources,
)
from schemas.constants import DEFAULT_LIMIT, DEFAULT_SENTENCE_EXAMPLE_LIMIT, AUDIO_DIR
from schemas.user import UserCreate, UserLogin, TokenResponse, TokenRefresh, UserResponse
from utils.auth import hash_password, create_access_token, create_refresh_token, verify_password, verify_token
from utils.data import read_jlpt_from_db, JLPT_REDIS_KEY
from utils.db import DBHandling
from utils.helpers import (get_filename_from_path, get_file_extension_from_path, validate_jlpt_level,
                           parse_bool_param, validate_star)
from utils.logger import get_logger
from utils.process_data import ProcessData
from utils.storage import (upload_file_to_minio, upload_string_to_minio,
                           generate_presigned_upload_url, PRESIGNED_URL_EXPIRY, storage_object_exists)
from utils.tts import TTSService, TTSAdapterError

# Create router
router = APIRouter()
log = get_logger(__name__)
tts_service = TTSService()

# ===== AUTH ========================================================================
@router.post("/register", response_model=UserResponse, dependencies=[Depends(rate_limiter(5, 60))])
async def register(
    user_data: UserCreate,
    db: DBHandling = Depends(get_db)
):
    """
    Register a new user. Raise 429 if called 5 times/minute.
    
    Body: {username, email, password, is_admin}
    Returns: {id, username, email, is_admin}
    """
    if await db.user_exists(user_data.username):
        raise HTTPException(status_code=409, detail="Username already taken")
    if await db.user_exists_by_email(user_data.email):
        raise HTTPException(status_code=409, detail="Email already registered")
    
    hashed_password = hash_password(user_data.password)
    user_id = await db.create_user(
        username=user_data.username,
        email=user_data.email,
        password_hash=hashed_password,
        is_admin=user_data.is_admin
    )
    
    if not user_id:
        raise HTTPException(status_code=500, detail="Failed to create user")
    
    user = await db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=500, detail="Created user but failed to fetch user record")

    return JSONResponse(
            status_code=HTTPStatus.CREATED,
            content={"id": user["id"],"username": user["username"],"email": user["email"],"is_admin": user["is_admin"]}
        )


@router.post("/login", dependencies=[Depends(rate_limiter(10, 60))])
async def login(
    credentials: UserLogin,
    db: DBHandling = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis)
):
    """
    Login user and return JWT tokens.
    Will raise 429 if failed [FAILED_LOGIN_LIMIT] times or spam call 10 times/minute.
    
    Body: {username, password}
    Returns: {access_token, refresh_token, token_type}
    """
    # Rate limit (check failed login)
    failed_attempts = await redis.get(f"login_attempts:{credentials.username}")
    if failed_attempts and int(failed_attempts) >= FAILED_LOGIN_LIMIT:
        await redis.expire(f"login_attempts:{credentials.username}", FAILED_LOGIN_BLOCK_MINUTES)
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {FAILED_LOGIN_BLOCK_MINUTES} minutes."
        )
    
    # Get user from DB + Verify password
    user = await db.get_user_by_username(credentials.username)
    if not user or not verify_password(credentials.password, user['password_hash']):
        await redis.incr(f"login_attempts:{credentials.username}")
        await redis.expire(f"login_attempts:{credentials.username}", FAILED_LOGIN_BLOCK_MINUTES)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Clear failed attempts on successful login
    await redis.delete(f"login_attempts:{credentials.username}")
    
    # Create tokens
    access_token = create_access_token(user['id'])
    refresh_token = create_refresh_token(user['id'])
    
    # Store refresh token in Redis
    expire_secs = REFRESH_TOKEN_EXPIRE_DAYS*24*60*60
    await redis.setex(f"refresh_token:{user['id']}", expire_secs, refresh_token)
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token
    )


@router.post("/logout")
async def logout(
    request: Request,
    current_user_id: int = Depends(get_current_user_id),
    redis: aioredis.Redis = Depends(get_redis)
):
    """
    Logout user by blacklisting their access token and delete refresh token.
    Requires Authorization header with valid JWT.
    """
    # Extract token and blacklist it
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        await redis.setex(f"blacklist:{token}", ACCESS_TOKEN_EXPIRE_MINUTES*60, "true")
    
    # Delete the refresh token
    await redis.delete(f"refresh_token:{current_user_id}")
    
    return {"message": "Logged out successfully"}


@router.post("/refresh", dependencies=[Depends(rate_limiter(2, 60))])
async def refresh_token(
    token_data: TokenRefresh,
    redis: aioredis.Redis = Depends(get_redis)
):
    """
    Use refresh token to renew access token.
    'Access token' is the one to be used in headers of the requests.
    'Refresh token' is used to get new access token when it expires when used logged in and requested an endpoint.
    
    Body: {refresh_token}
    Returns: {access_token, refresh_token, token_type}
    """
    # Verify refresh token
    user_id = verify_token(token_data.refresh_token, token_type="refresh")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    
    # Check if refresh token exists in Redis
    stored_token = await redis.get(f"refresh_token:{user_id}")
    if stored_token != token_data.refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token is invalid or expired")
    
    # Create new tokens
    access_token = create_access_token(user_id)
    new_refresh_token = create_refresh_token(user_id)
    
    # Update refresh token in Redis
    await redis.setex(f"refresh_token:{user_id}", REFRESH_TOKEN_EXPIRE_DAYS*24*60*60, new_refresh_token)
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token
    )


@router.get("/me", response_model=UserResponse)
async def get_current_profile(
    current_user: dict = Depends(get_current_user),
):
    """Return current authenticated user's profile."""
    return {
        "id": current_user["id"],
        "username": current_user["username"],
        "email": current_user["email"],
        "is_admin": current_user["is_admin"],
    }


# ===== INSERT ===================================================================
@router.post("/insert/file/bg")
async def upload_file_bg(
    request: Request,
    submittedFile: UploadFile = File(None),
    db: DBHandling = Depends(get_db),
    current_admin: dict = Depends(get_current_admin_user)
):
    """Handle file upload (.txt, .pdf, .docx). Admin only. After upload to storage,
    queue file processing as a background task and return a job ID."""
    if not submittedFile or not submittedFile.filename:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="No file uploaded")

    ext = get_file_extension_from_path(submittedFile.filename)
    if ext not in ProcessData.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Unsupported file type: .{ext}. Allowed: {', '.join(ProcessData.ALLOWED_EXTENSIONS)}"
        )

    idem_key = request.headers.get("Idempotency-Key", "")
    if not idem_key:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Missing Idempotency-Key header")

    file_name = get_filename_from_path(submittedFile.filename)
    book_id, created = await db.insert_book_init(current_admin["id"], file_name, idem_key)
    if book_id <= 0:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize book '{file_name}'"
        )
    if not created:
        return JSONResponse(
            status_code=HTTPStatus.OK,
            content={"book_id": book_id, "message": "Duplicate request ignored"}
        )

    object_name = ""
    error_detail = ""
    try:
        content_bytes = await submittedFile.read()
        object_name = f"{uuid.uuid4().hex}_{file_name}"
        object_name = upload_file_to_minio(io.BytesIO(content_bytes), object_name)
        if not object_name:
            error_detail = f"Failed to upload file {file_name} to external storage."
            raise RuntimeError(error_detail)

        if not await db.update_insert_book_status_uploaded(book_id, object_name):
            error_detail = "Failed to finalize uploaded file metadata"
            raise RuntimeError(error_detail)

        batch_id, _ = await db.create_job_book_batch(current_admin["id"], idem_key)
        if not batch_id:
            error_detail = "Failed to initialize insert batch"
            raise RuntimeError(error_detail)

        item_id = await db.create_job_book_batch_item(
            batch_id=batch_id,
            user_id=current_admin["id"],
            file_name=submittedFile.filename,
            file_size=len(content_bytes),
            object_name=object_name,
            status="QUEUED_PROCESS",
            book_id=book_id,
        )
        if not item_id:
            error_detail = "Failed to create batch item"
            raise RuntimeError(error_detail)

        await process_insert_file_job.kiq(
            batch_item_id=item_id,
            book_id=book_id,
            object_name=object_name,
            filename=submittedFile.filename,
            file_size=len(content_bytes),
        )
    except Exception as e:
        await compensate_insert_saga(db, book_id, object_name)
        if not error_detail:
            error_detail = "Failed to enqueue background task"
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=error_detail
        ) from e

    return JSONResponse(
        status_code=HTTPStatus.ACCEPTED,
        content={
            "job_id": item_id,
            "batch_id": batch_id,
            "book_id": book_id,
            "status": "QUEUED",
            "message": "Background file insert queued"
        }
    )


@router.post("/insert/files/bg")
async def upload_files_bg(
    request: Request,
    payload: dict = Body(...),
    db: DBHandling = Depends(get_db),
    current_admin: dict = Depends(get_current_admin_user)
):
    """Initialize multi-file direct-upload flow by returning presigned upload URLs.
    The actual file never sent to BE, this endpoint will only write the job to DB,
    get presigned MinIO/S3 URLs, send back to FE. It is expected that FE will handle
    the file uploads, then call `/insert/files/bg/finalize` to run the data handling process.

    `payload` should be: {'files': [{'filename': '...', 'content-type': '...', 'size': ... }, {...}, ...]}.
    
    """
    files = payload.get("files", []) if isinstance(payload, dict) else []
    if not isinstance(files, list) or not files:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Missing files metadata")

    idem_key = request.headers.get("Idempotency-Key", "").strip()
    if not idem_key:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Missing Idempotency-Key header")

    # Idempotent check this request
    batch_id, job_created = await db.create_job_book_batch(current_admin["id"], idem_key)
    if not batch_id:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Failed to initialize background batch request"
        )
    if not job_created:
        items = await db.get_job_book_batch_items(batch_id)
        return JSONResponse(
            status_code=HTTPStatus.OK,
            content={
                "batch_id": batch_id,
                "status": "DUPLICATE_REQUEST",
                "items": items,
                "message": "Duplicate request ignored"
            }
        )

    # Validate payload
    normalized_files = []
    for entry in files:
        if not isinstance(entry, dict):
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Invalid files metadata format")

        file_name = str(entry.get("filename", "")).strip()
        content_type = str(entry.get("content_type", "application/octet-stream")).strip() or "application/octet-stream"
        try:
            file_size = int(entry.get("size", 0) or 0)
        except (ValueError, TypeError):
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Invalid file size")

        if not file_name:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="One or more files are invalid")

        ext = get_file_extension_from_path(file_name)
        if ext not in ProcessData.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=f"Unsupported file type: .{ext}. Allowed: {', '.join(ProcessData.ALLOWED_EXTENSIONS)}"
            )
        normalized_files.append({
            "filename": file_name,
            "content_type": content_type,
            "size": file_size,
        })

    # Get presinged URL + write DB job + for each file
    upload_items: list[dict] = []
    failed_files: list[dict] = []
    for one_file in normalized_files:
        file_name = one_file["filename"]
        object_name = f"uploads/{current_admin['id']}/{batch_id}/{uuid.uuid4().hex}_{get_filename_from_path(file_name)}"
        try:
            upload_url = generate_presigned_upload_url(
                object_name,
                expiry=PRESIGNED_URL_EXPIRY,
                content_type=one_file["content_type"],
            )
            if not upload_url:
                failed_files.append({"file": file_name, "error": "Failed to create presigned upload URL"})
                continue

            item_id = await db.create_job_book_batch_item(
                batch_id=batch_id,
                user_id=current_admin["id"],
                file_name=file_name,
                file_size=one_file["size"],
                object_name=object_name,
                status="UPLOADING",
            )
            if not item_id:
                failed_files.append({"file": file_name, "error": "Failed to create file job"})
                continue

            upload_items.append({
                "item_id": item_id,
                "file_name": file_name,
                "file_size": one_file["size"],
                "content_type": one_file["content_type"],
                "object_name": object_name,
                "upload_url": upload_url,
                "expires_in": PRESIGNED_URL_EXPIRY,
            })
        except Exception as e:
            failed_files.append({"file": file_name, "error": str(e)})

    if not upload_items:
        await db.update_job_book_batch_status(batch_id, "FAILED", error="No upload URL was generated")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Failed to initialize multi-file upload"
        )

    return JSONResponse(
        status_code=HTTPStatus.ACCEPTED,
        content={
            "batch_id": batch_id,
            "status": "UPLOADING",
            "item_count": len(upload_items),
            "items": upload_items,
            "failed_files": failed_files,
            "message": "Presigned upload URLs generated"
        }
    )


@router.post("/insert/files/bg/finalize")
async def finalize_upload_files_bg(
    payload: dict = Body(...),
    db: DBHandling = Depends(get_db),
    current_admin: dict = Depends(get_current_admin_user)
):
    """Frontend upload completed. Calling to enqueue data processing jobs."""
    batch_id = str(payload.get("batch_id", "")).strip()
    item_ids = payload.get("item_ids", [])
    if not batch_id or not isinstance(item_ids, list) or not item_ids:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Missing batch_id or item_ids")

    # Validate request
    batch = await db.get_job_book_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Batch not found")
    if batch.get("user_id") != current_admin["id"]:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Not allowed to finalize this batch")

    # Idempotent check the request
    claimed = await db.update_job_book_batch_status(batch_id, "UPLOADED")
    if not claimed:
        items = await db.get_job_book_batch_items(batch_id)
        return JSONResponse(
            status_code=HTTPStatus.OK,
            content={
                "batch_id": batch_id,
                "status": "DUPLICATE_REQUEST",
                "items": items,
                "message": "Duplicate request ignored"
            }
        )

    queued_items = []
    failed_items = []
    for item_id in item_ids:
        item = await db.get_job_book_batch_item(str(item_id))
        if not item or item.get("batch_id") != batch_id:
            failed_items.append({"item_id": str(item_id), "error": "Item not found in batch"})
            continue

        object_name = item.get("object_name", "")
        if not storage_object_exists(object_name):
            await db.update_job_book_batch_item_status(item["id"], "FAILED_UPLOAD", error="Uploaded object not found")
            failed_items.append({"item_id": item["id"], "error": f"Expected uploaded object {object_name} not found"})
            continue

        # At this point the object exists in storage and can be queued for processing.
        book_id = await db.insert_book_init_uploaded(current_admin["id"], item["file_name"], item["id"])
        if book_id <= 0:
            await db.update_job_book_batch_item_status(item["id"], "FAILED_UPLOAD", error="Failed to initialize book")
            failed_items.append({"item_id": item["id"], "error": "Failed to initialize book"})
            continue

        if not await db.update_job_book_batch_item_queued_process(item["id"], book_id, object_name):
            await db.update_job_book_batch_item_status(item["id"], "FAILED_UPLOAD", error="Failed to update upload status")
            failed_items.append({"item_id": item["id"], "error": "Failed to update upload status"})
            continue

        await process_insert_file_job.kiq(
            batch_item_id=item["id"],
            book_id=book_id,
            object_name=object_name,
            filename=item["file_name"],
            file_size=item.get("file_size", 0),
        )
        queued_items.append({"item_id": item["id"], "job_id": item["id"], "book_id": book_id})

    if not queued_items:
        await db.update_job_book_batch_status(batch_id, "FAILED", error="No uploaded file could be queued")
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="No uploaded file could be queued")

    return JSONResponse(
        status_code=HTTPStatus.ACCEPTED,
        content={
            "batch_id": batch_id,
            "status": "QUEUED_PROCESS",
            "queued_items": queued_items,
            "failed_items": failed_items,
            "message": "Uploaded files finalized and queued"
        }
    )


@router.post("/insert/str/bg")
async def upload_string_bg(
    request: Request,
    stringName: str = Form(None),
    stringBody: str = Form(None),
    db: DBHandling = Depends(get_db),
    current_admin: dict = Depends(get_current_admin_user)
):
    """Handle upload JP text directly. Admin only. Upload to storage then
    queue the string processing as a background task and return a job ID."""
    if not stringName or not stringBody:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Missing book name or content"
        )
    string_size_bytes = len(stringBody.encode("utf-8"))
    if string_size_bytes > MAX_INSERT_STRING_BYTES:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"String content too long, max {MAX_INSERT_STRING_BYTES} bytes"
        )

    idem_key = request.headers.get("Idempotency-Key", "")
    if not idem_key:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Missing Idempotency-Key header")

    book_id, created = await db.insert_book_init(current_admin["id"], stringName, idem_key)
    if book_id <= 0:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize book '{stringName}'"
        )
    if not created:
        return JSONResponse(
            status_code=HTTPStatus.OK,
            content={"book_id": book_id, "message": "Duplicate request ignored"}
        )

    object_name = ""
    error_detail = ""
    try:
        object_name = f"{uuid.uuid4().hex}_{stringName}"
        object_name = upload_string_to_minio(stringBody, object_name)
        if not object_name:
            error_detail = f"Failed to upload file {stringName} to external storage."
            raise RuntimeError(error_detail)

        if not await db.update_insert_book_status_uploaded(book_id, object_name):
            error_detail = "Failed to finalize uploaded file metadata"
            raise RuntimeError(error_detail)

        batch_id, _ = await db.create_job_book_batch(current_admin["id"], idem_key)
        if not batch_id:
            error_detail = "Failed to initialize insert batch"
            raise RuntimeError(error_detail)

        item_job_id = await db.create_job_book_batch_item(
            batch_id=batch_id,
            user_id=current_admin["id"],
            file_name=stringName,
            file_size=len(stringBody.encode("utf-8")),
            object_name=object_name,
            action="INSERT_STR",
            status="QUEUED_PROCESS",
            book_id=book_id,
        )
        if not item_job_id:
            error_detail = "Failed to create batch item"
            raise RuntimeError(error_detail)

        await process_insert_str_job.kiq(batch_item_id=item_job_id, book_id=book_id, data=stringBody)
    except Exception as e:
        await compensate_insert_saga(db, book_id, object_name)
        if not error_detail:
            error_detail = "Failed to enqueue background task"
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=error_detail
        ) from e

    return JSONResponse(
        status_code=HTTPStatus.ACCEPTED,
        content={
            "job_id": item_job_id,
            "batch_id": batch_id,
            "book_id": book_id,
            "status": "QUEUED",
            "message": "Background insert queued"
        }
    )


@router.get("/api/job")
async def get_job_list(
    db: DBHandling = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    job_list = await db.get_job_book_list(current_user_id)
    return JSONResponse(
        status_code=HTTPStatus.OK,
        content={"job_list": job_list}
    )


@router.get("/api/job/{job_id}")
async def get_specific_job(
    job_id: str,
    db: DBHandling = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """Get status/details for a background job book."""
    job = await db.get_job_book(job_id)
    if not job:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Job not found")
    if job["user_id"] != current_user_id:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Not allowed to view this job")

    return JSONResponse(
        status_code=HTTPStatus.OK,
        content=job
    )

# =================================================================================


# ===== VIEW COLLECTION ===========================================================
@router.get("/view/word")
async def view_words(
    jlpt_level: str = "",
    star: bool | str = None,
    limit: int = DEFAULT_LIMIT,
    page: int = 1,
    db: DBHandling = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """
    View X words per page, with/without filters

    Param:
    - jlpt_level: filter by the JLPT level (N0 - not categorized, N5->N1)
    - star: starred words only
    - limit: the amount of words to show
    - page: the number of page to show
    """
    jlpt_level = validate_jlpt_level(jlpt_level)
    star_bool = parse_bool_param(star)

    result, page_count = await handle_view_words(db, current_user_id, jlpt_level, star_bool, limit, page)
    return JSONResponse(
        content=jsonable_encoder(
            {
                "word_list": result,
                "page_count": page_count,
                "page": page,
                "args": {"jlpt_level": jlpt_level, "star": star},
            }
        )
    )


@router.get("/api/view/search-word", dependencies=[Depends(rate_limiter(60, 60))])
async def api_search_word(
    word: str,
    limit: int = DEFAULT_LIMIT,
    db: DBHandling = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    current_user_id: int = Depends(get_current_user_id)
):
    """Search for a word, returns JSON results"""
    normalized_word = word.strip()
    cache_key = f"search_word:{normalized_word.lower()}"
    value = await redis_get_json(redis, cache_key)
    if value is not None:
        return JSONResponse(content=value)

    response_data = await handle_search_word(db, word, limit, bpv1_url_prefix)
    if "error" in response_data:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=response_data["error"])
    
    expire_secs = SEARCH_WORD_EXPIRE_MINUTES*60
    await redis_set_json(redis, cache_key, response_data, expire_secs)
    return JSONResponse(content=response_data)


@router.get("/view/word/{word_id}")
async def view_specific_word(
    word_id: int,
    sen_limit: int = DEFAULT_SENTENCE_EXAMPLE_LIMIT,
    db: DBHandling = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    current_user_id: int = Depends(get_current_user_id)
):
    """View details info of 1 word"""
    result, sentence_examples = await handle_view_specific_word(
        db, current_user_id, word_id, sen_limit, redis,
    )
    return JSONResponse(
        content=jsonable_encoder(
            {"word_details": result, "sen_ex": sentence_examples}
        )
    )


@router.post("/toggle-star")
async def toggle_star(
    request: Request,
    db: DBHandling = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """Toggle star status for word or book"""
    data = await request.json()
    try:
        obj_id = int(data.get("id", "a"))
    except:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Missing word id")
    
    obj_type = data.get("objType", None)
    if obj_type not in ["word", "book"]:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Missing star object type, must be either `word` or `book`"
        )
    
    star = validate_star(data.get("star", None))
    if star == -1:
        return {"success": False}
    
    updated_star = await toggle_star_helper(db, current_user_id, obj_id, obj_type, star)
    return {"success": updated_star}


@router.get("/audio/{filename}")
def serve_audio(filename: str):
    """Serve audio files. This approach is called as 'StaticA'."""
    audio_dir = os.path.join(os.path.dirname(__file__), "..", AUDIO_DIR)
    cache_headers = {
        # Audio fragments are effectively immutable; long-lived browser cache is safe.
        "Cache-Control": "public, max-age=31536000, immutable",
    }
    return FileResponse(
        os.path.join(audio_dir, filename),
        media_type='audio/wav',
        headers=cache_headers,
    )


@router.post("/tts")
async def text_to_speech(
    body: dict = Body(...),
    use_model: bool | str = True,
    db: DBHandling = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Generate WAV bytes from payload {'text': '...', 'lang': 'jp'|'en'}.
    Synchronous get/generate-upload audio. For async, use /tts/bg.
    Query param `use_model` defaults to True, when is true, will apply
    voice options from body:
    - 'speed': [0.5, 2.0]
    - 'pitch' or 'half_tone': [-24, 24]

    The endpoint exposes one contract while routing to language-specific engines.
    """
    text, lang = validate_tts_request(body)
    voice_options = parse_tts_voice_options(body, lang)
    use_model_bool = parse_bool_param(use_model)

    # Use StaticA
    if not use_model_bool:
        fallback = await tts_service.build_statica_fallback(text, lang, "TTS model disabled by request", db)
        if fallback:
            return JSONResponse(status_code=HTTPStatus.OK, content=fallback)
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "source": "statica",
                "reason": "StaticA fallback is only available for Japanese text",
                "lang": lang,
            },
        )

    try:
        result = await tts_service.synthesize(text, lang, redis, voice_options=voice_options)
    except TTSAdapterError as exc:
        fallback = await tts_service.build_statica_fallback(text, lang, str(exc), db)
        if fallback:
            return JSONResponse(status_code=HTTPStatus.OK, content=fallback)
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            detail={"source": "tts", "reason": str(exc), "lang": lang},
        ) from exc

    return Response(
        content=result.wav_bytes,
        media_type='audio/wav',
        headers={
            "Cache-Control": "private, max-age=120",
            "X-TTS-Engine": result.engine,
            "X-TTS-Lang": lang,
            "X-TTS-Source": result.source,
            "X-TTS-Object": result.object_name,
        },
    )


@router.post("/tts/bg")
async def text_to_speech_bg(
    body: dict = Body(...),
    use_model: bool | str = True,
    db: DBHandling = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Queue text-to-speech generation as a background job.
    Query param `use_model` defaults to True, when is true, will apply
    voice options from body:
    - 'speed': [0.5, 2.0]
    - 'pitch' or 'half_tone': [-24, 24]

    If cache already has this exact request, returns audio immediately.
    """
    text, lang = validate_tts_request(body)
    voice_options = parse_tts_voice_options(body, lang)
    use_model_bool = parse_bool_param(use_model)

    # Use StaticA
    if not use_model_bool:
        fallback = await tts_service.build_statica_fallback(text, lang, "TTS model disabled by request", db)
        if fallback:
            return JSONResponse(status_code=HTTPStatus.OK, content=fallback)
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "source": "statica",
                "reason": "StaticA fallback is only available for Japanese text",
                "lang": lang,
            },
        )

    # Check Redis
    engine_name = tts_service.jp_adapter.engine_name if lang == "jp" else tts_service.en_adapter.engine_name
    cached = await tts_service.get_cached_for_request(
        text, lang, engine_name, redis, voice_options
    )
    if cached is not None:
        return Response(
            content=cached.wav_bytes,
            media_type='audio/wav',
            headers={
                "Cache-Control": "private, max-age=120",
                "X-TTS-Engine": cached.engine,
                "X-TTS-Lang": lang,
                "X-TTS-Source": cached.source,
                "X-TTS-Object": cached.object_name,
            },
        )

    # Create job - idempotent check
    job_id = await db.create_job_tts(text=text, lang=lang, voice_options=voice_options)
    if not job_id:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Failed to initialize tts background job",
        )

    try:
        await process_tts_job.kiq(job_id=job_id)
    except Exception as exc:
        await db.update_job_tts_failed(job_id, error=str(exc))
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Failed to enqueue tts background task",
        ) from exc

    return JSONResponse(
        status_code=HTTPStatus.ACCEPTED,
        content={
            "job_id": job_id,
            "status": "QUEUED",
            "poll_url": f"{bpv1_url_prefix}/tts/job/{job_id}",
            "message": "Background TTS generation queued",
        },
    )


@router.get("/tts/job/{job_id}")
async def get_tts_job_status(
    job_id: str,
    db: DBHandling = Depends(get_db),
):
    """Get status/details for one async TTS job."""
    job = await db.get_job_tts(job_id)
    if not job:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="TTS job not found")

    return JSONResponse(status_code=HTTPStatus.OK, content=job)


@router.get("/tts/job/{job_id}/audio")
async def get_tts_job_audio(
    job_id: str,
    db: DBHandling = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Return WAV audio for a finished async TTS job."""
    job = await db.get_job_tts(job_id)
    if not job:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="TTS job not found")
    if job.get("status") != "FINISHED":
        raise HTTPException(status_code=HTTPStatus.CONFLICT, detail="TTS job is not finished")

    text = job.get("text", "")
    lang = job.get("lang", "")
    voice_options = job.get("voice_options", {}) or {}
    engine_name = tts_service.jp_adapter.engine_name if lang == "jp" else tts_service.en_adapter.engine_name
    cached = await tts_service.get_cached_for_request(text, lang, engine_name, redis, voice_options)
    if cached is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="TTS audio bytes not found in cache/storage")

    return Response(
        content=cached.wav_bytes,
        media_type='audio/wav',
        headers={
            "Cache-Control": "private, max-age=120",
            "X-TTS-Engine": cached.engine,
            "X-TTS-Lang": lang,
            "X-TTS-Source": cached.source,
            "X-TTS-Object": cached.object_name,
            "X-TTS-Job": job_id,
        },
    )


@router.get("/api/view/book")
async def view_books(
    star: bool | str = None,
    limit: int = DEFAULT_LIMIT,
    page: int = 1,
    db: DBHandling = Depends(get_db),
    current_user: dict = Depends(get_current_user_id)
):
    """
    View X book names per page, with/without star

    Param:
    - star: starred books only 
    - limit: the amount of books to show
    - page: the number of page to show
    """
    star_bool = parse_bool_param(star)
    result, page_count = await handle_view_books(db, current_user, star_bool, limit, page)
    return JSONResponse(
        status_code=HTTPStatus.OK,
        content=jsonable_encoder(
            {"book_list": result, "page_count": page_count, "page": page, "args": {"star": star}}
        )
    )


@router.get("/view/book/{book_id}")
async def view_specific_book(
    book_id: int,
    db: DBHandling = Depends(get_db),
    current_user: dict = Depends(get_current_user_id)
):
    """View content of 1 book"""
    return JSONResponse(
        content=jsonable_encoder(
            {"book_details": await handle_view_specific_book(db, current_user, book_id)}
        )
    )


@router.post("/del/book/bg/{book_id}")
async def delete_book_bg(
    request: Request,
    book_id: int,
    db: DBHandling = Depends(get_db),
    current_admin_user: dict = Depends(get_current_admin_user)
):
    """Queue book deletion in background and return a job ID."""
    book = await db.get_exact_book(user_id=current_admin_user["id"], book_id=book_id)
    if not book:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Book not found")

    # Because delete is auto idempotent, it's not necessary to send idem key
    idem_key = request.headers.get("Idempotency-Key", "").strip()
    if not idem_key:
        idem_key = f"delete-book:{current_admin_user['id']}:{book_id}:{uuid.uuid4().hex}"

    batch_id, _ = await db.create_job_book_batch(current_admin_user["id"], idem_key)
    if not batch_id:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Failed to initialize delete batch"
        )

    item_id = await db.create_job_book_batch_item(
        batch_id=batch_id,
        user_id=current_admin_user["id"],
        file_name=f"delete-book:{book_id}",
        file_size=0,
        object_name=book.get("object_name", ""),
        action="DELETE_BOOK",
        status="QUEUED_PROCESS",
        book_id=book_id,
    )
    if not item_id:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Failed to create delete batch item"
        )

    try:
        await process_delete_job_book.kiq(
            job_id="",
            book_id=book_id,
            object_name=book.get("object_name", ""),
            batch_item_id=item_id,
        )
    except Exception as e:
        await db.update_job_book_batch_item_status(item_id, "FAILED_PROCESS", error=str(e))
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Failed to enqueue background task"
        )

    return JSONResponse(
        status_code=HTTPStatus.ACCEPTED,
        content={
            "job_id": item_id,
            "batch_id": batch_id,
            "book_id": book_id,
            "status": "QUEUED",
            "message": "Background delete queued"
        }
    )

# =================================================================================


# ===== PROGRESS % ================================================================
@router.get("/api/progress")
async def api_progress(
    db: DBHandling = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    results = await handle_progress(db, current_user_id)
    return JSONResponse(content=results)

# =================================================================================


# ===== QUIZ % ====================================================================
@router.get("/quiz")
async def quiz(
    jlpt_level: str = "",
    star: bool | str = None,
    select_book: str = "",
    use_priority: str = "1",
    get_distractors_from_db: str = "1",
    db: DBHandling = Depends(get_db)
):
    """Quiz home page"""
    all_books = await get_all_book_name_and_id(db)
    return JSONResponse(
        content=jsonable_encoder(
            {
                "all_books": all_books,
                "args": {
                    "jlpt_level": jlpt_level,
                    "star": star,
                    "select_book": select_book,
                    "use_priority": use_priority,
                    "get_distractors_from_db": get_distractors_from_db,
                },
            }
        )
    )

# ----- Quiz JP ---------
@router.get("/quiz/jp")
async def quiz_jp(
    book_id: str = "",
    jlpt_level: str = "",
    star: bool | str = None,
    limit: int = DEFAULT_LIMIT,
    use_priority: bool | str = None,
    get_distractors_from_db: bool | str = None,
    db: DBHandling = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    pdata: ProcessData = Depends(get_pdata),
    current_user_id: int = Depends(get_current_user_id)
):
    """Get JP-to-EN quiz questions"""
    jlpt_level_validated = validate_jlpt_level(jlpt_level)
    star_bool = parse_bool_param(star)
    use_priority_bool = parse_bool_param(use_priority)
    get_distractors_bool = parse_bool_param(get_distractors_from_db)

    quizes = await build_quizes(
        "jp",
        pdata,
        db,
        user_id=current_user_id,
        limit=limit,
        jlpt_level=jlpt_level_validated,
        star=star_bool,
        book_id=book_id,
        use_priority=use_priority_bool,
        get_distractors_from_db=get_distractors_bool,
        redis=redis,
    )
    return JSONResponse(
        content=jsonable_encoder(
            {
                "quizes": quizes,
                "mode": "jp",
                "args": {
                    "jlpt_level": jlpt_level,
                    "star": star,
                    "use_priority": use_priority,
                    "get_distractors_from_db": get_distractors_from_db,
                },
            }
        )
    )

@router.get("/quiz/known")
async def quiz_known(
    book_id: str = "",
    jlpt_level: str = "",
    star: bool | str = None,
    limit: int = DEFAULT_LIMIT,
    get_distractors_from_db: bool | str = None,
    db: DBHandling = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    pdata: ProcessData = Depends(get_pdata),
    current_user_id: int = Depends(get_current_user_id)
):
    """Get 'already known' quiz questions"""
    jlpt_level_validated = validate_jlpt_level(jlpt_level)
    star_bool = parse_bool_param(star)
    get_distractors_bool = parse_bool_param(get_distractors_from_db)

    quizes = await build_quizes(
        "jp",
        pdata,
        db,
        user_id=current_user_id,
        limit=limit,
        jlpt_level=jlpt_level_validated,
        star=star_bool,
        book_id=book_id,
        use_priority=False,
        is_known=True,
        get_distractors_from_db=get_distractors_bool,
        redis=redis,
    )
    return JSONResponse(
        content=jsonable_encoder(
            {
                "quizes": quizes,
                "mode": "known",
                "args": {
                    "jlpt_level": jlpt_level,
                    "star": star,
                    "get_distractors_from_db": get_distractors_from_db,
                },
            }
        )
    )

# ----- Quiz EN ---------
@router.get("/quiz/en")
async def quiz_en(
    book_id: str = "",
    jlpt_level: str = "",
    star: bool | str = None,
    limit: int = DEFAULT_LIMIT,
    use_priority: bool | str = None,
    get_distractors_from_db: bool | str = None,
    db: DBHandling = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    pdata: ProcessData = Depends(get_pdata),
    current_user_id: int = Depends(get_current_user_id)
):
    """Get EN-to-JP quiz questions"""
    jlpt_level_validated = validate_jlpt_level(jlpt_level)
    star_bool = parse_bool_param(star)
    use_priority_bool = parse_bool_param(use_priority)
    get_distractors_bool = parse_bool_param(get_distractors_from_db)

    quizes = await build_quizes(
        "en",
        pdata,
        db,
        user_id=current_user_id,
        limit=limit,
        jlpt_level=jlpt_level_validated,
        star=star_bool,
        book_id=book_id,
        use_priority=use_priority_bool,
        get_distractors_from_db=get_distractors_bool,
        redis=redis,
    )
    return JSONResponse(
        content=jsonable_encoder(
            {
                "quizes": quizes,
                "mode": "en",
                "args": {
                    "jlpt_level": jlpt_level,
                    "star": star,
                    "use_priority": use_priority,
                    "get_distractors_from_db": get_distractors_from_db,
                },
            }
        )
    )


# ----- Quiz Sentence (JP) --------- TODO: NOT IMPLEMENTED YET
@router.get("/quiz/sentence")
def quiz_sentence(
    current_user_id: int = Depends(get_current_user_id)
):
    return {"message": "Not implemented yet"}


# ----- Quiz support --------
@router.post("/word/prio")
async def update_word_prio(
    request: Request,
    db: DBHandling = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """
    Update word priority based on quiz result.
    Expects JSON: { 'word_id': int, 'is_correct': bool, 'quized': int, 'occurrence': int }
    """
    data = await request.json()
    try:
        word_id = int(data.get("word_id", 0))
    except:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Invalid/Missing `word_id`")

    is_correct = parse_bool_param(data.get("is_correct", None))
    quized, occurrence = None, None
    try:
        quized = int(data.get("quized", None))
    except:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Invalid/Missing `quized`")
    try:
        occurrence = int(data.get("occurrence", None))
    except:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Invalid/Missing `occurrence`")

    success = await update_word_prio_after_answering(db, current_user_id, word_id, is_correct, quized, occurrence)
    return {"success": success}


@router.post("/word/prio/batch")
async def update_word_prio_batch(
    request: Request,
    db: DBHandling = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """Update quiz priority for a whole session in one request.

    Expects JSON:
      {
        "answers": [
          {"word_id": int, "is_correct": bool, "quized": int?, "occurrence": int?},
          ...
        ]
      }
    """
    data = await request.json()
    answers = data.get("answers", [])
    if not isinstance(answers, list) or not answers:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Invalid/Missing `answers`")

    normalized: list[dict] = []
    for item in answers:
        if not isinstance(item, dict):
            continue

        try:
            word_id = int(item.get("word_id", 0))
        except Exception:
            continue
        if not word_id:
            continue

        is_correct = parse_bool_param(item.get("is_correct", None))
        normalized_item = {"word_id": word_id, "is_correct": is_correct}
        if item.get("quized", None) is not None:
            try:
                normalized_item["quized"] = int(item.get("quized"))
            except Exception:
                pass
        if item.get("occurrence", None) is not None:
            try:
                normalized_item["occurrence"] = int(item.get("occurrence"))
            except Exception:
                pass
        normalized.append(normalized_item)

    stats = await update_word_prio_after_session(db, current_user_id, normalized)
    return {"success": stats["updated"] > 0 or stats["total"] == 0, **stats}


@router.post("/word/known")
async def toggle_word_known(
    request: Request,
    db: DBHandling = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """
    Update word priority to either -1 or recalculate based on quiz/occurrence.
    Expects JSON: { 'word_id': int, 'update_to_known': bool, 'quized': int, 'occurrence': int }
    """
    data = await request.json()
    try:
        word_id = int(data.get("word_id", 0))
    except:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Invalid/Missing `word_id`")

    update_to_known = parse_bool_param(data.get("update_to_known", None))
    occurrence, quized = None, None
    if not update_to_known:
        if data.get("occurrence", None) is not None:
            try:
                occurrence = int(data.get("occurrence"))
            except:
                raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Invalid `occurrence`")
        if data.get("quized", None) is not None:
            try:
                quized = int(data.get("quized"))
            except:
                raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Invalid `quized`")

    if update_to_known:
        success = await change_word_prio_to_negative(db, current_user_id, word_id)
    else:
        success = await reset_word_prio(db, current_user_id, word_id, occurrence, quized)
    return {"success": success}

# =================================================================================


# ===== SCRAPE ====================================================================
@router.post("/jlpt/scrape/bg/{source_id}")
async def scrape_jlpt_bg(
    request: Request,
    source_id: int,
    db: DBHandling = Depends(get_db),
    current_admin_user: dict = Depends(get_current_admin_user)
):
    """Scrape JLPT level from external websites, replace current jlpt_levels table values,
    update jlpt level for existing words. Then publish a message to Redis to read jlpt level
    mapping into memory."""
    idem_key = request.headers.get("Idempotency-Key", "")
    if not idem_key:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Missing Idempotency-Key header")

    source = ScrapeSources.from_source_id(source_id)
    if source is None:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Invalid source_id: {source_id}. Supported: 1={ScrapeSources.WIKIPEDIA.value}, 2={ScrapeSources.JLPT_SENSEI.value}",
        )

    # Idem check
    job_id, is_new = await db.create_job_scrape(
        user_id=current_admin_user["id"],
        idempotency_key=idem_key,
        trigger_type="MANUAL",
        source=source.value,
    )
    if not job_id:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Failed to initialize scrape job",
        )

    if is_new:
        try:
            await process_scrape_jlpt_job.kiq(job_id=job_id, source=source.value)
        except Exception as e:
            await db.update_job_scrape_status(job_id, "FAILED", error=str(e))
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail="Failed to enqueue scrape background task",
            )

    return JSONResponse(
        status_code=HTTPStatus.ACCEPTED,
        content={
            "job_id": job_id,
            "status": "QUEUED",
            "source": source.value,
            "message": "Background JLPT scrape queued" if is_new else "Duplicate request ignored",
        },
    )


@router.post("/jlpt/update-words/bg")
async def update_words_jlpt_bg(
    request: Request,
    db: DBHandling = Depends(get_db),
    current_admin_user: dict = Depends(get_current_admin_user)
):
    """Sync words.jlpt_level from jlpt_levels without scraping."""
    idem_key = request.headers.get("Idempotency-Key", "")
    if not idem_key:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Missing Idempotency-Key header")

    job_id, is_new = await db.create_job_scrape(
        user_id=current_admin_user["id"],
        idempotency_key=idem_key,
        trigger_type="MANUAL_UPDATE_WORDS",
        source="jlpt_levels",
    )
    if not job_id:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Failed to initialize update words job",
        )

    if is_new:
        try:
            await process_update_words_from_jlpt_job.kiq(job_id=job_id)
        except Exception as e:
            await db.update_job_scrape_status(job_id, "FAILED", error=str(e))
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail="Failed to enqueue update words background task",
            )

    return JSONResponse(
        status_code=HTTPStatus.ACCEPTED,
        content={
            "job_id": job_id,
            "status": "QUEUED",
            "source": "jlpt_levels",
            "message": "Background JLPT words sync queued" if is_new else "Duplicate request ignored",
        },
    )


@router.post("/jlpt/reload-cache")
async def reload_jlpt_cache(
    db: DBHandling = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    current_admin_user: dict = Depends(get_current_admin_user)
):
    """Reload in-memory JLPT cache from jlpt_levels table without restarting API."""
    await read_jlpt_from_db(db, redis)
    return JSONResponse(
        status_code=HTTPStatus.OK,
        content={
            "message": "JLPT cache reloaded",
            "count": await redis.hlen(JLPT_REDIS_KEY),
        },
    )


# =================================================================================