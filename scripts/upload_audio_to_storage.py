#!/usr/bin/env python
"""Upload local audio fragments to MinIO/S3 for multi-node deployments.

Usage examples:
  python scripts/upload_audio_to_storage.py
  python scripts/upload_audio_to_storage.py --source data/audio --prefix audio/fragments --dry-run
  python scripts/upload_audio_to_storage.py --overwrite

The script is idempotent by default (skips existing objects).
"""

from __future__ import annotations

import argparse
import mimetypes
from pathlib import Path
import sys

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

# Reuse app configuration and storage client setup.
if load_dotenv is not None:
    load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import MINIO_BUCKET  # noqa: E402
from utils.storage import init_bucket, s3_client  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload local audio files to MinIO/S3 bucket."
    )
    parser.add_argument(
        "--source",
        default="data/audio",
        help="Local audio folder to upload from (default: data/audio)",
    )
    parser.add_argument(
        "--prefix",
        default="audio/fragments",
        help="Object key prefix in storage (default: audio/fragments)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing objects instead of skipping them",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print upload actions without changing storage",
    )
    return parser.parse_args()


def object_exists(bucket: str, key: str) -> bool:
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False


def iter_audio_files(source_dir: Path):
    exts = {".wav", ".mp3", ".ogg", ".m4a", ".flac"}
    for path in sorted(source_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in exts:
            yield path


def main() -> int:
    args = parse_args()

    source_dir = Path(args.source)
    if not source_dir.exists() or not source_dir.is_dir():
        print(f"[ERROR] Source directory not found: {source_dir}")
        return 1

    files = list(iter_audio_files(source_dir))
    if not files:
        print(f"[ERROR] No audio files found in: {source_dir}")
        return 1

    if not args.dry_run:
        init_bucket()

    uploaded = 0
    skipped = 0
    failed = 0

    prefix = args.prefix.strip("/")

    for file_path in files:
        rel_path = file_path.relative_to(source_dir).as_posix()
        object_key = f"{prefix}/{rel_path}" if prefix else rel_path

        if not args.overwrite and not args.dry_run and object_exists(MINIO_BUCKET, object_key):
            skipped += 1
            print(f"[SKIP] s3://{MINIO_BUCKET}/{object_key}")
            continue

        if args.dry_run:
            uploaded += 1
            print(f"[DRY ] {file_path} -> s3://{MINIO_BUCKET}/{object_key}")
            continue

        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"

        try:
            with file_path.open("rb") as fh:
                s3_client.upload_fileobj(
                    fh,
                    MINIO_BUCKET,
                    object_key,
                    ExtraArgs={"ContentType": content_type, "CacheControl": "public,max-age=31536000,immutable"},
                )
            uploaded += 1
            print(f"[UPLD] {file_path} -> s3://{MINIO_BUCKET}/{object_key}")
        except Exception as exc:
            failed += 1
            print(f"[FAIL] {file_path} -> s3://{MINIO_BUCKET}/{object_key}: {exc}")

    print("\nSummary")
    print(f"- total:    {len(files)}")
    print(f"- uploaded: {uploaded}")
    print(f"- skipped:  {skipped}")
    print(f"- failed:   {failed}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
