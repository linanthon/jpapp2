from flask import g
from typing import TYPE_CHECKING

# Set path to allow import from files
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.web.handlers.helpers import create_app

if TYPE_CHECKING:
    from utils.db import DBHandling

app = create_app()

@app.teardown_appcontext
def close_db(exception=None):
    dbhandling: "DBHandling" = g.pop("db", None)
    if dbhandling is not None:
        dbhandling.close_db()

if __name__ == "__main__":
    app.run(debug=True, threaded=False)
