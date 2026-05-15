import os
import re
import requests

from bs4 import BeautifulSoup
from typing import Tuple, List, TYPE_CHECKING

from schemas.constants import (JLPT_DIR, STOPWORD_FILE, AUDIO_DIR, DEFAULT_LIMIT,
                               JP_WORD_PATTERN, EN_WORD_PATTERN, DEFAULT_DISTRACTOR_COUNT)
from schemas.quiz import QuizDistractors
from utils.logger import get_logger

if TYPE_CHECKING:
    from utils.db import DBHandling
    from utils.process_data import ProcessData


log = get_logger(__file__)

JLPT_DICT = {}
STOP_WORDS = []

ROMAJI_MAP = {
    # Hiragana – Basic
    "あ": "a", "い": "i", "う": "u", "え": "e", "お": "o",
    "か": "ka", "き": "ki", "く": "ku", "け": "ke", "こ": "ko",
    "さ": "sa", "し": "shi", "す": "su", "せ": "se", "そ": "so",
    "た": "ta", "ち": "chi", "つ": "tsu", "て": "te", "と": "to",
    "な": "na", "に": "ni", "ぬ": "nu", "ね": "ne", "の": "no",
    "は": "ha", "ひ": "hi", "ふ": "fu", "へ": "he", "ほ": "ho",
    "ま": "ma", "み": "mi", "む": "mu", "め": "me", "も": "mo",
    "や": "ya", "ゆ": "yu", "よ": "yo",
    "ら": "ra", "り": "ri", "る": "ru", "れ": "re", "ろ": "ro",
    "わ": "wa", "を": "wo", "ん": "n",

    # Hiragana – Dakuten & Handakuten
    "が": "ga", "ぎ": "gi", "ぐ": "gu", "げ": "ge", "ご": "go",
    "ざ": "za", "じ": "ji", "ず": "zu", "ぜ": "ze", "ぞ": "zo",
    "だ": "da", "ぢ": "dji", "づ": "dzu", "で": "de", "ど": "do",
    "ば": "ba", "び": "bi", "ぶ": "bu", "べ": "be", "ぼ": "bo",
    "ぱ": "pa", "ぴ": "pi", "ぷ": "pu", "ぺ": "pe", "ぽ": "po",

    # Hiragana – Yōon
    "きゃ": "kya", "きゅ": "kyu", "きょ": "kyo",
    "ぎゃ": "gya", "ぎゅ": "gyu", "ぎょ": "gyo",
    "しゃ": "sha", "しゅ": "shu", "しょ": "sho",
    "じゃ": "ja", "じゅ": "ju", "じょ": "jo",
    "ちゃ": "cha", "ちゅ": "chu", "ちょ": "cho",
    "ぢゃ": "jya", "ぢゅ": "jyu", "ぢょ": "jyo",
    "にゃ": "nya", "にゅ": "nyu", "にょ": "nyo",
    "ひゃ": "hya", "ひゅ": "hyu", "ひょ": "hyo",
    "びゃ": "bya", "びゅ": "byu", "びょ": "byo",
    "ぴゃ": "pya", "ぴゅ": "pyu", "ぴょ": "pyo",
    "みゃ": "mya", "みゅ": "myu", "みょ": "myo",
    "りゃ": "rya", "りゅ": "ryu", "りょ": "ryo",

    # Hiragana - sokuon
    "っか": "k", "っき": "k", "っく": "k", "っけ": "k", "っこ": "k",
    "っさ": "s", "っし": "s", "っす": "s", "っせ": "s", "っそ": "s",
    "った": "t", "っち": "t", "っつ": "t", "って": "t", "っと": "t",
    "っぱ": "p", "っぴ": "p", "っぷ": "p", "っぺ": "p", "っぽ": "p",

    # Katakana – Basic
    "ア": "a", "イ": "i", "ウ": "u", "エ": "e", "オ": "o",
    "カ": "ka", "キ": "ki", "ク": "ku", "ケ": "ke", "コ": "ko",
    "サ": "sa", "シ": "shi", "ス": "su", "セ": "se", "ソ": "so",
    "タ": "ta", "チ": "chi", "ツ": "tsu", "テ": "te", "ト": "to",
    "ナ": "na", "ニ": "ni", "ヌ": "nu", "ネ": "ne", "ノ": "no",
    "ハ": "ha", "ヒ": "hi", "フ": "fu", "ヘ": "he", "ホ": "ho",
    "マ": "ma", "ミ": "mi", "ム": "mu", "メ": "me", "モ": "mo",
    "ヤ": "ya", "ユ": "yu", "ヨ": "yo",
    "ラ": "ra", "リ": "ri", "ル": "ru", "レ": "re", "ロ": "ro",
    "ワ": "wa", "ヲ": "wo", "ン": "n",

    # Katakana – Dakuten & Handakuten
    "ガ": "ga", "ギ": "gi", "グ": "gu", "ゲ": "ge", "ゴ": "go",
    "ザ": "za", "ジ": "ji", "ズ": "zu", "ゼ": "ze", "ゾ": "zo",
    "ダ": "da", "ヂ": "ji", "ヅ": "zu", "デ": "de", "ド": "do",
    "バ": "ba", "ビ": "bi", "ブ": "bu", "ベ": "be", "ボ": "bo",
    "パ": "pa", "ピ": "pi", "プ": "pu", "ペ": "pe", "ポ": "po",

    # Katakana – Yōon
    "キャ": "kya", "キュ": "kyu", "キョ": "kyo",
    "ギャ": "gya", "ギュ": "gyu", "ギョ": "gyo",
    "シャ": "sha", "シュ": "shu", "ショ": "sho",
    "ジャ": "ja", "ジュ": "ju", "ジョ": "jo",
    "チャ": "cha", "チュ": "chu", "チョ": "cho",
    "ヂャ": "jya", "ヂュ": "jyu", "ヂョ": "jyo",
    "ニャ": "nya", "ニュ": "nyu", "ニョ": "nyo",
    "ヒャ": "hya", "ヒュ": "hyu", "ヒョ": "hyo",
    "ビャ": "bya", "ビュ": "byu", "ビョ": "byo",
    "ピャ": "pya", "ピュ": "pyu", "ピョ": "pyo",
    "ミャ": "mya", "ミュ": "myu", "ミョ": "myo",
    "リャ": "rya", "リュ": "ryu", "リョ": "ryo",

    # Katakana - sokuon
    "ッカ": "k", "ッキ": "k", "ック": "k", "ッケ": "k", "ッコ": "k",
    "ッサ": "s", "ッシ": "s", "ッス": "s", "ッセ": "s", "ッソ": "s",
    "ッタ": "t", "ッチ": "c", "ッツ": "t", "ッテ": "t", "ット": "t",
    "ッパ": "p", "ッピ": "p", "ップ": "p", "ッペ": "p", "ッポ": "p",

    # Extra loan words
    "フォ": "fo",
    "ヴォ": "vo",
    "ホゥ": "hu",   # uncommon
    "トゥ": "tu",
    "ドゥ": "du",
    "ウィ": "wi",   # included for completeness
    "ウゥ": "wu",   # very rare
    "スォ": "swo",  # ultra rare, sci-fi terms etc.
    "クォ": "kwo",  # or "quo"
    "グォ": "gwo",  # or "guo"
    "ツォ": "tso",  # used in some transliterations

    # ん ending (not sure some of these actually exist but I'll just list them all
    # (base + dakuten + handakuten + yoon)
    "あん": "an", "いん": "in", "うん": "un", "えん": "en", "おん": "on",
    "かん": "kan", "きん": "kin", "くん": "kun", "けん": "ken", "こん": "kon",
    "さん": "san", "しん": "shin", "すん": "sun", "せん": "sen", "そん": "son",
    "たん": "tan", "ちん": "chin", "つん": "tsun", "てん": "ten", "とん": "ton",
    "なん": "nan", "にん": "nin", "ぬん": "nun", "ねん": "nen", "のん": "non",
    "はん": "han", "ひん": "hin", "ふん": "fun", "へん": "hen", "ほん": "hon",
    "まん": "man", "みん": "min", "むん": "mun", "めん": "men", "もん": "mon",
    "やん": "yan", "ゆん": "yun", "よん": "yon",
    "らん": "ran", "りん": "rin", "るん": "run", "れん": "ren", "ろん": "ron",
    "わん": "wan",
    "がん": "gan", "ぎん": "gin", "ぐん": "gun", "げん": "gen", "ごん": "gon",
    "ざん": "zan", "じん": "jin", "ずん": "zun", "ぜん": "zen", "ぞん": "zon",
    "だん": "dan", "ぢん": "djin", "づん": "dzun", "でん": "den", "どん": "don",
    "ばん": "ban", "びん": "bin", "ぶん": "bun", "べん": "ben", "ぼん": "bon",
    "ぱん": "pan", "ぴん": "pin", "ぷん": "pun", "ぺん": "pen", "ぽん": "pon",
    "きゃん": "kyan", "きゅん": "kyun", "きょん": "kyon",
    "ぎゃん": "gyan", "ぎゅん": "gyun", "ぎょん": "gyon",
    "しゃん": "shan", "しゅん": "shun", "しょん": "shon",
    "じゃん": "jan",  "じゅん": "jun",  "じょん": "jon",
    "ちゃん": "chan", "ちゅん": "chun", "ちょん": "chon",
    "ぢゃん": "jyan", "ぢゅん": "jyun", "ぢょん": "jyon",
    "にゃん": "nyan", "にゅん": "nyun", "にょん": "nyon",
    "ひゃん": "hyan", "ひゅん": "hyun", "ひょん": "hyon",
    "びゃん": "byan", "びゅん": "byun", "びょん": "byon",
    "ぴゃん": "pyan", "ぴゅん": "pyun", "ぴょん": "pyon",
    "みゃん": "myan", "みゅん": "myun", "みょん": "myon",
    "りゃん": "ryan", "りゅん": "ryun", "りょん": "ryon",
    "アン": "an", "イン": "in", "ウン": "un", "エン": "en", "オン": "on",
    "カン": "kan", "キン": "kin", "クン": "kun", "ケン": "ken", "コン": "kon",
    "サン": "san", "シン": "shin", "スン": "sun", "セン": "sen", "ソン": "son",
    "タン": "tan", "チン": "chin", "ツン": "tsun", "テン": "ten", "トン": "ton",
    "ナン": "nan", "ニン": "nin", "ヌン": "nun", "ネン": "nen", "ノン": "non",
    "ハン": "han", "ヒン": "hin", "フン": "fun", "ヘン": "hen", "ホン": "hon",
    "マン": "man", "ミン": "min", "ムン": "mun", "メン": "men", "モン": "mon",
    "ヤン": "yan", "ユン": "yun", "ヨン": "yon",
    "ラン": "ran", "リン": "rin", "ルン": "run", "レン": "re", "ロン": "ro",
    "ワン": "wan",
    "ガン": "gan", "ギン": "gin", "グン": "gun", "ゲン": "gen", "ゴン": "gon",
    "ザン": "zan", "ジン": "jin", "ズン": "zun", "ゼン": "zen", "ゾン": "zon",
    "ダン": "dan", "ヂン": "jin", "ヅン": "zun", "デン": "den", "ドン": "don",
    "バン": "ban", "ビン": "bin", "ブン": "bun", "ベン": "ben", "ボン": "bon",
    "パン": "pan", "ピン": "pin", "プン": "pun", "ペン": "pen", "ポン": "pon",
    "キャン": "kyan", "キュン": "kyun", "キョン": "kyon",
    "ギャン": "gyan", "ギュン": "gyun", "ギョン": "gyon",
    "シャン": "shan", "シュン": "shun", "ション": "shon",
    "ジャン": "jan", "ジュン": "jun", "ジョン": "jon",
    "チャン": "cha", "チュン": "chun", "チョン": "chon",
    "ヂャン": "jyan", "ヂュン": "jyun", "ヂョン": "jyon",
    "ニャン": "nyan", "ニュン": "nyun", "ニョン": "nyon",
    "ヒャン": "hyan", "ヒュン": "hyun", "ヒョン": "hyon",
    "ビャン": "byan", "ビュン": "byun", "ビョン": "byon",
    "ピャン": "pyan", "ピュン": "pyun", "ピョン": "pyon",
    "ミャン": "myan", "ミュン": "myun", "ミョン": "myon",
    "リャン": "ryan", "リュン": "ryun", "リョン": "ryon",
}


