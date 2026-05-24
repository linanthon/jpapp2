## About this project
This is another version of the https://github.com/linanthon/jpapp. Focus on multi-user support, so the original project meaning might not make sense here.

Changes:
- Flask --> FastAPI
- psycopg2 --> asyncpg
- DB: Adds user. Favorite and progress are now user specific
- API: Adds auth

TODO backend:
- ~~Fix N+1 query~~
- ~~Restructure~~
- ~~Stop convert db Record~~
- ~~Add progress page~~
- ~~Accept word, vector/digital pdf files~~
- ~~Move inserted file into storage (MinIO)~~
- ~~Update sentence example when view word, avoid short/no meaning sentences~~
- ~~Search by kana, romaji, EN~~
- ~~API now is concurrent, insert will meet `process_data` bottle neck --> move to background job~~
- ~~Move jlpt level data scraping into bg job~~
- ~~Auto read jlpt level at start (after scrape)~~
- ~~Can insert multiple files~~
- ~~Redis LRU words + sentence examples~~
- TTS

TODO frontend
- Quiz update to Redis in session, update to DB once at end
- Fix goBack auth problem
- Fix view word filter adding infinite param
- Fix view specific book page
- Fix go back button in view specific
- Quiz not starting
- Unauthorize request goes to /v1/null

## How to run

Install requirements:
* pip install requirements.txt

Run each in separate command prompt:
* minio server minio-data/
* memurai
* taskiq worker app.taskiq_broker:broker app.tasks --workers 3

Uploads the audio files to MinIO (optional), check `scripts/Readme.md` for more details:
`python scripts/upload_audio_to_storage.py`

Start API server
* python -m app.main

App will auto load jlpt level data if existed in DB, otherwise call /v1/jlpt/scrape/bg/{source_id} to scrape and load data, currently only allow `source_id=1`.


## Audio

TTS setup (non-AI):
- JP: `pyopenjtalk-plus` with OpenJTalk UTF-8 dictionary and an HTS voice (for example, Mei Normal).
- EN: `eSpeak NG` (CLI model, no Python wrapper).

Audio generation uses TTS first. If TTS fails (or is disabled), the app falls back to built-in per-kana pre-recorded audio. This fallback is called `StaticA` in the source code.

How to install:

- OpenJTalk (JP)
  - Core wrapper: included in `requirements.txt` (`pyopenjtalk-plus`).
  - Dictionary: download from https://sourceforge.net/projects/open-jtalk/ (e.g.: `open_jtalk_dic_utf_8-1.11.tar.gz`), extract it, then set `OPENJTALK_DIC_PATH` in `app/config.py`.
  - HTS voice: download M001 from https://sourceforge.net/projects/open-jtalk/files/HTS%20voice/ or a Mei voice from https://github.com/hecomi/node-openjtalk/tree/master/voice/mei, then set `OPENJTALK_VOICE_PATH` in `app/config.py`.

- eSpeak NG (EN)
  - Download the Windows `.msi` installer from https://github.com/espeak-ng/espeak-ng/releases and install it. If installation/user adds to PATH, keep `ESPEAK_BIN` in `app/config.py` as is. Otherwise, update it `ESPEAK_BIN` to your eSpeak location.
