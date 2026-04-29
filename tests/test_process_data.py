"""Tests for utils/process_data.py — sentence streaming, word entry, wasei-eigo, audio mapping."""
import io
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock, patch
from utils.process_data import ProcessData
from utils.text_extractor import TxtExtractor


# ── _find_sentence_end ────────────────────────────────────────────────────────
class TestFindSentenceEnd:
    def test_period(self):
        assert ProcessData._find_sentence_end("テスト。残り") == 4

    def test_exclamation(self):
        assert ProcessData._find_sentence_end("すごい！次") == 4

    def test_newline(self):
        assert ProcessData._find_sentence_end("行一\n行二") == 3

    def test_no_delimiter(self):
        assert ProcessData._find_sentence_end("終わりなし") == -1

    def test_empty(self):
        assert ProcessData._find_sentence_end("") == -1

    def test_picks_first_delimiter(self):
        # ！ at index 3, ？ at index 7 — should pick ！(+1)
        assert ProcessData._find_sentence_end("すごい！本当？") == 4


# ── stream_sentences_str ──────────────────────────────────────────────────────
class TestStreamSentencesStr:
    def setup_method(self):
        self.pdata = ProcessData.__new__(ProcessData)

    def test_single_sentence_period(self):
        result = list(self.pdata.stream_sentences_str("これはテストです。"))
        assert result == ["これはテストです。"]

    def test_multiple_sentences(self):
        result = list(self.pdata.stream_sentences_str("一つ。二つ。三つ。"))
        assert result == ["一つ。", "二つ。", "三つ。"]

    def test_exclamation_mark(self):
        result = list(self.pdata.stream_sentences_str("すごい！本当？"))
        assert result == ["すごい！", "本当？"]

    def test_newline_separator(self):
        result = list(self.pdata.stream_sentences_str("行一\n行二\n"))
        assert result == ["行一", "行二"]

    def test_colon_separator(self):
        result = list(self.pdata.stream_sentences_str("名前：太郎。"))
        assert result == ["名前：", "太郎。"]

    def test_leftover_no_ending(self):
        result = list(self.pdata.stream_sentences_str("終わりなし"))
        assert result == ["終わりなし"]

    def test_empty_string(self):
        result = list(self.pdata.stream_sentences_str(""))
        assert result == []

    def test_ascii_delimiters(self):
        result = list(self.pdata.stream_sentences_str("Hello. World!"))
        assert result == ["Hello.", "World!"]


# ── stream_sentences_file ─────────────────────────────────────────────────────
def _make_mock_upload(filename: str, content: bytes):
    """Helper: create a mock UploadFile with .filename and .file (BytesIO)."""
    upload = MagicMock()
    upload.filename = filename
    upload.file = io.BytesIO(content)
    return upload


class TestStreamSentencesFile:
    def setup_method(self):
        self.pdata = ProcessData.__new__(ProcessData)
        # The uploaded file will be read in byte like setup in the _make_mock_upload
        # so which extractor does not matter
        txt_ext = TxtExtractor()
        self.pdata._extractors = {".txt": txt_ext}

    def test_missing_file(self):
        result = list(self.pdata.stream_sentences_file(None))
        assert result == []

    def test_missing_filename(self):
        upload = MagicMock()
        upload.filename = None
        result = list(self.pdata.stream_sentences_file(upload))
        assert result == []

    def test_unsupported_extension(self):
        upload = _make_mock_upload("test.xyz", b"some data")
        result = list(self.pdata.stream_sentences_file(upload))
        assert result == []

    def test_reads_file(self):
        upload = _make_mock_upload("test.txt", "文一。文二。".encode("utf-8"))
        result = list(self.pdata.stream_sentences_file(upload))
        assert result == ["文一。", "文二。"]

    def test_reads_file_with_leftover(self):
        upload = _make_mock_upload("test.txt", "文一。残り".encode("utf-8"))
        result = list(self.pdata.stream_sentences_file(upload))
        # assert "文一。" in result
        # assert "残り" in result
        assert result == ["文一。", "残り"]

    def test_strips_by_default(self):
        upload = _make_mock_upload("test.txt", "\n文一。\n".encode("utf-8"))
        result = list(self.pdata.stream_sentences_file(upload))
        assert all(not s.startswith("\n") for s in result if s)


