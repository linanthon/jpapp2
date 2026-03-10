import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.web.handlers.helpers import create_app
from app.web.bpv1 import router
import uvicorn

app = create_app()

# Include the router with all routes
app.include_router(router, prefix="/v1")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
