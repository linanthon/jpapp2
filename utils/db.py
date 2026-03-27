from contextlib import asynccontextmanager
import contextvars
import math
import os
import re
import asyncpg
from typing import List, Tuple, Dict

from app.web.handlers.config import DB_HOST, DB_PORT
from utils.logger import get_logger
from schemas.book import Book
from schemas.constants import (TABLE_WORDS, TABLE_BOOKS, TABLE_SENTENCES, TABLE_WORD_BOOK_REF,
                              TABLE_WORD_SENTENCE_REF, TABLE_SENTENCE_BOOK_REF, DB_NAME,
                              SQL_TABLE_SCRIPT, DEFAULT_LIMIT, SQL_WORD_PRIO_SCRIPT, TABLE_USER,
                              DEFAULT_FORMULA_K, DEFAULT_TIME_EXPODECAY, QUIZ_WORD_SORT_COLUMNS,
                              WORD_SENSES_REGEX, QUIZ_SOFT_CAP, QUIZ_HARD_CAP, DEFAULT_MULTI_PENALTY,
                              DEFAULT_DISTRACTOR_COUNT, TABLE_USER_WORD_PROGRESS, TABLE_USER_BOOK_STAR)
from schemas.quiz import Quiz
from schemas.sentence import Sentence
from schemas.word import Word

log = get_logger(__file__)


def _record_to_dict(record: asyncpg.Record) -> dict:
    """Convert an asyncpg Record to a plain dict."""
    return dict(record) if record else {}


def _records_to_dicts(records: list) -> List[dict]:
    """Convert a list of asyncpg Records to a list of dicts."""
    return [dict(r) for r in records] if records else []


# Allows transaction per connection (coroutine ok)
_txn_conn_var: contextvars.ContextVar[asyncpg.Connection | None] = contextvars.ContextVar(
    'txn_conn', default=None
)


