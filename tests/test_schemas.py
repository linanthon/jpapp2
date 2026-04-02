"""Tests for schemas — dataclass/Pydantic model validation."""
import pytest
from schemas.word import Word
from schemas.quiz import QuizDistractors
from schemas.user import UserCreate, UserLogin, UserResponse, TokenResponse, TokenRefresh


class TestWordSchema:
    def test_defaults(self):
        w = Word()
        assert w.word == ""
        assert w.senses == ""
        assert w.spelling == ""
        assert w.forms == ""
        assert w.jlpt_level == ""
        assert w.audio_mapping == []
        assert w.eigo is False

    def test_custom_values(self):
        w = Word(word="食べる", senses="to eat", spelling="タベル",
                 forms="食べ", jlpt_level="N5", audio_mapping=["ta", "be", "ru"], eigo=False)
        assert w.word == "食べる"
        assert w.jlpt_level == "N5"
        assert len(w.audio_mapping) == 3

    def test_independent_audio_lists(self):
        w1 = Word()
        w2 = Word()
        w1.audio_mapping.append("a")
        assert w2.audio_mapping == []  # default_factory ensures independence


class TestQuizDistractors:
    def test_defaults(self):
        qd = QuizDistractors()
        assert qd.jp == []
        assert qd.en == []

    def test_independent_lists(self):
        qd1 = QuizDistractors()
        qd2 = QuizDistractors()
        qd1.jp.append("word")
        assert qd2.jp == []


class TestUserSchemas:
    def test_user_create(self):
        u = UserCreate(username="test", email="t@t.com", password="pw")
        assert u.is_admin is False

    def test_user_create_admin(self):
        u = UserCreate(username="admin", email="a@a.com", password="pw", is_admin=True)
        assert u.is_admin is True

    def test_user_login(self):
        u = UserLogin(username="test", password="pw")
        assert u.username == "test"

    def test_user_response(self):
        u = UserResponse(id=1, username="test", email="t@t.com", is_admin=False)
        assert u.id == 1

    def test_token_response(self):
        t = TokenResponse(access_token="a", refresh_token="r")
        assert t.token_type == "bearer"

    def test_token_refresh(self):
        t = TokenRefresh(refresh_token="r")
        assert t.refresh_token == "r"
