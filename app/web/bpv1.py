from fastapi import APIRouter, Request, File, UploadFile, Form, Depends, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.templating import Jinja2Templates
from http import HTTPStatus
import tempfile
import os
import redis.asyncio as aioredis

from handlers.config import (bpv1_url_prefix, FAILED_LOGIN_LIMIT, REFRESH_TOKEN_EXPIRE_DAYS,
                            FAILED_LOGIN_BLOCK_MINUTES, ACCESS_TOKEN_EXPIRE_MINUTES)
from handlers.insert import handle_insert_file_stream, handle_insert_str_stream
from handlers.view import (handle_search_word, handle_view_specific_word, handle_view_words,
                           handle_view_books, handle_view_specific_book)
from handlers.helpers import (
    get_filename_from_path, toggle_star_helper, validate_jlpt_level,
    parse_bool_param, validate_star, delete_book_helper, get_all_book_name_and_id,
    get_db, get_pdata, get_jinja_globals, get_redis, get_current_user_id, get_current_admin_user
)
from handlers.quiz import (get_word_jp_quizes, update_word_prio_after_answering,
                           change_word_prio_to_negative, reset_word_prio, get_word_en_quizes)
from schemas.constants import DEFAULT_LIMIT, DEFAULT_SENTENCE_EXAMPLE_LIMIT, AUDIO_DIR
from schemas.user import UserCreate, UserLogin, TokenResponse, UserResponse, TokenRefresh
from utils.db import DBHandling
from utils.process_data import ProcessData
from utils.auth import hash_password, create_access_token, create_refresh_token, verify_password, verify_token

# Create router
router = APIRouter()

# Setup templates (html files)
templates_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=templates_dir)
templates.env.globals.update(get_jinja_globals())

# ===== HOME ======================================================================
@router.get("/")
def home():
    return templates.TemplateResponse("home.html", {"request": {}})


# ===== AUTH ========================================================================
@router.get("/login")
def login_page():
    """Serve login page"""
    return templates.TemplateResponse("login.html", {"request": {}})

@router.get("/register")
def register_page():
    """Serve register page"""
    return templates.TemplateResponse("register.html", {"request": {}})


@router.post("/register")
async def register(
    user_data: UserCreate,
    db: DBHandling = Depends(get_db)
):
    """
    Register a new user.
    
    Body: {username, email, password}
    Returns: {id, username, email, is_admin}
    """
    if db.user_exists(user_data.username):
        raise HTTPException(status_code=409, detail="Username already taken")
    if db.user_exists_by_email(user_data.email):
        raise HTTPException(status_code=409, detail="Email already registered")
    
    hashed_password = hash_password(user_data.password)
    user_id = db.create_user(
        username=user_data.username,
        email=user_data.email,
        password_hash=hashed_password,
        is_admin=False
    )
    
    if not user_id:
        raise HTTPException(status_code=500, detail="Failed to create user")
    
    user = db.get_user_by_id(user_id)
    return user


