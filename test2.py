from utils.data import scrape_all_jlpt
from utils.process_data import ProcessData
import os
import argparse

from fugashi import Tagger
from fugashi.fugashi import UnidicNode
from itertools import combinations
from jamdict import Jamdict
from jamdict.util import LookupResult
from jamdict.jmdict import JMDEntry

parser = argparse.ArgumentParser(description="")

parser.add_argument("--input_string", "-is", nargs="+", metavar=("CONTENT", "NAME"), help="A JP string, will ask for a nam, its words and sentences to database")

args = parser.parse_args()

if args.input_string is not None and len(args.input_string) > 0:
    print("ZZZZZZZZZZZZZZZ")


fugashi_tagger = Tagger()
jam = Jamdict()

def test_jmdict_select(n: int = 1):
    out = []
    with jam.jmdict.ctx() as ctx:  # low-level DB access
        rows = ctx.select("SELECT idseq FROM Entry ORDER BY RANDOM() LIMIT ?", (n,))
        for row in rows:
            e = jam.jmdict.get_entry(idseq=row["idseq"], ctx=ctx)
            print("----------------")
            print(e)
            print("text", e.text(True))
            print(e.kana_forms)
            print(e.kanji_forms)
            out.append(e)
            if len(out) >= n:
                break
    return out

def get_jmdict_table_names():
    with jam.jmdict.ctx() as ctx:  # low-level DB access
        rows = ctx.select("SELECT name FROM sqlite_master WHERE type='table'")
        return [row["name"] for row in rows ] 

def get_reading_table():
    with jam.jmdict.ctx() as ctx:
        # reading_info = ctx.select("PRAGMA table_info(Entry)")
        reading_info = ctx.select("SELECT * FROM SenseGloss LIMIT 10 OFFSET 0;")
        for col in reading_info:
            print("- - - - - - -")
            for k in col.keys():
                print(k, "\t", col[k])


a = get_reading_table()
print(a)


# See the Entry table structure
# print("\n=== Entry TABLE ===")
# entry_info = ctx.select("PRAGMA table_info(Entry)")
# for col in entry_info:
#     print(col)

# # See the Reading table structure  
# print("\n=== Reading TABLE ===")
# 