# ── _get_waseieigo_combs ──────────────────────────────────────────────────────
class TestGetWaseiEigoCombinations:
    def setup_method(self):
        self.pdata = ProcessData.__new__(ProcessData)

    def test_empty_dict(self):
        assert self.pdata._get_waseieigo_combs({}) == []

    def test_single_word(self):
        # Single word cannot form a combination
        assert self.pdata._get_waseieigo_combs({0: "ア"}) == []

    def test_adjacent_pair(self):
        result = self.pdata._get_waseieigo_combs({0: "ア", 1: "イ"})
        assert "アイ" in result

    def test_non_adjacent_ignored(self):
        result = self.pdata._get_waseieigo_combs({0: "ア", 5: "イ"})
        assert result == []

    def test_three_adjacent(self):
        result = self.pdata._get_waseieigo_combs({0: "ア", 1: "イ", 2: "ウ"})
        # pairs: アイ, イウ, アウ; triple: アイウ
        assert "アイ" in result
        assert "イウ" in result
        assert "アイウ" in result

    def test_two_groups(self):
        eigo = {0: "ア", 1: "イ", 5: "ウ", 6: "エ"}
        result = self.pdata._get_waseieigo_combs(eigo)
        assert "アイ" in result
        assert "ウエ" in result
        # Cross-group combo should NOT exist
        assert "アウ" not in result


# ── get_word_entry ────────────────────────────────────────────────────────────
class TestGetWordEntry:
    """Test get_word_entry with mocked Jamdict."""

    def setup_method(self):
        self.pdata = ProcessData.__new__(ProcessData)

    def test_string_lookup_found(self):
        mock_entry = MagicMock()
        mock_result = MagicMock()
        mock_result.entries = [mock_entry]
        mock_jam = MagicMock()
        mock_jam.lookup.return_value = mock_result
        self.pdata._local = MagicMock()
        self.pdata._local.jam = mock_jam

        result = self.pdata.get_word_entry("食べる")
        assert result is mock_entry
        mock_jam.lookup.assert_called_once_with("食べる")

    def test_string_lookup_not_found(self):
        mock_result = MagicMock()
        mock_result.entries = []
        mock_jam = MagicMock()
        mock_jam.lookup.return_value = mock_result
        self.pdata._local = MagicMock()
        self.pdata._local.jam = mock_jam

        result = self.pdata.get_word_entry("！")
        assert result is None

    def test_tagged_word_no_lemma(self):
        tagged = MagicMock()
        tagged.feature.lemma = None
        result = self.pdata.get_word_entry(tagged)
        assert result is None

    def test_tagged_word_with_dash_lemma(self):
        """Loanwords have lemma like 'トーク-talk', should split on dash."""
        tagged = MagicMock()
        tagged.surface = "トーク"
        tagged.feature.lemma = "トーク-talk"
        mock_entry = MagicMock()
        mock_result = MagicMock()
        mock_result.entries = [mock_entry]
        mock_jam = MagicMock()
        mock_jam.lookup.return_value = mock_result
        self.pdata._local = MagicMock()
        self.pdata._local.jam = mock_jam

        result = self.pdata.get_word_entry(tagged)
        assert result is mock_entry
        mock_jam.lookup.assert_called_once_with("トーク")

    def test_prefers_exact_form_match_over_first_entry(self):
        tagged = MagicMock()
        tagged.surface = "あ"
        tagged.feature.lemma = "あ"

        # First entry is a near match (e.g. あっ), second is exact (あ).
        near_entry = SimpleNamespace(
            kanji_forms=[],
            kana_forms=[SimpleNamespace(text="あっ")],
        )
        exact_entry = SimpleNamespace(
            kanji_forms=[],
            kana_forms=[SimpleNamespace(text="あ")],
        )

        mock_result = MagicMock()
        mock_result.entries = [near_entry, exact_entry]
        mock_jam = MagicMock()
        mock_jam.lookup.return_value = mock_result
        self.pdata._local = MagicMock()
        self.pdata._local.jam = mock_jam

        result = self.pdata.get_word_entry(tagged)
        assert result is exact_entry

    def test_falls_back_to_first_entry_when_no_exact_match(self):
        tagged = MagicMock()
        tagged.surface = "あ"
        tagged.feature.lemma = "あ"

        first_entry = SimpleNamespace(
            kanji_forms=[],
            kana_forms=[SimpleNamespace(text="ぁ")],
        )
        second_entry = SimpleNamespace(
            kanji_forms=[SimpleNamespace(text="阿")],
            kana_forms=[SimpleNamespace(text="ア")],
        )

        mock_result = MagicMock()
        mock_result.entries = [first_entry, second_entry]
        mock_jam = MagicMock()
        mock_jam.lookup.return_value = mock_result
        self.pdata._local = MagicMock()
        self.pdata._local.jam = mock_jam

        result = self.pdata.get_word_entry(tagged)
        assert result is first_entry


