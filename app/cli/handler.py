from fugashi.fugashi import UnidicNode
import os
from typing import Tuple, List, TYPE_CHECKING
import random

from common import do_insert_word_sentence_book_2_db
from utils.data import play_audio, is_japanese_word, is_english_word, is_word_or_number, get_quiz_distractors
from utils.logger import get_logger

from schemas.constants import (DEFAULT_LIMIT, QUIZ_WORD_SORT_COLUMNS, SORT_ORDER, JLPT_LEVELS,
                               MAX_WORD_DROP_IN_SENTENCE, MIN_SENTENCE_PERCENTAGE_REMAINS, DEFAULT_DISTRACTOR_COUNT)
from schemas.word import Word


if TYPE_CHECKING:
    from utils.db import DBHandling
    from utils.process_data import ProcessData

log = get_logger(__file__)

# === INSERT ===================================================================
def handle_insert_file(pdata: "ProcessData", db: "DBHandling", filename: str) -> None:
    """
    Handle input-ing a file, check file exist, insert as book (the book name is the file name),
    sentences, words to DB and link word-book, word-sentence, sentence-book IDs.

    Input:
    - filename: the full filename including path, the excluded-path-string at the end will be used as book name
    - pdata: a ProcessData object
    - db: a DBHandling object that is connected to the database
    """
    if not os.path.exists(filename):
        log.error(f"File '{filename}' not found")
        return
    
    book_id = do_insert_book(db, filename)
    if not book_id:
        return
    
    for sentence in pdata.stream_sentences_file(filename):
        do_insert_word_sentence_book_2_db(pdata, db, sentence, book_id)
        
def handle_insert_str(pdata: "ProcessData", db: "DBHandling", data: str, bookname: str = "") -> None:
    """
    Handle input-ing a string, check file exist, insert as book, sentences, words to DB
    and link word-book, word-sentence, sentence-book IDs.

    Input:
    - filename: the full filename including path, the excluded-path-string at the end will be used as book name
    - bookname: the document's name. Will ask for input if input is empty or None.
    - pdata: a ProcessData object
    - db: a DBHandling object that is connected to the database.
    """
    if not bookname:
        bookname = input("Enter this document name: ")
    book_id = do_insert_book(db, bookname, data)

    if not book_id:
        return
    for sentence in pdata.stream_sentences_str(data):
        do_insert_word_sentence_book_2_db(pdata, db, sentence, book_id)

def do_insert_book(db: "DBHandling", bookname: str, content: str = "") -> int:
    """Call DB to insert book.
    
    Input:
    - db
    - bookname: the file name, will use the last part as the book's name in DB
    - content (optional): the file's content, will read file if this is empty

    Output:
    - int: the inserted book_id. 0 if already existed. -1 if DB failed. -2 if file not found.
    """
    if not content:
        with open(bookname, "r", encoding="utf-8") as f:
            content = f.read()
    return db.insert_book(bookname, content)
# ==============================================================================


# === UPDATE ===================================================================
def handle_update_jlpt(db: "DBHandling", word: str, new_jlpt_level: str) -> None:
    """
    Update an existing Japanese word's JLPT level in DB
    """
    new_jlpt_level = new_jlpt_level.upper()
    if new_jlpt_level not in ["N0", "N5", "N4", "N3", "N2", "N1"]:
        print("Invalid JLPT level, must be one of: N0, N5, N4, N3, N2, N1")
        return

    if not is_japanese_word(word):
        print("Invalid word, must be Japanese")
        return

    if db.update_word_jlpt(word, new_jlpt_level):
        print("Updated")
    else:
        print("Word not found")

def handle_words_known(db: "DBHandling", words: str | List[str]) -> None:
    """
    Put a word's `quized` higher than the max value that is considered as known.
    This word will never show up in quiz anymore.
    """
    if type(words) == str:
        words = words.split(" ")
    if db.update_words_known(words):
        print("Success")
    else:
        print("Failed")

