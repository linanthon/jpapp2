from dataclasses import dataclass, field
from typing import List

@dataclass
class Word:
    """Transfer object for a Japanese word coming from the NLP pipeline.

    - word: the Kanji version (or Hiragana/Katakana if no Kanji)
    - senses: meaning, word type and position (verb, noun, ...)
    - spelling: the Hiragana/Katakana spelling
    - forms: other forms of this word, joined as "a, b, c"
    - jlpt_level: N5 -> N1, N0 for non-categorized
    - audio_mapping: list of romaji for the spelling
    - eigo: True if this is a borrowed English word (Gairaigo/Wasei-eigo)
    """
    word: str = ""
    senses: str = ""
    spelling: str = ""
    forms: str = ""
    jlpt_level: str = ""
    audio_mapping: List[str] = field(default_factory=list)
    eigo: bool = False
