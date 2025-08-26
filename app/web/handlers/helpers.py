from flask import Flask, g, current_app, Response

from typing import Tuple

from utils.db import DBHandling
from utils.process_data import ProcessData
from utils.data import read_stop_words, read_jlpt


def create_app():
    """
    Init app, connect db, migrate db, get fugashi tagger,
    jamdict, load stop words, load jlpt level mapping.
    Attach blueprint to app and return.
    """
    app = Flask(__name__)
    app.config.from_pyfile("config.py")

    # Get blueprint
    from app.web.bpv1 import bp
    app.register_blueprint(bp)

    # Connect DB and load stuff
    with app.app_context():
        get_dbhandling()
        get_processdata()
    read_stop_words()
    read_jlpt()

    return app

def get_dbhandling() -> DBHandling:
    """Connect DB, create database & tables. Must run in app.context"""
    if "db" not in g:
        g.db = DBHandling()
        g.db.connect_2_db(
            username=current_app.config.get("DB_USER", ""),
            password=current_app.config.get("DB_PASS", "")
        )
        g.db.migrate()
    return g.db

def get_processdata() -> ProcessData:
    """Load fugashi tagger and jamdict. Must run in app.context"""
    if "pdata" not in g:
        g.pdata = ProcessData()
    return g.pdata

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

def do_insert_book(db: "DBHandling", name: str, data: str = "") -> Tuple[int, Response | None]:
    """Call DB to insert book.
    
    Input:
    - db
    - name: the name to be inserted, should have no path, no extension
    - data (optional): the file's content, will read file if this is empty

    Output:
    - int: the inserted book_id if success. Otherwise,
        + 0: Response name already used
        + -1: if DB failed
        + -2 if file not found
    """
    if not name or not data:
        return Response("Error: No content", 400)
    
    book_id = db.insert_book(name, data)
    resp = None
    if book_id == 0:
        resp = Response("Error: (File)Name already used", 400)
    elif book_id == -1:
        resp = Response("Error: Failed to insert", 500)
    if book_id == -2:
        resp = Response("Error: File not found", 404)
    
    return book_id, resp

def str_2_byte(input_str: str):
    return input_str.encode("utf-8")