def handle_star_word(db: "DBHandling", words: str | List[str]) -> None:
    """Turn on/off word star"""
    if type(words) == str:
        words = words.split(" ")
    
    for word in words:
        if db.update_word_star(word):
            print(f"Updated {word}'s star")

def handle_star_sentence(db: "DBHandling", sentences: str | List[str]) -> None:
    """Turn on/off sentence star"""
    if type(sentences) == str:
        sentences = sentences.split(" ")
    
    for sen in sentences:
        if db.update_sentence_star(sen):
            print(f"Updated {sen}'s star")
# ==============================================================================


# === SEARCH == CLI ============================================================
def handle_view_word_cli(db: "DBHandling", word: str) -> None:
    """
    Query exact match for `word` and print its info with 5 sentences that includes it. Can play audio.
    """
    if not is_japanese_word(word):
        log.error("Must be Japanese word")
        return

    found_word = db.get_exact_word(word)
    if found_word:
        example_sentences = db.get_sentences_containing_word_by_id(found_word.word_id, 5)
        meanings = found_word.senses.split(";")
        log.info(f"1. {found_word.word} ({found_word.spelling}): {meanings[0]}. JLPT: {found_word.jlpt_level}")
        if found_word.forms:
            print(f"\tAll forms: {found_word.forms}")
        print(f"\tOccured: {found_word.occurrence}")
        print(f"\tQuized time: {found_word.quized}")
        if len(meanings) > 1:
            print(f"\tOther meanings: {meanings[1:]}")
        print(f"\tStar: {found_word.star}")
        print(f"\tExample sentences: {example_sentences}")

        while True:
            is_play = input("Play audio (y/n): ")
            if is_play.lower() == "y":
                play_audio(found_word.audio_mapping)
            else:
                break
    else:
        log.info(f"Word '{word}' not found")

def handle_search_word_cli(db: "DBHandling", word: str, limit: int = DEFAULT_LIMIT) -> None:
    """
    Search a word in either EN or JP, can not play sound.

    Input:
    - db: the DBHandling object for DB query
    - word: the word to query
    - limit: the number of word to query. If <= 0, use default value 10.
    """
    res: List[Word] = []
    if is_japanese_word(word):
        res = db.query_like_word(word, limit)
    elif is_english_word(word):
        res = db.query_word_sense(word, limit)
    else:
        log.error(f"Only input Japanese or English word, encounter unknown word: {word}")
        return
    
    if not res:
        print("Not found")
        return

    for i, a_word in enumerate(res):
        print(f"{i+1}. {a_word.word} ({a_word.spelling}): {a_word.senses.split(';')[0]}. JLPT: {a_word.jlpt_level}. Star {a_word.star}")
    
def handle_view_jlptlevel_cli(db: "DBHandling", level: str, limit: int = DEFAULT_LIMIT) -> None:
    """
    Get words of a JLPT level ('N5'), use 'N0' for non-categorized ones

    Input:
    - db: the DBHandling object for DB query
    - level: the JLPT level
    - limit: the number of word to query. If <= 0, use default value 10.
    """
    for i, word in enumerate(db.get_words_by_jlptlevel(level, limit)):
        print(f"{i+1}. {word}")


def handle_search_sentence_cli(db: "DBHandling", sentence: str, limit: int = DEFAULT_LIMIT) -> None:
    """
    Search a sentence in JP, get the sentences that most similar
    
    Input:
    - db: the DBHandling object
    - sentence: the sentence to query
    - limit: the number of sentence to query. If <= 0, use default value 10.
    """
    res = db.query_like_sentence(sentence, limit)
    if not res:
        print("Not found")
        return
    for i, a_sen in enumerate(res):
        print(f"{i+1}. {a_sen.sen} (Occured: {a_sen.occurrence}. Star: {a_sen.star})")


def handle_search_book_cli(db: "DBHandling", name: str, limit: int = DEFAULT_LIMIT) -> None:
    """
    Search a book by name, return those that most similar
    
    Input:
    - db: the DBHandling object
    - name: the book's name
    - limit: the number of sentence to query. If <= 0, use default value 10.
    """
    res = db.query_like_book(name, limit)
    if not res:
        print("Not found")
        return
    for i, a_book in enumerate(res):
        print(f"{i+1}. {a_book.name}")

