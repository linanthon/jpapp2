from typing import List

class Quiz:
    def __init__(self, jp: str = "", en: str = "", jlpt_level: str = "",
                 spelling: str = "", audio_mapping: List[str] = [],
                 occurrence: int = 1, quized: int = 0, star: bool = False):
        """
        - en (str): the English word (is the first meaning of the JP word)
        - jp (str): the Japanese word
        - spelling (str): the Higarana spelling of the word
        - jlpt_level (str): 'N5' -> 'N1', will covert 'N0' to empty string
        - audio_mapping (List[str]): the list of romaji of the spelling
        - occurrence (optional - int): the Japanese word occurrence
        - quized (optional - int): the Japanese word corrected quiz times
        - star (optional - bool): this word starred or not
        """
        self.jp = jp
        self.en = en
        self.jlpt_level = jlpt_level if jlpt_level != "N0" else ""
        self.spelling = spelling
        self.audio_mapping = audio_mapping
        self.occurrence = occurrence
        self.quized = quized
        self.start = star


class QuizDistractors:
    """
    A simple struct to store distractors for JP and EN.
    They should have the same length.
    """
    def __init__(self, jp_list: List[str] = [], en_list: List[str] = []):
        self.jp = jp_list
        self.en = en_list
