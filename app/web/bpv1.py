from fastapi import APIRouter, Request, File, UploadFile, Form, Depends, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Jinja2Templates
import tempfile
import os

from handlers.insert import handle_insert_file, handle_insert_str
from handlers.view import (handle_search_word, handle_view_specific_word, handle_view_words,
                           handle_view_books, handle_view_specific_book)
from handlers.helpers import (
    get_filename_from_path, is_api_request, toggle_star_helper, validate_jlpt_level,
    parse_bool_param, validate_star, delete_book_helper, get_all_book_name_and_id,
    get_db, get_pdata
)
from handlers.quiz import (get_word_jp_quizes, update_word_prio_after_answering,
                           change_word_prio_to_negative, reset_word_prio, get_word_en_quizes)
from schemas.constants import DEFAULT_LIMIT, DEFAULT_SENTENCE_EXAMPLE_LIMIT, AUDIO_DIR
from utils.db import DBHandling
from utils.process_data import ProcessData

# Create router
router = APIRouter()

# Setup templates
templates_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=templates_dir)

# ===== HOME ======================================================================
@router.get("/")
def home():
    return templates.TemplateResponse("home.html", {"request": {}})


# ===== INSERT ===================================================================
@router.get("/insert")
def insert():
    return templates.TemplateResponse("insert/insert.html", {"request": {}})


@router.post("/insert/file")
async def upload_file(
    request: Request,
    filename: str = None,
    submittedFilename: UploadFile = File(None),
    db: DBHandling = Depends(get_db),
    pdata: ProcessData = Depends(get_pdata)
):
    """
    Handle file upload.
    - Via API: filename query param with file content in request
    - Via UI: submittedFilename form field with file
    """
    tmp_path = filename or ""
    file_name = get_filename_from_path(tmp_path) if tmp_path else ""
    is_api_call = True

    # If no filename param -> handle from UI
    if not tmp_path:
        is_api_call = False
        if not submittedFilename:
            raise HTTPException(status_code=400, detail="No file uploaded")
        file_name = get_filename_from_path(submittedFilename.filename)
        
        # Save to temp file to open multiple times
        tmp = tempfile.NamedTemporaryFile(delete=False)
        tmp_path = tmp.name
        content = await submittedFilename.read()
        tmp.write(content)
        tmp.close()
    
    if is_api_call:
        return handle_insert_file(pdata, db, file_name, tmp_path, True)
    
    # For UI, stream the response
    async def generate():
        yield from handle_insert_file(pdata, db, file_name, tmp_path, False)
    
    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/insert/str")
async def upload_string(
    request: Request,
    stringName: str = Form(None),
    stringBody: str = Form(None),
    db: DBHandling = Depends(get_db),
    pdata: ProcessData = Depends(get_pdata)
):
    """
    Handle upload JP text directly.
    - Via API call: use request body {"name": ..., "data": ...}
    - Via UI: stored in "stringName" and "stringBody" in form
    """
    # Check if API call
    is_api_call = is_api_request(request)
    name = None
    data = None
    
    if is_api_call:
        body = await request.json()
        if body:
            name = body.get("name")
            data = body.get("data")
    else:
        # Handle UI form
        name = stringName
        data = stringBody
    
    if is_api_call:
        return handle_insert_str(pdata, db, name, data)
    
    # For UI, stream the response
    async def generate():
        yield from handle_insert_str(pdata, db, name, data)
    
    return StreamingResponse(generate(), media_type="text/event-stream")

# =================================================================================

# ===== VIEW COLLECTION ===========================================================
@router.get("/view")
def view():
    return templates.TemplateResponse("view/view.html", {"request": {}})


