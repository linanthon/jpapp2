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

Run each in separate command prompt:
* minio server minio-data/
* memurai
* taskiq worker app.taskiq_broker:broker app.tasks --workers 3

Uploads the audio files to MinIO (optional), check `scripts/Readme.md` for more details:
`python scripts/upload_audio_to_storage.py`

Start API server
* python -m app.main

App will auto load jlpt level data if existed in DB, otherwise call /v1/jlpt/scrape/bg/{source_id} to scrape and load data, currently only allow `source_id=1`.


Audio

Prioritise TTS (non-AI)
- JP: openjtalk python wrapper: https://pypi.org/project/pyopenjtalk-plus/ with Mei normal htsvoice and openjtalk utf-8 dictionary
- EN: eSpeak NG model (no wrapper)

Can disable TTS, will use pre-recorded audio of each character in that word's kana form. Worse in quality, built-in this app. This approach is called StaticA in source code.
