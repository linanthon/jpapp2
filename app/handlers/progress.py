from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from utils.db import DBHandling

async def handle_progress(db: "DBHandling", user_id: int) -> dict:
    return await db.get_user_progress(user_id)
