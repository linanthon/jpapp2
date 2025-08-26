import re

from utils.db import DBHandling
from app.cli.main import DB_USER, DB_PASS

db = DBHandling()
db.connect_2_db(username=DB_USER, password=DB_PASS)


db.truncate_all_tables()