Run this:

- Install postgres

- Update setup tools:
    python -m pip install --upgrade pip setuptools

- Install required modules
    pip install -r requirements.txt


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



- The audio, I record my own voice for the alphabets: Hiragana/Katakana, Dakuten, Handakuten,  and Yōon (Consonant + small ya/yu/yo (ちゅう, きゃ)).
Also includes special words ending with "ん" ("ご*飯*" -> "ご*はん*" -> "go *han*").
Makes 'a', 'i', 'u', 'e', 'o' sounds shorter to "solve" the double vowel problem without voicing everything
i.e.: "saikou": 
    normal: "sa..i..ko..u" -> shorten: "sa.i..ko.u"



Basic mora: Single kana characters (あ, か)
        Yōon: 
        Sokuon: Small tsu + consonant (っか)
        Long vowels: Kana + ー (カー)
        Katakana extensions: For foreign words (ファ, ディ)




Difficulties:

!!! Should double check these dict difficulties to be sure !!!
- Currently using `fugashi (MeCab wrapper) + unidic-lite` to tokenize sentences and get the word's base form.
    Then use `jamdict` to get information from word's base form.
    Why not just use `fugashi + unidic-lite`? Because the base form while correct, might not be the commonly used form.
    i.e: ご飯   -> lookup -> 御飯
         なさる -> lookup -> 為さる
    jamdict provides more information to work with regarding this issue.

- jamdict sometimes provides additional word(s) that are similar to the requested word and multiple forms making it rather confusing.