def handle_view_book_cli(db: "DBHandling", name: str) -> None:
    """
    Query exact match for a book's `name` and print its content.
    """
    print(db.get_exact_book(name).content)
# ==============================================================================


# === QUIZ =====================================================================
def handle_quiz_jp_cli(pdata: "ProcessData", db: "DBHandling", count: str | int,
                       get_distractors_from_db: bool = True) -> None:
    """
    This quiz shows JP, ask EN
    Query DB to get word and meanings to quiz user. Will ask for sorts, filters and use priority value.
    Will only get words with `quized` <= QUIZ_HARD_CAP.
    Correct choice will increase `quized` column and recalculate `priority`.
    Wrong choice will decrease `quized` (if > 0) and recalculate `priority`.

    Input:
    - pdata and db
    - count: the number of quiz to do
    - get_distractors_from_db: If true, the incorrect choices will be those of our DB. Otherwise,
    they will be taken from Jamdict's DB.
    """
    # Check quiz count is valid
    if not do_valid_quiz_count(count):
        return

    # Ask for sort, filter, use priority value
    sorts = input("Sort (i.e.: 'col1:asc,col2:desc'): ").strip()
    filters = input("Filter (i.e.: 'jlpt_level:N3,star'): ").strip()
    prio = input("Use priority value (default True, can not use with sort) (y/n): ").strip()

    sort_list, jlpt_filter, star_only, use_prio = do_validate_sort_filter_prio_cli(sorts, filters, prio)

    tests = db.get_quiz(count, sort_list, jlpt_filter, star_only, use_priority=use_prio)
    for i, test_case in enumerate(tests):
        # randomize correct answer location
        choices = [test_case.en]
        choices.extend(get_quiz_distractors(pdata, db, test_case.jp, test_case.en, get_distractors_from_db).en)
        random.shuffle(choices)
        random_choices = "'" + "', '".join(choices) + "'"

        ans = input(f"{i+1}. '{test_case.jp}' meaning is? ({random_choices}): ")
        # Update quized and priority if correct
        if ans == test_case.en:
            print("Correct!")
            db.update_quized_prio_ts(test_case.jp, test_case.occurrence, test_case.quized+1)
        else:
            print(f"Wrong! The correct meaning should be: {test_case.en}")
            if test_case.quized > 0:
                decr_prio = test_case.quized-1
                db.update_quized_prio_ts(test_case.jp, test_case.occurrence, decr_prio)

def handle_quiz_en_cli(pdata: "ProcessData", db: "DBHandling", count: str | int,
                       get_distractors_from_db: bool = True) -> None:
    """
    This quiz shows JP, ask for EN.
    Query DB to get word and meanings to quiz user. Will ask for sorts, filters and use priority value.
    Correct choice will increase `quized` column and recalculate `priority`.
    Wrong choice will decrease `quized` (if > 0) and recalculate `priority`.

    Input:
    - pdata and db
    - count: the number of quiz to do
    - get_distractors_from_db: If true, the incorrect choices will be those of our DB. Otherwise,
    they will be taken from Jamdict's DB.
    """
    # Check quiz count is valid
    if not do_valid_quiz_count(count):
        return

    # Ask for sort, filter, use priority value
    sorts = input("Sort (i.e.: 'col1:asc,col2:desc'): ").strip()
    filters = input("Filter (i.e.: 'jlpt_level:N3,star'): ").strip()
    prio = input("Use priority value (default True, can not use with sort) (y/n): ").strip()

    sort_list, jlpt_filter, star_only, use_prio = do_validate_sort_filter_prio_cli(sorts, filters, prio)
    tests = db.get_quiz(count, sort_list, jlpt_filter, star_only, use_priority=use_prio)
    for i, test_case in enumerate(tests):
        # get distractors, mix and randomize the answers' positions
        choices = [test_case.jp]
        choices.extend(get_quiz_distractors(pdata, db, test_case.jp, test_case.en, get_distractors_from_db).jp)
        random.shuffle(choices)
        random_choices = "'" + "', '".join(choices) + "'"

        ans = input(f"{i+1}. '{test_case.en}' in Japanese is? ({random_choices}): ")
        # Update quized and priority if correct
        if ans == test_case.jp:
            print("Correct!")
            db.update_quized_prio_ts(test_case.jp, test_case.occurrence, test_case.quized+1)
        else:
            print(f"Wrong! The correct JP should be: {test_case.jp}")
            if test_case.quized > 0:
                decr_prio = test_case.quized-1
                db.update_quized_prio_ts(test_case.jp, test_case.occurrence, decr_prio)

