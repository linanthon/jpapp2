import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from utils.db import DBHandling

def call_test(db: DBHandling):
    res = db.get_quiz(7, [], "", False, True, 3, ["wisteria", "person", "season"])

    for instance in res:
        print("Word:", instance.en, ". Meaning:", instance.jp)