@router.post("/login")
async def login(
    credentials: UserLogin,
    db: DBHandling = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis)
):
    """
    Login user and return JWT tokens.
    
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
    user = db.get_user_by_username(credentials.username)
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


@router.post("/refresh")
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


# ===== INSERT ===================================================================
@router.get("/insert")
def insert():
    """Serve insert page"""
    return templates.TemplateResponse("insert/insert.html", {"request": {}})


@router.post("/insert/file")
async def upload_file(
    request: Request,
    submittedFilename: UploadFile = File(None),
    db: DBHandling = Depends(get_db),
    pdata: ProcessData = Depends(get_pdata),
    current_admin: dict = Depends(get_current_admin_user)
):
    """
    Handle file upload. submittedFilename form field with file
    """
    if not submittedFilename:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="No file uploaded")
    file_name = get_filename_from_path(submittedFilename.filename)
    
    # Save to temp file to open multiple times
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp_path = tmp.name
    content = await submittedFilename.read()
    tmp.write(content)
    tmp.close()
    
    return StreamingResponse(
        handle_insert_file_stream(pdata, db, file_name, tmp_path),
        media_type="text/event-stream"
    )


@router.post("/insert/str")
async def upload_string(
    request: Request,
    stringName: str = Form(None),
    stringBody: str = Form(None),
    db: DBHandling = Depends(get_db),
    pdata: ProcessData = Depends(get_pdata),
    current_admin: dict = Depends(get_current_admin_user)
):
    """
    Handle upload JP text directly.
    Book name = "stringName" and book content = "stringBody" in form
    """
    return StreamingResponse(
        handle_insert_str_stream(pdata, db, stringName, stringBody),
        media_type="text/event-stream"
    )

# =================================================================================

# ===== VIEW COLLECTION ===========================================================
@router.get("/view")
def view():
    return templates.TemplateResponse("view/view.html", {"request": {}})


@router.get("/view/word")
def view_words(
    jlpt_level: str = "",
    star: bool | str = None,
    limit: int = DEFAULT_LIMIT,
    page: int = 1,
    db: DBHandling = Depends(get_db)
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

    result, page_count = handle_view_words(db, jlpt_level, star_bool, limit, page)
    return templates.TemplateResponse(
        "view/word/view_words.html",
        {"request": {}, "word_list": result, "page_count": page_count, "page": page,
         "args": {"jlpt_level": jlpt_level, "star": star}}
    )


@router.get("/view/search-word")
async def search_word(
    request: Request,
    word: str = "",
    limit: int = DEFAULT_LIMIT,
    db: DBHandling = Depends(get_db)
):
    """Search for a word"""
    # If UI and not word, that means it's the first time enter this page
    # Just render it, when provided a word, it'll call this function again
    if not word:
        return templates.TemplateResponse("view/word/search_word.html", {"request": {}})

    response_data = handle_search_word(db, word, limit, bpv1_url_prefix)

    # Check for error in response
    if "error" in response_data:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=response_data["error"])
    return response_data


@router.get("/view/word/{word_id}")
def view_specific_word(
    word_id: int,
    sen_limit: int = DEFAULT_SENTENCE_EXAMPLE_LIMIT,
    db: DBHandling = Depends(get_db)
):
    """View details info of 1 word"""
    result, sentence_examples = handle_view_specific_word(db, word_id, sen_limit)
    return templates.TemplateResponse(
        "view/word/view_specific_word.html",
        {"request": {}, "word_details": result, "sen_ex": sentence_examples}
    )


@router.post("/toggle-star")
async def toggle_star(
    request: Request,
    db: DBHandling = Depends(get_db)
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
    
    updated_star = toggle_star_helper(db, obj_id, obj_type, star)
    return {"success": updated_star}


@router.get("/audio/{filename}")
def serve_audio(filename: str):
    """Serve audio files"""
    # main.py is inside `app/web/` so we have to ../../
    audio_dir = os.path.join(os.path.dirname(__file__), "../../" + AUDIO_DIR)
    return FileResponse(os.path.join(audio_dir, filename), media_type='audio/wav')


@router.get("/view/book")
def view_books(
    star: bool | str = None,
    limit: int = DEFAULT_LIMIT,
    page: int = 1,
    db: DBHandling = Depends(get_db)
):
    """
    View X book names per page, with/without star

    Param:
    - star: starred books only 
    - limit: the amount of books to show
    - page: the number of page to show
    """
    star_bool = parse_bool_param(star)
    result, page_count = handle_view_books(db, star_bool, limit, page)
    return templates.TemplateResponse(
        "view/book/view_books.html",
        {"request": {}, "book_list": result, "page_count": page_count, "page": page,
         "args": {"star": star}}
    )


@router.get("/view/book/{book_id}")
def view_specific_book(
    book_id: int,
    db: DBHandling = Depends(get_db)
):
    """View content of 1 book"""
    return templates.TemplateResponse(
        "view/book/view_specific_book.html",
        {"request": {}, "book_details": handle_view_specific_book(db, book_id)}
    )


@router.post("/del/book")
async def delete_book(
    request: Request,
    db: DBHandling = Depends(get_db)
):
    """Delete a book"""
    data = await request.json()
    try:
        obj_id = int(data.get("id", "a"))
    except:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Missing book `id`")
    
    deleted = delete_book_helper(db, obj_id)
    return {"success": deleted}


# =================================================================================

# ===== PROGRESS % ================================================================
@router.get("/progress")
def progress():
    return {"message": "Progress function here"}

# =================================================================================



# ===== QUIZ % ====================================================================
@router.get("/quiz")
def quiz(
    jlpt_level: str = "",
    star: bool | str = None,
    select_book: str = "",
    use_priority: str = "1",
    get_distractors_from_db: str = "1",
    db: DBHandling = Depends(get_db)
):
    """Quiz home page"""
    all_books = get_all_book_name_and_id(db)
    return templates.TemplateResponse(
        "quiz/quiz_home.html",
        {"request": {}, "all_books": all_books,
         "args": {"jlpt_level": jlpt_level, "star": star, "select_book": select_book,
                  "use_priority": use_priority, "get_distractors_from_db": get_distractors_from_db}}
    )


# ----- Quiz JP ---------
@router.get("/quiz/jp")
def quiz_jp(
    book_id: str = "",
    jlpt_level: str = "",
    star: bool | str = None,
    limit: int = DEFAULT_LIMIT,
    use_priority: bool | str = None,
    get_distractors_from_db: bool | str = None,
    db: DBHandling = Depends(get_db),
    pdata: ProcessData = Depends(get_pdata)
):
    """Get JP-to-EN quiz questions"""
    jlpt_level_validated = validate_jlpt_level(jlpt_level)
    star_bool = parse_bool_param(star)
    use_priority_bool = parse_bool_param(use_priority)
    get_distractors_bool = parse_bool_param(get_distractors_from_db)

    quizes = get_word_jp_quizes(
        pdata,
        db,
        limit=limit,
        jlpt_level=jlpt_level_validated,
        star=star_bool,
        book_id=book_id,
        use_priority=use_priority_bool,
        get_distractors_from_db=get_distractors_bool
    )
    return templates.TemplateResponse(
        "quiz/quiz_run.html",
        {"request": {}, "quizes": quizes, "mode": "jp",
         "args": {"jlpt_level": jlpt_level, "star": star, "use_priority": use_priority,
                  "get_distractors_from_db": get_distractors_from_db}}
    )


@router.get("/quiz/known")
def quiz_known(
    book_id: str = "",
    jlpt_level: str = "",
    star: bool | str = None,
    limit: int = DEFAULT_LIMIT,
    get_distractors_from_db: bool | str = None,
    db: DBHandling = Depends(get_db),
    pdata: ProcessData = Depends(get_pdata)
):
    """Get 'already known' quiz questions"""
    jlpt_level_validated = validate_jlpt_level(jlpt_level)
    star_bool = parse_bool_param(star)
    get_distractors_bool = parse_bool_param(get_distractors_from_db)

    quizes = get_word_jp_quizes(
        pdata,
        db,
        limit=limit,
        jlpt_level=jlpt_level_validated,
        star=star_bool,
        book_id=book_id,
        use_priority=False,
        is_known=True,
        get_distractors_from_db=get_distractors_bool
    )
    return templates.TemplateResponse(
        "quiz/quiz_run.html",
        {"request": {}, "quizes": quizes, "mode": "known",
         "args": {"jlpt_level": jlpt_level, "star": star,
                  "get_distractors_from_db": get_distractors_from_db}}
    )


# ----- Quiz EN ---------
@router.get("/quiz/en")
def quiz_en(
    book_id: str = "",
    jlpt_level: str = "",
    star: bool | str = None,
    limit: int = DEFAULT_LIMIT,
    use_priority: bool | str = None,
    get_distractors_from_db: bool | str = None,
    db: DBHandling = Depends(get_db)
):
    """Get EN-to-JP quiz questions"""
    jlpt_level_validated = validate_jlpt_level(jlpt_level)
    star_bool = parse_bool_param(star)
    use_priority_bool = parse_bool_param(use_priority)
    get_distractors_bool = parse_bool_param(get_distractors_from_db)

    quizes = get_word_en_quizes(
        db,
        limit=limit,
        jlpt_level=jlpt_level_validated,
        star=star_bool,
        book_id=book_id,
        use_priority=use_priority_bool,
        get_distractors_from_db=get_distractors_bool
    )
    return templates.TemplateResponse(
        "quiz/quiz_run.html",
        {"request": {}, "quizes": quizes, "mode": "en",
         "args": {"jlpt_level": jlpt_level, "star": star, "use_priority": use_priority,
                  "get_distractors_from_db": get_distractors_from_db}}
    )


# ----- Quiz Sentence (JP) --------- TODO: NOT IMPLEMENTED YET
@router.get("/quiz/sentence")
def quiz_sentence():
    return {"message": "Not implemented yet"}


# ----- Quiz support --------
@router.post("/word/prio")
async def update_word_prio(
    request: Request,
    db: DBHandling = Depends(get_db)
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
    try:
        quized = int(data.get("quized", 0))
    except:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Invalid/Missing `quized`")
    
    try:
        occurrence = int(data.get("occurrence", 0))
    except:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Invalid/Missing `occurrence`")
    
    success = update_word_prio_after_answering(db, word_id, is_correct, quized, occurrence)
    return {"success": success}


@router.post("/word/known")
async def toggle_word_known(
    request: Request,
    db: DBHandling = Depends(get_db)
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
    
    update_to_known = parse_bool_param(data.get("update_to_known", False))
    occurrence, quized = 0, 0
    if not update_to_known:
        try:
            occurrence = int(data.get("occurrence", 0))
            quized = int(data.get("quized", 0))
        except:
            pass
    
    if update_to_known:
        success = change_word_prio_to_negative(db, word_id)
    else:
        success = reset_word_prio(db, word_id, occurrence, quized)
    return {"success": success}

# =================================================================================
