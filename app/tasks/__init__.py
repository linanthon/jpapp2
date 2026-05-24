"""Task module aggregation for Taskiq worker auto-discovery.

When worker starts with module path `app.tasks`, importing this package must
also import submodules that declare `@broker.task` functions.
"""

from app.tasks import job_books as _job_books  # noqa: F401
from app.tasks import job_scrape as _job_scrape  # noqa: F401
from app.tasks import job_tts as _job_tts  # noqa: F401

