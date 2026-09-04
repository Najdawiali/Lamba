"""
Storage Service — Abstraction over local filesystem and Cloudflare R2.

Configurable via STORAGE_BACKEND env var:
  - "local"  → saves to settings.upload_dir, serves via FastAPI StaticFiles (default, dev)
  - "r2"     → uploads to Cloudflare R2, returns public CDN URL (production)

Both backends return a URL string that the database stores in image_url.
The mobile app's resolveImageUrl() already handles both relative (/uploads/...)
and absolute (https://...) URLs, so zero frontend changes are needed.
"""

import os
import uuid
import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


class StorageService:
    """Unified file storage with local and R2 backends."""

    def __init__(self):
        self._r2_client = None

    def _get_r2_client(self):
        """Lazy-init boto3 S3 client for R2."""
        if self._r2_client is None:
            import boto3
            self._r2_client = boto3.client(
                "s3",
                endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
                aws_access_key_id=settings.r2_access_key_id,
                aws_secret_access_key=settings.r2_secret_access_key,
                region_name="auto",
            )
        return self._r2_client

    def _guess_content_type(self, filename: str) -> str:
        """Guess MIME type from file extension."""
        ext = os.path.splitext(filename)[1].lower()
        return {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".svg": "image/svg+xml",
        }.get(ext, "application/octet-stream")

    async def upload(
        self,
        file_bytes: bytes,
        original_filename: str,
        subfolder: str = "products",
    ) -> str:
        """
        Upload a file and return its public URL.

        Args:
            file_bytes: Raw file content
            original_filename: Original filename (used for extension)
            subfolder: Logical folder within the bucket (e.g., "products", "avatars")

        Returns:
            URL string — relative for local (/uploads/xxx.jpg),
            absolute for R2 (https://pub-xxx.r2.dev/products/xxx.jpg)
        """
        backend = getattr(settings, "storage_backend", "local").lower()

        file_ext = os.path.splitext(original_filename)[1] or ".jpg"
        unique_name = f"{uuid.uuid4()}{file_ext}"

        if backend == "r2":
            return await self._upload_r2(file_bytes, unique_name, subfolder)
        else:
            return self._upload_local(file_bytes, unique_name)

    def _upload_local(self, file_bytes: bytes, filename: str) -> str:
        """Save to local filesystem, return relative URL."""
        os.makedirs(settings.upload_dir, exist_ok=True)
        file_path = os.path.join(settings.upload_dir, filename)
        with open(file_path, "wb") as f:
            f.write(file_bytes)
        logger.info(f"[STORAGE] Local: saved {filename} ({len(file_bytes)} bytes)")
        return f"/uploads/{filename}"

    async def _upload_r2(self, file_bytes: bytes, filename: str, subfolder: str) -> str:
        """Upload to Cloudflare R2, return public CDN URL."""
        import asyncio

        key = f"{subfolder}/{filename}"
        content_type = self._guess_content_type(filename)

        def _do_upload():
            client = self._get_r2_client()
            client.put_object(
                Bucket=settings.r2_bucket_name,
                Key=key,
                Body=file_bytes,
                ContentType=content_type,
            )

        # Run boto3 (sync) in thread pool to avoid blocking the event loop
        await asyncio.get_event_loop().run_in_executor(None, _do_upload)

        public_url = f"{settings.r2_public_url.rstrip('/')}/{key}"
        logger.info(f"[STORAGE] R2: uploaded {key} ({len(file_bytes)} bytes) → {public_url}")
        return public_url

    async def delete(self, url: str) -> None:
        """Delete a file by its URL. Best-effort, no error on failure."""
        backend = getattr(settings, "storage_backend", "local").lower()

        try:
            if backend == "r2" and url.startswith("http"):
                # Extract key from URL
                base = settings.r2_public_url.rstrip("/")
                if url.startswith(base):
                    key = url[len(base):].lstrip("/")
                    import asyncio
                    def _do_delete():
                        client = self._get_r2_client()
                        client.delete_object(Bucket=settings.r2_bucket_name, Key=key)
                    await asyncio.get_event_loop().run_in_executor(None, _do_delete)
                    logger.info(f"[STORAGE] R2: deleted {key}")
            elif url.startswith("/uploads/"):
                filename = url.replace("/uploads/", "")
                file_path = os.path.join(settings.upload_dir, filename)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"[STORAGE] Local: deleted {filename}")
        except Exception as e:
            logger.warning(f"[STORAGE] Delete failed for {url}: {e}")


storage_service = StorageService()
