from schemas.constants import DEFAULT_LIMIT

from handlers.helpers import get_dbhandling

def get_word_jp_quizes(jlpt_level: str = None, star: bool = False, book_id: int = 0, limit: int = DEFAULT_LIMIT):
    db = get_dbhandling()
    db.get_quiz(limit=limit, jlpt_filter=jlpt_level, star_only=star, book_id=book_id)
    pass