def is_japanese_word(word: str) -> bool:
    return bool(JP_WORD_PATTERN.fullmatch(word))

def is_english_word(word: str) -> bool:
    return bool(EN_WORD_PATTERN.fullmatch(word))

def is_word_or_number(input_str: str) -> bool:
    """Check if a string only contains letters, digits and underscore"""
    return bool(re.fullmatch(r"\w+", input_str))

def read_stop_words(filename: str = STOPWORD_FILE) -> None:
    """Read stop words from file"""
    with open(filename, encoding="utf-8") as f:
        STOP_WORDS.extend([line.strip() for line in f if line.strip()])

def read_jlpt(dirname: str = JLPT_DIR) -> None:
    """Read word JLPT from files"""
    tier_list = ["N5", "N4", "N3", "N2", "N1"]
    for tier in tier_list:
        filename = f"{dirname}/{tier}.txt"
        if os.path.exists(filename):
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    for word in f.readlines():
                        JLPT_DICT[word.strip("\n")] = tier
            except Exception as e:
                log.error(f"Failed to read JLPT file {filename}: {e}")

"""Unavailable because failed to install miniaudio on Windows env"""
def play_audio(audio_mapping: List[str]) -> None:
    """
    Read all the audio files accordingly to audio_mapping, concatenate then play it
    """
    combined_pcm = bytearray()
    sample_rate = None
    for syllable in audio_mapping:
        audio_file = f"{AUDIO_DIR}/{syllable}.wav"
    #     miniaudio.play_file(audio_file)

    #     sound = miniaudio.decode_file(audio_file)
    #     if not sample_rate:
    #         sample_rate = sound.sample_rate
    #     combined_pcm.extend(sound.samples)

    # miniaudio.play_sample(sound.samples, sample_rate, 1)

