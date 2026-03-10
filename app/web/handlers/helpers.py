from fastapi import FastAPI, Depends, Request
from contextlib import asynccontextmanager
from typing import Tuple

from utils.db import DBHandling
from utils.process_data import ProcessData
from utils.data import read_stop_words, read_jlpt, scrape_all_jlpt

# cache word count for /view/word
view_count_cache = {}

# Load config
from dotenv import load_dotenv
load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup ----------------------------
    # Connect DB, migrate tables
    app.state.db = DBHandling()
    app.state.db.connect_2_db(
        username=DB_USER,
        password=DB_PASS
    )
    app.state.db.migrate()

    # Load fugashi tagger and jamdict
    app.state.pdata = ProcessData()
    
    yield
    
    # Shutdown ---------------------------
    if hasattr(app.state, "db"):
        app.state.db.close_db()

def create_app():
    """
    Create FastAPI app with lifespan, connect with DB, load dictionaries.
    Read stop words, JLPT levels / Scrape if no JLPT levels yet.
    """
    app = FastAPI(lifespan=lifespan)
    read_stop_words()
    scrape_all_jlpt()
    read_jlpt()
    return app

# ===== FastAPI Dependency Injection =====
def get_db(request: Request) -> DBHandling:
    """Get DB connection from app state"""
    return request.app.state.db

def get_pdata(request: Request) -> ProcessData:
    """Get ProcessData instance from app state"""
    return request.app.state.pdata

def get_filename_from_path(fullpath: str):
    """Get filename from full path, i.e.: c:/a/path/the_file.123.txt -> the_file.123"""
    if not fullpath:
        return ""
    
    temp = fullpath.strip()
    if "/" in fullpath:
        temp = temp.split("/")[-1]
    elif "\\" in fullpath:
        temp = temp.split("\\")[-1]
    temp = temp.split(".")

    return ".".join(temp[:-1])

def do_insert_book(db: DBHandling, name: str, data: str = "") -> Tuple[int, dict | None]:
    """Call DB to insert book.
    
    Input:
    - db
    - name: the name to be inserted, should have no path, no extension
    - data (optional): the file's content, will read file if this is empty

    Output:
    - int: the inserted book_id if success. Otherwise,
        + 0: name already used
        + -1: if DB failed
        + -2: if file not found
    - dict: error response dict, or None if success
    """
    if not name or not data:
        return -1, {"error": "No content"}
    
    book_id = db.insert_book(name, data)
    error_resp = None
    if book_id == 0:
        error_resp = {"error": "Name already used"}
    elif book_id == -1:
        error_resp = {"error": "Failed to insert"}
    elif book_id == -2:
        error_resp = {"error": "File not found"}
    
    return book_id, error_resp

def str_2_byte(input_str: str):
    return input_str.encode("utf-8")

def is_api_request(request: Request) -> bool:
    """Check if request is from API (JSON content-type)"""
    return request.headers.get("content-type", "").startswith("application/json")

def toggle_star_helper(db: DBHandling, obj_id: int, obj_type: str, star: int) -> bool:
    """Turn star on or off. Return true if success, false otherwise."""
    star_stt = True if star == 1 else False
    if obj_type == "word":
        return db.update_word_star(word_id=obj_id, new_star_status=star_stt)
    elif obj_type == "book":
        return db.update_book_star(book_id=obj_id, new_star_status=star_stt)
    else:
        return False

def validate_jlpt_level(jlpt_level: str) -> str:
    """Return upper cased jlpt_level if appropriate. Otherwise, return empty string"""
    jlpt_level = jlpt_level.upper()
    if jlpt_level in ["N0", "N5", "N4", "N3", "N2", "N1"]:
        return jlpt_level
    return ""

def validate_star(star_param) -> int:
    """
    Parse the star param obtained from frontend into integer:
        * 1: to star
        * 0: remove star
        * -1: invalid
    """
    if isinstance(star_param, bool):
        star = 1 if star_param else 0
    elif isinstance(star_param, (int, float)):
        star = 1 if int(star_param) != 0 else 0
    elif isinstance(star_param, str):
        s = star_param.strip().lower()
        if s in ["1", "true", "t", "yes", "y", "on"]:
            star = 1
        elif s in ["0", "false", "f", "no", "n", "off"]:
            star = 0
        else:
            star = -1
    else:
        star = -1
    return star

def parse_bool_param(val) -> bool:
    """Return True for common truthy query/JSON values, else False."""
    if isinstance(val, bool):
        return val
    if val is None:
        return False
    s = str(val).strip().lower()
    return s in ("1", "true", "t", "yes", "y", "on")

def reset_view_word_count():
    """call this when insert new book/word"""
    view_count_cache.clear()

def delete_book_helper(db: DBHandling, book_id: int) -> bool:
    with db.transaction():
        return db.delete_book(book_id=book_id)
    return False

def get_all_book_name_and_id(db: DBHandling):
    """call db.list_books with no star, 0 offset, query all"""
    return db.list_books(star=None, limit=None, offset=0)
