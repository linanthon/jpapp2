from flask import (Blueprint, request, render_template_string, render_template,
                   Response, stream_with_context, send_from_directory, jsonify)
import tempfile, os

from handlers.insert import handle_insert_file, handle_insert_str
from handlers.view import (handle_search_word, handle_view_specific_word, handle_view_words,
                           handle_view_books, handle_view_specific_book)
from handlers.helpers import (get_filename_from_path, is_api_request, toggle_star_helper, validate_jlpt_level,
                              parse_bool_param, validate_star, delete_book_helper, get_all_book_name_and_id)
from handlers.quiz import (get_word_jp_quizes, update_word_prio_after_answering,
                           change_word_prio_to_negative, reset_word_prio, get_word_en_quizes)

from schemas.constants import DEFAULT_LIMIT, DEFAULT_SENTENCE_EXAMPLE_LIMIT, AUDIO_DIR

# Need specify template folder because this is not main.py
bp = Blueprint(
    "main_ep", __name__, url_prefix="/v1",
    template_folder="templates", static_folder="static"
)

@bp.route("/")
def home():
    return render_template("home.html")

# ===== INSERT ===================================================================
@bp.route("/insert", methods=["GET"])
def insert():
    return render_template("insert/insert.html")

@bp.route("/insert/file", methods=["POST"])
def upload_file():
    # get "filename" arg in URL after "?" for possible API call
    tmp_path = request.args.get("filename", "")
    filename = get_filename_from_path(tmp_path) if tmp_path else ""
    is_api_call = True

    # If no URL argument -> handle for UI
    if not tmp_path:
        is_api_call = False
        theFile = request.files.get("submittedFilename")
        if not theFile:
            return "No file uploaded", 400
        filename = get_filename_from_path(theFile.filename)
        
        # save to temp file to open multiple times
        tmp = tempfile.NamedTemporaryFile(delete=False)
        tmp_path = tmp.name
        theFile.save(tmp_path)
        tmp.close()
    
    if is_api_call:
        return handle_insert_file(filename, tmp_path, True)
    return Response(
        stream_with_context(handle_insert_file(filename, tmp_path, False)),
        mimetype="text/event-stream"
    )

@bp.route("/insert/str", methods=["POST"])
def upload_string():
    """
    Handle upload JP text directly.
    - Via API call: use request body {"name": ..., "data": ...}
    - Via UI: stored in "stringName" and "stringBody" in html form
    """
    # Handle API call: 
    is_api_call = False
    if request.is_json:
        body = request.json
        if body:
            name = body.get("name")
            data = body.get("data")
            is_api_call = True
    # Handle UI: stored in html form
    else:
        name = request.form.get("stringName")
        data = request.form.get("stringBody")
    
    if is_api_call:
        return handle_insert_str(name, data)
    return Response(stream_with_context(handle_insert_str(name, data)),
        mimetype="text/event-stream"
    )

# =================================================================================

# ===== VIEW COLLECTION ===========================================================
@bp.route("/view")
def view():
    return render_template("view/view.html")

@bp.route("/view/word")
def view_words():
    """
    View X words per page, with/without filters

    Param:
    - jlpt_level: filter by the JLPT level (N0 - not categorized, N5->N1)
    - star: starred words only
    - limit: the amount of words to show
    - page: the number of page to show
    """
    jlpt_level = validate_jlpt_level(request.args.get("jlpt_level", ""))
    star = parse_bool_param(request.args.get("star", None))
    try:
        limit = int(request.args.get("limit", str(DEFAULT_LIMIT)))
    except:
        limit = DEFAULT_LIMIT
    try:
        page = int(request.args.get("page", "1"))
    except:
        page = 1

    result, page_count = handle_view_words(jlpt_level, star, limit, page)
    return render_template("view/word/view_words.html", word_list=result, page_count=page_count, page=page)

