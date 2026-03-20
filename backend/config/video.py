"""
AdEngineAI — Video Configuration
===================================
Single source of truth for all video generation.

HOW IT WORKS
------------
Set VIDEO_ENV in your .env:
    VIDEO_ENV=development  →  D-ID (free trial, good for testing)
    VIDEO_ENV=production   →  HeyGen (best avatar quality)

Each tool calls:
    from config.video import get_video_config
    cfg = get_video_config()

ASPECT RATIOS GENERATED PER SCRIPT
------------------------------------
    9x16  →  Reels / TikTok / YouTube Shorts
    1x1   →  Instagram Feed / Facebook Feed
    16x9  →  YouTube / LinkedIn

VOICE
-----
    Always ElevenLabs regardless of VIDEO_ENV.
    Audio is generated first, then passed to the video provider.
"""

import os
from dataclasses import dataclass
from enum import Enum

from dotenv import load_dotenv

load_dotenv()


class VideoProvider(str, Enum):
    DID = "did"
    HEYGEN = "heygen"
    MOCK = "mock"          # instant fake URLs — no API needed


@dataclass(frozen=True)
class VideoConfig:
    provider: VideoProvider
    api_key: str
    elevenlabs_api_key: str

    # D-ID specific
    did_presenter_id: str = "amy-Aq6OmGZnMt"   # default D-ID avatar
    did_driver_id: str = "bank"

    # HeyGen specific
    heygen_avatar_id: str = ""
    heygen_voice_id: str = ""

    def is_mock(self) -> bool:
        return self.provider == VideoProvider.MOCK

    def is_dev(self) -> bool:
        return self.provider == VideoProvider.DID

    def is_prod(self) -> bool:
        return self.provider == VideoProvider.HEYGEN


def get_video_config() -> VideoConfig:
    """
    Returns VideoConfig based on VIDEO_ENV.

    VIDEO_ENV=development  → D-ID
    VIDEO_ENV=production   → HeyGen
    VIDEO_ENV=mock         → instant fake URLs (no API needed)
    """
    env = os.getenv("VIDEO_ENV", "mock").lower()
    elevenlabs_key = os.getenv("ELEVENLABS_API_KEY", "")

    if env == "development":
        api_key = os.getenv("DID_API_KEY", "")
        if not api_key:
            raise EnvironmentError(
                "DID_API_KEY is not set. "
                "Add it to .env or set VIDEO_ENV=mock for testing without a video API."
            )
        return VideoConfig(
            provider=VideoProvider.DID,
            api_key=api_key,
            elevenlabs_api_key=elevenlabs_key,
            did_presenter_id=os.getenv("DID_PRESENTER_ID", "amy-Aq6OmGZnMt"),
        )

    elif env == "production":
        api_key = os.getenv("HEYGEN_API_KEY", "")
        if not api_key:
            raise EnvironmentError("HEYGEN_API_KEY is not set for production.")
        return VideoConfig(
            provider=VideoProvider.HEYGEN,
            api_key=api_key,
            elevenlabs_api_key=elevenlabs_key,
            heygen_avatar_id=os.getenv("HEYGEN_AVATAR_ID", ""),
            heygen_voice_id=os.getenv("HEYGEN_VOICE_ID", ""),
        )

    elif env == "mock":
        return VideoConfig(
            provider=VideoProvider.MOCK,
            api_key="mock",
            elevenlabs_api_key=elevenlabs_key,
        )

    else:
        raise ValueError(
            f"Invalid VIDEO_ENV='{env}'. "
            "Must be 'development', 'production', or 'mock'."
        )