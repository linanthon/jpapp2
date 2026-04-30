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
- Update sentence example when view word, avoid short/no meaning sentences
- Search by kana, romaji, EN
- API now is concurrent, insert will meet `process_data` bottle neck --> move to background job
- Can insert multiple files 
- Redis LRU words

TODO frontend
- Fix goBack auth problem
- Fix view word filter adding infinite param
- Fix view specific book page
- Fix go back button in view specific
- Quiz not starting
- Unauthorize request goes to /v1/null

Run each in separate command prompt:
* minio server minio-data/
* memurai
* taskiq worker app.taskiq_broker:broker app.tasks.job_books --workers 4
* python -m app.main