@router.get("/view/word")
def view_words(
    jlpt_level: str = "",
    star: bool = None,
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
    star = parse_bool_param(star)

    result, page_count = handle_view_words(db, jlpt_level, star, limit, page)
    return templates.TemplateResponse(
        "view/word/view_words.html",
        {"request": {}, "word_list": result, "page_count": page_count, "page": page}
    )


@router.get("/view/search-word")
async def search_word(
    request: Request,
    word: str = "",
    limit: int = DEFAULT_LIMIT,
    db: DBHandling = Depends(get_db)
):
    """Search for a word"""
    is_api_call = is_api_request(request)

    # If UI and not word, that means it's the first time enter this page
    # Just render it, when provided a word, it'll call this function again
    if not word:
        if is_api_call:
            raise HTTPException(status_code=400, detail="missing a JP or EN word")
        return templates.TemplateResponse("view/word/search_word.html", {"request": {}})

    if is_api_call:
        return handle_search_word(db, word, limit, "/v1", True)
    
    return handle_search_word(db, word, limit, "/v1", False)


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
        raise HTTPException(status_code=400, detail="Missing word id")
    
    obj_type = data.get("objType", None)
    if obj_type not in ["word", "book"]:
        raise HTTPException(
            status_code=400,
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
    star: bool = None,
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
    star = parse_bool_param(star)
    result, page_count = handle_view_books(db, star, limit, page)
    return templates.TemplateResponse(
        "view/book/view_books.html",
        {"request": {}, "book_list": result, "page_count": page_count, "page": page}
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
        raise HTTPException(status_code=400, detail="Missing book `id`")
    
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
def quiz(db: DBHandling = Depends(get_db)):
    """Quiz home page"""
    all_books = get_all_book_name_and_id(db)
    return templates.TemplateResponse(
        "quiz/quiz_home.html",
        {"request": {}, "all_books": all_books}
    )


# ----- Quiz JP ---------
@router.get("/quiz/jp")
def quiz_jp(
    book_id: str = "",
    jlpt_level: str = "",
    star: bool = None,
    limit: int = DEFAULT_LIMIT,
    use_priority: bool = None,
    get_distractors_from_db: bool = None,
    db: DBHandling = Depends(get_db),
    pdata: ProcessData = Depends(get_pdata)
):
    """Get JP-to-EN quiz questions"""
    jlpt_level = validate_jlpt_level(jlpt_level)
    star = parse_bool_param(star)
    use_priority = parse_bool_param(use_priority)
    get_distractors_from_db = parse_bool_param(get_distractors_from_db)

    quizes = get_word_jp_quizes(
        pdata,
        db,
        limit=limit,
        jlpt_level=jlpt_level,
        star=star,
        book_id=book_id,
        use_priority=use_priority,
        get_distractors_from_db=get_distractors_from_db
    )
    return templates.TemplateResponse(
        "quiz/quiz_run.html",
        {"request": {}, "quizes": quizes, "mode": "jp"}
    )


@router.get("/quiz/known")
def quiz_known(
    book_id: str = "",
    jlpt_level: str = "",
    star: bool = None,
    limit: int = DEFAULT_LIMIT,
    get_distractors_from_db: bool = None,
    db: DBHandling = Depends(get_db),
    pdata: ProcessData = Depends(get_pdata)
):
    """Get 'already known' quiz questions"""
    jlpt_level = validate_jlpt_level(jlpt_level)
    star = parse_bool_param(star)
    get_distractors_from_db = parse_bool_param(get_distractors_from_db)

    quizes = get_word_jp_quizes(
        pdata,
        db,
        limit=limit,
        jlpt_level=jlpt_level,
        star=star,
        book_id=book_id,
        use_priority=False,
        is_known=True,
        get_distractors_from_db=get_distractors_from_db
    )
    return templates.TemplateResponse(
        "quiz/quiz_run.html",
        {"request": {}, "quizes": quizes, "mode": "known"}
    )


# ----- Quiz EN ---------
@router.get("/quiz/en")
def quiz_en(
    book_id: str = "",
    jlpt_level: str = "",
    star: bool = None,
    limit: int = DEFAULT_LIMIT,
    use_priority: bool = None,
    get_distractors_from_db: bool = None,
    db: DBHandling = Depends(get_db)
):
    """Get EN-to-JP quiz questions"""
    jlpt_level = validate_jlpt_level(jlpt_level)
    star = parse_bool_param(star)
    use_priority = parse_bool_param(use_priority)
    get_distractors_from_db = parse_bool_param(get_distractors_from_db)

    quizes = get_word_en_quizes(
        db,
        limit=limit,
        jlpt_level=jlpt_level,
        star=star,
        book_id=book_id,
        use_priority=use_priority,
        get_distractors_from_db=get_distractors_from_db
    )
    return templates.TemplateResponse(
        "quiz/quiz_run.html",
        {"request": {}, "quizes": quizes, "mode": "en"}
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
        raise HTTPException(status_code=400, detail="Invalid/Missing `word_id`")
    
    is_correct = parse_bool_param(data.get("is_correct", None))
    try:
        quized = int(data.get("quized", 0))
    except:
        raise HTTPException(status_code=400, detail="Invalid/Missing `quized`")
    
    try:
        occurrence = int(data.get("occurrence", 0))
    except:
        raise HTTPException(status_code=400, detail="Invalid/Missing `occurrence`")
    
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
        raise HTTPException(status_code=400, detail="Invalid/Missing `word_id`")
    
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