def handle_quiz_sentence_cli(pdata: "ProcessData", db: "DBHandling", count: str | int,
                             get_distractors_from_db: bool = True) -> None:
    """
    This quiz shows JP sentences with random blanks from 1-3 words, fill in JP words.
    Each blank will give 4 choices.

    Input:
    - pdata: ProcessData object
    - db: DBHandling object connected to the database
    - count: the number of sentences to quiz
    - get_distractors_from_db: If true, randomly get incorrect choices using records in DB (default).
    If false, randomly get incorrect choices using Jamdict.
    """
    # Check quiz count is valid -> get `count` sentences
    if not do_valid_quiz_count(count):
        return
    records = db.query_random_sentences(count)

    for i, row in enumerate(records):
        # Tag sentence to words (might include number, symbols and all kind of languages)
        tagged_sen: List[str | UnidicNode] = pdata.tag_sentence(row.sen)

        # If only has 1 word, ignore this row -> get a new record different from existing records
        if len(tagged_sen) == 1:
            db.query_random_sentences(1, [r.sen for r in records])
            continue

        # Save JP words and get word counts
        jp_words = {}
        word_num_count = 0
        for i, word in enumerate(tagged_sen):
            if is_japanese_word(word.surface):
                jp_words[i] = word.surface
            
            if is_word_or_number:
                word_num_count += 1
        
        # Get the min words to drop in sentence to quiz
        # Randomly drop from 1 to MAX_WORD_DROP_IN_SENTENCE words, but
        # it can not exceed the JP word count in the sentence.
        # At the same time, the drop count can not exceed % of the sentence.
        can_drop = min(
            random.randint(1, MAX_WORD_DROP_IN_SENTENCE),
            len(jp_words)
        )
        while (can_drop / word_num_count) > MIN_SENTENCE_PERCENTAGE_REMAINS:
            can_drop -= 1
        # Can happen if sentence has 1 number/other-language-word and 1 JP word
        if can_drop == 0:
            records.append(db.query_random_sentences(1))
            continue

        correct_choices = []
        incorrect_choices = []
        chosen_idx = set()
        while can_drop > 0:
            # Can not choose adjacent words
            # Get available choices for choosing each time. If no more choices, break
            # (this means the actual drop might < can_drop)
            available = [i for i in jp_words.keys() if i not in chosen_idx]
            if not available:
                break

            # Choose random words to drop, save correct, get distractors
            choose_idx = random.choice(available)
            correct_choices.append(jp_words[choose_idx])
            incorrect_choices.append(
                get_quiz_distractors(pdata, db, jp_words[choose_idx], "", get_distractors_from_db).jp
            )

            # add chosen index and its adjacents, rm correct from sentence, choice pool
            chosen_idx.update([choose_idx-1, choose_idx, choose_idx+1])
            tagged_sen[choose_idx] = ""     # can not create UnidicNode, just do string
            del jp_words[choose_idx]
            can_drop -= 1
        correct_choices_len = len(correct_choices)

        # rebuild sentence with blanks
        quiz_sen = "".join(["____" if type(w) == str else w.surface for w in tagged_sen])

        # randomize the choices
        multiple_choice = ""
        for i in range(correct_choices_len):
            choices = [correct_choices[i]]
            choices.extend(incorrect_choices[i])
            random.shuffle(choices)
            multiple_choice = multiple_choice + f"{i+1}. '" + "', '".join(choices) + "'\n"

        # Ask
        ans = input(f"\nFill in blank(s), if multiple blanks, separate answers by ',':\n{quiz_sen}\n{multiple_choice}Ans: ").strip()
        split_ans = ans.split(",")
        is_right = True


        if len(split_ans) < correct_choices_len:
            is_right = False
            print(f"Missing answer(s)!\nThe correct answer(s): {correct_choices}")
        elif len(split_ans) > correct_choices_len:
            is_right = False
            print(f"Too many answer(s)!\nThe correct answer(s): {correct_choices}")
        else:
            for i in range(correct_choices_len):
                if split_ans[i] != correct_choices[i]:
                    is_right = False
                    print(f"Incorrect choice {i+1}, the correct one is: {correct_choices[i]}")
        if is_right:
            print("Correct!")
    

