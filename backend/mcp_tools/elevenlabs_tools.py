"""
AdEngineAI — ElevenLabs Tool
==============================
Generates voiceover audio from script text.
Called by each render agent in the Production Crew.

Always uses ElevenLabs regardless of VIDEO_ENV —
audio quality matters in both dev and prod.

If ELEVENLABS_API_KEY is not set, falls back to mock audio gracefully.
"""

import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Default voice IDs — good for ad content
# Find more at: https://api.elevenlabs.io/v1/voices
# Free premade voices — all work on your current plan
DEFAULT_VOICE_ID = "EXAVITQu4vr4xnSDxMaL"   # Sarah — mature, confident, good for ads

VOICES = {
    "professional": "EXAVITQu4vr4xnSDxMaL",  # Sarah — mature, reassuring
    "casual":       "iP95p4xoKVk53GoZ742B",  # Chris — charming, down to earth
    "energetic":    "TX3LPaxmHKxFdv7VOQHJ",  # Liam — energetic, social media creator
    "warm":         "cgSgspJ2msm6clMCkdW9",  # Jessica — playful, bright, warm
    "authoritative":"nPczCjzI2devNBz1zQrb",  # Brian — deep, resonant, comforting
}


@dataclass
class AudioResult:
    hook_type: str
    audio_url: str          # Cloudinary or S3 URL after upload
    audio_bytes: bytes      # raw audio — used for upload
    voice_id: str
    duration_secs: float
    is_mock: bool = False
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and bool(self.audio_url or self.audio_bytes)


class ElevenLabsTool:
    """
    Generates voiceover audio from script text.

    Usage:
        tool = ElevenLabsTool(api_key="your-key")
        result = await tool.generate(
            script="Your full script text here...",
            hook_type="problem",
            voice_style="professional",
        )
    """

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY", "")
        self._mock = not bool(self.api_key)
        if self._mock:
            logger.warning(
                "ELEVENLABS_API_KEY not set — using mock audio. "
                "Add key to .env for real voice generation."
            )

    async def generate(
        self,
        script: str,
        hook_type: str,
        voice_style: str = "professional",
    ) -> AudioResult:
        """
        Generates audio for a script.
        Returns AudioResult — never raises.
        Falls back to mock if API key missing or call fails.
        """
        if self._mock:
            return self._mock_result(hook_type)

        try:
            return await self._generate_real(script, hook_type, voice_style)
        except Exception as e:
            logger.error(f"ElevenLabs generation failed for {hook_type}: {e}")
            return AudioResult(
                hook_type=hook_type,
                audio_url="",
                audio_bytes=b"",
                voice_id=VOICES.get(voice_style, DEFAULT_VOICE_ID),
                duration_secs=0.0,
                is_mock=True,
                error=str(e),
            )

    async def generate_batch(
        self,
        scripts: list[tuple[str, str]],   # list of (script_text, hook_type)
        voice_style: str = "professional",
    ) -> list[AudioResult]:
        """
        Generates audio for multiple scripts concurrently.
        Returns results in same order as input.
        """
        import asyncio
        tasks = [
            self.generate(script, hook_type, voice_style)
            for script, hook_type in scripts
        ]
        return await asyncio.gather(*tasks)

    # ------------------------------------------------------------------
    # Real ElevenLabs API call
    # ------------------------------------------------------------------

    async def _generate_real(
        self, script: str, hook_type: str, voice_style: str
    ) -> AudioResult:
        try:
            from elevenlabs.client import ElevenLabs
        except ImportError:
            raise ImportError("elevenlabs not installed. Run: pip install elevenlabs")

        voice_id = VOICES.get(voice_style, DEFAULT_VOICE_ID)

        # ElevenLabs SDK is synchronous — run in executor to avoid blocking
        import asyncio
        loop = asyncio.get_event_loop()

        def _generate_sync():
            client = ElevenLabs(api_key=self.api_key)
            audio_generator = client.text_to_speech.convert(
                text=script,
                voice_id=voice_id,
                model_id="eleven_turbo_v2",
                output_format="mp3_44100_128",
            )
            # Convert generator to bytes
            return b"".join(audio_generator)

        audio_bytes = await loop.run_in_executor(None, _generate_sync)

        duration = self._estimate_duration(script)
        logger.info(
            f"ElevenLabs: generated {hook_type} audio "
            f"({len(audio_bytes)} bytes, ~{duration:.1f}s)"
        )

        return AudioResult(
            hook_type=hook_type,
            audio_url="",
            audio_bytes=audio_bytes,
            voice_id=voice_id,
            duration_secs=duration,
            is_mock=False,
        )


    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_duration(script: str) -> float:
        """Estimates audio duration from word count (~2.5 words/second for ads)."""
        words = len(script.split())
        return words / 2.5

    @staticmethod
    def _mock_result(hook_type: str) -> AudioResult:
        """Returns a mock audio result for testing without API key."""
        return AudioResult(
            hook_type=hook_type,
            audio_url=f"https://mock-audio.adengineai.com/{hook_type}.mp3",
            audio_bytes=b"mock_audio_bytes",
            voice_id=DEFAULT_VOICE_ID,
            duration_secs=58.0,
            is_mock=True,
        )