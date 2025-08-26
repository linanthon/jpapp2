from flask import (Blueprint, request, render_template_string,
                   render_template, Response, stream_with_context)
import tempfile, os

from handlers.insert import handle_insert_file, handle_insert_str
from handlers.helpers import get_filename_from_path

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
    if request.is_json:
        body = request.json
        if body:
            name = body.get("name")
            data = body.get("data")
    # Handle UI: stored in html form
    else:
        name = request.form.get("stringName")
        data = request.form.get("stringBody")
        
    return handle_insert_str(name, data)

# =================================================================================

# ===== VIEW COLLECTION ===========================================================
@bp.route("/view")
def view():
    return "View collection here"

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
