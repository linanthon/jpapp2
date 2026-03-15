from contextlib import contextmanager
import math
import os
import re
import psycopg2
import psycopg2.extras
from psycopg2 import sql, extensions
from typing import List, Tuple, Dict

from app.web.handlers.config import DB_HOST, DB_PORT
from utils.logger import get_logger
from schemas.book import Book
from schemas.constants import (TABLE_WORDS, TABLE_BOOKS, TABLE_SENTENCES, TABLE_WORD_BOOK_REF,
                              TABLE_WORD_SENTENCE_REF, TABLE_SENTENCE_BOOK_REF, DB_NAME,
                              SQL_TABLE_SCRIPT, DEFAULT_LIMIT, SQL_WORD_PRIO_SCRIPT,
                              DEFAULT_FORMULA_K, DEFAULT_TIME_EXPODECAY, QUIZ_WORD_SORT_COLUMNS,
                              WORD_SENSES_REGEX, QUIZ_SOFT_CAP, QUIZ_HARD_CAP, DEFAULT_MULTI_PENALTY,
                              DEFAULT_DISTRACTOR_COUNT, TABLE_USER_WORD_PROGRESS, TABLE_USER_BOOK_STAR)
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
        self._in_transaction = False
    
    def connect_2_db(self, username: str = "", password: str = "", 
                     dbname: str = "", host: str = DB_HOST, port: int = DB_PORT) -> None:
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
    
    def migrate(self, filename: str = SQL_TABLE_SCRIPT) -> bool:
        """Init all tables from file, including:
        - words: stores words, meaning, spelling, jlpt level, ...
        - books: the literature piece that user input
        - word_books: reference the words and the books containing them
        - word_sentences: reference the words and the sentences containing them
        """
        with open(filename, "r", encoding="utf-8") as f:
            sql_script = f.read()
        if self._safe_execute(sql_script):
            self._safe_commit()
            return True
        self._safe_rollback()
        return False

    def close_db(self) -> None:
        if self._cursor:
            self._cursor.close()
            self._cursor = None
        if self._conn:
            self._conn.close()
            self._conn = None

    # User ==================================================================================
    def create_user(self, username: str, email: str, password_hash: str, is_admin: bool = False) -> int:
        """
        Create a new user in the database.
        
        Input:
        - username: Username (must be unique)
        - email: Email address (must be unique)
        - password_hash: Hashed password
        - is_admin: Whether user is admin (default False)
        
        Output: User ID if successful, -1 if failed
        """
        query = sql.SQL(
            """INSERT INTO {table} (username, email, password_hash, is_admin, created_at, modified_at) 
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) RETURNING id;"""
        ).format(table=sql.Identifier("users"))
        
        if self._safe_execute(query, (username, email, password_hash, is_admin)):
            self._safe_commit()
            return self._cursor.fetchone()["id"]
        self._safe_rollback()
        return -1
    
    def get_user_by_id(self, user_id: int) -> dict | None:
        """
        Get user by ID (without password_hash).
        
        Output: User dict or None if not found.
        """
        query = sql.SQL("SELECT id, username, email, is_admin, created_at FROM {table} WHERE id = %s;").format(
            table=sql.Identifier("users")
        )
        
        if self._safe_execute(query, (user_id,)):
            result = self._cursor.fetchone()
            return dict(result) if result else None
        return None
    
    def get_user_by_username(self, username: str) -> dict | None:
        """
        Get user by username (includes password_hash for auth).
        
        Output: User dict (including password_hash) or None if not found.
        """
        query = sql.SQL(
            "SELECT id, username, email, password_hash, is_admin, created_at FROM {table} WHERE username = %s;"
        ).format(table=sql.Identifier("users"))
        
        if self._safe_execute(query, (username,)):
            result = self._cursor.fetchone()
            return dict(result) if result else None
        return None
    
    def user_exists(self, username: str) -> bool:
        """Check if username exists"""
        query = sql.SQL("SELECT COUNT(*) as count FROM {table} WHERE username = %s;").format(
            table=sql.Identifier("users")
        )
        
        if self._safe_execute(query, (username,)):
            result = self._cursor.fetchone()
            return result["count"] > 0 if result else False
        return False
    
    def user_exists_by_email(self, email: str) -> bool:
        """Check if email exists"""
        query = sql.SQL("SELECT COUNT(*) as count FROM {table} WHERE email = %s;").format(
            table=sql.Identifier("users")
        )
        
        if self._safe_execute(query, (email,)):
            result = self._cursor.fetchone()
            return result["count"] > 0 if result else False
        return False

    # Book ==================================================================================
    def insert_book(self, filename: str, content: str = "") -> int:
        """
        Read the whole file and insert into table books (if not in DB yet).
        If `content` is not empty/None, doesn't read file and use this instead.

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
            self._safe_commit()
            return self._cursor.fetchone()["id"]
        self._safe_rollback()
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
            self._safe_commit()
            return True
        self._safe_rollback()
        return False

    # TODO: fix when enable search book
    # def query_like_book(self, name: str, limit: int = DEFAULT_LIMIT, parse_dict: bool = False) -> List[Book] | List[dict]:
    #     """
    #     Query a list of books via LIKE %name%

    #     Input:
    #     - name: the book's name
    #     - limit: the amount of return records, if <= 0, use default value of 10.
         
    #     Output: a list of book's id and name, no content
    #     """
    #     res: List[Book] = []
    #     query = sql.SQL("SELECT id, name FROM {table} WHERE name LIKE %s LIMIT %s;").format(
    #         table=sql.Identifier(TABLE_BOOKS)
    #     )
    #     if limit < 1:
    #         limit = DEFAULT_LIMIT
    #     if self._safe_execute(query, (f"%{name}%", limit,)):
    #         for instance in self._cursor.fetchall():
    #             if parse_dict:
    #                 res.append(self._parse_book_dict(instance))
    #             else:
    #                 res.append(self._parse_book(instance))
    #     return res
    
    def get_exact_book(self, user_id: int = None, book_id: int = None, parse_dict: bool = False) -> Book | dict:
        """
        Query a book with the exact name or its ID.
        Returns the row of that book, empty dict if fail to get.
        """
        if not book_id:
            return None if parse_dict else Book()
        
        # Check if is starred by user
        is_star = False
        query = sql.SQL("""SELECT book_id FROM {table} 
                        WHERE user_id = {uid} AND star = true;""").format(
            table=sql.Identifier(TABLE_USER_BOOK_STAR),
            uid=sql.Literal(user_id)
        )
        if self._safe_execute(query):
            if self._cursor.fetchone():
                is_star = True
        
        # get the book
        query = sql.SQL("""SELECT id, created_at, name, content
                        FROM {table} WHERE book_id = {bid};""").format(
            table=sql.Identifier(TABLE_BOOKS),
            bid=sql.Literal(book_id)
        )
        res = None
        if self._safe_execute(query):
            if parse_dict:
                res = self._parse_book_dict(self._cursor.fetchone(), is_star)
            else:
                res = self._parse_book(self._cursor.fetchone(), is_star)
        return res
    
    def list_books(self, user_id: int = None, star: bool = False, 
                   limit: int = DEFAULT_LIMIT, offset: int = 0) -> List[dict]:
        """
        Query 'books' table to get a list of books

        Input:
        - user_id: the user ID
        - star: get only the starred books.
        - limit: the amount of return records. If <= 0, use default value of 10.
            If purposely left None, query all.
        - offset: skip the first X records.

        Output: a list of books (id, name, star, created_at)
        """
        book_star_ids = set()
        if star:
            if not user_id:
                return []
            
            query = sql.SQL("""SELECT book_id FROM {table} 
                            WHERE user_id = {uid} AND star = true;""").format(
                table=sql.Identifier(TABLE_BOOKS),
                uid=sql.Literal(user_id)
            )
            if self._safe_execute(query):
                for instance in self._cursor.fetchall():
                    book_star_ids.add(instance.get("id", 0))
        
        res: list = []
        query = sql.SQL("SELECT id, name, created_at FROM {table1}").format(
            table1=sql.Identifier(TABLE_BOOKS),
        )

        if limit is None:
            query += sql.SQL(" ORDER BY id OFFSET {offset}").format(
                offset=sql.Literal(offset)
            )
        elif limit < 1:
            query += sql.SQL(" ORDER BY id OFFSET {offset} LIMIT {limit};").format(
                offset=sql.Literal(offset),
                limit=sql.Literal(limit)
            )
        
        if self._safe_execute(query):
            for instance in self._cursor.fetchall():
                res.append(self._parse_book_dict(
                    instance, instance.get("id", 0) in book_star_ids
                ))
        return res

    def count_books(self, star: bool = False) -> int:
        """Count words in table (with filters)"""
        params = []
        res = 0
        query = sql.SQL("SELECT COUNT(id) FROM {table}").format(
            table=sql.Identifier(TABLE_BOOKS)
        )
        if star:
            query += sql.SQL(" WHERE star = true")

        if self._safe_execute(query, params):
            res = self._cursor.fetchone()["count"]
        return res

    def update_book_star(self, user_id: int = None, book_id: int = None, 
                         new_star_status: bool = None) -> bool:
        """
        Update a book's star. If specified 'new_star_status', will update to that.
        Returns True if success, Fail if not found/failed.
        """
        if not book_id or new_star_status is None:
            return False
        
        query = sql.SQL("""UPDATE {table} SET star = %s 
                        WHERE user_id = {uid} AND book_id = {bid};""").format(
            table=sql.Identifier(TABLE_USER_BOOK_STAR),
            uid=sql.Literal(user_id),
            bid=sql.Literal(book_id)
        )
        if self._safe_execute(query, (new_star_status,)) and self._cursor.rowcount > 0:
            self._safe_commit()
            return True
        self._safe_rollback()
        return False

    def delete_book(self, book_id: int = None) -> bool:
        """Remove book by name (exact match) or id, will also remove all
        its sentences and words. If those sentences/words have duplicate in another book,
        reduce their counts instead. Return true if success, otherwise false.
        """
        if not book_id:
            return False
        
        # Get all its sentence IDs
        query = sql.SQL("SELECT sentence_id FROM {table} WHERE book_id = {bid}").format(
            table=sql.Identifier(TABLE_SENTENCE_BOOK_REF),
            bid=sql.Literal(book_id)
        )
        if not self._safe_execute(query):
            return False
        sentence_ids = []
        for item in self._cursor.fetchall():
            sentence_ids.append(item["sentence_id"])

        # Track words and sentences decrement to commit properly
        word_decrements = {}
        sen_decrements = {}
        
        # Get all sentences from ref table to know how much we need to reduce its occurrence
        # Get before delete book to not lost ref
        if not self._collect_sentence_decrements(book_id, sen_decrements):
            self._safe_rollback()
            return False
        # Get all words from reft table for the same reason
        for sen_id in sentence_ids:
            if not self._collect_word_decrements(sen_id, word_decrements):
                self._safe_rollback()
                return False
        
        # Now delete book (this will cascade and delete sentence_book, word_book and user_book_star refs)
        query = sql.SQL("DELETE FROM {table} WHERE id = {bid}").format(
            table=sql.Identifier(TABLE_BOOKS),
            bid=sql.Literal(book_id)
        )
        deleted_book = self._safe_execute(query)
        if not deleted_book:
            self._safe_rollback()
            return False

        # Decrease count/Delete sentences (cascade delete word_sentence ref)
        for sen_id, decrement_count in sen_decrements.items():
            deleted_sen = self._decrement_sentece_occurrence(sen_id, decrement_count)
            if not deleted_sen:
                self._safe_rollback()
                return False
        # Decrease count/Delete words (cascade delete user_word_progress ref)
        for word_id, decrement_count in word_decrements.items():
            if not self._decrement_word_occurrence(word_id, decrement_count):
                self._safe_rollback()
                return False

        self._safe_commit()
        return True        

    # =======================================================================================

    # Word ==================================================================================
    # To lessen work for `process_data`, instead of doing like db.insert_update_sentence
    # Split it into `insert_word` and `update_word_occurrence`
    def insert_word(self, word: Word) -> int:
        """
        Insert into table `words` (if not in DB yet).

        Input: a Word that must contains the following fields:
        word, senses, spelling, forms, jlpt_level, audio.
        The other 4 fields: 'occurrence'=1, 'quized'=0, 'star'=false, 'priority'=1

        Output: the inserted word ID or existed word ID.
        """
        # Check if exist, return id
        if self._safe_execute(
            sql.SQL("SELECT id FROM {table} WHERE word = %s;"
                    ).format(table=sql.Identifier(TABLE_WORDS)),
            (word.word,)
        ):
            res = self._cursor.fetchone()
            if res:
                return res.get("id", 0)

        # Insert
        query = sql.SQL(
            """
            INSERT INTO {table} (word, senses, spelling, forms,
                occurrence, jlpt_level, audio_mapping)
            VALUES (%s, %s, %s, %s, 1, %s, %s) RETURNING id;
            """
        ).format(table=sql.Identifier(TABLE_WORDS))
        if self._safe_execute(query, (word.word, word.senses, word.spelling,
             word.forms, word.jlpt_level, word.audio_mapping,)):
            self._safe_commit()
            res = self._cursor.fetchone()
            if res:
                return res.get("id", 0)
        
        self._safe_rollback()
        return 0

    def update_word_occurrence(self, word: str, user_ids: list = []) -> bool:
        """
        Update a word's occurrence (word must match exact) in word table and
        priority using priority formula in the user word progress table (if input user_id).
        Return true if success, false if fail/not found.
        """
        # Get word occurrence
        word_id, occurrence = self.get_word_occurence(word=word)
        if occurrence == 0:
            return False
        
        with self.transaction():
            # Update word occurrence
            query1 = sql.SQL("""UPDATE {table1} SET occurrence = %s WHERE id = {wid};""").format(
                table1=sql.Identifier(TABLE_WORDS),
                wid=sql.Literal(word_id)
            )
            if not self._safe_execute(query1, (occurrence,)):
                self._safe_rollback()
                return False
        
            # Get quized and calc priority
            if user_ids:
                for user_id in user_ids:
                    quized = self.get_word_quized(word_id)
                    priority = self._priority_formula(occurrence, quized)
                    query2 = sql.SQL(
                        """UPDATE {table2} SET priority = %s WHERE user_id = {uid} AND word_id = {uid};"""
                    ).format(
                        table2=sql.Identifier(TABLE_USER_WORD_PROGRESS),
                        uid=sql.Literal(user_id),
                        wid=sql.Literal(word_id)
                    )

                    if not self._safe_execute(query2, (priority,)):
                        self._safe_rollback()
                        return False
                
            self._safe_commit()
        return True
    
    #TODO: currently not used, remove?
    def update_word_jlpt(self, word: str, new_jlpt_level: str) -> bool:
        """
        Update a word's jlpt level (word must match exact).
        Return true if success, false if fail/not found (update 0 row).
        """
        query = sql.SQL("UPDATE {table} SET jlpt_level = %s WHERE word = %s;").format(
            table=sql.Identifier(TABLE_WORDS)
        )
        if self._safe_execute(query, (new_jlpt_level, word,)) and self._cursor.rowcount > 0:
            self._safe_commit()
            return True
        self._safe_rollback()
        return False

    def update_words_known(self, user_id: int, word_ids: List[int] = []) -> bool:
        """Update words priority to -1.0 (to fail the > 0.0 check when query for quiz).
        Returns True if success, False if fail."""
        if not user_id or not word_ids:
            return False
        
        query = sql.SQL("""UPDATE {table} SET priority = -1.0 
                        WHERE user_id = {uid} AND word_id IN %s;""").format(
            table=sql.Identifier(TABLE_USER_WORD_PROGRESS),
            uid=sql.Literal(user_id)
        )
        if self._safe_execute(query, (tuple(word_ids),)) and self._cursor.rowcount > 0:
            self._safe_commit()
            return True
        self._safe_rollback()
        return False

    def update_word_star(self, user_id: int, word_id: int, new_star_status: bool = None) -> bool:
        """
        Update a word's star. If specified 'new_star_status', will update to that.
        Returns True if success, Fail if not found/failed.
        """
        if not user_id or not word_id or new_star_status is None:
            return False
        
        # Update star
        query = sql.SQL("UPDATE {table} SET star = %s WHERE user_id = {uid} AND word_id = {wid};").format(
            table=sql.Identifier(TABLE_USER_WORD_PROGRESS),
            uid=sql.Literal(user_id),
            wid=sql.Literal(word_id)
        )
        if self._safe_execute(query, (new_star_status,)):
            if self._cursor.rowcount > 0:
                self._safe_commit()
                return True
        else:
            self._safe_rollback()
            return False
        
        # Reach here = no update = need insert new row
        # Get word occurrence
        _, occurrence = self.get_word_occurence(word_id)
        if not occurrence:
            return False
        quized = 0  # insert here = never quized before
        priority = self._priority_formula(occurrence, quized)

        # Write
        query = sql.SQL("INSERT INTO {table} VALUES ({uid}, {wid}, %s, NOW(), %s, %s);").format(
            table=sql.Identifier(TABLE_USER_WORD_PROGRESS),
            uid=sql.Literal(user_id),
            wid=sql.Literal(word_id)
        )
        if self._safe_execute(query, (quized, new_star_status, priority,)):
            self._safe_commit()
            return True
        self._safe_rollback()
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
                # Search word doesn't care about user' specifics, use empty {}
                if parse_dict:
                    res.append(self._parse_word_dict(instance, {}))
                else:
                    res.append(self._parse_word(instance, {}))
        return res
    
    def get_exact_word(self, user_id: int = None, word_id: int = None, parse_dict: bool = False) -> Word | dict:
        """
        Query a word by word ID and user ID (to get star) in DB.

        Input:
        - user_id: the user ID.
        - word_id: the word ID.
        - parse_dict: true to parse to dict, false to parse to class Word. Default: false.
        """
        if not word_id:
            return None
        
        # Get user related fields: star, quized, priority
        user_progress = {}
        query = sql.SQL("""SELECT star, quized, priority FROM {table} 
                        WHERE user_id = {uid} AND word_id = {wid};""").format(
            table=sql.Identifier(TABLE_USER_WORD_PROGRESS),
            uid=sql.Literal(user_id),
            wid=sql.Literal(word_id)
        )
        if self._safe_execute(query):
            row = self._cursor.fetchone()
            if row:
                user_progress = row

        # Get word fields
        query = sql.SQL("""SELECT * FROM {table} WHERE id = {wid};""").format(
            table=sql.Identifier(TABLE_WORDS),
            wid=sql.Literal(word_id)
        )
        if self._safe_execute(query):
            res = self._cursor.fetchone()
            if res:
                if parse_dict:
                    return self._parse_word_dict(res, user_progress)
                else:
                    return self._parse_word(res, user_progress)
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
                # Search word doesn't care about user' specifics, use empty {}
                if parse_dict:
                    res.append(self._parse_word_dict(instance, {}))
                else:
                    res.append(self._parse_word(instance, {}))
        return res
    
    def get_word_occurence(self, word_id: int = None, word: str = "") -> Tuple[int, int]:
        """
        Get a word's 'id' and 'occurrence' (use either `word_id` or exact `word`).
        Return (0, 0) if not found.
        """
        if not word_id and not word:
            return (0, 0)
        
        query = sql.SQL("SELECT id, occurrence FROM {table}").format(
            table=sql.Identifier(TABLE_WORDS)
        )
        if word_id:
            query += sql.SQL(" WHERE id = {wid};").format(
                wid=sql.Literal(word_id)
            )
            params = []
        else:
            query += sql.SQL(" WHERE word = %s;")
            params = [word]
        if self._safe_execute(query, params):
            res = self._cursor.fetchone()
            if res:
                return (res.get("id", 0), res.get("occurrence", 0))
        return (0, 0)
    
    def get_user_word_quized(self, user_id: int, word_id: int = None) -> int:
        """
        Get a word's 'quized' by `user_id` and `word_id`, 0 if not found.
        """
        if not word_id:
            return 0
        
        query = sql.SQL("""SELECT quized FROM {table} 
                        WHERE user_id = {uid} AND word_id = {wid};""").format(
            table=sql.Identifier(TABLE_USER_WORD_PROGRESS),
            uid=sql.Literal(user_id),
            wid=sql.Literal(word_id)
        )
        if self._safe_execute(query):
            res = self._cursor.fetchone()
            if res:
                return res.get("quized", 0)
        return 0
    
    def list_words(self, user_id: int = None, jlpt_level: str = "", star: bool = False, limit: int = DEFAULT_LIMIT, offset: int = 0) -> List[dict]:
        """
        Query 'words' table to get a list of JP words and its 1st EN meaning, sort by `id`.

        Input:
        - user_id: user specific (for `star`)
        - jlpt_level: the JLPT level (N0 - for non-categorized, N5, N4, N3, N2, N1).
        - star: get only the starred words.
        - limit: the amount of return records, if <= 0, use default value of 10.
        - offset: skip the first X records.

        Output: a list of word (id, word, spelling, senses, star, priority)
        """
        res: list = []
        if limit < 1:
            limit = DEFAULT_LIMIT
        
        # Get user' specifics
        user_progress = {}
        query = sql.SQL("""SELECT word_id, star, quized, priority 
                        FROM {table} WHERE user_id = {uid}""").format(
            table=sql.Identifier(TABLE_USER_WORD_PROGRESS),
            uid=sql.Literal(user_id)
        )
        if star:
            query += sql.SQL(" AND star = true")
        if self._safe_execute(query):
            for instance in self._cursor.fetchall():
                user_progress[instance.get("word_id", 0)] = {
                    "star": instance.get("star"),
                    "quized": instance.get("quized"),
                    "priority": instance.get("priority")
                }

        params = []
        query = sql.SQL("SELECT * FROM {table}").format(
            table=sql.Identifier(TABLE_WORDS)
        )
        if jlpt_level:
            jlpt_level = jlpt_level.upper()
            query += sql.SQL(" WHERE jlpt_level = %s")
            params.append(jlpt_level)

        query += sql.SQL(" ORDER BY id OFFSET {offset} LIMIT {limit};").format(
            offset=sql.Literal(offset),
            limit=sql.Literal(limit)
        )
        if self._safe_execute(query, params):
            for instance in self._cursor.fetchall():
                instance["senses"] = self._extract_meanings(instance["senses"])[0]
                res.append(self._parse_word_dict(
                    instance, user_progress.get(instance.get("id", None), {})
                ))
        return res

    def count_words(self, user_id: int = 0, jlpt_level: str = "", star: bool = False) -> int:
        """Count words in table (with filters)"""
        if star and not user_id:
            return 0
        
        params = []
        res = 0
        query = sql.SQL("SELECT COUNT(a.id) FROM {table1} AS a").format(
            table1=sql.Identifier(TABLE_WORDS)
        )

        where_clauses = []
        if star:
            query += sql.SQL(" JOIN {table2} AS b ON b.word_id = a.id").format(
                table2=sql.Identifier(TABLE_USER_WORD_PROGRESS)
            )
            where_clauses.append(
                sql.SQL("b.user_id = {uid}").format(uid=sql.Literal(user_id))
            )
            where_clauses.append(sql.SQL("b.star = true"))
        if jlpt_level:
            jlpt_level = jlpt_level.upper()
            where_clauses.append(sql.SQL("a.jlpt_level = %s"))
            params.append(jlpt_level)
        if where_clauses:
            query = query + sql.SQL(" WHERE ") + sql.SQL(" AND ").join(where_clauses)

        if self._safe_execute(query, params):
            res = self._cursor.fetchone()["count"]
        return res
   
    def _collect_word_decrements(self, sen_id: int, word_decrements: dict) -> bool:
        """
        Get all word IDs in a sentence and add them to the decrement tracking dict.
        Results are saved into `word_decrements`.
        """
        if not sen_id:
            return False
        
        query = sql.SQL("SELECT word_id FROM {table} WHERE sentence_id = {sid}").format(
            table=sql.Identifier(TABLE_WORD_SENTENCE_REF),
            sid=sql.Literal(sen_id)
        )
        if not self._safe_execute(query):
            return False
        for item in self._cursor.fetchall():
            word_id = item["word_id"]
            word_decrements[word_id] = word_decrements.get(word_id, 0) + 1
        return True
    
    def _decrement_word_occurrence(self, word_id: int = None, decrement_count: int = 0) -> bool:
        """
        Decrement word occurrence by `decrement_count`.
        Deletes the word if new count = 0.
        """
        if not word_id or not decrement_count:
            return False

        # Get the words count
        query = sql.SQL("SELECT occurrence FROM {table} WHERE id = {wid}").format(
            table=sql.Identifier(TABLE_WORDS),
            wid=sql.Literal(word_id)
        )
        if not self._safe_execute(query):
            return False
        
        # Update count - 1 if has more than 1
        word_count = self._cursor.fetchone()["occurrence"]
        new_count = word_count - decrement_count

        if new_count > 0:
            query = sql.SQL("UPDATE {table} SET occurrence = {new_count} WHERE id = {wid};").format(
                table=sql.Identifier(TABLE_WORDS),
                new_count=sql.Literal(new_count),
                wid=sql.Literal(word_id)
            )
            # Trade off: either re-calc all user word priority here or just leave it to the next time they quiz
            # it will update after the quiz. On the user side, will seemingly see no difference.
        else:
            # if new_count = 0 --> delete user progress for this word ID
            query_del_progress = sql.SQL("DELETE FROM {table} WHERE word_id = {wid};").format(
                table=sql.Identifier(TABLE_USER_WORD_PROGRESS),
                wid=sql.Literal(word_id)
            )
            if not self._safe_execute(query_del_progress):
                self._safe_rollback()
                return False

            # Delete the word in word table 
            query = sql.SQL("DELETE FROM {table} WHERE id = {wid};").format(
                table=sql.Identifier(TABLE_WORDS),
                wid=sql.Literal(word_id)
            )
        if not self._safe_execute(query):
            self._safe_rollback()
            return False
        
        self._safe_commit()
        return True
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
        The 2 fields 'occurrence' default to 1, 'star' default False.

        Input: the sentence itself

        Output: the inserted sentence ID or the existed sentence ID. 0 if fail.
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
                return res.get("id")

        # Insert
        query = sql.SQL(
            """
            INSERT INTO {table} (sentence, occurrence)
            VALUES (%s, 1) RETURNING id;
            """
        ).format(table=sql.Identifier(TABLE_SENTENCES))
        if self._safe_execute(query, (sentence,)):
            self._safe_commit()
            return self._cursor.fetchone()["id"]
        self._safe_rollback()
        return 0

    def update_sentence_occurence(self, sentence_id: int, new_count: int) -> bool:
        """
        Get a word's occurrence (word must match exact).
        Return true if success, false if fail/not found.

        TODO: Need update when implement quiz sentence
        """
        query = sql.SQL("UPDATE {table} SET occurrence = %s WHERE id = %s;").format(
            table=sql.Identifier(TABLE_SENTENCES)
        )
        if self._safe_execute(query, (new_count, sentence_id,)):
            self._safe_commit()
            return True
        self._safe_rollback()
        return False
    
    def update_sentence_star(self, sentence: str, new_star_status: bool = None) -> bool:
        """
        Update a sentence's star. If specified 'new_star_status', will update to that.
        Otherwise, will query sentence first then update the star to the opposite status.
        Returns True if success, Fail if not found/failed.

        TODO: update when support user starring sentences
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
            self._safe_commit()
            return True
        self._safe_rollback()
        return False

    def get_sentence_occurence(self, sentence: str) -> int:
        """
        Get a sentence's occurrence (must match exact), 0 if not found
        """
        query = sql.SQL("SELECT occurrence FROM {table} WHERE sentence = %s;").format(
            table=sql.Identifier(TABLE_SENTENCES)
        )
        if self._safe_execute(query, (sentence,)):
            res = self._cursor.fetchone()
            if res:
                return res.get("occurrence", 0)
        return 0
    
    def _collect_sentence_decrements(self, book_id: int, sen_decrements: dict) -> bool:
        """
        Get all sentence IDs in a book and add them to the decrement tracking dict.
        Results are saved into `sen_decrements`.
        """
        if not book_id:
            return False
        
        query = sql.SQL("SELECT sentence_id FROM {table} WHERE book_id = {bid}").format(
            table=sql.Identifier(TABLE_SENTENCE_BOOK_REF),
            bid=sql.Literal(book_id)
        )
        if not self._safe_execute(query):
            return False
        for item in self._cursor.fetchall():
            sen_id = item["sentence_id"]
            sen_decrements[sen_id] = sen_decrements.get(sen_id, 0) + 1
        return True
    
    def _decrement_sentece_occurrence(self, sen_id: int = None, decrement_count: int = 0) -> bool:
        if not sen_id or not decrement_count:
            return False

        # Get the sentence count
        query = sql.SQL("SELECT occurrence FROM {table} WHERE id = {sid}").format(
            table=sql.Identifier(TABLE_SENTENCES),
            sid=sql.Literal(sen_id)
        )
        if not self._safe_execute(query):
            return False
        
        # Update count, delete if new count = 0
        new_count = self._cursor.fetchone()["occurrence"] - decrement_count
        if new_count > 0:
            query = sql.SQL("UPDATE {table} SET occurrence = {new_count} WHERE id = {sid}").format(
                table=sql.Identifier(TABLE_SENTENCES),
                new_count=sql.Literal(new_count),
                sid=sql.Literal(sen_id)
            )
        else:
            query = sql.SQL("DELETE FROM {table} WHERE id = {sid}").format(
                table=sql.Identifier(TABLE_SENTENCES),
                sid=sql.Literal(sen_id)
            )
        if not self._safe_execute(query):
            self._safe_rollback()
            return False
        
        self._safe_commit()
        return True
    
    def get_sentences_containing_word_by_id(self, word_id: int = None, limit: int = DEFAULT_LIMIT) -> List[str]:
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
        Uses ON CONFLICT DO NOTHING to silently skip if pair already exists.
        Return true if execution succeeded (whether inserted or already existed).
        Return false only on database error.
        """
        if word_id < 1 or book_id < 1:
            return False
        
        query = sql.SQL("INSERT INTO {table} (word_id, book_id) VALUES (%s, %s) ON CONFLICT DO NOTHING;"
                        ).format(table=sql.Identifier(TABLE_WORD_BOOK_REF))
        if self._safe_execute(query, (word_id, book_id)):
            self._safe_commit()
            return True
        self._safe_rollback()
        return False

    def insert_word_sentence_ref(self, word_id: int, sentence_id: int) -> bool:
        """
        Insert into table `word_sentence` for word and sentence references.
        Uses ON CONFLICT DO NOTHING to silently skip if pair already exists.
        Return true if execution succeeded (whether inserted or already existed).
        Return false only on database error.
        """
        if word_id < 1 or sentence_id < 1:
            return False

        query = sql.SQL("INSERT INTO {table} (word_id, sentence_id) VALUES (%s, %s) ON CONFLICT DO NOTHING;"
                        ).format(table=sql.Identifier(TABLE_WORD_SENTENCE_REF))
        if self._safe_execute(query, (word_id, sentence_id)):
            self._safe_commit()
            return True
        self._safe_rollback()
        return False
    
    def insert_sentence_book_ref(self, sentence_id: int, book_id: int) -> bool:
        """
        Insert into table `sentence_book` for sentence and book references.
        Uses ON CONFLICT DO NOTHING to silently skip if pair already exists.
        Return true if execution succeeded (whether inserted or already existed).
        Return false only on database error.
        """
        if sentence_id < 1 or book_id < 1:
            return False
        
        query = sql.SQL("INSERT INTO {table} (sentence_id, book_id) VALUES (%s, %s) ON CONFLICT DO NOTHING;"
                        ).format(table=sql.Identifier(TABLE_SENTENCE_BOOK_REF))
        if self._safe_execute(query, (sentence_id, book_id)):
            self._safe_commit()
            return True
        self._safe_rollback()
        return False
    # =======================================================================================

    # Quiz ==================================================================================
    def get_quiz(self, user_id: int = None, limit: int = DEFAULT_LIMIT,
                sorts: List[Tuple[str]] = [], jlpt_filter: str = "",
                star_only: bool = False, book_id: int = 0,
                use_priority: bool = True, is_known: bool = False,
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
        - user_id: user ID, used to get priority and/or star value.
        - limit: the number of quiz, default as DEFAULT_LIMIT.
        - sorts: a list of length 2 tuples, i.e.: [ ('col1', 'asc'), ('col2', 'desc') ]. Default: empty.
        Note that the order of this list is important, the smaller indexes will be prioritized when query.
        - jlpt_filter: the JLPT level to filter in query. Default: not use.
        - star_only: query only those that starred. Default: false.
        - book_id: will only query words of this book. Default: query from all books.
        - use_priority: use 'occurrence' and 'quized' to calculate priority or not.
        More 'occurrence' = higher prio, higher 'quized' = lower prio. This can not use together with sort.
        Note that this is refer to the original Japanese word. Default: True.
        - is_known: if true, will only get words that has `priority` <= 0.0 or
        `quized` > QUIZ_HARD_CAP. Default: false.
        - exclude_jp: the list of EN words to not include in query. Default: empty.
        - exclude_en: the list of EN words to not include in query. Default: empty.

        Output: a list of QuizEN objects.
        """
        # Build SQL
        sql_full, params = self._build_sort_filter_prio_sql(user_id, limit, sorts, jlpt_filter, star_only, book_id,
                                                            use_priority, is_known, True, exclude_jp, exclude_en)

        # Query
        q_res = []
        if self._safe_execute(sql_full, params):
            q_res = self._cursor.fetchall()

        # Get words and meanings
        res: List[Quiz] = []
        for row in q_res:
            res.append(self._parse_quiz(row))
        return res

    def update_quized_prio_ts(self, user_id: int = None, word_id: int = None,
                              occurrence: int = None, quized: int = None) -> bool:
        """
        Query `occurrence`, `quized` and `last_tested` (if didn't passed value in, `quized` will +1).
        Calc new `priority` value, formula depends on how big is `quized` compare to QUIZ_SOFT_CAP
        and QUIZ_HARD_CAP. Get current timestamp for last_tested. Save the new values to DB.

        Input:
        - user_id: the user ID.
        - word_id: the word ID.
        - occurrence (optional): the word's occurrence
        - quized (optional): the word's correct quiz count
        If both occurrence and quized are provided, will use these to calculate priority
        without querying the table.

        Output: returns True if success, False if fail
        """
        if word_id is None:
            return False
        
        # Get occurrence and quized if no value
        if occurrence is None or quized is None:
            row = self.get_exact_word(word_id)
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
                        last_tested = NOW()""").format(
            table=sql.Identifier(TABLE_USER_WORD_PROGRESS)
        )
        params = [quized, prio]
        query += sql.SQL(" WHERE user_id = {uid} AND word_id = {wid}").format(
            uid=sql.Literal(user_id),
            wid=sql.Literal(word_id)
        )
        if self._safe_execute(query, params) and self._cursor.rowcount > 0:
            self._safe_commit()
            return True
        self._safe_rollback()
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
        Query an exact word's `senses` column (if no `senses` pass in), get all the meaning out.
        Pass in either `word` or `senses`.
        Senses format example: "to receive,to get, (['Ichidan verb', 'transitive verb']); ...".
        Return example: ["to receive,to get,", "second meaning", ...]
        """
        if not senses and not word:
            return []

        if not senses and word:
            q_res = dict()
            query = sql.SQL("SELECT senses FROM {table} WHERE word = %s;").format(
                table=sql.Identifier(TABLE_WORDS)
            )
            if self._safe_execute(query, (word)):
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
                # will get until the first parenthesis '(' that has at least 1 character before it
                match = WORD_SENSES_REGEX.match(one_sense.strip())
                meaning = ""
                if match:
                    meaning = match.group(1).strip().rstrip(", ")
                    # Keep only the first 2 synonym for each meaning
                    if "," in meaning:
                        meaning = ", ".join(meaning.split(",")[:2])
                
                # Get the entire senses if failed to get the first meaning
                if not meaning:
                    meaning = all_senses
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
    
    def _safe_rollback(self):
        """Rollback only if connection exists and a transaction is active or aborted."""
        if not self._conn:
            return
        try:
            if self._conn.get_transaction_status() != extensions.TRANSACTION_STATUS_IDLE:
                self._conn.rollback()
        except:
            log.exception("safe rollback failed")
    
    def _safe_commit(self):
        """
        Commit only if connection exists and transaction is active and
        we're not inside an outer transaction.
        """
        if not self._conn:
            return
        try:
            # Is a nested commit -> do not actually commit here
            # The outer transaction manager will commit/rollback.
            if self._in_transaction:
                return
            # If not in our transaction wrapper, commit only when a transaction is active
            if self._conn.get_transaction_status() in (extensions.TRANSACTION_STATUS_INTRANS, extensions.TRANSACTION_STATUS_ACTIVE):
                self._conn.commit()
        except Exception:
            log.exception("safe_commit failed")
            raise

    @contextmanager
    def transaction(self):
        """Context manager to perform a multi-step transaction.

        Usage example:
            with db.transaction():
                db.delete_book(...)
        """
        if not self._conn:
            raise RuntimeError("No DB connection")
        # If in transaction (nested) -> yield, will commit/rollback by outermost manager
        outer = self._in_transaction
        try:
            # Mark transaction flag
            self._in_transaction = True
            yield
        except Exception:
            # Called function with this context manager ran into some error -> rollback
            try:
                self._safe_rollback()
            finally:
                self._in_transaction = outer
            raise
        else:
            # Success -> commit (if is outermost <=> don't have `outer`)
            try:
                if not outer and self._conn.get_transaction_status() in (
                extensions.TRANSACTION_STATUS_INTRANS, extensions.TRANSACTION_STATUS_ACTIVE):
                    self._conn.commit()
            finally:
                self._in_transaction = outer
    # =======================================================================================

    # Parsing ===============================================================================
    def _parse_word(self, word: dict, user_progress: dict = {}) -> Word:
        """Parse word dict from query result into Word class"""
        return Word(
            word_id=word.get("id", 0),
            word=word.get("word", ""),
            senses=word.get("senses", ""),
            spelling=word.get("spelling", ""),
            forms=word.get("forms", ""),
            jlpt_level=word.get("jlpt_level", ""),
            audio_mapping=word.get("audio_mapping", []),
            occurrence=word.get("occurrence", 1),
            star=user_progress.get("star", False),
            quized=user_progress.get("quized", 0),
            priority=user_progress.get("priority", 0.0)
        )
    
    def _parse_word_dict(self, word: dict, user_progress: dict) -> dict:
        """Keep the dict form, assure have enough fields, modify in-place and also return"""
        word["word_id"] = word.get("id", 0)
        word["word"] = word.get("word", "")
        word["senses"] = word.get("senses", "")
        word["spelling"] = word.get("spelling", "")
        word["forms"] = word.get("forms", "")
        word["jlpt_level"] = word.get("jlpt_level", "")
        word["audio_mapping"] = word.get("audio_mapping", [])
        word["occurrence"] = word.get("occurrence", 1)
        word["star"] = user_progress.get("star", False)
        word["quized"] = user_progress.get("quized", 0)
        word["priority"] = user_progress.get("priority", 0.0)
        return word

    def _parse_sentence(self, sentence: dict) -> Sentence:
        """Parse sentence dict from query result into Sentence class"""
        return Sentence(
            sen_id=sentence.get("id", 0),
            sentence=sentence.get("sentence", ""),
            star=sentence.get("star"),
            occurrence=sentence.get("occurrence"),
            quized=sentence.get("quized")
        )

    def _parse_book(self, book: dict, star: bool = False) -> Book:
        """Parse book dict from query result into Book class"""
        return Book(
            book_id=book.get("id", 0),
            created_at=book.get("created_at", ""),
            star=star,
            name=book.get("name", ""),
            content=book.get("content", ""),
        )
    
    def _parse_book_dict(self, book: dict, star: bool = False) -> dict:
        """Parse book dict from query result into a dict of Book"""
        book["book_id"] = book.get("id", 0)
        book["created_at"] = book.get("created_at", "")
        book["name"] = book.get("name", "")
        book["star"] = star
        book["content"] = book.get("content", "")
        return book
    
    def _parse_quiz(self, record: dict) -> Quiz:
        """Parse quiz dict from query result into Quiz class"""
        return Quiz(
            word_id = record.get("id", 0),
            jp = record.get("word", ""),
            en = self.get_meanings("", record.get("senses", ""))[0].split(",")[0],
            spelling = record["spelling"],
            jlpt_level = record["jlpt_level"],
            audio_mapping = record["audio_mapping"],
            occurrence = record["occurrence"],
            quized = record["quized"],
            star = record["star"]
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
        A wrapper function, use to calculate priority for a word that has been quized
        and get corrected > QUIZ_SOFT_CAP times
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
    def _build_sort_filter_prio_sql(self, user_id: int, limit: int = DEFAULT_LIMIT, sorts: List[Tuple[str]] = [],
                                    jlpt_filter: str = "", star_only: bool = False,
                                    book_id: int = 0, use_priority: bool = True, 
                                    is_known: bool = False, avoid_dash_sense: bool = False,
                                    exclude_jp: List[str] = [], exclude_en: List[str] = []) -> Tuple[sql.SQL, list]:
        """
        Build the SQL to query 'word', 'senses', 'jlpt_level', 'spelling', 'audio_mapping',
        'occurrence', 'quized', 'star' columns with sorts, filters and/or use priority vale.
        Use priority value is just a sort 'priority' DESC.

        Input: (check other params from get_quiz())
        - is_known: will only get words with `priority` <= 0.0 
        or `quized` > QUIZ_HARD_CAP if true. Default: false.
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
        sql_full = sql.SQL("""SELECT w.id, w.word, w.senses, w.jlpt_level, w.spelling,
                           w.audio_mapping, w.occurrence
                           FROM {table1} AS w
                           JOIN {table2} AS b ON w.id = b.word_id""").format(
                               table1=sql.Identifier(TABLE_WORDS)
                            )
        
        # ----- Book Filter ----- Guarantee keyword "WHERE"
        if book_id:
            # Join ref table to limit book_id
            sql_full += sql.SQL(" JOIN {ref_table} AS r ON w.id = r.word_id").format(
                                    ref_table=sql.Identifier(TABLE_WORD_BOOK_REF)
                                )
        
        # Put the user_id condition first to make use of index
        sql_full += sql.SQL(" WHERE b.user_id = {uid}").format(
            uid=sql.Literal(user_id)
        )

        # continue the book condition
        if book_id:
            conditions.append(sql.SQL("r.book_id = {bid}").format(
                bid=sql.Literal(book_id)
            ))
        
        # ----- Filter -----
        if exclude_jp:
            conditions.append(sql.SQL("w.word NOT IN %s"))
            params.append(tuple(exclude_jp))  # tuple so PostgreSQL understands IN clause
        if exclude_en:
            for ex_en in exclude_en:
                conditions.append(sql.SQL("w.senses NOT LIKE %s"))
                params.append(f"%{ex_en}%")
        if jlpt_filter:
            conditions.append(sql.SQL("w.jlpt_level = %s"))
            params.append(jlpt_filter)
        if star_only:
            conditions.append(sql.SQL("w.star = true"))

        # ----- Review known word mode -----
        if is_known:
            conditions.append(sql.SQL("(w.priority <= 0.0 OR w.quized > {hard_cap})").format(
                hard_cap=sql.Literal(QUIZ_HARD_CAP)
            ))
        else:
            conditions.append(sql.SQL("w.priority > 0.0"))

        # Avoid word with senses that have '-'
        if avoid_dash_sense:
            conditions.append(sql.SQL("w.senses NOT LIKE %s"))
            params.append("%-%")

        # Combine conditions
        if conditions:
            sql_full = sql_full + sql.SQL(" AND ") + sql.SQL(" AND ").join(conditions)
        
        # ----- Sort & Prio -----
        conditions.clear()  # clear condition for sort
        if sorts and not use_priority:
            order_parts = [
                sql.Identifier(col) + sql.SQL(f" {direction}")
                for col, direction in sorts
            ]
            conditions.append(sql.SQL(" ORDER BY w.{order}").format(
                order=sql.SQL(", w.").join(order_parts)
            ))
        elif not sorts and use_priority:
            # sort by priority instead
            conditions.append(sql.SQL(" ORDER BY w.priority DESC"))
        elif not sorts and not use_priority:
            # nothing specified, use `last_tested`
            conditions.append(sql.SQL(" ORDER BY w.last_tested ASC"))
        else:
            log.error("Can not use sort and priority value at the same time")
            return None, []
        
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
            self._safe_commit()
            return True
        self._safe_rollback()
        return False
    # =======================================================================================


    async def get_user_word_progress(self, user_id, word_id):
        # Try to get existing progress
        progress = await self._safe_execute(
            "SELECT * FROM user_word_progress WHERE user_id=$1 AND word_id=$2",
            user_id, word_id
        )
        
        if not progress:
            # Return default/empty progress (don't create row yet)
            return {
                'quized': 0,
                'star': False,
                'priority': 0,
                'last_tested': None
            }
        return progress

    async def quiz_word(self, user_id, word_id, is_correct):
        # Insert OR UPDATE
        await self._safe_execute(
            """
            INSERT INTO user_word_progress (user_id, word_id, quized, last_tested)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT(user_id, word_id) DO UPDATE
            SET quized = user_word_progress.quized + $3, last_tested = NOW()
            """,
            user_id, word_id, 1 if is_correct else -1
        )



    def truncate_all_tables(self) -> None:
        """USE FOR TEST ONLY"""
        with open("data/sql/truncate_all_tables.sql", "r", encoding="utf-8") as f:
            sql_script = f.read()
        self._cursor.execute(sql_script)

    def drop_database(self) -> None:
        """USE FOR TEST ONLY"""
        self._cursor.execute("DROP DATABASE IF EXISTS %s;", (self._dbname,))
        self._cursor.execute("CREATE DATABASE IF NOT EXISTS %s;", (self._dbname,))
