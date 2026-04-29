import os

# Load environment variables from '.env' file, for dev at local
# the '.env' file should have the values for DB creds and redis url.
from dotenv import load_dotenv
load_dotenv()

# DB
DB_USER = os.getenv("DB_USER", "")
DB_PASS = os.getenv("DB_PASS", "")
DB_HOST = os.getenv("DB_HOST", "localhost") # 'localhost' is for dev at local only
DB_PORT = int(os.getenv("DB_PORT", 5432))

# Auth & Security
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production") # requires >= 32 bytes
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 3))
FAILED_LOGIN_LIMIT = int(os.getenv("FAILED_LOGIN_LIMIT", 5))
FAILED_LOGIN_BLOCK_MINUTES = int(os.getenv("FAILED_LOGIN_BLOCK_MINUTES", 5))

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0") # 'localhost' is for dev at local only

# Taskiq
TASKIQ_BROKER_URL = os.getenv("TASKIQ_BROKER_URL", REDIS_URL)
TASKIQ_RESULT_URL = os.getenv("TASKIQ_RESULT_URL", REDIS_URL)

# MinIO Storage
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "miniouser")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "miniopass")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "jpapp-books")

# Blueprint prefix
bpv1_url_prefix = "/v1"
