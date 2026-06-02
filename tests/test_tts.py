import pytest
from unittest.mock import AsyncMock

from utils.tts import TTSService


class TestTTSJPModelInputResolution:
    @pytest.mark.asyncio
    async def test_resolve_jp_model_input_uses_exact_spelling(self):
        service = TTSService()
        db = AsyncMock()
        db.query_search_word.return_value = [
            {"word": "一歩", "spelling": "いっぽ"},
            {"word": "一方", "spelling": "いっぽう"},
        ]

        resolved = await service._resolve_jp_model_input("一歩", db)
        assert resolved == "いっぽ"

    @pytest.mark.asyncio
    async def test_resolve_jp_model_input_keeps_original_when_no_exact_match(self):
        service = TTSService()
        db = AsyncMock()
        db.query_search_word.return_value = [
            {"word": "一方", "spelling": "いっぽう"},
        ]

        original = "一歩"
        resolved = await service._resolve_jp_model_input(original, db)
        assert resolved == original
