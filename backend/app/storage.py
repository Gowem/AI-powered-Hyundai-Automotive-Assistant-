"""File storage: Supabase Storage (production) or local disk (development / reviewers).

Object keys are `{document_id}.pdf` inside the configured bucket.
"""

import asyncio
import hashlib
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from urllib.parse import parse_qs, urlparse

import httpx
import jwt

from app.config import Settings, get_settings

VIEW_URL_TTL = 600


class StorageError(Exception):
    pass


@dataclass
class SignedUpload:
    path: str
    token: str | None
    upload_url: str | None


@dataclass
class DownloadedFile:
    local_path: str
    size: int
    sha256: str
    head: bytes

    def cleanup(self) -> None:
        try:
            os.unlink(self.local_path)
        except FileNotFoundError:
            pass


class Storage(Protocol):
    mode: str

    async def create_signed_upload(self, key: str, document_id: uuid.UUID) -> SignedUpload: ...
    async def download_to_temp(self, key: str) -> DownloadedFile: ...
    async def signed_view_url(self, key: str, document_id: uuid.UUID) -> str: ...
    async def delete(self, key: str) -> None: ...
    async def exists(self, key: str) -> bool: ...


def _hash_file(path: str) -> tuple[int, str, bytes]:
    h = hashlib.sha256()
    size = 0
    head = b""
    with open(path, "rb") as f:
        while block := f.read(1024 * 1024):
            if not head:
                head = block[:16]
            size += len(block)
            h.update(block)
    return size, h.hexdigest(), head


class SupabaseStorage:
    mode = "supabase"

    def __init__(self, settings: Settings) -> None:
        if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
            raise StorageError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for STORAGE_BACKEND=supabase")
        self.base = settings.SUPABASE_URL.rstrip("/") + "/storage/v1"
        self.bucket = settings.SUPABASE_BUCKET
        key = settings.SUPABASE_SERVICE_ROLE_KEY
        self.headers = {"Authorization": f"Bearer {key}", "apikey": key}

    def _client(self, timeout: float = 30) -> httpx.AsyncClient:
        return httpx.AsyncClient(headers=self.headers, timeout=timeout)

    async def create_signed_upload(self, key: str, document_id: uuid.UUID) -> SignedUpload:
        async with self._client() as c:
            r = await c.post(f"{self.base}/object/upload/sign/{self.bucket}/{key}", headers={"x-upsert": "true"})
        if r.status_code >= 400:
            raise StorageError(f"Could not create signed upload URL ({r.status_code})")
        url = r.json().get("url", "")
        token = parse_qs(urlparse(url).query).get("token", [None])[0]
        if not token:
            raise StorageError("Signed upload URL did not contain a token")
        return SignedUpload(path=key, token=token, upload_url=None)

    async def download_to_temp(self, key: str) -> DownloadedFile:
        fd, tmp = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        try:
            async with (
                self._client(timeout=300) as c,
                c.stream("GET", f"{self.base}/object/authenticated/{self.bucket}/{key}") as r,
            ):
                if r.status_code == 404 or r.status_code == 400:
                    raise StorageError("Uploaded file not found in storage")
                if r.status_code >= 400:
                    raise StorageError(f"Storage download failed ({r.status_code})")
                with open(tmp, "wb") as f:  # noqa: ASYNC230 - streamed chunked writes
                    async for block in r.aiter_bytes(1024 * 1024):
                        f.write(block)
            size, digest, head = await asyncio.to_thread(_hash_file, tmp)
            return DownloadedFile(tmp, size, digest, head)
        except BaseException:
            os.unlink(tmp)
            raise

    async def signed_view_url(self, key: str, document_id: uuid.UUID) -> str:
        async with self._client() as c:
            r = await c.post(f"{self.base}/object/sign/{self.bucket}/{key}", json={"expiresIn": VIEW_URL_TTL})
        if r.status_code >= 400:
            raise StorageError(f"Could not sign view URL ({r.status_code})")
        signed = r.json().get("signedURL") or r.json().get("signedUrl")
        if not signed:
            raise StorageError("Storage did not return a signed URL")
        return self.base + signed if signed.startswith("/") else signed

    async def delete(self, key: str) -> None:
        async with self._client() as c:
            r = await c.request("DELETE", f"{self.base}/object/{self.bucket}", json={"prefixes": [key]})
        if r.status_code >= 400 and r.status_code != 404:
            raise StorageError(f"Storage delete failed ({r.status_code})")

    async def exists(self, key: str) -> bool:
        async with self._client() as c:
            r = await c.head(f"{self.base}/object/authenticated/{self.bucket}/{key}")
        return r.status_code == 200


class LocalStorage:
    """Stores files under LOCAL_UPLOAD_DIR. Uploads go to PUT /api/documents/{id}/upload."""

    mode = "local"

    def __init__(self, settings: Settings) -> None:
        self.root = Path(settings.LOCAL_UPLOAD_DIR).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.secret = settings.JWT_SECRET

    def path_for(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents:
            raise StorageError("Invalid storage key")
        return p

    def _token(self, document_id: uuid.UUID, purpose: str, ttl: int) -> str:
        now = datetime.now(UTC)
        return jwt.encode(
            {"doc": str(document_id), "p": purpose, "exp": int((now + timedelta(seconds=ttl)).timestamp())},
            self.secret,
            algorithm="HS256",
        )

    def verify_token(self, token: str, document_id: uuid.UUID, purpose: str) -> bool:
        try:
            data = jwt.decode(token, self.secret, algorithms=["HS256"])
        except jwt.PyJWTError:
            return False
        return data.get("doc") == str(document_id) and data.get("p") == purpose

    async def create_signed_upload(self, key: str, document_id: uuid.UUID) -> SignedUpload:
        token = self._token(document_id, "upload", 3600)
        return SignedUpload(path=key, token=token, upload_url=f"/api/documents/{document_id}/upload")

    async def download_to_temp(self, key: str) -> DownloadedFile:
        src = self.path_for(key)
        if not src.exists():
            raise StorageError("Uploaded file not found in storage")
        fd, tmp = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        await asyncio.to_thread(shutil.copyfile, src, tmp)
        size, digest, head = await asyncio.to_thread(_hash_file, tmp)
        return DownloadedFile(tmp, size, digest, head)

    async def signed_view_url(self, key: str, document_id: uuid.UUID) -> str:
        return f"/api/documents/{document_id}/file?token={self._token(document_id, 'view', VIEW_URL_TTL)}"

    async def delete(self, key: str) -> None:
        try:
            self.path_for(key).unlink()
        except FileNotFoundError:
            pass

    async def exists(self, key: str) -> bool:
        return self.path_for(key).exists()


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        s = get_settings()
        _storage = SupabaseStorage(s) if s.STORAGE_BACKEND == "supabase" else LocalStorage(s)
    return _storage


def set_storage(storage: Storage | None) -> None:
    global _storage
    _storage = storage
