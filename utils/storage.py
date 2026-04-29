import boto3
from botocore.config import Config
from botocore.exceptions import NoCredentialsError, ClientError
import io
from functools import wraps
from typing import Any

from app.config import MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_BUCKET
from utils.logger import get_logger

log = get_logger(__name__)

# boto3 treats MinIO identically to AWS S3
# Initialize s3 client
s3_client = boto3.client(
    "s3",
    endpoint_url=MINIO_ENDPOINT,
    aws_access_key_id=MINIO_ACCESS_KEY,
    aws_secret_access_key=MINIO_SECRET_KEY,
    region_name="us-east-1",  # MinIO usually requires a dummy region
    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
)

PRESIGNED_URL_EXPIRY = 3600  # 1 hour
MAX_RETRIES = 3


def _retry(max_retries=MAX_RETRIES):
    """Decorator that retries a function up to max_retries times on ClientError.
    ClientError is the base exception for all MinIO/S3 transient errors."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except ClientError as e:
                    last_exc = e
                    log.warning(f"{func.__name__} attempt {attempt}/{max_retries} failed: {e}")
            log.error(f"{func.__name__} failed after {max_retries} retries")
            raise last_exc
        return wrapper
    return decorator


def init_bucket():
    try:
        s3_client.head_bucket(Bucket=MINIO_BUCKET)
    except ClientError:
        s3_client.create_bucket(Bucket=MINIO_BUCKET)

@_retry()
def _upload_to_minio(file_object: Any, object_name: str) -> str:
    """Upload data to an S3/MinIO bucket and return the object name.

    `data` can be:
    - a file-like object (e.g. submittedFile.file)
    - a str (will be UTF-8 encoded automatically)
    """
    init_bucket()

    try:
        s3_client.upload_fileobj(file_object, MINIO_BUCKET, object_name)
        return object_name
    except (FileNotFoundError, NoCredentialsError) as e:
        log.error(f"Failed to upload to MinIO: {e}")
        return None
    
def upload_file_to_minio(file_object: Any, object_name: str) -> str:
    """Upload a file to MinIO/S3, in this project, it is the
    submittedFile.file by user from frontend. Becareful of this will read
    the file and the file will be closed.

    Input:
    - file_object: the file
    - object_name: unique name for the uploaded file

    Output: Returns object_name if success, None if fail
    """
    return _upload_to_minio(file_object, object_name)

def upload_string_to_minio(data: str, object_name: str) -> str:
    """Make the input string into a BytesIO file then upload it to MinIO/S3

    Input:
    - data: the file
    - object_name: unique name for the uploaded file

    Output: Returns object_name if success, None if fail
    """
    file_object = io.BytesIO(data.encode("utf-8"))
    return _upload_to_minio(file_object, object_name)


@_retry()
def upload_file_from_path_to_minio(file_path: str, object_name: str) -> str:
    """Upload a file from `file_path` to an S3 bucket and return the object name.
    In the context of this project, it's from a temp file."""
    init_bucket()

    try:
        s3_client.upload_file(file_path, MINIO_BUCKET, object_name)
        return object_name
    except (FileNotFoundError, NoCredentialsError) as e:
        log.error(f"Failed to upload to MinIO: {e}")
        return None

@_retry()
def get_file_from_minio_as_stream(object_name: str) -> io.BytesIO:
    """Download an object from S3/MinIO and return it as a seeked BytesIO stream."""
    file_stream = io.BytesIO()
    response = s3_client.get_object(Bucket=MINIO_BUCKET, Key=object_name)
    file_stream.write(response["Body"].read())
    file_stream.seek(0)
    return file_stream

@_retry()
def get_file_download_link(object_name: str, expiry: int = PRESIGNED_URL_EXPIRY) -> str:
    """Return a presigned download URL for the frontend.
    Backend won't have to store the file in memory."""
    try:
        url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": MINIO_BUCKET, "Key": object_name},
            ExpiresIn=expiry,
        )
        return url
    except ClientError as e:
        log.error(f"Failed to generate presigned URL: {e}")
        return ""
