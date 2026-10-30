"""Klien S3 langsung (boto3) untuk Hugging Face S3.

Modul ini menjadi satu-satunya lapisan yang berbicara ke object storage.
Endpoint HF S3 (``https://s3.hf.co/<namespace>``) memakai *path-style
addressing* dan signature v4, sehingga konfigurasi bucket cukup dari
variabel ``SIDEWA_HF_S3_*``.

Semua operasi menormalkan kegagalan boto3 menjadi :class:`S3Error` agar
pemanggil (media sync, Drive) tidak perlu mengetahui detail botocore.
"""

from __future__ import annotations

import logging
import mimetypes
import tempfile
import threading
from pathlib import Path
from typing import Any, Iterator

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

from ..config import settings

logger = logging.getLogger("sidewa.s3")

# Berkas aplikasi maksimal 90 MB (Drive) dan 15 MB (media), jadi unggahan
# normal cukup satu PUT. Ambang multipart dibuat tinggi agar HF S3 tidak
# menerima multipart untuk berkas yang sebenarnya kecil.
TRANSFER_CONFIG = TransferConfig(
    multipart_threshold=200 * 1024 * 1024,
    multipart_chunksize=64 * 1024 * 1024,
    max_concurrency=4,
    use_threads=True,
)

_MISSING_CODES = {
    "404",
    "NoSuchKey",
    "NoSuchBucket",
    "NoSuchUpload",
    "NotFound",
}
_UNSUPPORTED_CODES = {
    "405",
    "501",
    "MethodNotAllowed",
    "NotImplemented",
    "XNotImplemented",
}

_client_lock = threading.Lock()
_client: Any = None


class S3Error(RuntimeError):
    """Kegagalan operasi S3 yang aman ditampilkan ke pengguna."""


class S3NotFound(S3Error):
    """Objek atau bucket tidak ditemukan."""


def configured() -> bool:
    return bool(settings.hf_s3_configured)


def _build_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.hf_s3_endpoint,
        region_name=settings.hf_s3_region or "us-east-1",
        aws_access_key_id=settings.hf_s3_access_key_id,
        aws_secret_access_key=settings.hf_s3_secret_access_key,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=10,
            read_timeout=120,
        ),
    )


def client():
    """Klien boto3 bersama; dibuat sekali per proses."""
    global _client
    if not configured():
        raise S3Error("HF S3 belum dikonfigurasi (SIDEWA_HF_S3_*).")
    with _client_lock:
        if _client is None:
            _client = _build_client()
        return _client


def reset() -> None:
    """Lupakan klien (dipakai setelah konfigurasi berubah pada pengujian)."""
    global _client
    with _client_lock:
        _client = None


# ─────────────────────────────────────────────────────────────────────────────
# Diagnosa kesalahan
# ─────────────────────────────────────────────────────────────────────────────


def is_missing(exc: BaseException) -> bool:
    if isinstance(exc, ClientError):
        error = exc.response.get("Error", {})
        code = str(error.get("Code", ""))
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        return code in _MISSING_CODES or status == 404
    return False


def _is_unsupported(exc: BaseException) -> bool:
    if isinstance(exc, ClientError):
        error = exc.response.get("Error", {})
        code = str(error.get("Code", ""))
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        return code in _UNSUPPORTED_CODES or status in {405, 501}
    return False


def _detail(exc: BaseException) -> str:
    if isinstance(exc, ClientError):
        error = exc.response.get("Error", {})
        code = str(error.get("Code", "")).strip()
        message = str(error.get("Message", "")).strip()
        if code and message:
            return f"{code}: {message}"
        return code or message or str(exc)
    return str(exc) or exc.__class__.__name__


def _raise(operation: str, exc: BaseException) -> None:
    detail = _detail(exc)
    logger.warning("S3 %s gagal: %s", operation, detail)
    if is_missing(exc):
        raise S3NotFound(f"Objek tidak ditemukan ({detail}).") from exc
    raise S3Error(f"Operasi S3 gagal ({detail}).") from exc


# ─────────────────────────────────────────────────────────────────────────────
# Operasi dasar
# ─────────────────────────────────────────────────────────────────────────────


def ping(prefix: str | None = None) -> dict[str, Any]:
    """Pastikan bucket dapat dibaca tanpa membuat/mengubah apa pun."""
    kwargs: dict[str, Any] = {"Bucket": settings.hf_s3_bucket, "MaxKeys": 1}
    if prefix:
        kwargs["Prefix"] = prefix
    try:
        response = client().list_objects_v2(**kwargs)
    except (ClientError, BotoCoreError) as exc:
        _raise("list", exc)
    return {
        "objects": int(response.get("KeyCount") or 0),
        "prefix": prefix or "",
    }


def put_file(
    bucket: str,
    key: str,
    source: str | Path,
    content_type: str | None = None,
    metadata: dict[str, str] | None = None,
) -> None:
    extra: dict[str, Any] = {}
    if content_type:
        extra["ContentType"] = content_type
    if metadata:
        extra["Metadata"] = {str(k): str(v) for k, v in metadata.items()}
    try:
        client().upload_file(
            str(source),
            bucket,
            key,
            ExtraArgs=extra or None,
            Config=TRANSFER_CONFIG,
        )
    except (ClientError, BotoCoreError, OSError) as exc:
        _raise(f"unggah {key}", exc)


