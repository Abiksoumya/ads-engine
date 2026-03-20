"""
AdEngineAI — Storage Configuration
=====================================
Single source of truth for all file storage across every agent.

HOW IT WORKS
------------
Set STORAGE_ENV in your .env:
    STORAGE_ENV=development  →  Cloudinary (free tier, great for testing)
    STORAGE_ENV=production   →  AWS S3 + CloudFront CDN

Each agent / service calls:
    from config.storage import get_storage
    storage = get_storage()
    url = await storage.upload_video(file_bytes, filename)

No agent ever imports cloudinary or boto3 directly.
Swap environments by changing one line in .env.

WHAT GETS STORED
----------------
    videos/     → rendered MP4 files (9:16, 1:1, 16:9 variants)
    audio/      → ElevenLabs voice files
    thumbnails/ → video thumbnail images

FOLDER STRUCTURE (same in both environments)
    adengineai/{user_id}/{campaign_id}/videos/{hook_type}_{ratio}.mp4
    adengineai/{user_id}/{campaign_id}/audio/{hook_type}.mp3
    adengineai/{user_id}/{campaign_id}/thumbnails/{hook_type}.jpg
"""

import os
from dataclasses import dataclass
from enum import Enum

from dotenv import load_dotenv

load_dotenv()


class StorageProvider(str, Enum):
    CLOUDINARY = "cloudinary"
    S3 = "s3"


@dataclass(frozen=True)
class StorageConfig:
    provider: StorageProvider

    # Cloudinary
    cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""

    # S3
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    s3_bucket: str = ""
    aws_region: str = "us-east-1"
    cloudfront_url: str = ""

    def is_dev(self) -> bool:
        return self.provider == StorageProvider.CLOUDINARY

    def is_prod(self) -> bool:
        return self.provider == StorageProvider.S3


def get_storage_config() -> StorageConfig:
    """
    Returns StorageConfig based on STORAGE_ENV.
    Call this once and pass the config down — don't call it in a loop.
    """
    env = os.getenv("STORAGE_ENV", "development").lower()

    if env == "development":
        return StorageConfig(
            provider=StorageProvider.CLOUDINARY,
            cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME", ""),
            cloudinary_api_key=os.getenv("CLOUDINARY_API_KEY", ""),
            cloudinary_api_secret=os.getenv("CLOUDINARY_API_SECRET", ""),
        )
    elif env == "production":
        return StorageConfig(
            provider=StorageProvider.S3,
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", ""),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", ""),
            s3_bucket=os.getenv("AWS_S3_BUCKET", "adengineai-videos"),
            aws_region=os.getenv("AWS_REGION", "us-east-1"),
            cloudfront_url=os.getenv("AWS_CLOUDFRONT_URL", ""),
        )
    else:
        raise ValueError(
            f"Invalid STORAGE_ENV='{env}'. Must be 'development' or 'production'."
        )