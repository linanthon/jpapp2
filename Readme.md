## About this project
This is another version of the https://github.com/linanthon/jpapp. Now supports async, added multi-user, new UI. The multi-user support aspect might not make sense for the initial purpose (which is allowing user to insert the material they want to study what they chose), but for study purpose, it's included.

Demo: 

Changes
- Added user management: now has register, login, logout functions. Learning progress binds to individual user.
- Added Redis: used to cache user's tokens; LRU words, sentence examples; be message stream for Taskiq; JLPT levels mapping.
- Added Taskiq: used to handle background jobs: scraping JLPT level from Wikipedia, insert new material (book), Text To Speech generation. -> Now return job ID quickly after request to not wait for heavy processes, avoid bottle neck.
- Added MinIO: storage used to store book's content instead of in DB. Returns download URL to frontend.
- Updated search function: can now search in Kanji, Kana (the alphabets), Romaji and English. Implemented typo tolerance but this feature is limited so correct word is preferred.
- Added Text To Speech (TTS): now playing audio will prioritise using TTS (applied for both JP and EN). Can toggle off to use the built-in pre-recorded audio approach (this is referred as StaticA in source code, only JP).
- Added Progress page: see study progress
- Added Job page (admin only): see initialized background jobs.
- JLPT level mapping: startup app will auto read data to Redis in background. If no JLPT data, will auto queue a scrape job. Added endpoint for JLPT scraping (will replace current data).
- Insert file/string: moved process to background job, allows inserting multiple files at once.
- Moves Flask to FastAPI, psycopg2 to asynpg: supports async natively.
- Others: bug fixes, N+1 queries, removed unecessary data type conversion, idempotent checks, ...

## How to run

Create virtual environment then install requirements:
* pip install requirements.txt

Run each in separate CMD/PowerShell:

* MinIO
  - Download `minio.exe`: https://dl.min.io/community/server/minio/release/windows-amd64/
  - Setup username password in your `.env` or:
    - PowerShell:
      - `$env:MINIO_ROOT_USER="miniouser"`
      - `$env:MINIO_ROOT_PASSWORD="miniopass"`
    - CMD:
      - `set MINIO_ROOT_USER="miniouser"`
      - `set MINIO_ROOT_PASSWORD="miniopass"`
  - Run:
    `{your-minio-exe} server {your-minio-data-folder-path}`
    - PowerShell example: `./minio.exe server ./minio-data`

* Memurai ("Redis")
  - Download: https://www.memurai.com/get-memurai?version=windows-valkey
  - Run `memurai`
  - if opened before, can check with `memurai-cli ping`

* Taskiq
  - Installed in pip requirements 
  - Run `taskiq worker app.taskiq_broker:broker app.tasks --workers {number-of-workers}`

Uploads the audio files to MinIO (optional), check `scripts/Readme.md` for more details:
`python scripts/upload_audio_to_storage.py`

Setup your `.env` following the `.env_example` file.

Start API server
* `python -m app.main`

Start Frontend:
* `npm run build`
* `npm run dev` (local) / `npm start` (prod)

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
