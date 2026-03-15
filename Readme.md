## About this project
This is another version of the https://github.com/linanthon/jpapp. Focus on multi-user support, so the original project meaning might not make sense here.

Changes:
- Flask --> FastAPI
- psycopg2 --> asyncpg
- DB: Adds user. Favorite and progress are now user specific
- API: Adds auth

TODO backend:
- Fix N+1 query
- Stop convert db Record
- Redis LRU words

TODO frontend
- Fix view specific book page
- Fix go back button in view specific
- Quiz not starting
