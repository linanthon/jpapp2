from jamdict import Jamdict
from fugashi import Tagger
import MeCab
import jamorasep

import re

from utils.process_data import ProcessData
from utils.data import is_japanese_word


fugashi_tagger = Tagger()
jam = Jamdict()

# =================== Test Mecab =====================

# wakati = MeCab.Tagger() # "-Owakati"
# print(wakati.parse("ご飯を食べなさい").split())


# =================== Test main funcs ================
sen = "ご飯を食べなさい富士山"
sen1 = "【富士吉田】 富士山が世界文化遺産に登録されてから10年を迎え、今年"
sen2 = "【１２３】これはテストです！"
sen3 = "テーブルニュース、フリートーク"
sen4 = "On the テーブル mountain, there's ご飯を食べなさい a river..."

def random_jmdict_entries(n: int):
    out = []
    with jam.jmdict.ctx() as ctx:  # low-level DB access
        rows = ctx.select("SELECT idseq FROM Entry ORDER BY RANDOM() LIMIT ?", (n,))
        for row in rows:
            e = jam.jmdict.get_entry(idseq=row["idseq"], ctx=ctx)
            print("----------------")
            print(e)
            print("text", e.text(True))
            print(e.kana_forms)
            print(e.kanji_forms)
            out.append(e)
            if len(out) >= n:
                break
    return out  # map each entry to (word, english_gloss) per your schema

a = random_jmdict_entries(3)
# print(a)

# a = jam.lookup("フォン")
# print("entries: ", a.entries[0].kana_forms)
# b = jamorasep.parse(a.entries[0].kana_forms[0].text)
# print(b)

# for word in fugashi_tagger(sen4):
#     print("=======\nWord:", word.surface)
#     if is_japanese_word(word.surface):
#         print("--- is JP word ---")
#     # print("feature:", word.feature)
#     if word.feature.lemma is None:
#         continue

#     lemma = word.feature.lemma.split("-")[0]
#     print("Lemma:", lemma)

#     a = jam.lookup(lemma)
#     if a.entries is not None and len(a.entries) > 0:
#         print("entries kanji: ", a.entries[0].kanji_forms)
#         print("Entries kana: ", a.entries[0].kana_forms)
#         print("Entries sense: ", a.entries[0].senses)
#         for sense in a.entries[0].senses:
#             ele = sense.to_dict()
#             meaning = []
#             for gloss in ele["SenseGloss"]:
#                 print("gloss:",gloss["text"], ", pos:", ele["pos"])
        # print("type:", type(a.entries[0].kanji_forms[0].text))
        # print("Entries info: ", a.entries[0].kanji_forms[0].info)
        # print("Entries pri: ", a.entries[0].kanji_forms[0].pri)


# ================== Test jamorasep ===================
# print(jamorasep.convert_lst_of_mora(["シャンプーハット"], output_format="katakana"))
# print(jamorasep.convert_lst_of_mora(["シャンプーハット"], output_format="simple-ipa"))
# print(jamorasep.convert_lst_of_mora(["シャンプーハット"], output_format="kunrei"))
# print(jamorasep.convert_lst_of_mora(["シャンプーハット"], output_format="hepburn"))


spelling = "さいしん"
a = jamorasep.parse(spelling)
# print("jamorasep parse: ", a)

# =================== JamDict showcase ================



# result = jam.lookup('食べる')
# for entry in result.entries:
# 	print(entry.kana_forms[0])
# 	ans = jamorasep.separate(entry.kana_forms[0])
# 	print("AAA: ", ans)

# res = jam.lookup("食べる")
# for entry in res.entries:
# 	print("------------------------------")
# 	print("Spelling (Hiragana):", entry.kana_forms)
# 	print("Kanji:", entry.kanji_forms)
	# print("Meanings:", entry.senses[0])    # [<meaning#1> <word type#1>, <meaning#2> <word type#2>]
	# print("ID Seq", entry.idseq)    # useless
	# print("Info", entry.info)   # useless
	# print("Text", entry.text)   # useless

	# for sense in entry.senses:
	# 	print(sense.to_dict())
		
	# 	sense_collect[pos]

# ================= working =======================
# for word in fugashi_tagger(sentence):
#     res2 = jam.lookup(word.feature.lemma)
#     for entry in res2.entries:
#         print("-----------------------------------------")
#         print("Kanji:", entry.kanji_forms[0] if entry.kanji_forms else "")
#         print("Spelling (Hiragana):", entry.kana_forms[0])
#         print("Meanings:", entry.senses[0])
#         print("Text", entry.text)
#         break
# =================================================

# kanji_result = jam.lookup("読").kanji_entries
# for k in kanji_result:
#     print("Literal:", k.literal)
#     print("Meaning:", k.meanings)
#     print("Onyomi:", k.onyomi)
#     print("Kunyomi:", k.kunyomi)


# result = jam.lookup("学生")
# for entry in result.entries:
#     print("JLPT level:", entry.jlpt)
#     print("Common:", entry.is_common)
	

# result = jam.lookup("勉強")
# for entry in result.entries:
#     readings = [k.text for k in entry.kana_forms]
#     print("Readings:", readings)