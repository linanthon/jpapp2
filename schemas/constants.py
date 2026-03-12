from typing import List
import re

# --- Paths
AUDIO_DIR = "data/audio"
JLPT_DIR = "data/jlpt"
STOPWORD_FILE = "data/stopwords.txt"
SQL_TABLE_SCRIPT = "data/sql/tables.sql"
SQL_WORD_PRIO_SCRIPT = "data/sql/priority_view.sql"

# --- Table names
DB_NAME = "jpapp2"
TABLE_WORDS = "words"
TABLE_BOOKS = "books"
TABLE_SENTENCES = "sentences"
TABLE_WORD_BOOK_REF = "word_book"
TABLE_WORD_SENTENCE_REF = "word_sentence"
TABLE_SENTENCE_BOOK_REF = "sentence_book"
TABLE_USER = "users"
TABLE_USER_WORD_PROGRESS = "user_word_progress"
TABLE_USER_SENTENCE_PROGRESS = "user_sentence_progress"

# --- Defaults
DEFAULT_LIMIT: int = 10
DEFAULT_DISTRACTOR_COUNT: int = 3
DEFAULT_FORMULA_K: float = 0.5      # smaller = higher prior
DEFAULT_TIME_EXPODECAY: float = 5
DEFAULT_MULTI_PENALTY: float = 0.2  # 20% less priority when quized > QUIZ_SOFT_CAP. Smaller = higher prior
DEFAULT_SENTENCE_EXAMPLE_LIMIT: int = 5

# --- Quiz related
QUIZ_WORD_SORT_COLUMNS: List[str] = ["word", "occurrence", "quized", "last_tested", "jlpt_level"]
SORT_ORDER: List[str] = ["asc", "desc"]
JLPT_LEVELS: List[str] = ["N5", "N4", "N3", "N2", "N1", "N0", "n5", "n4", "n3", "n2", "n1", "n0"]
QUIZ_SOFT_CAP: int = 20     # Will use diff prio formula to appear less
QUIZ_HARD_CAP: int = 40     # Never appear again
WORD_SENSES_REGEX = re.compile(r"^(.+?)\s*\(")  # Capture at least 1 char before first parenthesis
MAX_WORD_DROP_IN_SENTENCE: int = 3
MIN_SENTENCE_PERCENTAGE_REMAINS: float = 0.5

# --- Extra
# This regex matches only Japanese characters (hiragana, katakana, kanji)
JP_WORD_PATTERN = re.compile(r'^[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFFー]+$')
EN_WORD_PATTERN = re.compile(r'^[A-Za-z]+$')
