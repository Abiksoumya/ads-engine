"""
AdEngineAI — Production Crew
==============================
Framework: CrewAI (parallel multi-agent execution)

Why CrewAI here?
    5 scripts render simultaneously — one agent per script.
    CrewAI handles parallel execution and result aggregation natively.
    Without it you'd manually manage asyncio tasks.

Pipeline per render agent:
    1. Generate voice (ElevenLabs)
    2. Upload audio (Cloudinary/S3)
    3. Generate video (D-ID/HeyGen) — all 3 aspect ratios
    4. Upload videos (Cloudinary/S3)
    5. Return RenderResult

Used by: orchestrator/agent.py
Input:   list[Script] (5 scripts from Director)
Output:  list[RenderResult] (5 rendered campaigns)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

from config.video import get_video_config, VideoProvider
from config.storage import get_storage_config
from config.storage_client import StorageClient
from director.agent import Script
from mcp_tools.elevenlabs_tools import ElevenLabsTool, AudioResult
from mcp_tools.did_tools import DIDTool, VideoResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output type
# ---------------------------------------------------------------------------

@dataclass
class RenderResult:
    """Full render output for one hook variant."""
    hook_type: str
    script: Script

    # Audio
    audio: Optional[AudioResult] = None

    # Videos per aspect ratio
    video_9x16: Optional[VideoResult] = None   # Reels / TikTok
    video_1x1: Optional[VideoResult] = None    # Feed
    video_16x9: Optional[VideoResult] = None   # YouTube

    # Errors
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return (
            len(self.errors) == 0
            and self.audio is not None
            and self.video_9x16 is not None
        )

    @property
    def is_mock(self) -> bool:
        return (
            (self.audio is not None and self.audio.is_mock)
            or (self.video_9x16 is not None and self.video_9x16.is_mock)
        )

    def best_video_url(self) -> str:
        """Returns the best available video URL."""
        for video in [self.video_9x16, self.video_1x1, self.video_16x9]:
            if video and video.success:
                return video.video_url
        return ""


# ---------------------------------------------------------------------------
# Single render agent — one per script
# ---------------------------------------------------------------------------

class RenderAgent:
    """
    Renders one script into audio + video.
    5 of these run concurrently in the Production Crew.
    """

    def __init__(
        self,
        script: Script,
        elevenlabs: ElevenLabsTool,
        did: DIDTool,
        storage: StorageClient,
        campaign_id: str,
        user_id: str = "dev",
        voice_style: str = "professional",
    ):
        self.script = script
        self.elevenlabs = elevenlabs
        self.did = did
        self.storage = storage
        self.campaign_id = campaign_id
        self.user_id = user_id
        self.voice_style = voice_style

    async def render(self) -> RenderResult:
        """
        Runs the full render pipeline for one script.
        Never raises — errors go into RenderResult.errors.
        """
        result = RenderResult(
            hook_type=self.script.hook_type,
            script=self.script,
        )

        logger.info(f"RenderAgent starting: {self.script.hook_type}")

        # Step 1 — Generate audio
        try:
            audio = await self.elevenlabs.generate(
                script=self.script.script,
                hook_type=self.script.hook_type,
                voice_style=self.voice_style,
            )
            result.audio = audio

            # Upload audio — non-fatal if storage fails
            if audio.audio_bytes and not audio.is_mock:
                try:
                    audio_url = await self.storage.upload_audio(
                        file_bytes=audio.audio_bytes,
                        campaign_id=self.campaign_id,
                        hook_type=self.script.hook_type,
                        user_id=self.user_id,
                    )
                    audio.audio_url = audio_url
                except Exception as upload_err:
                    logger.warning(
                        f"Audio upload skipped ({self.script.hook_type}): {upload_err}"
                    )
                    audio.audio_url = f"local://{self.script.hook_type}.mp3"

            logger.info(
                f"Audio ready: {self.script.hook_type} "
                f"({'mock' if audio.is_mock else 'real'}, ~{audio.duration_secs:.0f}s)"
            )

        except Exception as e:
            error = f"Audio generation failed ({self.script.hook_type}): {e}"
            logger.error(error)
            result.errors.append(error)
            return result

        # Step 2 — Generate videos (all 3 aspect ratios concurrently)
        try:
            audio_url = result.audio.audio_url if result.audio else ""
            audio_bytes = result.audio.audio_bytes if result.audio else None

            videos = await self.did.generate_all_ratios(
                audio_url=audio_url,
                hook_type=self.script.hook_type,
                audio_bytes=audio_bytes,
            )

            # Upload videos if real (skip upload for mock URLs)
            for ratio, video in videos.items():
                if video.success and not video.is_mock:
                    try:
                        import httpx
                        async with httpx.AsyncClient(timeout=60.0) as client:
                            r = await client.get(video.video_url)
                            video_bytes = r.content
                        stored_url = await self.storage.upload_video(
                            file_bytes=video_bytes,
                            campaign_id=self.campaign_id,
                            hook_type=self.script.hook_type,
                            ratio=ratio,
                            user_id=self.user_id,
                        )
                        video.video_url = stored_url
                    except Exception as e:
                        logger.warning(f"Video upload to storage failed ({ratio}): {e} — keeping D-ID URL")
                        # D-ID URL stays as-is — already set, don't overwrite

            result.video_9x16 = videos.get("9x16")
            result.video_1x1 = videos.get("1x1")
            result.video_16x9 = videos.get("16x9")

            logger.info(
                f"Videos ready: {self.script.hook_type} "
                f"({'mock' if result.is_mock else 'real'})"
            )

        except Exception as e:
            error = f"Video generation failed ({self.script.hook_type}): {e}"
            logger.error(error)
            result.errors.append(error)

        return result


# ---------------------------------------------------------------------------
# Production Crew — runs 5 RenderAgents in parallel
# ---------------------------------------------------------------------------

class ProductionCrew:
    """
    Renders all 5 scripts in parallel.
    One RenderAgent per script — all run concurrently via asyncio.gather.

    Usage:
        crew = ProductionCrew(campaign_id="campaign_123")
        results = await crew.render(scripts)
    """

    def __init__(
        self,
        campaign_id: str,
        user_id: str = "dev",
        voice_style: str = "professional",
    ):
        self.campaign_id = campaign_id
        self.user_id = user_id
        self.voice_style = voice_style

        # Initialise tools from config
        video_cfg = get_video_config()
        storage_cfg = get_storage_config()

        self.elevenlabs = ElevenLabsTool(api_key=video_cfg.elevenlabs_api_key)
        self.storage = StorageClient(storage_cfg)

        # Video provider — D-ID or mock
        if video_cfg.provider == VideoProvider.DID:
            self.did = DIDTool(
                api_key=video_cfg.api_key,
                presenter_id=video_cfg.did_presenter_id,
            )
        else:
            # Mock provider
            self.did = DIDTool(api_key="mock")

        logger.info(
            f"ProductionCrew ready — "
            f"video: {video_cfg.provider} | "
            f"audio: {'real' if video_cfg.elevenlabs_api_key else 'mock'} | "
            f"storage: {storage_cfg.provider}"
        )

    async def render(self, scripts: list[Script]) -> list[RenderResult]:
        """
        Renders all scripts in parallel.
        Returns results in same order as input scripts.
        Always returns 5 results — failed renders have errors in result.errors.
        """
        logger.info(f"ProductionCrew: rendering {len(scripts)} scripts in parallel")

        agents = [
            RenderAgent(
                script=script,
                elevenlabs=self.elevenlabs,
                did=self.did,
                storage=self.storage,
                campaign_id=self.campaign_id,
                user_id=self.user_id,
                voice_style=self.voice_style,
            )
            for script in scripts
        ]

        # All 5 render simultaneously
        results = await asyncio.gather(
            *[agent.render() for agent in agents],
            return_exceptions=False,
        )

        successful = sum(1 for r in results if r.success)
        mock_count = sum(1 for r in results if r.is_mock)

        logger.info(
            f"ProductionCrew complete — "
            f"{successful}/{len(results)} successful, "
            f"{mock_count} mock renders"
        )

        return list(results)