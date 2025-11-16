Run this:

- Install postgres.
    For Windows, add new system variable:
        PGCLIENTENCODING=UTF8

    Connect to postgres database, confirm the outputs of below sql lines are UTF8:
        SHOW server_encoding;
        SHOW client_encoding;
    
    Optional: in command prompt/power shell, enter:
        chcp 65001
    Should see output: Active code page: 65001
    This allows showing Japanese in command prompt/power shell.

- Update setup tools:
    python -m pip install --upgrade pip setuptools

- Install required modules
    pip install -r requirements.txt

    If fail to install jamdict_data on Windows due to wheel:
        - Run `pip install jamdict==0.1a11.post2`, should work normally
        - Manually download jamdict_data 1.5 from pypip: https://files.pythonhosted.org/packages/97/a5/075928aed2b3b70459fc1db396397dfa6714d266c143c51af9b648551a4e/jamdict_data-1.5.tar.gz
        - Extract the tar.gz (should get jamdict_data folder) into your environment, i.e.: pyenv/Lib/site-packages
        - Inside the extracted jamdict_data folder, remove the small size `jamdict.db` (~500kb) if exist, extract the ~50mb `jamdict.db.xz` here


Info:

- pip will install uni-diclite and jamdict in environment while scraping JLPT will store in the 'data/jlpt' folder

- For scraping data, you can either use the built-in scraping feature or provide the JLPT files yourself,
    including n5.txt, n4.txt, n3.txt, n2.txt, n1.txt. Each word seperated by ','.
    For sources, you can visit:
        - https://en.wiktionary.org/wiki/Appendix:JLPT (built-in)
        - https://www.kanshudo.com/collections/wikipedia_jlpt (refuse scrape bot)
        - https://www.japandict.com/lists/jlpt
        - https://docs.google.com/spreadsheets/d/1m6P8KXrzkgcp9Yxq6AH3uge7kA5yOudwzRN074Cuep0


- The stop word file is composed of AI generated words and https://github.com/stopwords-iso/stopwords-ja/blob/master/stopwords-ja.txt

- Originally, I wanted to groupby word meaning by its part-of-speech (pos).
But reality is that 1 word can have multiple meaning, each meaning can have multiple pos.
I'm not Japanese expert to guarantee anything so I just leave this be.



- The audio, I record Google translate for the alphabets: Hiragana/Katakana, Dakuten, Handakuten,
Yōon (Consonant + small ya/yu/yo (ちゅう, きゃ)) and Sokuon
Also includes special words ending with "ん" ("ご*飯*" -> "ご*はん*" -> "go *han*").
Makes 'a', 'i', 'u', 'e', 'o' sounds shorter to "solve" the double vowel problem without voicing everything
i.e.: "saikou": 
    normal: "sa..i..ko..u" -> shorten: "sa.i..ko.u"
- For Sokuon, have to record every combination 

- Audio, instead of all the hassle, maybe just use TTS like OpenJTalk (gen a .wav file of a word, then we read that file)



Basic mora: Single kana characters (あ, か)
        Yōon: 
        Sokuon: Small tsu + consonant (っか)
        Long vowels: Kana + ー (カー)
        Katakana extensions: For foreign words (ファ, ディ)




Difficulties:

!!! Should double check these dict difficulties to be sure !!!
- Currently using `fugashi (MeCab wrapper) + unidic-lite` to tokenize sentences and 
    get the word's dictionary base form (avoid JP conjugate) = lemma.
    However, MeCab way of handling loan word is that it returns "トーク-talk",
    So we `lemma.split("-")[0]`.
    Then use `jamdict` to get information from said base form.

    Why not just use `fugashi + unidic-lite` to get word info?
    Because the base form while correct, might not be the commonly used form.
    i.e: ご飯   -> lookup -> 御飯
         なさる -> lookup -> 為さる
    Meanwhile, (in my experience) jamdict output more commonly used form and
    more detailed word senses (meaning and part-of-speech).

- jamdict sometimes provides additional word(s) that are similar to the requested word
    and multiple forms making it rather confusing. In this project, just get the first
    returned record.

- After tagging words of a sentence, if met with multiple katakana words consecutively,
    will attach them together and try to get the their lemma for possible combinations.
