"""
AdEngineAI — D-ID Tool
========================
Generates AI avatar videos using D-ID API.
Used in VIDEO_ENV=development.

D-ID takes an audio file + avatar and renders a lip-synced video.
We pass the ElevenLabs audio URL → D-ID renders the avatar speaking it.

API docs: https://docs.d-id.com/reference/createtalk
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# How long to wait between polling for video status (seconds)
POLL_INTERVAL = 5
# Maximum total wait time for a video render (seconds)
MAX_WAIT = 300   # 5 minutes


@dataclass
class VideoResult:
    hook_type: str
    video_url: str          # public URL of rendered video
    thumbnail_url: str
    duration_secs: float
    aspect_ratio: str       # "9x16" | "1x1" | "16x9"
    provider: str           # "did" | "heygen" | "mock"
    is_mock: bool = False
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and bool(self.video_url)


class DIDTool:
    """
    Generates lip-synced avatar videos using D-ID.

    Usage:
        tool = DIDTool(api_key="your-did-key")
        result = await tool.generate_video(
            audio_url="https://...",
            hook_type="problem",
            aspect_ratio="9x16",
        )
    """

    BASE_URL = "https://api.d-id.com"

    def __init__(
        self,
        api_key: str,
        presenter_id: str = "amy-Aq6OmGZnMt",
        driver_id: str = "bank",
    ):
        self.api_key = api_key
        self.presenter_id = presenter_id
        self.driver_id = driver_id
        self._mock = api_key == "mock"

    async def generate_video(
        self,
        audio_url: str,
        hook_type: str,
        aspect_ratio: str = "9x16",
        audio_bytes: Optional[bytes] = None,
    ) -> VideoResult:
        """
        Generates a video from audio.
        Returns VideoResult — never raises.
        """
        if self._mock:
            return self._mock_result(hook_type, aspect_ratio)

        try:
            return await self._generate_real(
                audio_url, audio_bytes, hook_type, aspect_ratio
            )
        except Exception as e:
            logger.error(f"D-ID generation failed for {hook_type}: {e}")
            return VideoResult(
                hook_type=hook_type,
                video_url="",
                thumbnail_url="",
                duration_secs=0.0,
                aspect_ratio=aspect_ratio,
                provider="did",
                is_mock=True,
                error=str(e),
            )

    async def generate_all_ratios(
        self,
        audio_url: str,
        hook_type: str,
        audio_bytes: Optional[bytes] = None,
    ) -> dict[str, VideoResult]:
        """
        Generates 9x16, 1x1, and 16x9 versions concurrently.
        Returns dict keyed by aspect ratio.
        """
        tasks = {
            ratio: self.generate_video(audio_url, hook_type, ratio, audio_bytes)
            for ratio in ["9x16", "1x1", "16x9"]
        }
        results = await asyncio.gather(*tasks.values())
        return dict(zip(tasks.keys(), results))

    # ------------------------------------------------------------------
    # Real D-ID API
    # ------------------------------------------------------------------

    async def _generate_real(
        self,
        audio_url: str,
        audio_bytes: Optional[bytes],
        hook_type: str,
        aspect_ratio: str,
    ) -> VideoResult:
        try:
            import httpx
            import base64
        except ImportError:
            raise ImportError("httpx not installed.")

        headers = {
            "Authorization": f"Basic {base64.b64encode(self.api_key.encode()).decode()}",
            "Content-Type": "application/json",
        }

        # Build audio URL — base64 encode bytes if no hosted URL
        if audio_bytes and (not audio_url or audio_url.startswith("local://")):
            encoded = base64.b64encode(audio_bytes).decode()
            audio_script_url = f"data:audio/mp3;base64,{encoded}"
        else:
            audio_script_url = audio_url

        payload = {
            "source_url": "https://d-id-public-bucket.s3.us-east-1.amazonaws.com/alice.jpg",
            "script": {
                "type": "audio",
                "audio_url": audio_script_url,
            },
            "config": {
                "stitch": True,
                "result_format": "mp4",
                "fluent": True,
                "pad_audio": 0.5,
            },
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/talks",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            talk_id = response.json()["id"]
            logger.info(f"D-ID job submitted: {talk_id} ({hook_type} {aspect_ratio})")

            video_url = await self._poll_until_ready(client, headers, talk_id)

        return VideoResult(
            hook_type=hook_type,
            video_url=video_url,
            thumbnail_url="",
            duration_secs=60.0,
            aspect_ratio=aspect_ratio,
            provider="did",
            is_mock=False,
        )

    async def _poll_until_ready(
        self, client, headers: dict, talk_id: str
    ) -> str:
        """Polls D-ID until the video is ready. Returns the video URL."""
        elapsed = 0
        while elapsed < MAX_WAIT:
            await asyncio.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL

            response = await client.get(
                f"{self.BASE_URL}/talks/{talk_id}",
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            status = data.get("status")

            if status == "done":
                url = data.get("result_url", "")
                logger.info(f"D-ID render complete: {talk_id} → {url}")
                return url
            elif status == "error":
                raise RuntimeError(
                    f"D-ID render failed: {data.get('error', 'unknown error')}"
                )
            else:
                logger.debug(f"D-ID polling {talk_id}: {status} ({elapsed}s)")

        raise TimeoutError(f"D-ID render timed out after {MAX_WAIT}s")

    # ------------------------------------------------------------------
    # Mock
    # ------------------------------------------------------------------

    @staticmethod
    def _mock_result(hook_type: str, aspect_ratio: str) -> VideoResult:
        return VideoResult(
            hook_type=hook_type,
            video_url=f"https://mock-video.adengineai.com/{hook_type}_{aspect_ratio}.mp4",
            thumbnail_url=f"https://mock-video.adengineai.com/{hook_type}_thumb.jpg",
            duration_secs=60.0,
            aspect_ratio=aspect_ratio,
            provider="mock",
            is_mock=True,
        )