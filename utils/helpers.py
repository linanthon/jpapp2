import os
import json

def get_basename_from_path(fullpath: str):
    """Get filename and keep the extension (if exists)."""
    if not fullpath:
        return ""
    normalized = fullpath.strip().replace('\\', '/')
    return normalized.split('/')[-1]

def get_filename_from_path(fullpath: str):
    """Get filename from full path, i.e.: c:/a/path/the_file.123.txt -> the_file.123"""
    if not fullpath:
        return ""
    
    temp = fullpath.strip()
    if "/" in fullpath:
        temp = temp.split("/")[-1]
    elif "\\" in fullpath:
        temp = temp.split("\\")[-1]
    temp = temp.split(".")

    return ".".join(temp[:-1])

def get_file_extension_from_path(fullpath: str):
    """Get file extension from full path, i.e.: c:/a/path/the_file.123.txt -> .txt"""
    return os.path.splitext(fullpath)[-1].lower()

def str_2_byte(input_str: str):
    return input_str.encode("utf-8")

def validate_jlpt_level(jlpt_level: str) -> str:
    """Return upper cased jlpt_level if appropriate. Otherwise, return empty string"""
    jlpt_level = jlpt_level.upper()
    if jlpt_level in ["N0", "N5", "N4", "N3", "N2", "N1"]:
        return jlpt_level
    return ""

def validate_star(star_param) -> int:
    """
    Parse the star param obtained from frontend into integer:
        * 1: to star
        * 0: remove star
        * -1: invalid
    """
    if isinstance(star_param, bool):
        star = 1 if star_param else 0
    elif isinstance(star_param, (int, float)):
        star = 1 if int(star_param) != 0 else 0
    elif isinstance(star_param, str):
        s = star_param.strip().lower()
        if s in ["1", "true", "t", "yes", "y", "on"]:
            star = 1
        elif s in ["0", "false", "f", "no", "n", "off"]:
            star = 0
        else:
            star = -1
    else:
        star = -1
    return star

def parse_bool_param(val) -> bool:
    """Return True for common truthy query/JSON values, else False."""
    if isinstance(val, bool):
        return val
    if val is None:
        return False
    s = str(val).strip().lower()
    return s in ("1", "true", "t", "yes", "y", "on")


def normalize_voice_options(voice_options) -> dict:
    """Coerce voice options payload into a dict.

    Accepts None/dict/JSON-string and returns {} for invalid inputs.
    """
    if voice_options is None:
        return {}
    if isinstance(voice_options, dict):
        return voice_options
    if isinstance(voice_options, str):
        try:
            parsed = json.loads(voice_options)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}
