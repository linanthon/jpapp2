import os

# Load environment variables from '.env' file, for dev at local
# the '.env' file should have the values for DB creds and redis url.
from dotenv import load_dotenv
load_dotenv()

def _env_bool(name: str, default: bool) -> bool:
	raw = os.getenv(name)
	if raw is None:
		return default
	return raw.strip().lower() in {"1", "true", "yes", "on"}

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
SEARCH_WORD_EXPIRE_MINUTES = int(os.getenv("SEARCH_WORD_EXPIRE_MINUTES", 60))
WORD_CORE_CACHE_EXPIRE_SECONDS = int(os.getenv("WORD_CORE_CACHE_EXPIRE_SECONDS", 720))
WORD_SENTENCE_EXPIRE_SECONDS = int(os.getenv("WORD_SENTENCE_EXPIRE_SECONDS", 180))
WORD_SENTENCE_VERSION_KEY = os.getenv("WORD_SENTENCE_VERSION_KEY", "word_sentence_cache_version")
SEARCH_WORD_VERSION_KEY = os.getenv("SEARCH_WORD_VERSION_KEY", "search_word")
FAILED_LOGIN_LIMIT = int(os.getenv("FAILED_LOGIN_LIMIT", 5))
FAILED_LOGIN_BLOCK_MINUTES = int(os.getenv("FAILED_LOGIN_BLOCK_MINUTES", 5))

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0") # 'localhost' is for dev at local only
JLPT_CACHE_RELOAD_STREAM = os.getenv("JLPT_CACHE_RELOAD_STREAM", "jlpt_cache_reload_stream")
JLPT_CACHE_RELOAD_GROUP = os.getenv("JLPT_CACHE_RELOAD_GROUP", "jlpt_cache_reload_group")
JLPT_CACHE_RELOAD_BLOCK_MS = int(os.getenv("JLPT_CACHE_RELOAD_BLOCK_MS", 5000))
JLPT_CACHE_RELOAD_STREAM_MAXLEN = int(os.getenv("JLPT_CACHE_RELOAD_STREAM_MAXLEN", 1000))

# Taskiq
TASKIQ_BROKER_URL = os.getenv("TASKIQ_BROKER_URL", REDIS_URL)
TASKIQ_RESULT_URL = os.getenv("TASKIQ_RESULT_URL", REDIS_URL)
TASKIQ_QUEUE_NAME = os.getenv("TASKIQ_QUEUE_NAME", "taskiq")
TASKIQ_CONSUMER_GROUP = os.getenv("TASKIQ_CONSUMER_GROUP", "taskiq")
TASKIQ_DLQ_STREAM = os.getenv("TASKIQ_DLQ_STREAM", "taskiq_dlq")
TASKIQ_MAX_ATTEMPTS = int(os.getenv("TASKIQ_MAX_ATTEMPTS", 3))
TASKIQ_MAX_WORKERS = int(os.getenv("TASKIQ_MAX_WORKERS", 4))
TASKIQ_STREAM_MAXLEN_MAIN = int(os.getenv("TASKIQ_STREAM_MAXLEN_MAIN", 10000))
TASKIQ_STREAM_MAXLEN_DLQ = int(os.getenv("TASKIQ_STREAM_MAXLEN_DLQ", 10000))

# MinIO Storage
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "miniouser")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "miniopass")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "jpapp-books")
MAX_INSERT_STRING_BYTES = int(os.getenv("MAX_INSERT_STRING_BYTES", 15000))  # 15kb = 5k JP characters

# Audio
TTS_ENABLED = _env_bool("TTS_ENABLED", True)
TTS_DEFAULT_JP_ENGINE = os.getenv("TTS_DEFAULT_JP_ENGINE", "openjtalk")
TTS_DEFAULT_EN_ENGINE = os.getenv("TTS_DEFAULT_EN_ENGINE", "espeak")
OPENJTALK_BIN = os.getenv("OPENJTALK_BIN", "open_jtalk")
OPENJTALK_DIC_PATH = os.getenv("OPENJTALK_DIC_PATH", "tts/open_jtalk_dic_utf_8-1.11")
OPENJTALK_VOICE_PATH = os.getenv("OPENJTALK_VOICE_PATH", "tts/mei_normal.htsvoice") # one voice only
ESPEAK_BIN = os.getenv("ESPEAK_BIN", "espeak-ng")
ESPEAK_EN_VOICE = os.getenv("ESPEAK_EN_VOICE", "en-us")
TTS_TIMEOUT_MS = int(os.getenv("TTS_TIMEOUT_MS", 2000))
TTS_MAX_TEXT_LEN = int(os.getenv("TTS_MAX_TEXT_LEN", 500))
TTS_JP_SPEED_DEFAULT = float(os.getenv("TTS_JP_SPEED_DEFAULT", "0.55"))
TTS_JP_HALF_TONE_DEFAULT = float(os.getenv("TTS_JP_HALF_TONE_DEFAULT", "-2.5"))

# Blueprint prefix
bpv1_url_prefix = "/v1"
