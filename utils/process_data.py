from fugashi import Tagger
from fugashi.fugashi import UnidicNode
from itertools import combinations
from jamdict import Jamdict
from jamdict.util import LookupResult
from jamdict.jmdict import JMDEntry
import jamorasep
import os
from psycopg2 import sql

from typing import List, TYPE_CHECKING

from utils.db import DBHandling
from utils.data import JLPT_DICT, STOP_WORDS, ROMAJI_MAP, is_japanese_word
from utils.logger import get_logger
from schemas.constants import DEFAULT_DISTRACTOR_COUNT
from schemas.word import Word

if TYPE_CHECKING:
    from werkzeug.datastructures import FileStorage 

log = get_logger(__file__)

class ProcessData():
    """Use to process incoming Japanese data, stream file, tag sentence, get word info, ..."""
    
    def __init__(self):
        self.tagger = Tagger()
        self.jam = Jamdict()
    
    def process_sentence(self, sentence: str, db: DBHandling) -> List[Word]:
        """
        Tokenize the sentence into words -> ignore non Japanese words
        -> get their info into a dict -> return the list of them.
        Also search for and process potential Wasei-eigo words.

        Input:
        - sentence: the sentence to process
        - db: the DBHandling object that connected to DB.

        Output: a list of word dicts, the keys include: word, forms, spelling,
        senses, occurrence, jlpt_level, audio
        """
        words: List[Word] = []
        eigo = {}
        for i, word in enumerate(self.tagger(sentence)):
            # Ignore non JP
            if not is_japanese_word(word.surface):
                continue

            row = self._get_jamdict_info(word, db)
            if row:
                # Save borrow English words for potential wasei-eigo
                if row.eigo:
                    eigo[i] = row.word
                words.append(row)
        
        # Handle possible Wasei-eigo combinations
        potential_wasei_eigo = self._get_waseieigo_combs(eigo)
        for wasei_eigo in potential_wasei_eigo:
            row = self._get_jamdict_info(wasei_eigo, db)
            if row:
                words.append(row)
        return words

    def stream_sentences_file(self, filename: str, chunk_size: int = 30, auto_strip: bool = True):
        """
        Read file splitted into chunks, return is a generator, 1 sentence at a time.
        A sentence is a not empty string of words that ends with one of [。, \\n, ！, ？, ：, ., !, ?, :].
        """
        if not os.path.exists(filename):
            log.error(f"File '{filename}' not found")
            return ""

        buffer = ""
        with open(filename, mode="r", encoding="utf-8") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                buffer += chunk
                while True:
                    end = max(buffer.find("。") + 1, buffer.find("！") + 1, 
                              buffer.find("？") + 1, buffer.find("：") + 1, buffer.find("\n") + 1,
                              buffer.find(".") + 1,  buffer.find("!") + 1,
                              buffer.find("?") + 1,  buffer.find(":") + 1)
                    if end == 0:
                        break
                    
                    sentence = buffer[:end]
                    if auto_strip:
                        sentence = buffer[:end].strip("\n").strip()
                        
                    buffer = buffer[end:]
                    if sentence:
                        yield sentence
        # The left over
        if buffer:
            yield buffer

    def stream_sentences_str(self, content: str):
        """
        From input `content`, return is a generator, 1 sentence at a time.
        A sentence is a not empty string of words that ends with one of [。, \\n, ！, ？, ：, ., !, ?, :].
        """
        buffer = content
        while True:
            end = max(buffer.find("。") + 1, buffer.find("！") + 1, 
                        buffer.find("？") + 1, buffer.find("：") + 1, buffer.find("\n") + 1,
                        buffer.find(".") + 1,  buffer.find("!") + 1,
                        buffer.find("?") + 1,  buffer.find(":") + 1)
            if end == 0:
                break
            sentence = buffer[:end].strip("\n").strip()
            buffer = buffer[end:]
            if sentence:
                yield sentence
        # The left over
        if buffer:
            yield buffer

    def get_word_entry(self, tagged_word: UnidicNode | str) -> JMDEntry:
        """
        Get Fugashi tokenized word's lemma (dictionary base form).
        However, lemma might not be useful as it's not commonly used.
        Use Jamdict to precise lookup lemma for all possible base forms (all in 1 instance)
        usually the commonly used form will be at index 0, ignore the rest.

        Input:
        - tagged_word: fugashi tagged (tokenized) word or a string
        
        Output: The entry at index 0 if found, otherwise, None
        """
        if type(tagged_word) is str:
            lemma = tagged_word
        else:
            lemma = tagged_word.feature.lemma
            # No lemma if is number or common symbols but Japanese symbols will still bypass this
            if lemma is None:
                return None
            
            # Handle lemma for Loanwords (Gairaigo) and Wasei-eigo
            # i.e.: Fugashi will give lemma like "トーク-talk"
            lemma = lemma.split("-")[0] if "-" in lemma else lemma
        
        entries: LookupResult = self.jam.lookup(lemma).entries
        # No entries if the tagged word is symbol (【, ！,、, ♫, ...)
        if len(entries) == 0:
            return None
        return entries[0]

    def _get_waseieigo_combs(self, eigo: dict) -> list:
        """
        Combine Katakana words that are potentially a Wasei-eigo type word.

        Input: a dict:
        - key: index the word appeared in sentence
        - value: the word

        Output: a list of potential Wasei-eigo words
        """
        # Group those that are next to each other (index-wise)
        sorted_items = sorted(eigo.items())     # safety meassure
        groups = []
        current_group = []
        prev_index = None
        for index, word in sorted_items:
            if prev_index is None or index == prev_index + 1:
                current_group.append(word)
            else:
                # Only take groups with at least 2 words
                if len(current_group) > 1:
                    groups.append(current_group)
                current_group = [word]
            prev_index = index
        # Remnant
        if len(current_group) > 1:
            groups.append(current_group)

        # For each group, get possible combinations while maintain the order
        waseieigo = []
        for group in groups:
            for r in range(2, len(group) + 1):
                for combo in combinations(group, r):
                    waseieigo.append(''.join(combo))
        return waseieigo

    def _get_jamdict_info(self, word: UnidicNode | str, db: DBHandling) -> Word:
        """
        Get the word's Jamdict entry via `self.get_word_entry()`, parse its info
        into the returning Word:
        - word (str): the Kanji form or Katakana form of the word (if no Kanji)
        - eigo (bool): true if Katakana only word
        - forms (str): a string of joined list elements about other kanji forms the word has
        - spelling (str): the Katakana form
        - senses (str): this word's meanings and types (pos)
        - jlpt_level (str): the JLPT of this word
        - audio (list[str]): a list of audio IDs get from DB

        If the word is stop words or failed to lookup Jamdict, return None.

        If the word is already in DB, increase its occurrence in DB
        and calculate new priority then return None
        """
        # Ignore if stop word
        if (type(word) == UnidicNode and word.surface in STOP_WORDS) or \
           (type(word) == str and word in STOP_WORDS):
            return None

        # Ignore number, symbols and lookup jamdict entries[0]
        entry = self.get_word_entry(word)
        if not entry:
            return None
        
        row = Word()

        # if is Gairaigo or Wasei-eigo -> doesn't have kanji form
        try:
            row.word = entry.kanji_forms[0].text
        except:
            row.word = entry.kana_forms[0].text
            row.eigo = True

        # Check and update occurrence if word existed.
        # Stop proccess and return Word as is (only has value for `word`)
        if db.update_word_occurrence(row.word):
            return row

        row.forms = ", ".join([k.text for k in entry.kanji_forms[1:]]) if len(entry.kanji_forms) > 1 else ""
        row.spelling = entry.kana_forms[0].text

        # Get meaning and Part-of-speech (pos)
        # index 0 will be considered as main, the rests are considered as `extra`
        # Note that 1 sense might have multiple pos as well as multiple meaning
        row_senses = ""
        for sense in entry.senses:
            # i.e.: {'pos': ['Ichidan verb', 'transitive verb'], 'SenseGloss': [{'lang': 'eng', 'text': 'to eat'}, ...]}
            ele = sense.to_dict()
            meaning = []
            for gloss in ele["SenseGloss"]:
                meaning.append(gloss["text"])
            row_senses += f"{','.join(meaning)}, ({ele['pos']}); "
        row.senses = row_senses[:-2] if row_senses else ""

        # Get word tier, can be None, use 'N0' instead
        row.jlpt_level = JLPT_DICT.get(row.word, "N0")

        # Search db and attach the IDs
        row.audio_mapping = self._sep_mora_get_audio_mapping(row.spelling)
        return row
    
    def _sep_mora_get_audio_mapping(self, spelling: str) -> list:
        """
        Separate the spelling of a word (can be Higarana or Katakana)
        into a list of letters. Return a list of romaji mapping for the letters.

        Handle problems
        - "ん" ending: i.e. はん is read as ["han"], not ["ha", "n"].
        When see "ん", remove the latest romaji ("ha") in list then add "n" ("han").
        - TO BE CONTINUE:
            + i, u ending: "saikou" = "sai" "kou. Might never update this and just read the "i" and "u" very fast.
            + prolonged ending: "chiisai" = "chii" "sai". The "chii" is just "chi" but slightly longer, not reading "i".
            The writing of this is a dash, not actual letter. Might update audio for this or just ignore it.
        """
        audio_romaji_list = []
        kana_list: list = jamorasep.parse(spelling)
        i = 0
        while i < len(kana_list):
            kana = kana_list[i]
            new_romaji = None
            # If kana split is "ん"/"ン"
            if i > 0 and kana in ["ん", "ン"]:
                # remove the previous audio mapping
                # add the audio of "<previous romaji> + n"
                prev_romaji = audio_romaji_list.pop()
                new_romaji = prev_romaji + "n"
            
            # If is prolonged sound
            elif i > 0 and kana == "ー":
                new_romaji = audio_romaji_list[-1][-1]
                #TODO: if update prolonged .wav, need pop prev, new = prev + prev[-1] (i.e.: "chii" instead of "chi" "i")

            # If is Sokuon (small tsu) 
            elif i > 0 and kana in ["っ", "ッ"] and i < len(kana_list):
                # We needs the word after small tsu to determine what kind it is, among k, s, t, p
                new_romaji = ROMAJI_MAP.get(kana + kana_list[i+1][0])

                # Approach #2: for more natural, requires more audio files
                # i.e.: word = "学校" -> "ガ" "っ" "こ" -> "ga" "っ"... -> "ga" "k"... -> "gak" ...
                # very important to only get the FIRST character of the next segment
                # because ROMAJI_MAP does not have 'っぴょ'
                # temp_mapping = ROMAJI_MAP.get(kana + kana_list[i+1][0])
                # if temp_mapping:
                #     prev_romaji = audio_romaji_list.pop() 
                #     new_romaji = prev_romaji + temp_mapping
            else:
                new_romaji = ROMAJI_MAP.get(kana)

            if new_romaji:
                audio_romaji_list.append(new_romaji)
            else:
                log.error(f"""Failed to get audio mapping for word of spelling '{spelling}',
                          not found for '{kana}'""")
                return []
            
            i += 1

        return audio_romaji_list


    def tag_sentence(self, sentence: str) -> List:
        return self.tagger(sentence)
    
    def get_random_jamdict_entries(self, exclude_jp: str = "", exclude_en: str = "",
                                   limit: int = DEFAULT_DISTRACTOR_COUNT) -> List[JMDEntry]:
        """
        Get random word in Jamdict, then extract its JP word or EN word (the first meaning).
        This is used to get distractors (incorrect answer choices) for quiz.

        Input:
        - exclude_jp: the JP word of the question or the correct answer
        - exclude_en: the EN word of the question or the correct answer
        - limit: the number of distractors

        Output: a list of JMDEntry, note that the `senses` property is List[Sense].
        """
        out: List[JMDEntry] = []
        with self.jam.jmdict.ctx() as ctx:
            query = """SELECT DISTINCT e.idseq FROM Entry e 
                        JOIN Sense s ON e.idseq = s.idseq 
                        JOIN SenseGloss sg on s.id = sg.sid WHERE 1=1"""
            params = []

            # Exclude the JP word
            if exclude_jp:
                # Exclude exact match word in both Kanji and Kana
                query += """
                AND NOT EXISTS (
                    SELECT k.idseq FROM Kanji k WHERE k.idseq = e.idseq AND k.text = ?
                )
                AND NOT EXISTS (
                    SELECT r.idseq FROM Kana r WHERE r.idseq = e.idseq AND r.text = ?
                )"""
                params.extend([exclude_jp, exclude_jp])

            # Exclude those of the same meaning
            if exclude_en:
                query += " AND sg.text NOT LIKE ?"
                params.append(f"%{exclude_en}%")

            query += f" ORDER BY RANDOM() LIMIT {limit}"

            rows = ctx.select(query, params)
            for row in rows:
                entry = self.jam.jmdict.get_entry(idseq=row["idseq"], ctx=ctx)
                if entry:
                    out.append(entry)
        return out
