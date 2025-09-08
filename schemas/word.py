from typing import List

class Word:
    def __init__(self, word_id=0, word="", senses="", spelling="", forms="", jlpt_level="",
                 audio_mapping=[], star=False, occurence=0, quized=0):
        """
        - word (str): the Kanji version (or the version that is commonly used, can also be Higarana/Katakana)
        - senses (str): the meaning, word type and position (verb, noun, ...)
        - spelling (str): the Higarana spelling of the word
        - forms (str): a joined list of the other forms of this word, i.e.: "a, b, c"
        - jlpt_level (str): N5 -> N1, N0 for non-categorized words
        - audio_mapping (list[str]): the list of romaji of the spelling
        - star (bool): favorite the word
        - occurence (int): the times this word has appeared
        - quized (int): the times this word has been quized
        """
        self.word_id = word_id
        self.word = word
        self.senses = senses
        self.spelling = spelling
        self.forms = forms
        self.jlpt_level = jlpt_level
        self.audio_mapping: List[str] = audio_mapping
        self.star = star
        self.occurrence = occurence
        self.quized = quized

        # For tracking borrowed English words
        self.eigo: bool = False

        # For splitting senses str into list
        self.meaning: list = []