def str_2_int(input_str: str) -> int:
    try:
        inte = int(input_str)
    except Exception:
        inte = DEFAULT_LIMIT
    return inte


async def get_quiz_distractors(pdata: "ProcessData", db: "DBHandling", jp_word: str = "",
                         en_word: str = "", get_distractors_from_db: bool = True,
                         distractor_count: int = DEFAULT_DISTRACTOR_COUNT) -> QuizDistractors:
    """
    Get JP distractors (incorrect JP choices for the current quiz) using either our DB
    or Jamdict's DB. Parse the query result into 2 list of strings for JP and EN.
    For 'jp_word' and 'en_word' input param, must include at least one of them.
    
    Input:
    - pdata: A ProcessData object
    - db: A DBHanding object connected to Database
    - get_distractors_from_db: If true, use db.(). If False, draw random words from Jamdict.
    - jp_word: The JP word in quiz, will query different than this word.
    - en_word: The EN/first meaning of the JP word, will query different meaning than this.
    - distractor_count: The number of false Japanese word for the queried English word. Default: 3.

    Output: A tuple of
    - list of incorrect JP word choices.
    - list of incorrect EN word choices.
    """
    if not jp_word and not en_word:
        log.error("Must have at least 'jp_word' or 'en_word'")
        return None

    res = QuizDistractors()   # dataclass uses field(default_factory=list)
    instances = []
    if get_distractors_from_db:
        instances = await db.get_distractors(jp_word, en_word, distractor_count)

    # if obtained enough distractors from DB -> use them
    # Otherwise, get from jamdict instead
    if len(instances) == distractor_count:
        for instance in instances:
            res.jp.append(instance["jp"])
            res.en.append(instance["en"])
    else:
        for instance in pdata.get_random_jamdict_entries(jp_word, en_word, distractor_count):
            # kanji might be missing for english borrowed words, kana always exists
            jp_choice = instance.kanji_forms[0].text if instance.kanji_forms else instance.kana_forms[0].text
            # the senses is List[Senses], take the first one, use `text()` to get only the meaning (no pos)
            en_choice = instance.senses[0].text()

            res.jp.append(jp_choice)
            res.en.append(en_choice)
    return res

