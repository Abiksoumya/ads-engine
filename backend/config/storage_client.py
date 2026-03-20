"""
AdEngineAI — Storage Client
=============================
Unified file storage interface — same API for Cloudinary and S3.

Usage anywhere in the codebase:
    from config.storage import get_storage_config
    from config.storage_client import StorageClient

    cfg = get_storage_config()
    client = StorageClient(cfg)

    url = await client.upload_video(video_bytes, "campaign_123", "problem", "9x16")
    # Returns public URL — same shape whether Cloudinary or S3
"""

import logging
import os
from pathlib import Path
from typing import Optional

from config.storage import StorageConfig, StorageProvider

logger = logging.getLogger(__name__)


class StorageClient:

    def __init__(self, cfg: StorageConfig):
        self.cfg = cfg
        self._init_provider()

    def _init_provider(self):
        if self.cfg.provider == StorageProvider.CLOUDINARY:
            self._init_cloudinary()
        else:
            self._init_s3()

    def _init_cloudinary(self):
        try:
            import cloudinary
            cloudinary.config(
                cloud_name=self.cfg.cloud_name,
                api_key=self.cfg.cloudinary_api_key,
                api_secret=self.cfg.cloudinary_api_secret,
                secure=True,
            )
            logger.info(f"Storage: Cloudinary initialised (cloud={self.cfg.cloud_name})")
        except ImportError:
            raise ImportError("cloudinary not installed. Run: pip install cloudinary")

    def _init_s3(self):
        try:
            import boto3
            self._s3 = boto3.client(
                "s3",
                aws_access_key_id=self.cfg.aws_access_key_id,
                aws_secret_access_key=self.cfg.aws_secret_access_key,
                region_name=self.cfg.aws_region,
            )
            logger.info(f"Storage: S3 initialised (bucket={self.cfg.s3_bucket})")
        except ImportError:
            raise ImportError("boto3 not installed. Run: pip install boto3")

    # ------------------------------------------------------------------
    # Public API — same interface regardless of provider
    # ------------------------------------------------------------------

    async def upload_video(
        self,
        file_bytes: bytes,
        campaign_id: str,
        hook_type: str,
        ratio: str,          # "9x16" | "1x1" | "16x9"
        user_id: str = "dev",
    ) -> str:
        """
        Uploads a rendered video. Returns public URL.

        Path: adengineai/{user_id}/{campaign_id}/videos/{hook_type}_{ratio}.mp4
        """
        key = f"adengineai/{user_id}/{campaign_id}/videos/{hook_type}_{ratio}.mp4"
        return await self._upload(file_bytes, key, content_type="video/mp4")

    async def upload_audio(
        self,
        file_bytes: bytes,
        campaign_id: str,
        hook_type: str,
        user_id: str = "dev",
    ) -> str:
        """
        Uploads a voice audio file. Returns public URL.

        Path: adengineai/{user_id}/{campaign_id}/audio/{hook_type}.mp3
        """
        key = f"adengineai/{user_id}/{campaign_id}/audio/{hook_type}.mp3"
        return await self._upload(file_bytes, key, content_type="audio/mpeg")

    async def upload_thumbnail(
        self,
        file_bytes: bytes,
        campaign_id: str,
        hook_type: str,
        user_id: str = "dev",
    ) -> str:
        """
        Uploads a video thumbnail. Returns public URL.

        Path: adengineai/{user_id}/{campaign_id}/thumbnails/{hook_type}.jpg
        """
        key = f"adengineai/{user_id}/{campaign_id}/thumbnails/{hook_type}.jpg"
        return await self._upload(file_bytes, key, content_type="image/jpeg")

    async def delete_file(self, url: str) -> bool:
        """Deletes a file by its public URL. Returns True on success."""
        if self.cfg.provider == StorageProvider.CLOUDINARY:
            return await self._delete_cloudinary(url)
        else:
            return await self._delete_s3(url)

    def get_public_url(self, key: str) -> str:
        """
        Converts a storage key to a public URL.
        For S3 + CloudFront: uses CDN URL.
        For Cloudinary: constructs delivery URL.
        """
        if self.cfg.provider == StorageProvider.CLOUDINARY:
            return f"https://res.cloudinary.com/{self.cfg.cloud_name}/video/upload/{key}"
        else:
            if self.cfg.cloudfront_url:
                return f"{self.cfg.cloudfront_url.rstrip('/')}/{key}"
            return f"https://{self.cfg.s3_bucket}.s3.{self.cfg.aws_region}.amazonaws.com/{key}"

    # ------------------------------------------------------------------
    # Private: provider implementations
    # ------------------------------------------------------------------

    async def _upload(self, file_bytes: bytes, key: str, content_type: str) -> str:
        if self.cfg.provider == StorageProvider.CLOUDINARY:
            return await self._upload_cloudinary(file_bytes, key, content_type)
        else:
            return await self._upload_s3(file_bytes, key, content_type)

    async def _upload_cloudinary(self, file_bytes: bytes, key: str, content_type: str) -> str:
        import asyncio
        import cloudinary.uploader

        resource_type = "video" if "video" in content_type or "audio" in content_type else "image"

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: cloudinary.uploader.upload(
                file_bytes,
                public_id=key.replace("/", "_").replace(".", "_"),
                resource_type=resource_type,
                folder="adengineai",
                overwrite=True,
            )
        )
        url = result.get("secure_url", "")
        logger.info(f"Cloudinary upload: {key} → {url}")
        return url

    async def _upload_s3(self, file_bytes: bytes, key: str, content_type: str) -> str:
        import asyncio

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self._s3.put_object(
                Bucket=self.cfg.s3_bucket,
                Key=key,
                Body=file_bytes,
                ContentType=content_type,
            )
        )
        url = self.get_public_url(key)
        logger.info(f"S3 upload: {key} → {url}")
        return url

    async def _delete_cloudinary(self, url: str) -> bool:
        import asyncio
        import cloudinary.uploader

        public_id = url.split("/upload/")[-1].split(".")[0]
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: cloudinary.uploader.destroy(public_id)
        )
        return result.get("result") == "ok"

    async def _delete_s3(self, url: str) -> bool:
        import asyncio

        key = url.split(f"{self.cfg.s3_bucket}/")[-1]
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self._s3.delete_object(Bucket=self.cfg.s3_bucket, Key=key)
        )
        return True