# ── _sep_mora_get_audio_mapping ───────────────────────────────────────────────
class TestSepMoraGetAudioMapping:
    def setup_method(self):
        self.pdata = ProcessData.__new__(ProcessData)

    @patch("utils.process_data.jamorasep")
    def test_basic_mapping(self, mock_jamorasep):
        mock_jamorasep.parse.return_value = ["た", "べ", "る"]
        result = self.pdata._sep_mora_get_audio_mapping("たべる")
        assert result == ["ta", "be", "ru"]

    @patch("utils.process_data.jamorasep")
    def test_n_ending(self, mock_jamorasep):
        """はん should map to 'han' not 'ha' + 'n'."""
        mock_jamorasep.parse.return_value = ["は", "ん"]
        result = self.pdata._sep_mora_get_audio_mapping("はん")
        assert result == ["han"]

    @patch("utils.process_data.jamorasep")
    def test_prolonged_sound(self, mock_jamorasep):
        mock_jamorasep.parse.return_value = ["ラ", "ー"]
        result = self.pdata._sep_mora_get_audio_mapping("ラー")
        assert result == ["ra", "a"]

    @patch("utils.process_data.jamorasep")
    def test_sokuon(self, mock_jamorasep):
        """Small tsu (っ) should combine with next kana's first char."""
        # jamorasep splits into individual mora; sokuon logic uses kana_list[i+1][0]
        mock_jamorasep.parse.return_value = ["が", "っ", "こ", "う"]
        result = self.pdata._sep_mora_get_audio_mapping("がっこう")
        assert result[0] == "ga"
        assert result[1] == "k"  # sokuon maps っ+こ -> "k"
        assert result[2] == "ko"

    @patch("utils.process_data.jamorasep")
    def test_unknown_kana_returns_empty(self, mock_jamorasep):
        """If a kana has no ROMAJI_MAP entry, return empty list."""
        mock_jamorasep.parse.return_value = ["♪"]
        result = self.pdata._sep_mora_get_audio_mapping("♪")
        assert result == []


# ── tag_sentence ──────────────────────────────────────────────────────────────
class TestTagSentence:
    def test_returns_tagged_list(self):
        pdata = ProcessData.__new__(ProcessData)
        pdata.tagger = MagicMock(return_value=["tagged1", "tagged2"])
        result = pdata.tag_sentence("test sentence")
        assert result == ["tagged1", "tagged2"]
        pdata.tagger.assert_called_once_with("test sentence")


# ── process_sentence ──────────────────────────────────────────────────────────
class TestProcessSentence:
    @pytest.mark.asyncio
    async def test_empty_sentence(self):
        pdata = ProcessData.__new__(ProcessData)
        pdata.tagger = MagicMock(return_value=[])
        pdata._get_waseieigo_combs = MagicMock(return_value=[])
        result = await pdata.process_sentence("", AsyncMock())
        assert result == []

    @pytest.mark.asyncio
    @patch("utils.process_data.is_japanese_word", return_value=False)
    async def test_non_jp_words_skipped(self, mock_is_jp):
        pdata = ProcessData.__new__(ProcessData)
        word_node = MagicMock()
        word_node.surface = "hello"
        pdata.tagger = MagicMock(return_value=[word_node])
        pdata._get_waseieigo_combs = MagicMock(return_value=[])
        result = await pdata.process_sentence("hello", AsyncMock())
        assert result == []


# ── Integration: stream → process_sentence pipeline ──────────────────────────
def _make_tagged_word(surface, lemma, is_katakana=False):
    """Helper: create a mock UnidicNode-like object."""
    word = MagicMock()
    word.surface = surface
    word.feature = MagicMock()
    word.feature.lemma = lemma
    return word