@bp.route("/view/search-word")
def search_word():
    word = request.args.get("word", "")
    try:
        limit = int(request.args.get("limit"))
    except:
        limit = DEFAULT_LIMIT
    is_api_call = is_api_request()

    # If UI and not word, that means it's the first time enter this page
    # Just render it, when provided a word, it'll call this function again
    if not word:
        if is_api_call:
            return Response("Error: missing a JP or EN word", 400)
        return render_template("view/word/search_word.html")

    if is_api_call:
        return handle_search_word(word, limit, bp.url_prefix, True)
    # The `search_res` below will be catch in HTML
    return handle_search_word(word, limit, bp.url_prefix, False)

@bp.route("/view/word/<int:word_id>")
def view_specific_word(word_id: int):
    """
    View details info of 1 word

    Param:
    - sen: the number of sentence example
    """
    try:
        sen_limit = int(request.args.get("sen", ""))
    except:
        sen_limit = DEFAULT_SENTENCE_EXAMPLE_LIMIT
    result, sentence_examples = handle_view_specific_word(word_id, sen_limit)
    return render_template("view/word/view_specific_word.html", word_details=result, sen_ex=sentence_examples)

@bp.route("/toggle-star", methods=["POST"])
def toggle_star():
    data = request.get_json()
    try:
        obj_id = int(data.get("id", "a"))
    except:
        return jsonify({"success": False, "error": "Missing word id"}), 400
    
    obj_type = data.get("objType", None)
    if obj_type not in ["word", "book"]:
        return jsonify({"success": False, "error": "Missing star object type, must be either `word` or `book`"}), 400
    
    star = validate_star(data.get("star", None))
    if star == -1:
        return jsonify({"success": False})
    updated_star = toggle_star_helper(obj_id, obj_type, star)
    return jsonify({"success": updated_star})

@bp.route("/audio/<string:filename>")
def serve_audio(filename: str):
    # main.py is inside `app/web/` so we have ../../
    audio_dir = os.path.join(os.path.dirname(__file__), "../../"+AUDIO_DIR)
    return send_from_directory(audio_dir, filename, mimetype='audio/wav')

@bp.route("/view/book")
def view_books():
    """
    View X book names per page, with/without star

    Param:
    - star: starred words only
    - limit: the amount of words to show
    - page: the number of page to show
    """
    star = parse_bool_param(request.args.get("star", None))
    try:
        limit = int(request.args.get("limit", str(DEFAULT_LIMIT)))
    except:
        limit = DEFAULT_LIMIT
    try:
        page = int(request.args.get("page", "1"))
    except:
        page = 1

    result, page_count = handle_view_books(star, limit, page)
    return render_template("view/book/view_books.html", book_list=result, page_count=page_count, page=page)

@bp.route("/view/book/<int:book_id>")
def view_specific_book(book_id: int):
    """View content of 1 book"""
    return render_template("view/book/view_specific_book.html", book_details=handle_view_specific_book(book_id))

@bp.route("/del/book", methods=["POST"])
def delete_book():
    data = request.get_json()
    try:
        obj_id = int(data.get("id", "a"))
    except:
        return jsonify({"success": False, "error": "Missing book `id`"}), 400
    
    deleted = delete_book_helper(obj_id)
    return jsonify({"success": deleted})
        
        
# =================================================================================

# ===== PROGRESS % ================================================================
@bp.route("/progress")
def progress():
    return "Progress function here"

# =================================================================================



# ===== QUIZ % ====================================================================
@bp.route("/quiz", methods=["GET"])
def quiz():
    all_books = get_all_book_name_and_id()
    return render_template("quiz/quiz_home.html", all_books=all_books)

# ----- Quiz JP ---------
@bp.route("/quiz/jp", methods=["GET"])
def quiz_jp():
    book_id = request.args.get("book_id", "")
    jlpt_level = validate_jlpt_level(request.args.get("jlpt_level", ""))
    star = parse_bool_param(request.args.get("star", None))
    try:
        limit = int(request.args.get("limit", str(DEFAULT_LIMIT)))
    except:
        limit = DEFAULT_LIMIT
    use_priority = parse_bool_param(request.args.get("use_priority", None))
    get_distractors_from_db = parse_bool_param(request.args.get("get_distractors_from_db", None))

    quizes = get_word_jp_quizes(limit=limit, jlpt_level=jlpt_level, star=star, book_id=book_id,
                                use_priority=use_priority, 
                                get_distractors_from_db=get_distractors_from_db)
    return render_template("quiz/quiz_run.html", quizes=quizes, mode="jp")

