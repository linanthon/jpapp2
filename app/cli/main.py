import argparse

# Set path to allow import from files
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from utils.data import read_stop_words, scrape_all_jlpt, read_jlpt, str_2_int
from utils.db import DBHandling
from app.cli.handler import (handle_insert_file, handle_insert_str, handle_view_word_cli, handle_search_word_cli,
                             handle_search_sentence_cli, handle_search_book_cli, handle_view_book_cli,
                             handle_view_jlptlevel_cli, handle_update_jlpt, handle_quiz_jp_cli, handle_quiz_en_cli,
                             handle_words_known, handle_quiz_sentence_cli, handle_star_word, handle_star_sentence,
                             handle_progress_word)
from app.cli.test import call_test
from utils.process_data import ProcessData

DB_USER = "postgres"
DB_PASS = "2"

def main():
    # Connect DB, create database & tables
    db = DBHandling()
    db.connect_2_db(username=DB_USER, password=DB_PASS)
    db.migrate()

    # Load stuff
    read_stop_words()
    read_jlpt()
    parser = argparse.ArgumentParser(description="")
    pdata = ProcessData()
    
    # Options:
    # 1. Insert
    parser.add_argument("--input_file", "-if", help="A filename, read its content and add itself, its words and sentences to database")
    parser.add_argument("--input_string", "-is", nargs=2, metavar=("CONTENT", "NAME"), help="A JP string, will ask for a nam, its words and sentences to database")
    # 2. Update
    parser.add_argument("--update_jlpt", "-uj", nargs="+", help="A word (exact match) and its new JLPT level")
    parser.add_argument("--words_known", "-wk", nargs="+", help="A list of word (exact match) separated by ' '. Words markded as known will never show up in quiz.")
    parser.add_argument("--star_word", "-stw", nargs="+", help="A list of word (exact match) separated by ' '. Stars words.")
    parser.add_argument("--star_sentence", "-sts", nargs="+", help="A list of sentence (exact match) separated by ' '. Stars sentences, this really is just extra function.")
    # 3. View collection
    parser.add_argument("--view_word", "-vw", help="View an exact word in Japanese")
    parser.add_argument("--search_word", "-sw", nargs="+", help="Search a word in Japanese. Can not be empty string. Can provide an addition integer value for the amount of records to get (default 10).")
    parser.add_argument("--view_level", "-vl", nargs="+", help="Name of a level, i.e.: 'N5'. List all words of this level. There are words that are not categorized into a level, use 'N0' for them. Can provide an addition integer value for the amount of records to get (default 10)")
    parser.add_argument("--search_sentence", "-ss", nargs="+", help="Search a JP sentence containing this string. If want to search all, use empty string (''). Can provide an addition integer value for the amount of records to get (default 10).")
    parser.add_argument("--view_book", "-vb", help="View content of a book with exact name")
    parser.add_argument("--search_book", "-sb", nargs="+", help="Name of an inserted file. If want to search all, use empty string (''). Can provide an addition integer value for the amount of records to get (default 10).")
    # 4. Scrape JLPT level
    parser.add_argument("--scrape", "-sc", help="Scrape JLPT level, options: 0: wikipedia (default), ...", action="store_true")
    # 5. Quiz
    parser.add_argument("--quiz_jp", "-qj", help="The number of words to quiz, see JP, guess EN.")
    parser.add_argument("--quiz_en", "-qe", help="The number of words to quiz, see EN, guess JP.")
    parser.add_argument("--quiz_sen", "-qs", nargs="+", help="The number of JP sentences to quiz (fill in blank) and boolean to use your DB (true) or Jamdict's DB (false) to get incorrect choices, i.e.: '5 false'.")
    # 6. Progress
    parser.add_argument("--progress_word", "-pw", nargs="?", const="default", help="Can input 'jlpt_level' to show coverage group by jlpt_level.")

    # ... more
    parser.add_argument("--test", "-t")
    
    args = parser.parse_args()
    # 1. Insert ======================
    if args.input_file is not None and len(args.input_file) > 0:
        handle_insert_file(pdata, db, args.input_file)
    elif args.input_string is not None and len(args.input_string) > 0:
        content = args.input_string[0]
        bookname = args.input_string[1] if len(args.input_string) > 1 else ""
        handle_insert_str(pdata, db, content, bookname)

    # 2. Update ======================
    elif args.update_jlpt is not None and len(args.update_jlpt) > 0:
        word = args.update_jlpt[0]
        new_jlpt_level = args.update_jlpt[1] if len(args.update_jlpt) > 1 else "a"
        handle_update_jlpt(db, word, new_jlpt_level)
    elif args.words_known is not None and len(args.words_known) > 0:
        handle_words_known(db, args.words_known)
    elif args.star_word is not None and len(args.star_word) > 0:
        handle_star_word(db, args.star_word)
    elif args.star_sentence is not None and len(args.star_sentence) > 0:
        handle_star_sentence(db, args.star_sentence)

    # 3. View collection ======================
    elif args.view_word is not None and len(args.view_word) > 0:
        handle_view_word_cli(db, args.view_word)
    elif args.search_word is not None and len(args.search_word) > 0:
        word = args.search_word[0]
        limit = str_2_int(args.search_word[1] if len(args.search_word) > 1 else "a")
        handle_search_word_cli(db, word, limit)
    elif args.view_level is not None and len(args.view_level) > 0:
        level = args.view_level[0].upper()
        limit = str_2_int(args.view_level[1] if len(args.view_level) > 1 else "a")
        handle_view_jlptlevel_cli(db, level, limit)

    elif args.search_sentence is not None and len(args.search_sentence) > 0:
        sentence = args.search_sentence[0]
        limit = str_2_int(args.search_sentence[1] if len(args.search_sentence) > 1 else "a")
        handle_search_sentence_cli(db, sentence, limit)

    elif args.view_book is not None and len(args.view_book) > 0:
        handle_view_book_cli(db, args.view_book)
    elif args.search_book is not None and len(args.search_book) > 0:
        name = args.search_book[0]
        limit = str_2_int(args.search_book[1] if len(args.search_book) > 1 else "a")
        handle_search_book_cli(db, name, limit)

    # 4. Scrape
    elif args.scrape:
        if type(args.scrape) == bool:
            option = 0
        else:
            try:
                option = int(args.scrape)
            except:
                option = -1
        scrape_all_jlpt(option)
        # Re-read after scraping
        read_jlpt("data/jlpt/")

    # 5. Quiz
    elif args.quiz_jp is not None and len(args.quiz_jp) > 0:
        handle_quiz_jp_cli(pdata, db, args.quiz_jp)
    elif args.quiz_en is not None and len(args.quiz_en) > 0:
        handle_quiz_en_cli(pdata, db, args.quiz_en)
    elif args.quiz_sen is not None and len(args.quiz_sen) > 0:
        try:
            get_distract_by_db = bool(args.quiz_sen[1])
        except:
            get_distract_by_db = False
        handle_quiz_sentence_cli(pdata, db, args.quiz_sen[0], get_distract_by_db)

    # 6. Progress
    elif args.progress_word:
        grb_jlpt = False
        if args.progress_word is not None and args.progress_word == "jlpt_level":
            grb_jlpt = True
        handle_progress_word(db, grb_jlpt)

    # Test
    elif args.test is not None and len(args.test) > 0:
        call_test(db)

if __name__ == "__main__":
    main()