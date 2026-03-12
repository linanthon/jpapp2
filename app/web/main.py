import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.web.handlers.config import bpv1_url_prefix
from app.web.handlers.helpers import create_app
from app.web.bpv1 import router
from fastapi.staticfiles import StaticFiles
import uvicorn

app = create_app()

# Add the router with prefix (like blueprint in Flask)
app.include_router(router, prefix=bpv1_url_prefix)

# Add static files
app.mount("/static", StaticFiles(directory="app/web/static"), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