class DBHandling:
    def __init__(self, db_name: str = DB_NAME):
        """Init DB manage instance, no input"""
        self._pool: asyncpg.Pool = None
        self._dbname = db_name

    async def connect_2_db(self, username: str = "", password: str = "",
                           dbname: str = "", host: str = DB_HOST, port: int = DB_PORT) -> None:
        if username == "" or password == "":
            return -1

        # Create DB
        if dbname and dbname != DB_NAME:
            self._dbname = dbname
        if self._dbname != "postgres":
            admin_conn = await asyncpg.connect(
                database="postgres",
                user=username,
                password=password,
                host=host,
                port=port
            )
            try:
                row = await admin_conn.fetchrow(
                    "SELECT 1 FROM pg_database WHERE datname = $1;", self._dbname
                )
                if not row:
                    try:
                        await admin_conn.execute(f'CREATE DATABASE "{self._dbname}";')
                    except asyncpg.exceptions.DuplicateDatabaseError:
                        pass    # avoid error on race condition when N workers
            finally:
                await admin_conn.close()

        # Create a connection pool to the designated database
        self._pool = await asyncpg.create_pool(
            database=self._dbname,
            user=username,
            password=password,
            host=host,
            port=port,
            min_size=2,
            max_size=10
        )

    async def migrate(self, filename: str = SQL_TABLE_SCRIPT) -> bool:
        """Init all tables from file, including:
        - words: stores words, meaning, spelling, jlpt level, ...
        - books: the literature piece that user input
        - word_books: reference the words and the books containing them
        - word_sentences: reference the words and the sentences containing them
        """
        with open(filename, "r", encoding="utf-8") as f:
            sql_script = f.read()
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(sql_script)
            return True
        except Exception as e:
            log.error(f"Migration failed: {e}")
            return False

    async def close_db(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    # ---- Internal: acquire a connection (transaction-aware) ----
    def _get_conn(self):
        """Return the transaction connection for this coroutine context, or None."""
        return _txn_conn_var.get()

    async def _fetchrow(self, query: str, *args) -> dict | None:
        """Execute query and return a single row as dict, or None."""
        conn = self._get_conn()
        try:
            if conn:
                row = await conn.fetchrow(query, *args)
            else:
                async with self._pool.acquire() as c:
                    row = await c.fetchrow(query, *args)
            return _record_to_dict(row) if row else None
        except Exception as e:
            log.error(f"Query failed: {query}, error: {e}")
            return None

    async def _fetch(self, query: str, *args) -> List[dict]:
        """Execute query and return all rows as list of dicts."""
        conn = self._get_conn()
        try:
            if conn:
                rows = await conn.fetch(query, *args)
            else:
                async with self._pool.acquire() as c:
                    rows = await c.fetch(query, *args)
            return _records_to_dicts(rows)
        except Exception as e:
            log.error(f"Query failed: {query}, error: {e}")
            return []

    async def _execute(self, query: str, *args) -> str | None:
        """Execute a query (INSERT/UPDATE/DELETE) and return the status string, or None on error."""
        conn = self._get_conn()
        try:
            if conn:
                return await conn.execute(query, *args)
            else:
                async with self._pool.acquire() as c:
                    return await c.execute(query, *args)
        except Exception as e:
            log.error(f"Query failed: {query}, error: {e}")
            return None

    @asynccontextmanager
    async def transaction(self):
        """Context manager to perform a multi-step transaction.

        Usage example:
            async with db.transaction():
                await db.delete_book(...)

        Nested calls automatically use a savepoint so only the inner block
        rolls back on failure, leaving the outer transaction intact.
        """
        if not self._pool:
            raise RuntimeError("No DB connection")
        conn = _txn_conn_var.get()
        if conn is not None:
            # Already inside a transaction: use a savepoint for the nested block
            async with conn.transaction():
                yield
            return
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                token = _txn_conn_var.set(conn)
                try:
                    yield
                finally:
                    _txn_conn_var.reset(token)

    # User ==================================================================================
    async def create_user(self, username: str, email: str, password_hash: str, is_admin: bool = False) -> int:
        """
        Create a new user in the database.

        Input:
        - username: Username (must be unique)
        - email: Email address (must be unique)
        - password_hash: Hashed password
        - is_admin: Whether user is admin (default False)

        Output: User ID if successful, -1 if failed
        """
        row = await self._fetchrow(
            f"""INSERT INTO {TABLE_USER} (username, email, password_hash, is_admin, created_at, modified_at)
            VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) RETURNING id;""",
            username, email, password_hash, is_admin
        )
        return row["id"] if row else -1

    async def get_user_by_id(self, user_id: int) -> dict | None:
        """
        Get user by ID (without password_hash).

        Output: User dict or None if not found.
        """
        return await self._fetchrow(
            f"SELECT id, username, email, is_admin, created_at FROM {TABLE_USER} WHERE id = $1;",
            user_id
        )

    async def get_user_by_username(self, username: str) -> dict | None:
        """
        Get user by username (includes password_hash for auth).

        Output: User dict (including password_hash) or None if not found.
        """
        return await self._fetchrow(
            f"SELECT id, username, email, password_hash, is_admin, created_at FROM {TABLE_USER} WHERE username = $1;",
            username
        )

    async def user_exists(self, username: str) -> bool:
        """Check if username exists"""
        row = await self._fetchrow(
            f"SELECT COUNT(*) as count FROM {TABLE_USER} WHERE username = $1;", username
        )
        return row["count"] > 0 if row else False

    async def user_exists_by_email(self, email: str) -> bool:
        """Check if email exists"""
        row = await self._fetchrow(
            "SELECT COUNT(*) as count FROM users WHERE email = $1;", email
        )
        return row["count"] > 0 if row else False

    # Book ==================================================================================
    async def insert_book(self, filename: str, content: str = "") -> int:
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
        row = await self._fetchrow(
            f"SELECT COUNT(*) FROM {TABLE_BOOKS} WHERE name = $1;", bookname
        )
        if row and row["count"]:
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
        row = await self._fetchrow(
            f"INSERT INTO {TABLE_BOOKS} (name, content) VALUES ($1, $2) RETURNING id;",
            bookname, content
        )
        return row["id"] if row else -1

    async def update_book(self, book_id: int = 0, name: str = "", append_content: str = "") -> bool:
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

        if book_id:
            status = await self._execute(
                f"UPDATE {TABLE_BOOKS} SET content = COALESCE(content, '') || $1 WHERE id = $2;",
                append_content, book_id
            )
        else:
            status = await self._execute(
                f"UPDATE {TABLE_BOOKS} SET content = COALESCE(content, '') || $1 WHERE name = $2;",
                append_content, name
            )
        return status is not None

    async def get_exact_book(self, user_id: int = None, book_id: int = None, parse_dict: bool = False) -> Book | dict:
        """
        Query a book with the exact name or its ID.
        Returns the row of that book, empty dict if fail to get.
        """
        if not book_id:
            return None if parse_dict else Book()

        # Check if is starred by user
        is_star = False
        row = await self._fetchrow(
            f"SELECT book_id FROM {TABLE_USER_BOOK_STAR} WHERE user_id = $1 AND star = true;",
            user_id
        )
        if row:
            is_star = True

        # get the book
        row = await self._fetchrow(
            f"SELECT id, created_at, name, content FROM {TABLE_BOOKS} WHERE id = $1;",
            book_id
        )
        if row:
            if parse_dict:
                return self._parse_book_dict(row, is_star)
            else:
                return self._parse_book(row, is_star)
        return None

    async def list_books(self, user_id: int = None, star: bool = False,
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

            star_rows = await self._fetch(
                f"SELECT book_id FROM {TABLE_USER_BOOK_STAR} WHERE user_id = $1 AND star = true;",
                user_id
            )
            for instance in star_rows:
                book_star_ids.add(instance.get("book_id", 0))

        if limit is None:
            rows = await self._fetch(
                f"SELECT id, name, created_at FROM {TABLE_BOOKS} ORDER BY id OFFSET $1;",
                offset
            )
        else:
            if limit < 1:
                limit = DEFAULT_LIMIT
            rows = await self._fetch(
                f"SELECT id, name, created_at FROM {TABLE_BOOKS} ORDER BY id OFFSET $1 LIMIT $2;",
                offset, limit
            )

        res = []
        for instance in rows:
            res.append(self._parse_book_dict(
                instance, instance.get("id", 0) in book_star_ids
            ))
        return res

    async def count_books(self, star: bool = False) -> int:
        """Count books in table (with filters)"""
        if star:
            row = await self._fetchrow(
                f"SELECT COUNT(id) FROM {TABLE_BOOKS} WHERE star = true"
            )
        else:
            row = await self._fetchrow(
                f"SELECT COUNT(id) FROM {TABLE_BOOKS}"
            )
        return row["count"] if row else 0

    async def update_book_star(self, user_id: int = None, book_id: int = None,
                               new_star_status: bool = None) -> bool:
        """
        Update a book's star. If specified 'new_star_status', will update to that.
        Returns True if success, Fail if not found/failed.
        """
        if not book_id or new_star_status is None:
            return False

        status = await self._execute(
            f"UPDATE {TABLE_USER_BOOK_STAR} SET star = $1 WHERE user_id = $2 AND book_id = $3;",
            new_star_status, user_id, book_id
        )
        if status and self._get_rowcount(status) > 0:
            return True
        return False

    async def delete_book(self, book_id: int = None) -> bool:
        """Remove book by name (exact match) or id, will also remove all
        its sentences and words. If those sentences/words have duplicate in another book,
        reduce their counts instead. Return true if success, otherwise false.
        """
        if not book_id:
            return False

        # Get all its sentence IDs
        rows = await self._fetch(
            f"SELECT sentence_id FROM {TABLE_SENTENCE_BOOK_REF} WHERE book_id = $1",
            book_id
        )
        sentence_ids = [item["sentence_id"] for item in rows]

        # Track words and sentences decrement to commit properly
        word_decrements = {}
        sen_decrements = {}

        # Get all sentences from ref table to know how much we need to reduce its occurrence
        # Get before delete book to not lost ref
        # Get all words from ref table for the same reason
        if not await self._collect_object_decrements([book_id], "sentence_id", TABLE_SENTENCE_BOOK_REF, "book_id", sen_decrements) or \
            not await self._collect_object_decrements(sentence_ids, "word_id", TABLE_WORD_SENTENCE_REF, "sentence_id", word_decrements):
            return False

        # Now delete book (this will cascade and delete sentence_book, word_book and user_book_star refs)
        status = await self._execute(
            f"DELETE FROM {TABLE_BOOKS} WHERE id = $1", book_id
        )
        if not status:
            return False

        # Decrease count/Delete sentences (cascade delete word_sentence ref)
        # Decrease count/Delete words (cascade delete user_word_progress ref)
        if not await self._decrement_object_occurrence(sen_decrements, TABLE_SENTENCES) or \
            not await self._decrement_object_occurrence(word_decrements, TABLE_WORDS):
            return False

        return True

    # =======================================================================================

    # Word ==================================================================================
    async def insert_word(self, word: Word) -> int:
        """
        Insert into table `words` (if not in DB yet).

        Input: a Word that must contains the following fields:
        word, senses, spelling, forms, jlpt_level, audio.
        The other 4 fields: 'occurrence'=1, 'quized'=0, 'star'=false, 'priority'=1

        Output: the inserted word ID or existed word ID.
        """
        # Check if exist, return id
        row = await self._fetchrow(
            f"SELECT id FROM {TABLE_WORDS} WHERE word = $1;", word.word
        )
        if row:
            return row.get("id", 0)

        # Insert
        row = await self._fetchrow(
            f"""INSERT INTO {TABLE_WORDS} (word, senses, spelling, forms,
                occurrence, jlpt_level, audio_mapping)
            VALUES ($1, $2, $3, $4, 1, $5, $6) RETURNING id;""",
            word.word, word.senses, word.spelling,
            word.forms, word.jlpt_level, word.audio_mapping
        )
        if row:
            return row.get("id", 0)
        return 0

    async def update_word_occurrence(self, word: str, user_ids: list = []) -> bool:
        """
        Update a word's occurrence (word must match exact) in word table and
        priority using priority formula in the user word progress table (if input user_id).
        Return true if success, false if fail/not found.
        """
        # Get word occurrence
        word_id, occurrence = await self.get_word_occurence(word=word)
        if occurrence == 0:
            return False

        async with self.transaction():
            # Update word occurrence
            status = await self._execute(
                f"UPDATE {TABLE_WORDS} SET occurrence = $1 WHERE id = $2;",
                occurrence, word_id
            )
            if not status:
                return False

            # Get quized and calc priority
            if user_ids:
                for user_id in user_ids:
                    quized = await self.get_user_word_quized(user_id, word_id)
                    priority = self._priority_formula(occurrence, quized)
                    status = await self._execute(
                        f"UPDATE {TABLE_USER_WORD_PROGRESS} SET priority = $1 WHERE user_id = $2 AND word_id = $3;",
                        priority, user_id, word_id
                    )
                    if not status:
                        return False

        return True

    #TODO: currently not used, remove?
    async def update_word_jlpt(self, word: str, new_jlpt_level: str) -> bool:
        """
        Update a word's jlpt level (word must match exact).
        Return true if success, false if fail/not found (update 0 row).
        """
        status = await self._execute(
            f"UPDATE {TABLE_WORDS} SET jlpt_level = $1 WHERE word = $2;",
            new_jlpt_level, word
        )
        if status and self._get_rowcount(status) > 0:
            return True
        return False

    async def update_words_known(self, user_id: int, word_ids: List[int] = []) -> bool:
        """Update words priority to -1.0 (to fail the > 0.0 check when query for quiz).
        Returns True if success, False if fail."""
        if not user_id or not word_ids:
            return False

        # asyncpg doesn't support IN with tuple, use ANY($1) with a list instead
        status = await self._execute(
            f"UPDATE {TABLE_USER_WORD_PROGRESS} SET priority = -1.0 WHERE user_id = $1 AND word_id = ANY($2);",
            user_id, word_ids
        )
        if status and self._get_rowcount(status) > 0:
            return True
        return False

    async def update_word_star(self, user_id: int, word_id: int, new_star_status: bool = None) -> bool:
        """
        Update a word's star. If specified 'new_star_status', will update to that.
        Returns True if success, Fail if not found/failed.
        """
        if not user_id or not word_id or new_star_status is None:
            return False

        # Update star
        status = await self._execute(
            f"UPDATE {TABLE_USER_WORD_PROGRESS} SET star = $1 WHERE user_id = $2 AND word_id = $3;",
            new_star_status, user_id, word_id
        )
        if status and self._get_rowcount(status) > 0:
            return True

        if status is None:
            return False

        # Reach here = no update = need insert new row
        # Get word occurrence
        _, occurrence = await self.get_word_occurence(word_id)
        if not occurrence:
            return False
        quized = 0  # insert here = never quized before
        priority = self._priority_formula(occurrence, quized)

        # Write
        status = await self._execute(
            f"INSERT INTO {TABLE_USER_WORD_PROGRESS} VALUES ($1, $2, $3, NOW(), $4, $5);",
            user_id, word_id, quized, new_star_status, priority
        )
        return status is not None

    async def query_like_word(self, word: str, limit: int = DEFAULT_LIMIT, parse_dict: bool = False) -> List[Word] | List[dict]:
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
        rows = await self._fetch(
            f"SELECT * FROM {TABLE_WORDS} WHERE word LIKE $1 LIMIT $2;",
            f"%{word}%", limit
        )
        for instance in rows:
            # Search word doesn't care about user' specifics, use empty {}
            if parse_dict:
                res.append(self._parse_word_dict(instance, {}))
            else:
                res.append(self._parse_word(instance, {}))
        return res

    async def get_exact_word(self, user_id: int = None, word_id: int = None, parse_dict: bool = False) -> Word | dict:
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
        if user_id is not None:
            row = await self._fetchrow(
                f"SELECT star, quized, priority FROM {TABLE_USER_WORD_PROGRESS} WHERE user_id = $1 AND word_id = $2;",
                user_id, word_id
            )
            if row:
                user_progress = row

        # Get word fields
        row = await self._fetchrow(
            f"SELECT * FROM {TABLE_WORDS} WHERE id = $1;", word_id
        )
        if row:
            if parse_dict:
                return self._parse_word_dict(row, user_progress)
            else:
                return self._parse_word(row, user_progress)
        return None

    async def query_word_sense(self, sense: str, limit: int = DEFAULT_LIMIT, parse_dict: bool = False) -> List[Word] | List[dict]:
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
        sense_q = f"%{sense.lower()}%"
        rows = await self._fetch(
            f"""SELECT *, POSITION($1 IN LOWER(senses)) AS match_pos
                FROM {TABLE_WORDS} WHERE LOWER(senses) LIKE $2
                ORDER BY match_pos LIMIT $3;""",
            sense_q, sense_q, limit
        )
        for instance in rows:
            # Search word doesn't care about user' specifics, use empty {}
            if parse_dict:
                res.append(self._parse_word_dict(instance, {}))
            else:
                res.append(self._parse_word(instance, {}))
        return res

    async def get_word_occurence(self, word_id: int = None, word: str = "") -> Tuple[int, int]:
        """
        Get a word's 'id' and 'occurrence' (use either `word_id` or exact `word`).
        Return (0, 0) if not found.
        """
        if not word_id and not word:
            return (0, 0)

        if word_id:
            row = await self._fetchrow(
                f"SELECT id, occurrence FROM {TABLE_WORDS} WHERE id = $1;", word_id
            )
        else:
            row = await self._fetchrow(
                f"SELECT id, occurrence FROM {TABLE_WORDS} WHERE word = $1;", word
            )
        if row:
            return (row.get("id", 0), row.get("occurrence", 0))
        return (0, 0)

    async def get_user_word_quized(self, user_id: int, word_id: int = None) -> int:
        """
        Get a word's 'quized' by `user_id` and `word_id`, 0 if not found.
        """
        if not word_id:
            return 0

        row = await self._fetchrow(
            f"SELECT quized FROM {TABLE_USER_WORD_PROGRESS} WHERE user_id = $1 AND word_id = $2;",
            user_id, word_id
        )
        if row:
            return row.get("quized", 0)
        return 0

    async def list_words(self, user_id: int = None, jlpt_level: str = "", star: bool = False,
                         limit: int = DEFAULT_LIMIT, offset: int = 0) -> List[dict]:
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
        if star:
            progress_rows = await self._fetch(
                f"SELECT word_id, star, quized, priority FROM {TABLE_USER_WORD_PROGRESS} WHERE user_id = $1 AND star = true;",
                user_id
            )
        else:
            progress_rows = await self._fetch(
                f"SELECT word_id, star, quized, priority FROM {TABLE_USER_WORD_PROGRESS} WHERE user_id = $1;",
                user_id
            )
        for instance in progress_rows:
            user_progress[instance.get("word_id", 0)] = {
                "star": instance.get("star"),
                "quized": instance.get("quized"),
                "priority": instance.get("priority")
            }

        if jlpt_level:
            jlpt_level = jlpt_level.upper()
            rows = await self._fetch(
                f"SELECT * FROM {TABLE_WORDS} WHERE jlpt_level = $1 ORDER BY id OFFSET $2 LIMIT $3;",
                jlpt_level, offset, limit
            )
        else:
            rows = await self._fetch(
                f"SELECT * FROM {TABLE_WORDS} ORDER BY id OFFSET $1 LIMIT $2;",
                offset, limit
            )

        for instance in rows:
            instance["senses"] = self._extract_meanings(instance["senses"])[0]
            res.append(self._parse_word_dict(
                instance, user_progress.get(instance.get("id", None), {})
            ))
        return res

    async def count_words(self, user_id: int = 0, jlpt_level: str = "", star: bool = False) -> int:
        """Count words in table (with filters)"""
        if star and not user_id:
            return 0

        params = []
        param_idx = 1
        query = f"SELECT COUNT(a.id) FROM {TABLE_WORDS} AS a"
        where_clauses = []

        if star:
            query += f" JOIN {TABLE_USER_WORD_PROGRESS} AS b ON b.word_id = a.id"
            where_clauses.append(f"b.user_id = ${param_idx}")
            params.append(user_id)
            param_idx += 1
            where_clauses.append("b.star = true")
        if jlpt_level:
            jlpt_level = jlpt_level.upper()
            where_clauses.append(f"a.jlpt_level = ${param_idx}")
            params.append(jlpt_level)
            param_idx += 1
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        row = await self._fetchrow(query, *params)
        return row["count"] if row else 0

    async def _collect_object_decrements(self, obj_ids: list, obj_id_col: str, ref_table: str,
                                         target_id_col: str, obj_decrements: dict) -> bool:
        """
        Get all wor/sentence IDs of a sentence/book and add them to the decrement tracking dict.
        Results are saved into `obj_decrements`.
        """
        if not obj_ids:
            return False

        rows = await self._fetch(
            f"SELECT {obj_id_col} FROM {ref_table} WHERE {target_id_col} = ANY($1)",
            obj_ids
        )
        for item in rows:
            obj_id = item[obj_id_col]
            obj_decrements[obj_id] = obj_decrements.get(obj_id, 0) + 1
        return True
    
    async def _decrement_object_occurrence(self, obj_decrements: dict, table_name: str) -> bool:
        """
        Decrement word/sentence occurrence. Deletes the word if occurrence - decrement count = 0.

        Input:
        - obj_decrements: key = word/sentence ID, value = decrement count
        - table_name: the word or sentence table name
        """
        if not obj_decrements:
            return False
        
        obj_ids = list(obj_decrements.keys())
        decrements = list(obj_decrements.values())

        await self._execute(
            f"""DELETE FROM {table_name}
                USING unnest($1::int[], $2::int[]) AS d(wid, dec)
                WHERE {table_name}.id = d.wid
                AND {table_name}.occurrence - d.dec <= 0""",
            obj_ids, decrements
        )

        # Update the rest
        status = await self._execute(
            f"""UPDATE {table_name} SET occurrence = {table_name}.occurrence - d.dec
                FROM unnest($1::int[], $2::int[]) AS d(sid, dec)
                WHERE {table_name}.id = d.sid
                AND {table_name}.occurrence - d.dec > 0""",
            obj_ids, decrements
        )

        return status is not None
    # =======================================================================================

    # Sentence ==============================================================================
    async def query_like_sentence(self, sentence: str, limit: int = DEFAULT_LIMIT) -> List[Sentence]:
        """
        Query sentence in DB, will return a list of all sentences that are `LIKE '%sentence%'`

        Input:
        - sentence: the sentence to be query %sentence%
        - limit: the amount of return records, if <= 0, use default value of 10.
        """
        if limit < 1:
            limit = DEFAULT_LIMIT
        res: List[Sentence] = []
        rows = await self._fetch(
            f"SELECT * FROM {TABLE_SENTENCES} WHERE sentence LIKE $1 LIMIT $2;",
            f"%{sentence}%", limit
        )
        for instance in rows:
            res.append(self._parse_sentence(instance))
        return res

    async def query_random_sentences(self, limit: int = DEFAULT_LIMIT, exclude: List[str] = []) -> List[Sentence]:
        """
        Query a number of sentences randomly. Returns a list of parsed Sentence_s.

        Input:
        - limit: the amount of return records, if <= 0, use default value of 10.
        - exclude: the list of sentences to ignore
        """
        res: List[Sentence] = []
        if exclude:
            rows = await self._fetch(
                f"SELECT * FROM {TABLE_SENTENCES} WHERE sentence != ALL($1) LIMIT $2;",
                exclude, limit
            )
        else:
            rows = await self._fetch(
                f"SELECT * FROM {TABLE_SENTENCES} LIMIT $1;", limit
            )
        for sen in rows:
            res.append(self._parse_sentence(sen))
        return res

    async def get_exact_sentence(self, sentence: str) -> dict:
        """
        Query a sentence in DB, will return a sentence that is `= 'sentence'`
        """
        row = await self._fetchrow(
            f"SELECT * FROM {TABLE_SENTENCES} WHERE sentence = $1;", sentence
        )
        return row if row else {}

    async def insert_update_sentence(self, sentence: str) -> int:
        """
        Insert into table `sentences`, will update occurrence if sentence existed.
        The 2 fields 'occurrence' default to 1, 'star' default False.

        Input: the sentence itself

        Output: the inserted sentence ID or the existed sentence ID. 0 if fail.
        """
        # Check exist -> up occurrence
        row = await self._fetchrow(
            f"SELECT id, occurrence FROM {TABLE_SENTENCES} WHERE sentence = $1;",
            sentence
        )
        if row:
            await self.update_sentence_occurence(row.get("id"), row.get("occurrence") + 1)
            return row.get("id")

        # Insert
        row = await self._fetchrow(
            f"INSERT INTO {TABLE_SENTENCES} (sentence, occurrence) VALUES ($1, 1) RETURNING id;",
            sentence
        )
        return row["id"] if row else 0

    async def update_sentence_occurence(self, sentence_id: int, new_count: int) -> bool:
        """
        Update a sentence's occurrence.
        Return true if success, false if fail/not found.

        TODO: Need update when implement quiz sentence
        """
        status = await self._execute(
            f"UPDATE {TABLE_SENTENCES} SET occurrence = $1 WHERE id = $2;",
            new_count, sentence_id
        )
        return status is not None

    async def update_sentence_star(self, sentence: str, new_star_status: bool = None) -> bool:
        """
        Update a sentence's star. If specified 'new_star_status', will update to that.
        Otherwise, will query sentence first then update the star to the opposite status.
        Returns True if success, Fail if not found/failed.

        TODO: update when support user starring sentences
        """
        if not new_star_status:
            row = await self._fetchrow(
                f"SELECT star FROM {TABLE_SENTENCES} WHERE sentence = $1;", sentence
            )
            if row:
                db_star = row.get("star", False)
                new_star_status = False if db_star else True

        if new_star_status is None:
            log.error(f"Sentence {sentence} not found")
            return False

        status = await self._execute(
            f"UPDATE {TABLE_SENTENCES} SET star = $1 WHERE sentence = $2;",
            new_star_status, sentence
        )
        if status and self._get_rowcount(status) > 0:
            return True
        return False

    async def get_sentence_occurence(self, sentence: str) -> int:
        """
        Get a sentence's occurrence (must match exact), 0 if not found
        """
        row = await self._fetchrow(
            f"SELECT occurrence FROM {TABLE_SENTENCES} WHERE sentence = $1;", sentence
        )
        return row.get("occurrence", 0) if row else 0

    async def get_sentences_containing_word_by_id(self, word_id: int = None, limit: int = DEFAULT_LIMIT) -> List[str]:
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
        rows = await self._fetch(
            f"""SELECT s.sentence FROM {TABLE_SENTENCES} s
            JOIN {TABLE_WORD_SENTENCE_REF} ws ON s.id = ws.sentence_id
            WHERE ws.word_id = $1
            ORDER BY RANDOM() LIMIT $2;""",
            word_id, limit
        )
        return [sen["sentence"] for sen in rows if sen.get("sentence", "")]
    # =======================================================================================

    # Insert References =====================================================================
    async def insert_word_book_ref(self, word_id: int, book_id: int) -> bool:
        """
        Insert into table `word_book` for word and book references.
        Uses ON CONFLICT DO NOTHING to silently skip if pair already exists.
        Return true if execution succeeded (whether inserted or already existed).
        Return false only on database error.
        """
        if word_id < 1 or book_id < 1:
            return False

        status = await self._execute(
            f"INSERT INTO {TABLE_WORD_BOOK_REF} (word_id, book_id) VALUES ($1, $2) ON CONFLICT DO NOTHING;",
            word_id, book_id
        )
        return status is not None

    async def insert_word_sentence_ref(self, word_id: int, sentence_id: int) -> bool:
        """
        Insert into table `word_sentence` for word and sentence references.
        Uses ON CONFLICT DO NOTHING to silently skip if pair already exists.
        Return true if execution succeeded (whether inserted or already existed).
        Return false only on database error.
        """
        if word_id < 1 or sentence_id < 1:
            return False

        status = await self._execute(
            f"INSERT INTO {TABLE_WORD_SENTENCE_REF} (word_id, sentence_id) VALUES ($1, $2) ON CONFLICT DO NOTHING;",
            word_id, sentence_id
        )
        return status is not None

    async def insert_sentence_book_ref(self, sentence_id: int, book_id: int) -> bool:
        """
        Insert into table `sentence_book` for sentence and book references.
        Uses ON CONFLICT DO NOTHING to silently skip if pair already exists.
        Return true if execution succeeded (whether inserted or already existed).
        Return false only on database error.
        """
        if sentence_id < 1 or book_id < 1:
            return False

        status = await self._execute(
            f"INSERT INTO {TABLE_SENTENCE_BOOK_REF} (sentence_id, book_id) VALUES ($1, $2) ON CONFLICT DO NOTHING;",
            sentence_id, book_id
        )
        return status is not None
    # =======================================================================================

    # Quiz ==================================================================================
    async def get_quiz(self, user_id: int = None, limit: int = DEFAULT_LIMIT,
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
        sql_full, params = self._build_sort_filter_prio_sql(
            user_id, limit, sorts, jlpt_filter, star_only, book_id,
            use_priority, is_known, True, exclude_jp, exclude_en
        )
        if not sql_full:
            return []

        # Query
        q_res = await self._fetch(sql_full, *params)

        # Get words and meanings
        res: List[Quiz] = []
        for row in q_res:
            res.append(self._parse_quiz(row))
        return res

    async def update_quized_prio_ts(self, user_id: int = None, word_id: int = None,
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
            row = await self.get_exact_word(word_id=word_id)
            if not row:
                return False
            occurrence = row.occurrence
            quized = row.quized + 1

        # Calc priority and update table
        if quized > QUIZ_HARD_CAP:
            prio = 0.0
        elif quized > QUIZ_SOFT_CAP:
            prio = self._priority_softcap_formula(occurrence, quized)
        else:
            prio = self._priority_formula(occurrence, quized)

        status = await self._execute(
            f"""UPDATE {TABLE_USER_WORD_PROGRESS} SET quized = $1, priority = $2,
                last_tested = NOW() WHERE user_id = $3 AND word_id = $4;""",
            quized, prio, user_id, word_id
        )
        if status and self._get_rowcount(status) > 0:
            return True
        return False

    async def get_distractors(self, exclude_jp: str = "", exclude_en: str = "",
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
        rows = await self._fetch(query, *params)
        for row in rows:
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
        Get all meanings from a senses string. Pass in either `word` or `senses`.
        Note: This is kept synchronous since it only parses a string (no DB call needed
        when senses is provided). Use get_meanings_from_db() if you need to look up from DB.
        Senses format example: "to receive,to get, (['Ichidan verb', 'transitive verb']); ...".
        Return example: ["to receive,to get,", "second meaning", ...]
        """
        if not senses and not word:
            return []

        if not senses and word:
            # Caller should use get_meanings_from_db() for DB lookup
            return []

        return self._extract_meanings(senses)

    async def get_meanings_from_db(self, word: str) -> List[str]:
        """Query an exact word's senses from DB then extract meanings."""
        row = await self._fetchrow(
            f"SELECT senses FROM {TABLE_WORDS} WHERE word = $1;", word
        )
        senses = row.get("senses", "") if row else ""
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

    @staticmethod
    def _get_rowcount(status: str) -> int:
        """Extract affected row count from asyncpg status string like 'UPDATE 1' or 'DELETE 3'."""
        if not status:
            return 0
        parts = status.split()
        try:
            return int(parts[-1])
        except (ValueError, IndexError):
            return 0

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
    def _build_sort_filter_prio_sql(self, user_id: int, limit: int = DEFAULT_LIMIT,
                                    sorts: List[Tuple[str]] = [],
                                    jlpt_filter: str = "", star_only: bool = False,
                                    book_id: int = 0, use_priority: bool = True,
                                    is_known: bool = False, avoid_dash_sense: bool = False,
                                    exclude_jp: List[str] = [], exclude_en: List[str] = []) -> Tuple[str, list]:
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
        - Built SQL string with $N placeholders
        - list of params to pass in on query execution
        """
        conditions = []
        params = []
        param_idx = 1

        sql_full = f"""SELECT w.id, w.word, w.senses, w.jlpt_level, w.spelling,
                       w.audio_mapping, w.occurrence, b.quized, b.star
                       FROM {TABLE_WORDS} AS w
                       JOIN {TABLE_USER_WORD_PROGRESS} AS b ON w.id = b.word_id"""

        # ----- Book Filter -----
        if book_id:
            sql_full += f" JOIN {TABLE_WORD_BOOK_REF} AS r ON w.id = r.word_id"

        # Put the user_id condition first to make use of index
        sql_full += f" WHERE b.user_id = ${param_idx}"
        params.append(user_id)
        param_idx += 1

        # continue the book condition
        if book_id:
            conditions.append(f"r.book_id = ${param_idx}")
            params.append(book_id)
            param_idx += 1

        # ----- Filter -----
        if exclude_jp:
            conditions.append(f"w.word != ALL(${param_idx})")
            params.append(exclude_jp)
            param_idx += 1
        if exclude_en:
            for ex_en in exclude_en:
                conditions.append(f"w.senses NOT LIKE ${param_idx}")
                params.append(f"%{ex_en}%")
                param_idx += 1
        if jlpt_filter:
            conditions.append(f"w.jlpt_level = ${param_idx}")
            params.append(jlpt_filter)
            param_idx += 1
        if star_only:
            conditions.append("b.star = true")

        # ----- Review known word mode -----
        if is_known:
            conditions.append(f"(b.priority <= 0.0 OR b.quized > {QUIZ_HARD_CAP})")
        else:
            conditions.append("b.priority > 0.0")

        # Avoid word with senses that have '-'
        if avoid_dash_sense:
            conditions.append(f"w.senses NOT LIKE ${param_idx}")
            params.append("%-%")
            param_idx += 1

        # Combine conditions
        if conditions:
            sql_full += " AND " + " AND ".join(conditions)

        # ----- Sort & Prio -----
        if sorts and not use_priority:
            # Whitelist sort columns and directions to prevent injection
            allowed_cols = set(QUIZ_WORD_SORT_COLUMNS)
            allowed_dirs = {"asc", "desc"}
            order_parts = []
            for col, direction in sorts:
                if col in allowed_cols and direction.lower() in allowed_dirs:
                    order_parts.append(f"w.{col} {direction}")
            if order_parts:
                sql_full += " ORDER BY " + ", ".join(order_parts)
        elif not sorts and use_priority:
            sql_full += " ORDER BY b.priority DESC"
        elif not sorts and not use_priority:
            sql_full += " ORDER BY b.last_tested ASC"
        else:
            log.error("Can not use sort and priority value at the same time")
            return None, []

        # Add count
        sql_full += f" LIMIT ${param_idx};"
        params.append(limit)
        return sql_full, params

    def _build_distractors_sql(self, exclude_jp: str, exclude_en: str = "",
                               limit: int = DEFAULT_DISTRACTOR_COUNT) -> Tuple[str, list]:
        """
        Query `limit` number of 'word' and 'senses' from table words that
        'word' != exclude_jp and 'senses' NOT LIKE '%exclude_en%' (if specified)

        Input:
        - exclude_jp: the JP word in quiz, will query different than this word.
        - exclude_en (optional): the EN/first meaning of the JP word, will query different meaning than this.
        - limit: the number of distractor meanings to query.

        Output: the built sql query and list of params
        """
        params = [exclude_jp, "%-%"]
        param_idx = 3
        query = f"SELECT word, senses FROM {TABLE_WORDS} WHERE word != $1 AND senses NOT LIKE $2"
        if exclude_en:
            query += f" AND senses NOT LIKE ${param_idx}"
            params.append(f"%{exclude_en}%")
            param_idx += 1
        query += f" ORDER BY RANDOM() LIMIT ${param_idx};"
        params.append(limit)
        return (query, params)
    # ----------------------------------

    # Word priority on quiz ========== Leave this alone for now =============================
    def _priority_formula2(self, k: float = 0.5) -> str:
        """
        A wrapping function to calculate word show up priority, if want to change formula,
        just change in this function instead of change it everywhere in this class
        """
        return self._priority_expodecay2(k)

    def _priority_expodecay2(self, k: float = 0.5) -> str:
        """
        The formula SQL, 'occurrence * EXP(-{k} * quized)'

        Input:
        - k: slider for formula
        """
        return f"occurrence * EXP(-{k} * quized)"

    async def refresh_word_priority_view(self, filename: str = SQL_WORD_PRIO_SCRIPT) -> bool:
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
        query = script.format(
            formula=self._priority_formula2(),
            table=TABLE_WORDS
        )
        status = await self._execute(query)
        return status is not None
    # =======================================================================================


    async def truncate_all_tables(self) -> None:
        """USE FOR TEST ONLY"""
        with open("data/sql/truncate_all_tables.sql", "r", encoding="utf-8") as f:
            sql_script = f.read()
        await self._execute(sql_script)

    async def drop_database(self) -> None:
        """USE FOR TEST ONLY"""
        await self._execute(f'DROP DATABASE IF EXISTS "{self._dbname}";')
        await self._execute(f'CREATE DATABASE IF NOT EXISTS "{self._dbname}";')
