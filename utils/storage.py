import boto3
from botocore.exceptions import NoCredentialsError, ClientError
import io
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
    region_name="us-east-1" # MinIO usually requires a dummy region
)

def init_bucket():
    try:
        s3_client.head_bucket(Bucket=MINIO_BUCKET)
    except ClientError:
        s3_client.create_bucket(Bucket=MINIO_BUCKET)

def upload_file_to_minio(file_object: Any, object_name: str) -> str:
    """Upload a file to an S3 bucket and return the object name.
    In the context of this project, it's directly from `submittedFile.file`."""
    init_bucket()

    #TODO: add retry
    try:
        s3_client.upload_fileobj(file_object, MINIO_BUCKET, object_name)
        return object_name
    except (FileNotFoundError, NoCredentialsError) as e:
        log.error(f"Failed to upload to MinIO: {e}")
        return None
    
def upload_file_from_path_to_minio(file_path: str, object_name: str) -> str:
    """Upload a file from `file_path` to an S3 bucket and return the object name.
    In the context of this project, it's from a temp file."""
    init_bucket()

    #TODO: add retry
    try:
        s3_client.upload_file(file_path, MINIO_BUCKET, object_name)
        return object_name
    except (FileNotFoundError, NoCredentialsError) as e:
        log.error(f"Failed to upload to MinIO: {e}")
        return None

def get_file_from_minio_as_stream(object_name):
    # Create a BytesIO buffer (since files are binary)
    file_stream = io.BytesIO()
    #TODO: add retry
    response = s3_client.get_object(Bucket=MINIO_BUCKET, Key=object_name)
    file_stream.write(response["Body"].read())
    file_stream.seek(0)
    return file_stream

def get_file_download_link(object_name):
    """Return download link for frontend to do the download.
    Backend won't have to store the file in memory"""
    #TODO
    # http://minio.../bucket/file_abc123.pdf?X-Amz-Algorithm=...&X-Amz-Signature=xyz&Expires=360
    # X-Amz-Signature = generated using your secret key
    return ""
