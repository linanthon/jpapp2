import math
import os
import re
import psycopg2
import psycopg2.extras
from psycopg2 import sql
from typing import List, Tuple, Dict

from utils.logger import get_logger
from schemas.book import Book
from schemas.constants import (TABLE_WORDS, TABLE_BOOKS, TABLE_SENTENCES, TABLE_WORD_BOOK_REF,
                              TABLE_WORD_SENTENCE_REF, TABLE_SENTENCE_BOOK_REF, DB_NAME,
                              SQL_TABLE_SCRIPT, DEFAULT_LIMIT, SQL_WORD_PRIO_SCRIPT,
                              DEFAULT_FORMULA_K, DEFAULT_TIME_EXPODECAY, QUIZ_WORD_SORT_COLUMNS,
                              WORD_SENSES_REGEX, QUIZ_SOFT_CAP, QUIZ_HARD_CAP, DEFAULT_MULTI_PENALTY,
                              DEFAULT_DISTRACTOR_COUNT)
from schemas.quiz import Quiz
from schemas.sentence import Sentence
from schemas.word import Word

log = get_logger(__file__)

class DBHandling:
    def __init__(self, db_name: str = DB_NAME):
        """Init DB manage instance, no input"""
        self._conn = None
        self._cursor = None
        self._dbname = db_name
    
    def connect_2_db(self, username: str = "", password: str = "", 
                     dbname: str = "", host: str = "localhost", port: int = 5432) -> None:
        if username == "" or password == "":
            return -1
        
        # Create DB
        if dbname and dbname != DB_NAME:
            self._dbname = dbname
        if self._dbname != "postgres":
            admin_conn = psycopg2.connect(
                dbname="postgres",
                user=username,
                password=password,
                host=host,
                port=port
            )
            admin_conn.autocommit = True    # Must be true to run CREATE DATABASE (can not be run in transaction)

            admin_cursor = admin_conn.cursor()
            admin_cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (self._dbname,))
            if not admin_cursor.fetchone():
                admin_cursor.execute(f"CREATE DATABASE {self._dbname};")
            admin_cursor.close()
            admin_conn.close()

        # Connect to the desinated database
        self._conn = psycopg2.connect(
            dbname=self._dbname,
            user=username,
            password=password,
            host=host,
            port=port
        )
        self._cursor = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    def migrate(self, filename: str = SQL_TABLE_SCRIPT) -> None:
        """Init all tables from file, including:
        - words: stores words, meaning, spelling, jlpt level, ...
        - books: the literature piece that user input
        - word_books: reference the words and the books containing them
        - word_sentences: reference the words and the sentences containing them
        """
        with open(filename, "r", encoding="utf-8") as f:
            sql_script = f.read()
        if self._safe_execute(sql_script):
            self._conn.commit()
        else:
            self._conn.rollback()

    def close_db(self) -> None:
        if self._cursor:
            self._cursor.close()
            self._cursor = None
        if self._conn:
            self._conn.close()
            self._conn = None

    # Book ==================================================================================
    def insert_book(self, filename: str, content: str = "") -> int:
        """
        Read the whole file and insert into table books (if not in DB yet).
        Don't read file if `content` is not empty/None and use this in place of 'file's content'.

        Input:
        - filename: The full path filename.
        - content: The content of the document. Because this function is design for both
        a real file and not. If filename is a real file, leave this empty. If filename is
        just a name to name this document, then must have content.

        Output: Return the inserted book ID. 0 if already existed. -1 if DB failed.
        -2 if file not found.
        """
        # If is file (not content str)
        bookname = filename
        if not content:
            # Get the <file name> in /some/path/`<file name>`.txt or \ instead of /
            match = re.search(r'[^\\/]+(?=\.[^\\.]+$)', filename)
            if match:
                bookname = match.group()
            else:
                match = re.search(r'[^\\/]', filename)
                if match:
                    bookname = match.group()

        # Check exist
        if self._safe_execute(
            sql.SQL("SELECT COUNT(*) FROM {table} WHERE name = %s;"
                    ).format(table=sql.Identifier(TABLE_BOOKS)),
            (bookname,)
        ):
            if self._cursor.fetchone()["count"]:
                return 0

        # Read file
        if not content:
            if os.path.exists(filename):
                with open(filename, "r", encoding="utf-8") as f:
                    content = f.read()
            else:
                log.error(f"File {filename} not found")
                return -2

        # Insert
        query = sql.SQL("INSERT INTO {table} (name, content) VALUES (%s, %s) RETURNING id;"
                        ).format(table=sql.Identifier(TABLE_BOOKS))
        if self._safe_execute(query, (bookname, content,)):
            self._conn.commit()
            return self._cursor.fetchone()["id"]
        self._conn.rollback()
        return -1

    def update_book(self, book_id: int = 0, name: str = "", append_content: str = "") -> bool:
        """
        Append data to an existing record's `content` column.

        Input:
        - book_id: the book's ID
        - name: the book's name
        - append_content: the data to append to the `content` column's value

        Output: return True if success, False otherwise.
        """
        if not book_id and not name:
            log.error("Must have either book ID or name to update content.")
            return False
        
        query = sql.SQL("UPDATE {table} SET content = COALESCE(content, '') || %s").format(
            table=sql.Identifier(TABLE_BOOKS)
        )
        params = [append_content]

        if book_id:
            query += sql.SQL(" WHERE id = {book_id};").format(
                book_id=sql.Literal(book_id)
            )
        else:
            query += sql.SQL(" WHERE name = %s;")
            params.append(name)
        
        if self._safe_execute(query, params):
            self._conn.commit()
            return True
        self._conn.rollback()
        return False

    def query_like_book(self, name: str, limit: int = DEFAULT_LIMIT) -> List[Book]:
        """
        Query a list of books via LIKE %name%

        Input:
        - name: the book's name
        - limit: the amount of return records, if <= 0, use default value of 10.
         
        Output: a list of book's id and name, no content
        """
        res: List[Book] = []
        query = sql.SQL("SELECT id, name FROM {table} WHERE name LIKE %s LIMIT %s;").format(
            table=sql.Identifier(TABLE_BOOKS)
        )
        if limit < 1:
            limit = DEFAULT_LIMIT
        if self._safe_execute(query, (f"%{name}%", limit,)):
            for instance in self._cursor.fetchall():
                res.append(self._parse_book(instance))
        return res
    
    def get_exact_book(self, name: str = "", book_id: int = None) -> Book:
        """
        Query a book with the exact name or its ID.
        Returns the row of that book.
        """
        success = False
        res = Book()
        if book_id:
            query = sql.SQL("SELECT * FROM {table} WHERE id = %s;").format(
                table=sql.Identifier(TABLE_BOOKS)
            )
            success = self._safe_execute(query, (book_id,))
        elif name:
            query = sql.SQL("SELECT * FROM {table} WHERE name = %s;").format(
                table=sql.Identifier(TABLE_BOOKS)
            )
            success = self._safe_execute(query, (name,))
        if success:
            res = self._parse_book(self._cursor.fetchone())
        return res
    # =======================================================================================

    # Word ==================================================================================
    def insert_word(self, word: Word) -> int:
        """
        Insert into table `words` (if not in DB yet).

        Input: a Word that must contains the following fields:
        word, senses, spelling, forms, jlpt_level, audio.
        The other 4 fields: 'occurrence'=1, 'quized'=0, 'star'=false, 'priority'=1

        Output: the inserted word ID.
        """
        # Check exist
        if self._safe_execute(
            sql.SQL("SELECT COUNT(*) FROM {table} WHERE word = %s;"
                    ).format(table=sql.Identifier(TABLE_WORDS)),
            (word.word,)
        ):
            res = self._cursor.fetchone()
            if res and res.get("count"):
                return 0

        # Insert
        query = sql.SQL(
            """
            INSERT INTO {table} (word, senses, spelling, forms,
                occurrence, jlpt_level, audio_mapping, quized,
                star, priority)
            VALUES (%s, %s, %s, %s, 1, %s, %s, 0, false, 1) RETURNING id;
            """
        ).format(table=sql.Identifier(TABLE_WORDS))
        if self._safe_execute(query, (word.word, word.senses, word.spelling,
             word.forms, word.jlpt_level, word.audio_mapping,)):
            self._conn.commit()
            return self._cursor.fetchone()["id"]
        self._conn.rollback()
        return 0

    def update_word_occurence(self, word: str) -> bool:
        """
        Update a word's occurence (word must match exact) and
        its priority using priority formula.
        Return true if success, false if fail/not found.
        """
        # Get word occurence and quized
        (occurrence, quized) = self._get_word_occurence_quized(word)
        if occurrence == 0:
            return False
        
        # Calc priority and update
        priority = self._priority_formula(occurrence, quized)
        query = sql.SQL("""UPDATE {table} SET occurrence = %s,
                        priority = %s WHERE word = %s;""").format(
            table=sql.Identifier(TABLE_WORDS)
        )
        if self._safe_execute(query, (occurrence+1, priority, word,)):
            self._conn.commit()
            return True
        self._conn.rollback()
        return False
    
    def update_word_jlpt(self, word: str, new_jlpt_level: str) -> bool:
        """
        Update a word's jlpt level (word must match exact).
        Return true if success, false if fail/not found (update 0 row).
        """
        query = sql.SQL("UPDATE {table} SET jlpt_level = %s WHERE word = %s;").format(
            table=sql.Identifier(TABLE_WORDS)
        )
        if self._safe_execute(query, (new_jlpt_level, word,)) and self._cursor.rowcount > 0:
            self._conn.commit()
            return True
        self._conn.rollback()
        return False

    def update_words_known(self, words: List[str]) -> bool:
        """
        Update words `quized` to be QUIZ_HARD_CAP+1 and priority to 0.
        Returns True if success, False if fail.
        """
        query = sql.SQL("UPDATE {table} SET quized = %s, priority = 0 WHERE word IN %s;").format(
            table=sql.Identifier(TABLE_WORDS)
        )
        if self._safe_execute(query, (QUIZ_HARD_CAP+1, tuple(words))) and self._cursor.rowcount > 0:
            self._conn.commit()
            return True
        self._conn.rollback()
        return False

    def update_word_star(self, word: str, new_star_status: bool = None) -> bool:
        """
        Update a word's star. If specified 'new_star_status', will update to that.
        Otherwise, will query word first then update the star to the opposite status.
        Returns True if success, Fail if not found/failed.
        """
        if not new_star_status:
            query = sql.SQL("SELECT star FROM {table} WHERE word = %s;").format(
                table=sql.Identifier(TABLE_WORDS)
            )
            if self._safe_execute(query, (word,)):
                res = self._cursor.fetchone()
                if res:
                    # Default will mark as True
                    db_star = res.get("star", False)
                    new_star_status = False if db_star else True
        
        if new_star_status is None:
            log.error(f"word {word} not found")
            return False
        
        query = sql.SQL("UPDATE {table} SET star = %s WHERE word = %s;").format(
            table=sql.Identifier(TABLE_WORDS)
        )
        if self._safe_execute(query, (new_star_status, word,)) and self._cursor.rowcount > 0:
            self._conn.commit()
            return True
        self._conn.rollback()
        return False

    def query_like_word(self, word: str, limit: int = DEFAULT_LIMIT, parse_dict: bool = False) -> List[Word] | List[dict]:
        """
        Query word in DB, will return a list of all words that are `LIKE '%word%'`

        Input:
        - word: the word to be query %word%
        - limit: the amount of return records, if <= 0, use default value of 10.

        Output: a list of Word objects
        """
        if limit < 1:
            limit = DEFAULT_LIMIT
        res = []
        query = sql.SQL("SELECT * FROM {table} WHERE word LIKE %s LIMIT {limit};").format(
            table=sql.Identifier(TABLE_WORDS),
            limit=sql.Literal(limit)
        )
        if self._safe_execute(query, (f"%{word}%",)):
            for instance in self._cursor.fetchall():
                if parse_dict:
                    res.append(self._parse_word_dict(instance))
                else:
                    res.append(self._parse_word(instance))
        return res
    
    def get_exact_word(self, word: str, parse_dict: bool = False) -> Word | dict:
        """
        Query a word in DB, will return a word that is `= 'word'`

        Input:
        - word: the exact JP word to search
        - parse_dict: true to parse to dict, false to parse to class Word. Default: false
        """
        query = sql.SQL("SELECT * FROM {table} WHERE word = %s;").format(
            table=sql.Identifier(TABLE_WORDS)
        )
        if self._safe_execute(query, (word,)):
            res = self._cursor.fetchone()
            if res:
                if parse_dict:
                    return self._parse_word_dict(res)
                else:
                    return self._parse_word(res)
        return None
    
    def query_word_sense(self, sense: str, limit: int = DEFAULT_LIMIT, parse_dict: bool = False) -> List[Word] | List[dict]:
        """
        Query words table using sense (in English), aka. search by EN word(s).
        Will sort result based on sense matching position.

        Input:
        - sense: the English meaning of the JP word
        - limit: the amount of return records, if <= 0, use default value of 10.
        - parse_dict: If true, return list of dict. Otherwise return list of Word.

        Output: Returns a list of Word objects
        """
        if limit < 1:
            limit = DEFAULT_LIMIT
        res: List[Word] = []
        query = sql.SQL("""SELECT *, POSITION(%s IN LOWER(senses)) AS match_pos
                        FROM {table} WHERE LOWER(senses) LIKE %s
                        ORDER BY match_pos LIMIT {limit};""").format(
            table=sql.Identifier(TABLE_WORDS),
            limit=sql.Literal(limit)
        )
        sense_q = f"%{sense.lower()}%"
        if self._safe_execute(query, (sense_q, sense_q,)):
            for instance in self._cursor.fetchall():
                if parse_dict:
                    res.append(self._parse_word_dict(instance))
                else:
                    res.append(self._parse_word(instance))
        return res
    
    def get_words_by_jlptlevel(self, level: str = "N5", limit: int = DEFAULT_LIMIT) -> List[str]:
        """
        Query 'words' table to get words by JLPT level (i.e.: 'N5').

        Input:
        - level: the JLPT level (N0 - for non-categorized, N5, N4, N3, N2, N1)
        - limit: the amount of return records, if <= 0, use default value of 10.

        Output: a list of word of this level (only the word, no other info such as spelling, senses, ...)
        """
        res: List[str] = []
        if limit < 1:
            limit = DEFAULT_LIMIT
        
        level = level.upper()
        query = sql.SQL("SELECT word FROM {table} WHERE jlpt_level = %s LIMIT {limit};").format(
            table=sql.Identifier(TABLE_WORDS),
            limit=sql.Literal(limit)
        )
        if self._safe_execute(query, (level,)):
            res = [instance["word"] for instance in self._cursor.fetchall() if len(instance.get("word", "")) > 0]
        return res
    
    def _get_word_occurence_quized(self, word: str) -> Tuple[int, int]:
        """
        Get a word's 'occurence' and 'quized' (word must match exact), 0 if not found
        """
        query = sql.SQL("SELECT occurrence, quized FROM {table} WHERE word = %s;").format(
            table=sql.Identifier(TABLE_WORDS)
        )
        if self._safe_execute(query, (word,)):
            res = self._cursor.fetchone()
            if res:
                return (res.get("occurrence", 0), res.get("quized", 0))
        return (0, 0)
    
    def get_all_words_quized(self, grb_jlpt: bool = False) -> Dict[str, List[int]]:
        """
        Query the entire words table, get all `quized` as a list. If `grb_jlpt` is true,
        sort them into JLPT levels.

        Input:
        - grb_jlpt: to groupby jlpt_level or not.

        Output: a dict of keys are the JLPT levels ('N0' for non-jlpt level words, 'N5' -> 'N1') and
        "ALL", the values are list of 3 elements:
        [x < QUIZ_SOFT_CAP, QUIZ_SOFT_CAP < x < QUIZ_HARD_CAP, x > QUIZ_HARD_CAP].
        Note that if grb_jlpt=True, the values are only in the 'N0', 'N5' -> 'N1' keys.
        Otherwise, the values are only in 'ALL'.
        """
        res = {"N0": [0, 0, 0], "N1": [0, 0, 0], "N2": [0, 0, 0],
               "N3": [0, 0, 0], "N4": [0, 0, 0], "N5": [0, 0, 0], "ALL": [0, 0, 0]}
        query = sql.SQL("SELECT quized, jlpt_level FROM {table};").format(
            table=sql.Identifier(TABLE_WORDS)
        )
        if self._safe_execute(query):
            for row in self._cursor.fetchall():
                if grb_jlpt:
                    if row["quized"] > QUIZ_HARD_CAP:
                        res[row.get("jlpt_level", "N0")][2] += 1
                    elif row["quized"] > QUIZ_SOFT_CAP:
                        res[row.get("jlpt_level", "N0")][1] += 1
                    else:
                        res[row.get("jlpt_level", "N0")][0] += 1
                else:
                    if row["quized"] > QUIZ_HARD_CAP:
                        res["ALL"][2] += 1
                    elif row["quized"] > QUIZ_SOFT_CAP:
                        res["ALL"][1] += 1
                    else:
                        res["ALL"][0] += 1
        return res
    
    def list_words(self, jlpt_level: str = "", star: bool = False, limit: int = DEFAULT_LIMIT, offset: int = 0) -> List[dict] | List[Word]:
        """
        Query 'words' table to get a list of JP words and its 1st EN meaning, sort by `id`.

        Input:
        - jlpt_level: the JLPT level (N0 - for non-categorized, N5, N4, N3, N2, N1).
        - star: get only the starred words.
        - limit: the amount of return records, if <= 0, use default value of 10.
        - offset: skip the first X records.

        Output: a list of word of this level (only the word, no other info such as spelling, senses, ...)
        """
        res: list = []
        if limit < 1:
            limit = DEFAULT_LIMIT
        
        params = []
        query = sql.SQL("SELECT word, spelling, senses FROM {table}").format(
            table=sql.Identifier(TABLE_WORDS)
        )
        if jlpt_level:
            jlpt_level = jlpt_level.upper()
            query += sql.SQL(" WHERE jlpt_level = %s")
            params.append(jlpt_level)
        if star:
            if jlpt_level:
                query += sql.SQL(" AND star = true")
            else:
                query += sql.SQL(" WHERE star = true")

        query += sql.SQL(" ORDER BY id OFFSET {offset} LIMIT {limit};").format(
            offset=sql.Literal(offset),
            limit=sql.Literal(limit)
        )
        if self._safe_execute(query, params):
            for instance in self._cursor.fetchall():
                instance["senses"] = self._extract_meanings(instance["senses"])[0]
                res.append(self._parse_word_dict(instance))
        return res

    def count_words(self, jlpt_level: str = "", star: bool = False) -> int:
        """Count words in table (with filters)"""
        params = []
        res = 0
        query = sql.SQL("SELECT COUNT(id) FROM {table}").format(
            table=sql.Identifier(TABLE_WORDS)
        )
        where_clauses = []
        if jlpt_level:
            jlpt_level = jlpt_level.upper()
            where_clauses.append(sql.SQL("jlpt_level = %s"))
            params.append(jlpt_level)
        if star:
            where_clauses.append(sql.SQL("star = true"))
        if where_clauses:
            query = query + sql.SQL(" WHERE ") + sql.SQL(" AND ").join(where_clauses)

        if self._safe_execute(query, params):
            res = self._cursor.fetchone()["count"]
        return res
        
    # =======================================================================================

    # Sentence ==============================================================================
    def query_like_sentence(self, sentence: str, limit: int = DEFAULT_LIMIT) -> List[Sentence]:
        """
        Query sentence in DB, will return a list of all sentences that are `LIKE '%sentence%'`

        Input:
        - sentence: the sentence to be query %sentence%
        - limit: the amount of return records, if <= 0, use default value of 10.
        """
        if limit < 1:
            limit = DEFAULT_LIMIT
        res: List[Sentence] = []
        query = sql.SQL("SELECT * FROM {table} WHERE sentence LIKE %s LIMIT {limit};").format(
            table=sql.Identifier(TABLE_SENTENCES),
            limit=sql.Literal(limit)
        )
        if self._safe_execute(query, (f"%{sentence}%",)):
            for instance in self._cursor.fetchall():
                res.append(self._parse_sentence(instance))
        return res
    
    def query_random_sentences(self, limit: int = DEFAULT_LIMIT, exclude: List[str] = []) -> List[Sentence]:
        """
        Query a number of sentences randomly. Returns a list of parsed Sentence_s.
        
        Input:
        - limit: the amount of return records, if <= 0, use default value of 10.
        - exclude: the list of sentences to ignore
        """
        res: List[Sentence] = []
        params = []
        query = sql.SQL("SELECT * FROM {table}").format(
            table=sql.Identifier(TABLE_SENTENCES)
        )
        if exclude:
            query += sql.SQL(" WHERE sentence NOT IN %s")
            params.append(tuple(exclude))
        query += sql.SQL(" LIMIT %s;")
        params.append(limit)

        if self._safe_execute(query, params):
            for sen in self._cursor.fetchall():
                res.append(self._parse_sentence(sen))
        return res

    def get_exact_sentence(self, sentence: str) -> dict:
        """
        Query a sentence in DB, will return a sentence that is `= 'sentence'`
        """
        query = sql.SQL("SELECT * FROM {table} WHERE sentence = %s;").format(
            table=sql.Identifier(TABLE_SENTENCES)
        )
        if self._safe_execute(query, (sentence,)):
            res = self._cursor.fetchone()
            if res:
                return res
        return {}
    
    def insert_update_sentence(self, sentence: str) -> int:
        """
        Insert into table `sentences`, will update occurrence if sentence existed.
        The 2 fields 'occurence' default to 1, 'star' default False.

        Input: the sentence itself

        Output: the inserted sentence ID, 0 if update existed word occurrence.
        """
        # Check exist -> up occurrence
        if self._safe_execute(
            sql.SQL("SELECT id, occurrence FROM {table} WHERE sentence = %s;"
                    ).format(table=sql.Identifier(TABLE_SENTENCES)),
            (sentence,)
        ):
            res = self._cursor.fetchone()
            if res:
                self.update_sentence_occurence(res.get("id"), res.get("occurrence")+1)
                return 0

        # Insert
        query = sql.SQL(
            """
            INSERT INTO {table} (sentence, occurrence, star)
            VALUES (%s, 1, false) RETURNING id;
            """
        ).format(table=sql.Identifier(TABLE_SENTENCES))
        if self._safe_execute(query, (sentence,)):
            self._conn.commit()
            return self._cursor.fetchone()["id"]
        self._conn.rollback()
        return 0

    def update_sentence_occurence(self, sentence_id: int, new_count: int) -> bool:
        """
        Get a word's occurence (word must match exact).
        Return true if success, false if fail/not found.
        """
        query = sql.SQL("UPDATE {table} SET occurrence = %s WHERE id = %s;").format(
            table=sql.Identifier(TABLE_SENTENCES)
        )
        if self._safe_execute(query, (new_count, sentence_id,)):
            self._conn.commit()
            return True
        self._conn.rollback()
        return False
    
    def update_sentence_star(self, sentence: str, new_star_status: bool = None) -> bool:
        """
        Update a sentence's star. If specified 'new_star_status', will update to that.
        Otherwise, will query sentence first then update the star to the opposite status.
        Returns True if success, Fail if not found/failed.
        """
        if not new_star_status:
            query = sql.SQL("SELECT star FROM {table} WHERE sentence = %s;").format(
                table=sql.Identifier(TABLE_SENTENCES)
            )
            if self._safe_execute(query, (sentence,)):
                res = self._cursor.fetchone()
                if res:
                    # Default will mark as True
                    db_star = res.get("star", False)
                    new_star_status = False if db_star else True
        
        if new_star_status is None:
            log.error(f"Sentence {sentence} not found")
            return False
        
        query = sql.SQL("UPDATE {table} SET star = %s WHERE sentence = %s;").format(
            table=sql.Identifier(TABLE_SENTENCES)
        )
        if self._safe_execute(query, (new_star_status, sentence)) and self._cursor.rowcount > 0:
            self._conn.commit()
            return True
        self._conn.rollback()
        return False

    def get_sentence_occurence(self, sentence: str) -> int:
        """
        Get a sentence's occurence (must match exact), 0 if not found
        """
        query = sql.SQL("SELECT occurrence FROM {table} WHERE sentence = %s;").format(
            table=sql.Identifier(TABLE_SENTENCES)
        )
        if self._safe_execute(query, (sentence,)):
            res = self._cursor.fetchone()
            if res:
                return res.get("occurrence", 0)
        return 0
    
    # this func currently not used
    def get_sentences_containing_word(self, word: str, limit: int = DEFAULT_LIMIT) -> List[str]:
        """
        Get limited amount sentences that contains a word.
        
        Input:
        - word: the word to query
        - limit: the number of sentences to query. If <= 0, use default value 10.

        Output: a list of sentences containing the word, length <= `sentence_count`.
        """
        if limit < 1:
            limit = DEFAULT_LIMIT
        query = sql.SQL("SELECT sentence FROM {table} WHERE sentence LIKE %s LIMIT {limit};").format(
            table=sql.Identifier(TABLE_SENTENCES),
            limit=sql.Literal(limit)
        )
        if self._safe_execute(query, (f"%{word}%",)):
            return [sen["sentence"] for sen in self._cursor.fetchall() if sen.get("sentence", "")]
        return []
    
    def get_sentences_containing_word_by_id(self, word_id: int, limit: int = DEFAULT_LIMIT) -> List[str]:
        """
        Get limited amount sentences that their IDs are associated with this word ID.
        
        Input:
        - word_id: the word's ID
        - limit: the number of sentences to query. If <= 0, use default value 10.

        Output: a list of sentences that their IDs are associated with this word ID,
        length <= `sentence_count`. Return empty if not found or word_id < 1.
        """
        if word_id < 1:
            return []

        if limit < 1:
            limit = DEFAULT_LIMIT
        query = sql.SQL("""SELECT s.sentence FROM {sen_table} s
            JOIN {word_sen_table} ws ON s.id = ws.sentence_id
            WHERE ws.word_id = %s
            ORDER BY RANDOM() LIMIT {limit};""").format(
                sen_table=sql.Identifier(TABLE_SENTENCES),
                word_sen_table=sql.Identifier(TABLE_WORD_SENTENCE_REF),
                limit=sql.Literal(limit)
            )
        if self._safe_execute(query, (word_id,)):
            return [sen["sentence"] for sen in self._cursor.fetchall() if sen.get("sentence", "")]
        return []
    # =======================================================================================

    # Insert References =====================================================================
    def insert_word_book_ref(self, word_id: int, book_id: int) -> bool:
        """
        Insert into table `word_book` for word and book references.
        Return true if success, otherwise, false.
        """
        if word_id < 1 or book_id < 1:
            return False
        
        query = sql.SQL("INSERT INTO {table} (word_id, book_id) VALUES (%s, %s) ON CONFLICT DO NOTHING;"
                        ).format(table=sql.Identifier(TABLE_WORD_BOOK_REF))
        if self._safe_execute(query, (word_id, book_id,)):
            self._conn.commit()
            return True
        self._conn.rollback()
        return False

    def insert_word_sentence_ref(self, word_id: int, sentence_id: int) -> bool:
        """
        Insert into table `word_sentence` for word and sentence references.
        Return true if success, otherwise, false.
        """
        if word_id < 1 or sentence_id < 1:
            return False

        query = sql.SQL("INSERT INTO {table} (word_id, sentence_id) VALUES (%s, %s) ON CONFLICT DO NOTHING;"
                        ).format(table=sql.Identifier(TABLE_WORD_SENTENCE_REF))
        if self._safe_execute(query, (word_id, sentence_id,)):
            self._conn.commit()
            return True
        self._conn.rollback()
        return False
    
    def insert_sentence_book_ref(self, sentence_id: int, book_id: int) -> bool:
        """
        Insert into table `sentence_book` for sentence and book references.
        Return true if success, otherwise, false.
        """
        if sentence_id < 1 or book_id < 1:
            return False
        
        query = sql.SQL("INSERT INTO {table} (sentence_id, book_id) VALUES (%s, %s) ON CONFLICT DO NOTHING;"
                        ).format(table=sql.Identifier(TABLE_SENTENCE_BOOK_REF))
        if self._safe_execute(query, (sentence_id, book_id,)):
            self._conn.commit()
            return True
        self._conn.rollback()
        return False
    # =======================================================================================

    # Quiz ==================================================================================
    def get_quiz(self, limit: int = DEFAULT_LIMIT,
                sorts: List[Tuple[str]] = [], jlpt_filter: str = "",
                star_only: bool = False, use_priority: bool = True, 
                exclude_jp: List[str] = [], exclude_en: List[str] = []) -> List[Quiz]:
        """
        Query DB, get random words records and parse into Quiz objects.
        Can sort multiple columns, can have at once multiple filters (jlpt_level, star_only),
        can use priority column (can not use along with sort).
        The 'EN word' is just the first meaning in the `senses` column in TABLE_WORDS
        This function will also avoid query EN that has dash ('-'),
        to not just show '-ive' and have no idea what it is.

        Note: Will not get words with `priority=0`, aka. `quized` > QUIZ_HARD_CAP.
        Does not get distractors for the quiz! In other words, this only include
        the correct answers.

        Input:
        - sorts: a list of length 2 tuples, i.e.: [ ('col1', 'asc'), ('col2', 'desc') ]. Default: empty.
        Note that the order of this list is important, the smaller indexes will be prioritized when query.
        - jlpt_filter: the JLPT level to filter in query. Default: not use.
        - star_only: query only those that starred. Default: false.
        - use_priority: use 'occurence' and 'quized' to calculate priority or not.
        More 'occurence' = higher prio, higher 'quized' = lower prio. This can not use together with sort.
        Note that this is refer to the original Japanese word. Default: True.
        - exclude_jp: the list of EN words to not include in query. Default: empty.
        - exclude_en: the list of EN words to not include in query. Default: empty.

        Output: a list of QuizEN objects.
        """
        # Build SQL
        sql_full, params = self._build_sort_filter_prio_sql(sorts, jlpt_filter, star_only, use_priority,
                                                            limit, True, exclude_jp, exclude_en)

        # Query
        q_res = []
        if self._safe_execute(sql_full, params):
            q_res = self._cursor.fetchall()

        # Get words and meanings
        res: List[Quiz] = []
        for row in q_res:
            res.append(Quiz(
                jp=row["word"],
                en=self.get_meanings("", row["senses"])[0].split(",")[0],
                spelling=row["spelling"],
                jlpt_level=row["jlpt_level"],
                audio_mapping=row["audio_mapping"],
                occurrence=row["occurrence"],
                quized=row["quized"],
                star=row["star"]
            ))
        return res

    def update_quized_prio_ts(self, word: str, occurrence: int = None, quized: int = None) -> bool:
        """
        Query `occurrence`, `quized` and `last_tested` (if didn't passed value in, `quized` will +1).
        Calc new `priority` value, formula depends on how big is `quized` compare to QUIZ_SOFT_CAP
        and QUIZ_HARD_CAP. Get current timestamp for last_tested. Save the new values to DB.

        Input:
        - word: the word to update
        - occurrence (optional): the word's occurrence
        - quized (optional): the word's correct quiz count
        If both occurrence and quized are provided, will use these to calculate priority
        without querying the table.

        Output: returns True if success, False if fail
        """
        # Get occurrence and quized if no value
        if occurrence is None or quized is None:
            row = self.get_exact_word(word)
            occurrence = row.occurrence
            quized = row.quized + 1

        # Calc priority and update table
        if quized > QUIZ_HARD_CAP:
            prio = 0.0
        elif quized > QUIZ_SOFT_CAP:
            prio = self._priority_softcap_formula(occurrence, quized)
        else:
            prio = self._priority_formula(occurrence, quized)

        query = sql.SQL("""UPDATE {table} SET quized = %s, priority = %s,
                        last_tested = NOW() WHERE word = %s;""").format(
            table=sql.Identifier(TABLE_WORDS)
        )
        if self._safe_execute(query, (quized, prio, word)) and self._cursor.rowcount > 0:
            self._conn.commit()
            return True
        self._conn.rollback()
        return False

    def get_distractors(self, exclude_jp: str = "", exclude_en: str = "",
                        limit: int = DEFAULT_DISTRACTOR_COUNT) -> List[Quiz]:
        """
        Gets random Japanese words other than the `exclude_jp` for its meaning `exclude_en`.
        Query `limit` random different words and get their first meanings in `senses`.
        Does not get the meanings that contains '-' in them, i.e.: 的's sense: -ical,-ive,-al,-ic,-y.

        Input:
        - exclude_jp: the JP word in quiz, will query different than this word.
        - exclude_en: the EN/first meaning of the JP word, will query different meaning than this.
        - limit: the number of distractor meanings to query.

        Output: a list of Quiz objects, only include the incorrect JP and EN words. Empty if fail.
        """
        res: List[Quiz] = []
        query, params = self._build_distractors_sql(exclude_jp, exclude_en, limit)
        if self._safe_execute(query, params):
            for row in self._cursor.fetchall():
                res.append(Quiz(
                    jp=row["word"],
                    en=self.get_meanings("", row["senses"])[0]
                ))
        return res
    
    # quiz sentence requires ProcessData to tag sentence to get the words.
    # call db.query_random_sentences() and db.get_en_meaning_distractors() for it
    # =======================================================================================


    # Helpers ===============================================================================
    def get_meanings(self, word: str, senses: str) -> List[str]:
        """
        Query an exact word's `senses` column, get all the meaning out.
        Senses format example: "to receive,to get, (['Ichidan verb', 'transitive verb']); ...".
        Return example: ["to receive,to get,", "second meaning", ...]
        """
        if not senses and word:
            q_res = dict()
            query = sql.SQL("SELECT senses FROM {table} WHERE word = %s;").format(
                table=sql.Identifier(TABLE_WORDS)
            )
            if self._safe_execute(query, (word,)):
                q_res = self._cursor.fetchone()
            senses = q_res.get("senses", "") if q_res else ""

        return self._extract_meanings(senses)
    
    def _extract_meanings(self, senses: str) -> List[str]:
        """Use regex to split senses and get just the meanings (drop example and pos).
        the sense format: meaning1_1,meaning1_2, (e.g.: exampleA,exampleB) ([pos]);..."""
        res = []
        if senses:
            all_senses = [chunk.strip() for chunk in senses.split(";") if chunk.strip()]
            for one_sense in all_senses:
                # regex the get just the meaning part
                match = WORD_SENSES_REGEX.match(one_sense)
                if match:
                    meaning = match.group(1).strip().rstrip(", ")
                    # Keep only the first 2 synonym for each meaning
                    if "," in meaning:
                        meaning = ", ".join(meaning.split(",")[:2])
                    res.append(meaning)
        return res

    def _safe_execute(self, query: sql.SQL, params=None) -> bool:
        """
        Wrap cursor executing query, return True/False on Success/Failure.
        """
        if not str(query):
            return False
        
        try:
            if params:
                self._cursor.execute(query, params)
            else:
                self._cursor.execute(query)
            return True
        except psycopg2.Error as e:
            log.error(f"Query failed: {query}, error: {e}")
            return False
        except Exception as e:
            log.exception(f"Unexpected error during DB query: {e}")
            return False
    # =======================================================================================

    # Parsing ===============================================================================
    def _parse_word(self, word: dict) -> Word:
        """Parse word dict from query result into Word class"""
        return Word(
            word_id=word.get("id", 0),
            word=word.get("word", ""),
            senses=word.get("senses", ""),
            spelling=word.get("spelling", ""),
            forms=word.get("forms", ""),
            jlpt_level=word.get("jlpt_level", ""),
            star=word.get("star", ""),
            occurence=word.get("occurrence", ""),
            quized=word.get("quized", "")
        )
    
    def _parse_word_dict(self, word: dict) -> dict:
        """Keep the dict form, assure have enough fields, modify in-place and also return"""
        word["id"] = word.get("id", 0)
        word["word"] = word.get("word", "")
        word["senses"] = word.get("senses", "")
        word["spelling"] = word.get("spelling", "")
        word["forms"] = word.get("forms", "")
        word["jlpt_level"] = word.get("jlpt_level", "")
        word["star"] = word.get("star", "")
        word["occurence"] = word.get("occurrence", "")
        word["quized"] = word.get("quized", "")
        return word

    def _parse_sentence(self, sentence: dict) -> Sentence:
        """Parse sentence dict from query result into Sentence class"""
        return Sentence(
            sen_id=sentence.get("id", 0),
            sentence=sentence.get("sentence", ""),
            star=sentence.get("star"),
            occurence=sentence.get("occurrence"),
            quized=sentence.get("quized")
        )

    def _parse_book(self, book: dict) -> Book:
        """Parse book dict from query result into Book class"""
        return Book(
            book_id=book.get("id", 0),
            name=book.get("name", ""),
            content=book.get("content", ""),
        )
    # =======================================================================================

    # Quiz Helpers ==========================================================================
    # ------- Normal formula ----------
    def _priority_formula(self, occurrence: int, quized: int, k: float = DEFAULT_FORMULA_K) -> float:
        """
        A wrapping function to calculate word show up priority, if want to change formula,
        just change in this function instead of change it everywhere in this class
        """
        return self._priority_expodecay(occurrence, quized, k)

    def _priority_expodecay(self, occurrence: int, quized: int, k: float = DEFAULT_FORMULA_K) -> float:
        """
        Calc the priority of a word to show in quiz. Using exponential decay approach.

        Input:
        - occurrence: the times this word occured in documents
        - quized: the times this word is guessed correctly
        """
        return occurrence * math.exp(-k * quized)
    
    # More formulas...
    # ---------------------------------

    # ------- Soft cap formula --------
    def _priority_softcap_formula(self, occurrence: int, quized: int, k: float = DEFAULT_FORMULA_K,
                                  p: float = DEFAULT_MULTI_PENALTY) -> float:
        """
        Use to calculate priority for a word that has been quized and get corrected > QUIZ_SOFT_CAP times
        """
        return self._priority_multiplier_penalty(occurrence, quized, k, p)

    def _priority_multiplier_penalty(self, occurrence: int, quized: int, k: float = DEFAULT_FORMULA_K,
                                     p: float = DEFAULT_MULTI_PENALTY) -> float:
        """
        Calc priority using the base exponential decay, introduce multiplier penalty.
        i.e.: `p` = 0.2 means priority will be 20% lower after soft cap.
        """
        return self._priority_expodecay(occurrence, quized, k) / (1 + p * (quized - QUIZ_SOFT_CAP))
    
    # More formulas...
    # ----------------------------------

    # -------- Build SQLs --------------
    def _build_sort_filter_prio_sql(self, sorts: List[Tuple[str]] = [], jlpt_filter: str = "",
                                    star_only: bool = False, use_priority: bool = True,
                                    limit: int = DEFAULT_LIMIT, avoid_dash_sense: bool = False,
                                    exclude_jp: List[str] = [], exclude_en: List[str] = []) -> Tuple[sql.SQL, list]:
        """
        Build the SQL to query 'word', 'senses', 'jlpt_level', 'spelling', 'audio_mapping',
        'occurrence', 'quized', 'star' columns with sorts, filters and/or use priority vale.
        Use priority value is just a sort 'priority' DESC.

        Will not get words with `priority=0`, aka. `quized` > QUIZ_HARD_CAP.

        Input: (check other params from get_quiz())
        - avoid_dash_sense: avoid querying record whose 'senses' includes dashes ('-'),
        i.e.: 的's senses is '-ical,-ive,-al,-ic,-y'
        - exclude_jp: list of JP words to exclude
        - exclude_en: list of EN words to exclude

        Output:
        - Built psycopg2.sql.SQL
        - list of params to pass in on query execution
        """
        conditions = []
        params = []
        sql_full = sql.SQL("""SELECT word, senses, jlpt_level, spelling,
                           audio_mapping, occurrence, quized, star FROM {table}
                           WHERE priority > 0.0""").format(
            table=sql.Identifier(TABLE_WORDS)
        )
        
        # ----- Filter -----
        if exclude_jp:
            conditions.append(sql.SQL("word NOT IN %s"))
            params.append(tuple(exclude_jp))  # tuple so PostgreSQL understands IN clause
        if exclude_en:
            for ex_en in exclude_en:
                conditions.append(sql.SQL("senses NOT LIKE %s"))
                params.append(f"%{ex_en}%")
        if jlpt_filter:
            conditions.append(sql.SQL("jlpt_level = %s"))
            params.append(jlpt_filter)
        if star_only:
            conditions.append(sql.SQL("star = true"))

        # Combine filters
        if conditions:
            sql_full += sql.SQL(" AND ").join(conditions)
            conditions.clear()  # clear condition for sort

        # Avoid word with senses that have '-'
        if avoid_dash_sense:
            sql_full += sql.SQL(" AND senses NOT LIKE %s")
            params.append("%-%")
        
        # ----- Sort & Prio -----
        if sorts and not use_priority:
            order_parts = [
                sql.Identifier(col) + sql.SQL(f" {direction}")
                for col, direction in sorts
            ]
            conditions.append(sql.SQL(" ORDER BY {order}").format(
                order=sql.SQL(", ").join(order_parts)
            ))
        elif not sorts and use_priority:
            conditions.append(sql.SQL(" ORDER BY {order} DESC").format(
                order=sql.Identifier("priority")
            ))
        else:
            log.error("Can not use sort and priority value at the same time")
            return []
        
        # Combine sort
        if conditions:
            sql_full += conditions[0]

        # Add count
        sql_full += sql.SQL(" LIMIT %s;")
        params.append(limit)
        return sql_full, params

    def _build_distractors_sql(self, exclude_jp: str, exclude_en: str = "", limit: int = DEFAULT_DISTRACTOR_COUNT) -> Tuple[sql.SQL, List[str]]:
        """
        Query `limit` number of 'word' and 'senses' from table words that
        'word' != exclude_jp and 'senses' NOT LIKE '%exclude_en%' (if specified)

        Input:
        - exclude_jp: the JP word in quiz, will query different than this word.
        - exclude_en (optional): the EN/first meaning of the JP word, will query different meaning than this.
        - limit: the number of distractor meanings to query.

        Output: the built sql query and list of params
        """
        params = [exclude_jp, f"%-%"]
        query = sql.SQL("SELECT word, senses FROM {table} WHERE word != %s AND senses NOT LIKE %s").format(
            table=sql.Identifier(TABLE_WORDS)
        )
        if exclude_en:
            query += sql.SQL(" AND senses NOT LIKE %s")
            params.append(f"%{exclude_en}%")
        query += sql.SQL(" ORDER BY RANDOM() LIMIT {limit};").format(limit=sql.Literal(limit))
        return (query, params)
    # ----------------------------------

    # Word priority on quiz ========== Leave this alone for now =============================
    def _priority_formula2(self, k: float = 0.5) -> sql.SQL:
        """
        A wrapping function to calculate word show up priority, if want to change formula,
        just change in this function instead of change it everywhere in this class
        """
        return self._priority_expodecay(k)

    def _priority_expodecay2(self, k: float = 0.5) -> sql.SQL:
        """
        The formula SQL, 'occurrence * EXP(-{k} * quized)'

        Input:
        - k: slider for formula
        """
        return sql.SQL(f"occurrence * EXP(-{k} * quized)")
    
    def refresh_word_priority_view(self, filename: str = SQL_WORD_PRIO_SCRIPT) -> bool:
        """
        Create or update the word priority view, which calculate the words priority
        from table words, currently using the exponential decay formula.

        Input: the word_priority view script, default SQL_WORD_PRIO_SCRIPT

        Output: True if success, False if failed
        """
        # Check script
        if not os.path.exists(filename):
            log.error(f"Word priority view SQL script not found: {filename}")
            return False
        script = ""
        with open(filename, "r") as f:
            script = f.read()
        if not script:
            log.error(f"Word priority view SQL script is empty: {filename}")
            return False
        
        # Using exponential decay formula
        query = sql.SQL(script).format(
            formula=self._priority_formula(),
            table=sql.Identifier(TABLE_WORDS)
        )
        if self._safe_execute(query):
            self._conn.commit()
            return True
        self._conn.rollback()
        return False
    # =======================================================================================



    def truncate_all_tables(self) -> None:
        """USE FOR TEST ONLY"""
        with open("data/sql/truncate_all_tables.sql", "r", encoding="utf-8") as f:
            sql_script = f.read()
        self._cursor.execute(sql_script)

    def drop_database(self) -> None:
        """USE FOR TEST ONLY"""
        self._cursor.execute("DROP DATABASE IF EXISTS %s;", (self._dbname,))
        self._cursor.execute("CREATE DATABASE IF NOT EXISTS %s;", (self._dbname,))
