from utils.data import scrape_all_jlpt
from utils.process_data import ProcessData
import os
import argparse

parser = argparse.ArgumentParser(description="")

parser.add_argument("--input_string", "-is", nargs="+", metavar=("CONTENT", "NAME"), help="A JP string, will ask for a nam, its words and sentences to database")

args = parser.parse_args()

if args.input_string is not None and len(args.input_string) > 0:
    print("ZZZZZZZZZZZZZZZ")