@bp.route("/quiz/known", methods=["GET"])
def quiz_known():
    book_id = request.args.get("book_id", "")
    jlpt_level = validate_jlpt_level(request.args.get("jlpt_level", ""))
    star = parse_bool_param(request.args.get("star", None))
    try:
        limit = int(request.args.get("limit", str(DEFAULT_LIMIT)))
    except:
        limit = DEFAULT_LIMIT
    get_distractors_from_db = parse_bool_param(request.args.get("get_distractors_from_db", None))

    quizes = get_word_jp_quizes(limit=limit, jlpt_level=jlpt_level, star=star, book_id=book_id,
                                use_priority=False, is_known=True,
                                get_distractors_from_db=get_distractors_from_db)
    return render_template("quiz/quiz_run.html", quizes=quizes, mode="known")

# ----- Quiz EN ---------
@bp.route("/quiz/en", methods=["GET"])
def quiz_en():
    book_id = request.args.get("book_id", "")
    jlpt_level = validate_jlpt_level(request.args.get("jlpt_level", ""))
    star = parse_bool_param(request.args.get("star", None))
    try:
        limit = int(request.args.get("limit", str(DEFAULT_LIMIT)))
    except:
        limit = DEFAULT_LIMIT
    use_priority = parse_bool_param(request.args.get("use_priority", None))
    get_distractors_from_db = parse_bool_param(request.args.get("get_distractors_from_db", None))

    quizes = get_word_en_quizes(limit=limit, jlpt_level=jlpt_level, star=star, book_id=book_id,
                                use_priority=use_priority, 
                                get_distractors_from_db=get_distractors_from_db)
    return render_template("quiz/quiz_run.html", quizes=quizes, mode="en")

# ----- Quiz Sentence (JP) --------- TODO: NOT IMPLEMENTED YET
@bp.route("/quiz/sentence", methods=["GET"])
def quiz_sentence():
    return render_template("quiz/quiz_sentence.html")

# ----- Quiz support --------
@bp.route("/word/prio", methods=["POST"])
def update_word_prio():
    """
    Update word priority based on quiz result.
    Expects JSON: { 'word_id': int, 'is_correct': bool }
    """
    data = request.get_json()
    try:
        word_id = int(data.get("word_id", 0))
    except:
        return jsonify({"success": False, "error": "Invalid/Missing `word_id`"}), 400
    is_correct = parse_bool_param(data.get("is_correct", None))
    try:
        quized = int(data.get("quized", 0))
    except:
        return jsonify({"success": False, "error": "Invalid/Missing `quized`"}), 400
    try:
        occurrence = int(data.get("occurrence", 0))
    except:
        return jsonify({"success": False, "error": "Invalid/Missing `occurrence`"}), 400
    
    success = update_word_prio_after_answering(word_id, is_correct, quized, occurrence)
    return jsonify({"success": success})

@bp.route("/word/known", methods=["POST"])
def toggle_word_known():
    """
    Update word priority to either -1 or recalculate based on its current quized and occurrence.
    Expects JSON: { 'word_id': int, 'update_to_known': bool, 'quized': int (optional), 'occurrence': int (optional) }
    """
    data = request.get_json()
    try:
        word_id = int(data.get("word_id", 0))
    except:
        return jsonify({"success": False, "error": "Invalid/Missing `word_id`"}), 400
    update_to_known = parse_bool_param(data.get("update_to_known", False))
    if not update_to_known:
        try:
            occurrence = int(data.get("occurrence", 0))
            quized = int(data.get("quized", 0))
        except:
            pass
    
    if update_to_known:
        success = change_word_prio_to_negative(word_id)
    else:
        success = reset_word_prio(word_id, occurrence, quized)

    return jsonify({"success": success})
# =================================================================================
