"""Tests for utils/helpers.py — pure functions, no external deps."""
import pytest
from utils.helpers import (
    get_filename_from_path,
    get_file_extension_from_path,
    str_2_byte,
    validate_jlpt_level,
    validate_star,
    parse_bool_param,
)


# ── get_filename_from_path ────────────────────────────────────────────────────
class TestGetFilenameFromPath:
    def test_unix_path(self):
        assert get_filename_from_path("c:/a/path/the_file.123.txt") == "the_file.123"

    def test_windows_path(self):
        assert get_filename_from_path("c:\\a\\path\\file.txt") == "file"

    def test_filename_only(self):
        assert get_filename_from_path("readme.md") == "readme"

    def test_no_extension(self):
        # edge: split on '.' gives single part, join all but last → ""
        assert get_filename_from_path("noext") == ""

    def test_empty_string(self):
        assert get_filename_from_path("") == ""

    def test_none(self):
        assert get_filename_from_path(None) == ""

    def test_multiple_dots(self):
        assert get_filename_from_path("archive.tar.gz") == "archive.tar"

# ── get_filename_from_path ────────────────────────────────────────────────────
class TestGetFileExtensionFromPath:
    def test_unix_path(self):
        assert get_file_extension_from_path("c:/a/path/the_file.123.txt") == ".txt"

# ── str_2_byte ────────────────────────────────────────────────────────────────
class TestStr2Byte:
    def test_ascii(self):
        assert str_2_byte("hello") == b"hello"

    def test_unicode(self):
        assert str_2_byte("日本語") == "日本語".encode("utf-8")

    def test_empty(self):
        assert str_2_byte("") == b""


# ── validate_jlpt_level ──────────────────────────────────────────────────────
class TestValidateJlptLevel:
    @pytest.mark.parametrize("inp,expected", [
        ("N0", "N0"), ("N1", "N1"), ("N2", "N2"),
        ("N3", "N3"), ("N4", "N4"), ("N5", "N5"),
        ("n1", "N1"), ("n5", "N5"),
    ])
    def test_valid(self, inp, expected):
        assert validate_jlpt_level(inp) == expected

    @pytest.mark.parametrize("inp", ["", "N6", "A1", "abc", "5"])
    def test_invalid(self, inp):
        assert validate_jlpt_level(inp) == ""


# ── validate_star ─────────────────────────────────────────────────────────────
class TestValidateStar:
    @pytest.mark.parametrize("inp,expected", [
        (True, 1), (False, 0),
        (1, 1), (0, 0), (42, 1), (0.0, 0), (1.5, 1),
        ("1", 1), ("true", 1), ("True", 1), ("t", 1), ("yes", 1), ("y", 1), ("on", 1),
        ("0", 0), ("false", 0), ("False", 0), ("f", 0), ("no", 0), ("n", 0), ("off", 0),
    ])
    def test_valid(self, inp, expected):
        assert validate_star(inp) == expected

    @pytest.mark.parametrize("inp", ["maybe", "2", None, [], {}])
    def test_invalid(self, inp):
        assert validate_star(inp) == -1


# ── parse_bool_param ──────────────────────────────────────────────────────────
class TestParseBoolParam:
    @pytest.mark.parametrize("inp", [True, "1", "true", "True", "t", "yes", "y", "on"])
    def test_truthy(self, inp):
        assert parse_bool_param(inp) is True

    @pytest.mark.parametrize("inp", [False, None, "0", "false", "no", "off", "random", ""])
    def test_falsy(self, inp):
        assert parse_bool_param(inp) is False
