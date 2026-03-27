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
- Redis LRU words
- PgBouncer to scale Postgres max connections
- API now is concurrent, insert will meet `process_data` bottle neck

TODO frontend
- Fix view specific book page
- Fix go back button in view specific
- Quiz not starting
- Unauthorize insert string goes to /v1/null
