## Installation:
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

- Create python environment

        python -m venv .pyenv
        .pyenv/Scripts/activate

- Update setup tools:
    
        python -m pip install --upgrade pip setuptools

- Install required modules:

        pip install -r requirements.txt

    If fail to install jamdict_data on Windows due to wheel:
    - Run `pip install jamdict==0.1a11.post2`, should work normally
    - Manually download jamdict_data 1.5 from pypip: https://files.pythonhosted.org/packages/97/a5/075928aed2b3b70459fc1db396397dfa6714d266c143c51af9b648551a4e/jamdict_data-1.5.tar.gz
    - Extract the tar.gz (should get jamdict_data folder) into your environment, i.e.: `pyenv/Lib/site-packages`
    - Inside the extracted jamdict_data folder, remove the small size `jamdict.db` (~500kb) if exist, extract the ~50mb `jamdict.db.xz` here

## How to use
After installation, to use web UI, run"
    
    python app/web/main.py

Then go on your browser, enter the `localhost:5000/{api_version}`, currently, the application is using `v1`:

    http://127.0.0.1:5000/v1

Use `Insert -> Choose file` to upload japanese documents. **!! Currently only receiving .txt !!!**. Alternatively, `Insert -> Enter string`, you can directly paste the document words into it (remember to name it).

After that, the application will read each sentence > tagged word in said sentences > lookup words in `jamdict` database > save all the words, sentences and this document (calls book) to your database. Then you can:
- View the words in `View collection -> Search word/View words`
- Vite the document in `View collection -> View books`
- Quiz words in `Quiz`, currently only `JP -> EN`, `EN -> JP` and `Review known JP` modes are working.

Click on the `★` to mark/unmark word/book as favorite.

In viewing a specific word, if you find yourself too familiar with this word already and wish it to never again appear in quizes, click on the `Mark as known` on top right corner. This will change the word's `priority` to fail query condition for quiz. After that, the button should change to `Unmark known`, this will reverse `priority` value (your previous progress on this word is kept). Of course, this has no function on words that you have already answered it correctly in quizes so many times that the application count it as known. (In code: change the `schemas/constansts.py`'s `QUIZ_SOFT_CAP` and `QUIZ_HARD_CAP` for the "known" cap).

To quiz "known" words, use the `Quiz -> Review known JP` mode (applied for both auto/manual mark as known by application/user).

In viewing a specific book, if use `Delete book` button, it will delete this book, all its sentences and words. The sentences/words that also exist in other books will still be kept and their `priority` will be updated.

## Categorize JLPT level:
- First time running the application, it will scrape JLPT level data from Wikipedia and store it in the `data/jlpt/` folder. If any of the files already existed, will not scrape.
- For scraping data, you can either use the built-in scraping feature or provide the JLPT files yourself, including n5.txt, n4.txt, n3.txt, n2.txt, n1.txt. Each word seperated by ','. Provide the files before running the application the first time to prevent the auto scrape, and before insert book to apply said JLPT levels. For sources, you can visit:
    - https://en.wiktionary.org/wiki/Appendix:JLPT (built-in)
    - https://www.kanshudo.com/collections/wikipedia_jlpt (refuse scrape bot)
    - https://www.japandict.com/lists/jlpt
    - https://docs.google.com/spreadsheets/d/1m6P8KXrzkgcp9Yxq6AH3uge7kA5yOudwzRN074Cuep0
- Words not included in those files with not be categorized
- Re-scraping while application is running not implemented. Remove the `/data/jlpt/{level}.txt` files and restart the application to re-scrape.

## The way of handling JP words:
Currently using "`fugashi (MeCab wrapper) + unidic-lite` to tokenize sentences and get the word's dictionary base form (avoid JP conjugate)" = `lemma`. However, MeCab way of handling loan word is that it returns "トーク-talk", so we `lemma.split("-")[0]`. Then use `jamdict` to get information from said base form.

Why not just use `fugashi + unidic-lite` to get word info? Because the base form while correct, might not be the commonly used form, i.e:

        ご飯   -> fugashi lookup -> 御飯
        なさる -> fugashi lookup -> 為さる

Meanwhile, (in my experience) `jamdict` output more commonly used form and more detailed word senses (meaning and part-of-speech). `jamdict` sometimes provides additional word(s) that are similar to the requested word and multiple forms making it rather confusing. In this project, just get the first returned record.

After tagging words of a sentence, if met with **multiple katakana words consecutively**, will record each words and try attaching them together to get possible combinations of their lemma (can be a long load word).

(long idiom?)

## Other notes
- The stop word file is composed of AI generated words and https://github.com/stopwords-iso/stopwords-ja/blob/master/stopwords-ja.txt
- Originally, I wanted to groupby word meaning by its part-of-speech (pos). But reality is that 1 word can have multiple meaning, each meaning can have multiple pos. I'm not Japanese expert to guarantee anything so I just leave this be.
- The audio, I record Google translate for the alphabets: Hiragana/Katakana, Dakuten, Handakuten, Yōon (Consonant + small ya/yu/yo (ちゅう, きゃ)) and Sokuon Also includes special words ending with "ん" ("ご*飯*" -> "ご*はん*" -> "go *han*"). Map the audio file names with the Kana characters in spelling of the word. For Sokuon, I just record a supposed "silent sound". Of course, it's not perfect and the reading sounds unnatural.
    * Basic mora: Single kana characters (あ, か)
    * Yōon: Kana + small ya/yu/yo (きゃ)
    * Sokuon: Small tsu + consonant (っか)
    * Long vowels: Kana + ー (カー)
    * Katakana extensions: For foreign words (ファ, ディ)

## Quiz system
Calculate `priority` to show up in quiz based on the word's `quized` (correct times in quiz) and `occurrence` (the word's appearance through out all inserted documents/book)
