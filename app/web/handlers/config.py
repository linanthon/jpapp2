import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# DB
DB_USER = os.getenv("DB_USER", "")
DB_PASS = os.getenv("DB_PASS", "")

# Blueprint prefix
bpv1_url_prefix = "/v1"
