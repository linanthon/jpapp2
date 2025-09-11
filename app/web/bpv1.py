from flask import (Blueprint, request, render_template_string, render_template,
                   Response, stream_with_context, send_from_directory, jsonify)
import tempfile, os

from handlers.insert import handle_insert_file, handle_insert_str
from handlers.view import handle_search_word, handle_view_word
from handlers.helpers import get_filename_from_path, is_api_request

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

@bp.route("/view/word/<string:word>")
def view_word(word: str):
    """
    Param:
    - sen: the number of sentence example
    """
    try:
        limit = int(request.args.get("sen", ""))
    except:
        limit = DEFAULT_SENTENCE_EXAMPLE_LIMIT
    result, sentence_examples = handle_view_word(word, limit)
    return render_template("view/word/view_word.html", word_details=result, sen_ex=sentence_examples)

@bp.route("/toggle_star", methods=["POST"])
def toggle_star():
    data = request.get_json()
    word = data.get("word")

    if not word:
        return jsonify({"success": False, "error": "Missing word"}), 400

    # Example: flip star state in DB
    new_state = db.toggle_star(word)   # <-- implement this
    return jsonify({"success": True, "starred": new_state})

@bp.route("/audio/<path:filename>")
def serve_audio(filename):
    # main.py is inside `app/web/` so we have ../../
    audio_dir = os.path.join(os.path.dirname(__file__), "../../"+AUDIO_DIR)
    return send_from_directory(audio_dir, filename)

# =================================================================================

# ===== PROGRESS % ================================================================
@bp.route("/progress")
def progress():
    return "Progress function here"

# =================================================================================



# ===== QUIZ % ====================================================================
@bp.route("/quiz", methods=["GET"])
def quiz():
    return render_template("quiz/quiz_home.html")

# ----- Quiz JP ---------
@bp.route("/quiz/jp", methods=["GET"])
def quiz_jp():
    return render_template("quiz/quiz_jp.html")

@bp.route("/quiz/check", methods=["POST"])
def quiz_check():
    user_answer = request.form.get("answer", "")
    if user_answer == "本":  # "hon"
        return render_template("quiz/quiz_result.html")
    else:
        return render_template_string("""
            <p>❌ Wrong, the correct answer is 本.</p>
            <a href="{{ url_for('main_ep.quiz') }}">Try again</a>
        """)

# ----- Quiz EN ---------
@bp.route("/quiz/en", methods=["GET"])
def quiz_en():
    return render_template("quiz/quiz_en.html")

# ----- Quiz Sentence (JP) ---------
@bp.route("/quiz/sentence", methods=["GET"])
def quiz_sentence():
    return render_template("quiz/quiz_sentence.html")
# =================================================================================
