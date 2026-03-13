import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# DB
DB_USER = os.getenv("DB_USER", "")
DB_PASS = os.getenv("DB_PASS", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))

# Auth & Security
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 3
FAILED_LOGIN_LIMIT: int = os.getenv("FAILED_LOGIN_LIMIT", 5)
FAILED_LOGIN_BLOCK_MINUTES: int = os.getenv("FAILED_LOGIN_BLOCK_MINUTES", 5)

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Blueprint prefix
bpv1_url_prefix = "/v1"
