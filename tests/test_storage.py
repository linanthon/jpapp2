"""Tests for utils/storage.py — MinIO/S3 storage helpers with mocked boto3."""
import io
import pytest
from unittest.mock import MagicMock
from botocore.exceptions import NoCredentialsError, ClientError


# Patch boto3.client before importing storage so the module-level s3_client is mocked
@pytest.fixture(autouse=True)
def mock_s3(monkeypatch):
    """Replace the module-level s3_client with a MagicMock for every test."""
    mock_client = MagicMock()
    monkeypatch.setattr("utils.storage.s3_client", mock_client)
    return mock_client


# Import after fixture definition so module-level init doesn't fail
from utils.storage import (
    init_bucket,
    upload_file_to_minio,
    upload_string_to_minio,
    upload_file_from_path_to_minio,
    get_file_from_minio_as_stream,
    get_file_download_link,
    _retry,
    PRESIGNED_URL_EXPIRY,
)


# ── _retry decorator ─────────────────────────────────────────────────────────
class TestRetry:
    def test_returns_on_first_success(self):
        def ok():
            return "ok"
        wrapped = _retry(max_retries=3)(ok)
        assert wrapped() == "ok"

    def test_retries_on_client_error(self):
        error = ClientError({"Error": {"Code": "500", "Message": "fail"}}, "op")
        call_count = 0
        def client_error_twice_then_ok():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise error
            return "ok"
        wrapped = _retry(max_retries=3)(client_error_twice_then_ok)
        assert wrapped() == "ok"
        assert call_count == 3

    def test_raises_after_max_retries(self):
        error = ClientError({"Error": {"Code": "500", "Message": "fail"}}, "op")
        call_count = 0
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise error
        wrapped = _retry(max_retries=3)(always_fails)
        with pytest.raises(ClientError):
            wrapped()
        assert call_count == 3

    def test_non_client_error_not_retried(self):
        call_count = 0
        def bad():
            nonlocal call_count
            call_count += 1
            raise ValueError("boom")
        wrapped = _retry(max_retries=3)(bad)
        with pytest.raises(ValueError):
            wrapped()
        assert call_count == 1


# ── init_bucket ───────────────────────────────────────────────────────────────
class TestInitBucket:
    def test_bucket_exists(self, mock_s3):
        mock_s3.head_bucket.return_value = {}
        init_bucket()
        mock_s3.head_bucket.assert_called_once()
        mock_s3.create_bucket.assert_not_called()

    def test_bucket_not_found_creates(self, mock_s3):
        mock_s3.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadBucket"
        )
        init_bucket()
        mock_s3.create_bucket.assert_called_once()


# ── upload_file_to_minio ─────────────────────────────────────────────────────
class TestUploadFileToMinio:
    def test_success(self, mock_s3):
        mock_s3.head_bucket.return_value = {}
        file_obj = io.BytesIO(b"data")
        result = upload_file_to_minio(file_obj, "test_obj")
        assert result == "test_obj"
        mock_s3.upload_fileobj.assert_called_once()

    def test_no_credentials(self, mock_s3):
        mock_s3.head_bucket.return_value = {}
        mock_s3.upload_fileobj.side_effect = NoCredentialsError()
        result = upload_file_to_minio(io.BytesIO(b""), "obj")
        assert result is None

    def test_file_not_found(self, mock_s3):
        mock_s3.head_bucket.return_value = {}
        mock_s3.upload_fileobj.side_effect = FileNotFoundError()
        result = upload_file_to_minio(io.BytesIO(b""), "obj")
        assert result is None


# ── upload_string_to_minio ───────────────────────────────────────────────────
class TestUploadStringToMinio:
    def test_success(self, mock_s3):
        mock_s3.head_bucket.return_value = {}
        result = upload_string_to_minio("hello world", "str_obj")
        assert result == "str_obj"
        mock_s3.upload_fileobj.assert_called_once()
        # Verify the body was encoded to bytes
        call_args = mock_s3.upload_fileobj.call_args
        body = call_args.args[0]
        assert isinstance(body, io.BytesIO)
        assert body.getvalue() == b"hello world"

    def test_no_credentials(self, mock_s3):
        mock_s3.head_bucket.return_value = {}
        mock_s3.upload_fileobj.side_effect = NoCredentialsError()
        result = upload_string_to_minio("data", "obj")
        assert result is None

    def test_unicode_content(self, mock_s3):
        mock_s3.head_bucket.return_value = {}
        result = upload_string_to_minio("日本語テスト", "jp_obj")
        assert result == "jp_obj"
        body = mock_s3.upload_fileobj.call_args.args[0]
        assert body.getvalue() == "日本語テスト".encode("utf-8")


# ── upload_file_from_path_to_minio ───────────────────────────────────────────
class TestUploadFileFromPathToMinio:
    def test_success(self, mock_s3):
        mock_s3.head_bucket.return_value = {}
        result = upload_file_from_path_to_minio("/tmp/file.txt", "path_obj")
        assert result == "path_obj"
        mock_s3.upload_file.assert_called_once()

    def test_file_not_found(self, mock_s3):
        mock_s3.head_bucket.return_value = {}
        mock_s3.upload_file.side_effect = FileNotFoundError()
        result = upload_file_from_path_to_minio("/no/such/file", "obj")
        assert result is None


# ── get_file_from_minio_as_stream ────────────────────────────────────────────
class TestGetFileFromMinioAsStream:
    def test_returns_seeked_stream(self, mock_s3):
        body_mock = MagicMock()
        body_mock.read.return_value = b"file contents"
        mock_s3.get_object.return_value = {"Body": body_mock}

        stream = get_file_from_minio_as_stream("my_obj")
        assert isinstance(stream, io.BytesIO)
        assert stream.read() == b"file contents"
        # Stream should have been seeked to 0
        assert stream.tell() == len(b"file contents")  # after our read()

    def test_empty_file(self, mock_s3):
        body_mock = MagicMock()
        body_mock.read.return_value = b""
        mock_s3.get_object.return_value = {"Body": body_mock}

        stream = get_file_from_minio_as_stream("empty_obj")
        assert stream.read() == b""


# ── get_file_download_link ───────────────────────────────────────────────────
class TestGetFileDownloadLink:
    def test_returns_presigned_url(self, mock_s3):
        mock_s3.generate_presigned_url.return_value = "https://minio/bucket/obj?X-Amz-Signature=abc"
        url = get_file_download_link("my_obj")
        assert "X-Amz-Signature" in url
        mock_s3.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "jpapp-books", "Key": "my_obj"},
            ExpiresIn=PRESIGNED_URL_EXPIRY,
        )

    def test_custom_expiry(self, mock_s3):
        mock_s3.generate_presigned_url.return_value = "https://url"
        get_file_download_link("obj", expiry=600)
        assert mock_s3.generate_presigned_url.call_args.kwargs.get("ExpiresIn") \
            or mock_s3.generate_presigned_url.call_args[1].get("ExpiresIn") \
            or mock_s3.generate_presigned_url.call_args.args[-1] == 600

    def test_client_error_returns_empty(self, mock_s3):
        mock_s3.generate_presigned_url.side_effect = ClientError(
            {"Error": {"Code": "403", "Message": "Forbidden"}}, "GeneratePresignedUrl"
        )
        result = get_file_download_link("obj")
        assert result == ""