def _make_jamdict_entry(kanji_text=None, kana_text="カナ", senses=None):
    """Helper: create a mock JMDEntry with kanji/kana forms and senses."""
    entry = MagicMock()
    if kanji_text:
        kanji_form = MagicMock()
        kanji_form.text = kanji_text
        entry.kanji_forms = [kanji_form]
    else:
        entry.kanji_forms = []
    kana_form = MagicMock()
    kana_form.text = kana_text
    entry.kana_forms = [kana_form]
    if senses is None:
        sense = MagicMock()
        sense.to_dict.return_value = {
            "pos": ["Verb"],
            "SenseGloss": [{"lang": "eng", "text": "to eat"}],
        }
        senses = [sense]
    entry.senses = senses
    return entry


class TestStreamThenProcess:
    """Integration tests that feed text through stream → tag → process."""

    def setup_method(self):
        self.pdata = ProcessData.__new__(ProcessData)
        self.pdata._local = MagicMock()
        self.pdata._extractors = {".txt": TxtExtractor()}
        self.mock_db = AsyncMock()
        # By default, word not yet in DB
        self.mock_db.update_word_occurrence = AsyncMock(return_value=False)

    @pytest.mark.asyncio
    @patch("utils.process_data.jamorasep")
    @patch("utils.process_data.is_japanese_word", return_value=True)
    @patch("utils.process_data.STOP_WORDS", [])
    @patch("utils.process_data.JLPT_DICT", {"食べる": "N5"})
    async def test_single_sentence_yields_words(self, mock_is_jp, mock_jamorasep):
        """Stream a single sentence, process it, get Word objects back."""
        mock_jamorasep.parse.return_value = ["た", "べ", "る"]
        tagged = _make_tagged_word("食べる", "食べる")
        self.pdata.tagger = MagicMock(return_value=[tagged])
        entry = _make_jamdict_entry(kanji_text="食べる", kana_text="たべる")
        self.pdata._local.jam = MagicMock()
        self.pdata._local.jam.lookup.return_value = MagicMock(entries=[entry])

        sentences = list(self.pdata.stream_sentences_str("食べる。"))
        assert sentences == ["食べる。"]

        words = await self.pdata.process_sentence(sentences[0], self.mock_db)
        assert len(words) == 1
        assert words[0].word == "食べる"
        assert words[0].spelling == "たべる"
        assert words[0].jlpt_level == "N5"
        assert words[0].audio_mapping == ["ta", "be", "ru"]

    @pytest.mark.asyncio
    @patch("utils.process_data.jamorasep")
    @patch("utils.process_data.is_japanese_word", return_value=True)
    @patch("utils.process_data.STOP_WORDS", [])
    @patch("utils.process_data.JLPT_DICT", {"走る": "N4", "飲む": "N5"})
    async def test_multi_sentence_text(self, mock_is_jp, mock_jamorasep):
        """Stream multi-sentence text, process each, collect all words."""
        text = "走る。飲む。"
        sentences = list(self.pdata.stream_sentences_str(text))
        assert sentences == ["走る。", "飲む。"]

        entries = {
            "走る": _make_jamdict_entry(kanji_text="走る", kana_text="はしる",
                                       senses=[MagicMock(to_dict=MagicMock(return_value={
                                           "pos": ["Verb"], "SenseGloss": [{"lang": "eng", "text": "to run"}]}))]),
            "飲む": _make_jamdict_entry(kanji_text="飲む", kana_text="のむ",
                                       senses=[MagicMock(to_dict=MagicMock(return_value={
                                           "pos": ["Verb"], "SenseGloss": [{"lang": "eng", "text": "to drink"}]}))]),
        }
        audio = {
            "はしる": ["ha", "shi", "ru"],
            "のむ": ["no", "mu"],
        }
        mock_jamorasep.parse.side_effect = lambda s: list(s)  # char-by-char fallback

        all_words = []
        for sent in sentences:
            tagged = _make_tagged_word(sent.rstrip("。"), sent.rstrip("。"))
            self.pdata.tagger = MagicMock(return_value=[tagged])
            lemma = sent.rstrip("。")
            self.pdata._local.jam = MagicMock()
            self.pdata._local.jam.lookup.return_value = MagicMock(entries=[entries[lemma]])
            mock_jamorasep.parse.side_effect = lambda s, a=audio: a.get(s, [])

            words = await self.pdata.process_sentence(sent, self.mock_db)
            all_words.extend(words)

        assert len(all_words) == 2
        assert {w.word for w in all_words} == {"走る", "飲む"}
        assert all_words[0].jlpt_level == "N4"
        assert all_words[1].jlpt_level == "N5"

    @pytest.mark.asyncio
    @patch("utils.process_data.jamorasep")
    @patch("utils.process_data.is_japanese_word", return_value=True)
    @patch("utils.process_data.STOP_WORDS", [])
    @patch("utils.process_data.JLPT_DICT", {"猫": "N4"})
    async def test_non_dictionary_words_filtered(self, mock_is_jp, mock_jamorasep):
        """Words with no Jamdict entry are filtered out of results."""
        mock_jamorasep.parse.return_value = ["ね", "こ"]
        tagged_neko = _make_tagged_word("猫", "猫")
        tagged_no = _make_tagged_word("の", "の")
        self.pdata.tagger = MagicMock(return_value=[tagged_neko, tagged_no])

        entry = _make_jamdict_entry(kanji_text="猫", kana_text="ねこ",
                                    senses=[MagicMock(to_dict=MagicMock(return_value={
                                        "pos": ["Noun"], "SenseGloss": [{"lang": "eng", "text": "cat"}]}))])

        def lookup_side_effect(lemma):
            if lemma == "猫":
                return MagicMock(entries=[entry])
            return MagicMock(entries=[])

        self.pdata._local.jam = MagicMock()
        self.pdata._local.jam.lookup.side_effect = lookup_side_effect

        words = await self.pdata.process_sentence("猫の。", self.mock_db)
        assert len(words) == 1
        assert words[0].word == "猫"

    @pytest.mark.asyncio
    @patch("utils.process_data.jamorasep")
    @patch("utils.process_data.is_japanese_word", return_value=True)
    @patch("utils.process_data.STOP_WORDS", [])
    @patch("utils.process_data.JLPT_DICT", {})
    async def test_existing_word_only_updates_occurrence(self, mock_is_jp, mock_jamorasep):
        """If word already exists in DB, update_word_occurrence returns True
        and _get_jamdict_info returns a Word with only `word` set."""
        mock_jamorasep.parse.return_value = ["た", "べ", "る"]
        self.mock_db.update_word_occurrence = AsyncMock(return_value=True)

        tagged = _make_tagged_word("食べる", "食べる")
        self.pdata.tagger = MagicMock(return_value=[tagged])
        entry = _make_jamdict_entry(kanji_text="食べる", kana_text="たべる")
        self.pdata._local.jam = MagicMock()
        self.pdata._local.jam.lookup.return_value = MagicMock(entries=[entry])

        words = await self.pdata.process_sentence("食べる。", self.mock_db)
        # Word returned but with only .word populated (no senses, no audio)
        assert len(words) == 1
        assert words[0].word == "食べる"
        assert words[0].senses == ""
        assert words[0].audio_mapping == []

    @pytest.mark.asyncio
    @patch("utils.process_data.jamorasep")
    @patch("utils.process_data.is_japanese_word", return_value=True)
    @patch("utils.process_data.STOP_WORDS", [])
    @patch("utils.process_data.JLPT_DICT", {})
    async def test_katakana_word_sets_eigo_flag(self, mock_is_jp, mock_jamorasep):
        """A katakana-only word (no kanji forms) should set eigo=True."""
        mock_jamorasep.parse.return_value = ["ビ", "ー", "ル"]
        tagged = _make_tagged_word("ビール", "ビール")
        self.pdata.tagger = MagicMock(return_value=[tagged])

        # No kanji forms → word comes from kana_forms
        entry = _make_jamdict_entry(kanji_text=None, kana_text="ビール",
                                    senses=[MagicMock(to_dict=MagicMock(return_value={
                                        "pos": ["Noun"], "SenseGloss": [{"lang": "eng", "text": "beer"}]}))])
        self.pdata._local.jam = MagicMock()
        self.pdata._local.jam.lookup.return_value = MagicMock(entries=[entry])

        words = await self.pdata.process_sentence("ビール。", self.mock_db)
        assert len(words) == 1
        assert words[0].word == "ビール"
        assert words[0].eigo is True

    @pytest.mark.asyncio
    @patch("utils.process_data.jamorasep")
    @patch("utils.process_data.is_japanese_word", return_value=True)
    @patch("utils.process_data.STOP_WORDS", [])
    @patch("utils.process_data.JLPT_DICT", {})
    async def test_wasei_eigo_combination_processed(self, mock_is_jp, mock_jamorasep):
        """Two adjacent katakana words trigger wasei-eigo combination lookup."""
        mock_jamorasep.parse.side_effect = lambda s: list(s)
        # Two adjacent katakana words
        tagged1 = _make_tagged_word("アイス", "アイス")
        tagged2 = _make_tagged_word("クリーム", "クリーム")
        self.pdata.tagger = MagicMock(return_value=[tagged1, tagged2])

        ice_entry = _make_jamdict_entry(kanji_text=None, kana_text="アイス",
                                        senses=[MagicMock(to_dict=MagicMock(return_value={
                                            "pos": ["Noun"], "SenseGloss": [{"lang": "eng", "text": "ice"}]}))])
        cream_entry = _make_jamdict_entry(kanji_text=None, kana_text="クリーム",
                                          senses=[MagicMock(to_dict=MagicMock(return_value={
                                              "pos": ["Noun"], "SenseGloss": [{"lang": "eng", "text": "cream"}]}))])
        combo_entry = _make_jamdict_entry(kanji_text=None, kana_text="アイスクリーム",
                                          senses=[MagicMock(to_dict=MagicMock(return_value={
                                              "pos": ["Noun"], "SenseGloss": [{"lang": "eng", "text": "ice cream"}]}))])

        def lookup_side_effect(lemma):
            entries_map = {
                "アイス": [ice_entry],
                "クリーム": [cream_entry],
                "アイスクリーム": [combo_entry],
            }
            result = MagicMock()
            result.entries = entries_map.get(lemma, [])
            return result

        self.pdata._local.jam = MagicMock()
        self.pdata._local.jam.lookup.side_effect = lookup_side_effect

        words = await self.pdata.process_sentence("アイスクリーム。", self.mock_db)
        # Should have the 2 individual words + the wasei-eigo combo
        assert len(words) == 3
        word_texts = [w.word for w in words]
        assert "アイスクリーム" in word_texts

    @pytest.mark.asyncio
    @patch("utils.process_data.jamorasep")
    @patch("utils.process_data.is_japanese_word", return_value=True)
    @patch("utils.process_data.STOP_WORDS", [])
    @patch("utils.process_data.JLPT_DICT", {"食べる": "N5"})
    async def test_file_stream_to_process(self, mock_is_jp, mock_jamorasep):
        """Full pipeline: read file → stream sentences → process each."""
        mock_jamorasep.parse.return_value = ["た", "べ", "る"]
        upload = _make_mock_upload("input.txt", "食べる。飲む。".encode("utf-8"))

        entry_taberu = _make_jamdict_entry(kanji_text="食べる", kana_text="たべる")
        entry_nomu = _make_jamdict_entry(kanji_text="飲む", kana_text="のむ",
                                         senses=[MagicMock(to_dict=MagicMock(return_value={
                                             "pos": ["Verb"], "SenseGloss": [{"lang": "eng", "text": "to drink"}]}))])

        sentences = list(self.pdata.stream_sentences_file(upload))
        assert len(sentences) == 2

        all_words = []
        for sent in sentences:
            tagged = _make_tagged_word(sent.rstrip("。"), sent.rstrip("。"))
            self.pdata.tagger = MagicMock(return_value=[tagged])
            lemma = sent.rstrip("。")
            lookup_map = {"食べる": entry_taberu, "飲む": entry_nomu}
            self.pdata._local.jam = MagicMock()
            self.pdata._local.jam.lookup.return_value = MagicMock(
                entries=[lookup_map.get(lemma, entry_taberu)]
            )
            words = await self.pdata.process_sentence(sent, self.mock_db)
            all_words.extend(words)

        assert len(all_words) == 2
        assert all_words[0].word == "食べる"
        assert all_words[1].word == "飲む"
        assert all_words[0].senses != ""
        assert "to drink" in all_words[1].senses