def put_bytes(
    bucket: str,
    key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> None:
    try:
        client().put_object(
            Bucket=bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
    except (ClientError, BotoCoreError) as exc:
        _raise(f"tulis {key}", exc)


def download_file(bucket: str, key: str, destination: str | Path) -> None:
    try:
        client().download_file(
            bucket,
            key,
            str(destination),
            Config=TRANSFER_CONFIG,
        )
    except (ClientError, BotoCoreError, OSError) as exc:
        _raise(f"unduh {key}", exc)


def delete_object(bucket: str, key: str) -> bool:
    """Hapus satu objek. ``False`` bila objek memang sudah tidak ada."""
    try:
        client().delete_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if is_missing(exc):
            return False
        _raise(f"hapus {key}", exc)
    except BotoCoreError as exc:
        _raise(f"hapus {key}", exc)
    return True


def copy_object(bucket: str, source_key: str, destination_key: str) -> None:
    """Salin objek di sisi server, dengan fallback unduh→unggah."""
    try:
        client().copy_object(
            Bucket=bucket,
            Key=destination_key,
            CopySource={"Bucket": bucket, "Key": source_key},
        )
        return
    except ClientError as exc:
        if is_missing(exc):
            _raise(f"salin {source_key}", exc)
        if not _is_unsupported(exc):
            _raise(f"salin {source_key}", exc)
        logger.info(
            "S3 copy_object tidak didukung (%s); memakai unduh→unggah.", _detail(exc)
        )
    except BotoCoreError as exc:
        logger.info(
            "S3 copy_object gagal (%s); memakai unduh→unggah.", _detail(exc)
        )

    content_type = mimetypes.guess_type(source_key)[0] or "application/octet-stream"
    handle = tempfile.NamedTemporaryFile(prefix="sidewa-s3-", suffix=".part", delete=False)
    temporary = Path(handle.name)
    handle.close()
    try:
        download_file(bucket, source_key, temporary)
        put_file(bucket, destination_key, temporary, content_type)
    finally:
        temporary.unlink(missing_ok=True)


def exists(bucket: str, key: str, *, is_dir: bool = False) -> bool:
    """Cek objek/folder tanpa bergantung pada HeadObject (tidak selalu ada di HF)."""
    if not key:
        return False
    prefix = key.rstrip("/") + "/" if is_dir else key
    try:
        response = client().list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=20)
    except (ClientError, BotoCoreError) as exc:
        if is_missing(exc):
            return False
        _raise(f"periksa {key}", exc)
    contents = response.get("Contents") or []
    if is_dir:
        return bool(contents)
    return any(str(item.get("Key") or "") == key for item in contents)


def list_dir(bucket: str, prefix: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Daftar isi satu folder: (objek, daftar prefix subfolder)."""
    normalized = prefix if not prefix or prefix.endswith("/") else f"{prefix}/"
    objects: list[dict[str, Any]] = []
    folders: list[str] = []
    paginator = client().get_paginator("list_objects_v2")
    try:
        for page in paginator.paginate(
            Bucket=bucket, Prefix=normalized, Delimiter="/"
        ):
            folders.extend(
                str(item.get("Prefix") or "")
                for item in page.get("CommonPrefixes") or []
            )
            objects.extend(page.get("Contents") or [])
    except (ClientError, BotoCoreError) as exc:
        _raise(f"daftar {normalized}", exc)
    return objects, folders


def iter_objects(bucket: str, prefix: str) -> Iterator[dict[str, Any]]:
    """Iterasi seluruh objek di bawah prefix (rekursif)."""
    normalized = prefix if not prefix or prefix.endswith("/") else f"{prefix}/"
    paginator = client().get_paginator("list_objects_v2")
    try:
        for page in paginator.paginate(Bucket=bucket, Prefix=normalized):
            for item in page.get("Contents") or []:
                yield item
    except (ClientError, BotoCoreError) as exc:
        _raise(f"daftar {normalized}", exc)


def total_size(bucket: str, prefix: str) -> int:
    return sum(int(item.get("Size") or 0) for item in iter_objects(bucket, prefix))


def delete_prefix(bucket: str, prefix: str) -> int:
    """Hapus semua objek di bawah prefix. Mengembalikan jumlah objek."""
    keys = [str(item.get("Key") or "") for item in iter_objects(bucket, prefix)]
    keys = [key for key in keys if key]
    if not keys:
        return 0

    deleted = 0
    for start in range(0, len(keys), 1000):
        batch = [{"Key": key} for key in keys[start : start + 1000]]
        try:
            response = client().delete_objects(
                Bucket=bucket,
                Delete={"Objects": batch, "Quiet": True},
            )
        except ClientError as exc:
            if not _is_unsupported(exc):
                _raise(f"hapus folder {prefix}", exc)
            for item in batch:
                if delete_object(bucket, item["Key"]):
                    deleted += 1
            continue
        except BotoCoreError as exc:
            _raise(f"hapus folder {prefix}", exc)
        errors = response.get("Errors") or []
        deleted += len(batch) - len(errors)
        if errors:
            logger.warning("S3 menghapus %s objek dengan %s galat.", len(batch), len(errors))
    return deleted


def copy_prefix(bucket: str, source_prefix: str, destination_prefix: str) -> int:
    """Salin seluruh objek dari satu prefix folder ke prefix lain."""
    source = source_prefix if source_prefix.endswith("/") else f"{source_prefix}/"
    destination = (
        destination_prefix
        if destination_prefix.endswith("/")
        else f"{destination_prefix}/"
    )
    copied = 0
    for item in iter_objects(bucket, source):
        key = str(item.get("Key") or "")
        if not key:
            continue
        suffix = key[len(source) :]
        copy_object(bucket, key, f"{destination}{suffix}")
        copied += 1
    return copied


def presign(bucket: str, key: str, expires: int = 1800) -> str:
    try:
        return client().generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=max(60, int(expires)),
        )
    except (ClientError, BotoCoreError) as exc:
        _raise(f"tanda tangan {key}", exc)
    raise S3Error("Tautan unduh langsung tidak tersedia.")