def do_valid_quiz_count(count: str | int) -> bool:
    """Check if quiz count is correct"""
    if type(count) is str:
        try:
            count = int(count)
        except:
            print("Quiz count must be integer")
            return False
    if count < 1:
        print("Quiz count must be > 0")
        return False
    return True

def do_validate_sort_filter_prio_cli(sorts: str, filters: str, prio: str = "y") -> Tuple[List[Tuple[str]], str, bool, bool]:
    """
    Check validity and reformat sort, filter, use_prio input params. Return tuple (example):
    - sort: [ ('col1', 'asc'), ('col2', 'desc') ]
    - jlpt_filter: 'N3'
    - star_only: False
    - prio: True
    """
    sort_list = []
    jlpt_filter = ""
    star_only = False
    use_prio = False

    if sorts:
        split_sort = sorts.lower().split(",")
        for instance in split_sort:
            if ":" in instance:
                temp = instance.split(":")
                if len(temp) == 2:
                    if temp[0] in QUIZ_WORD_SORT_COLUMNS and temp[1] in SORT_ORDER:
                        sort_list.append(tuple(temp))
                    else:
                        log.error(f"Invalid sort argument, either the column is not allowed or the order is incorrect (only accept {SORT_ORDER}): {instance}. This sort will be ignored.")
                else:
                    log.error(f"Invalid sort argument, each element must be 'column_name:order': {instance}.")
            else:
                log.error(f"Invalid sort argument, missing colon: {instance}.")

    if filters:
        split_filter = filters.lower().split(",")
        for instance in split_filter:
            # jlpt_level filter has an argument to specify level
            if "jlpt_level" in instance:
                temp = instance.split(":")
                if len(temp) == 2:
                    if temp[0] == "jlpt_level" and temp[1] in JLPT_LEVELS:
                        jlpt_filter = temp[1].upper()
                    else:
                        log.error(f"Invalid filter argument: {instance}. Only `jlpt_level:<value>` is allowed if use ':'.")
                else:
                    log.error(f"Invalid filter argument: {instance}. Must have length of 2 if use ':'.")
            else:
                if instance == "star":
                    star_only = True
                else:
                    log.error(f"Invalid filter argument, this column is not allowed: {instance}.")

    if prio.lower() == "y" or not sort_list:
        use_prio = True

    return (sort_list, jlpt_filter, star_only, use_prio)
# ==============================================================================


# Progress - Summary ===========================================================
def handle_progress_word(db: "DBHandling", grb_jlpt: bool = False) -> None:
    q_res = db.get_all_words_quized(grb_jlpt)
    if grb_jlpt:
        for lv in ["N1", "N2", "N3", "N4", "N5", "N0"]:
            print(f"=== JLPT {lv} ===")
            do_print_progress(q_res[lv])
    else:
        do_print_progress(q_res["ALL"])

def do_print_progress(cate: list):
    total = sum(cate)
    over_hard_cap = (cate[2] / total) * 100
    over_soft_cap = (cate[1] / total) * 100
    remaining = 100 - over_hard_cap - over_soft_cap
    print(f"Fluent: {over_hard_cap:.2f}")
    print(f"Known: {over_soft_cap:.2f}")
    print(f"Remaining: {remaining:.2f}")
# ==============================================================================

