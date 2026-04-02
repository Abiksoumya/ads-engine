"""
AdEngineAI — fal.ai Kling Video Tool
=======================================
Replaces did_tools.py for video generation.

Uses Kling 2.6 Pro via fal.ai API:
  - Image to video (product image + scene prompt)
  - Text to video (scene prompt only)

Pricing:
  $0.07/sec without audio
  $0.14/sec with audio (we use ElevenLabs separately)

fal.ai docs: https://fal.ai/models/fal-ai/kling-video

Used by:
  production/crew.py  (render pipeline)
  tasks/render_tasks.py
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Kling model options ─────────────────────────────────────────────────────

# Model versions available on fal.ai
KLING_MODELS = {
    "v2.6_pro": "fal-ai/kling-video/v2.6/pro/image-to-video",
    "v2.6_pro_text": "fal-ai/kling-video/v2.6/pro/text-to-video",
    "v2.1_pro": "fal-ai/kling-video/v2.1/pro/image-to-video",
    "v2.1_pro_text": "fal-ai/kling-video/v2.1/pro/text-to-video",
    "v1.6_pro": "fal-ai/kling-video/v1.6/pro/image-to-video",
    "v1.6_pro_text": "fal-ai/kling-video/v1.6/pro/text-to-video",
}

# Default model
DEFAULT_IMAGE_MODEL = "fal-ai/kling-video/v2.1/pro/image-to-video"
DEFAULT_TEXT_MODEL  = "fal-ai/kling-video/v2.6/pro/text-to-video"

# Aspect ratios
ASPECT_RATIOS = {
    "9:16": "9:16",    # TikTok / Reels / Shorts
    "1:1": "1:1",      # Instagram Feed / Facebook
    "16:9": "16:9",    # YouTube / LinkedIn
}


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------

@dataclass
class KlingSceneResult:
    """Result of one Kling video generation."""
    hook_type: str
    scene_number: int
    video_url: str
    duration_secs: float
    aspect_ratio: str
    provider: str = "kling"
    is_mock: bool = False
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return bool(self.video_url) and not self.is_mock


@dataclass
class KlingVideoResult:
    """All aspect ratio variants for one scene."""
    hook_type: str
    scene_number: int
    video_url_9x16: Optional[str] = None
    video_url_1x1: Optional[str] = None
    video_url_16x9: Optional[str] = None
    duration_secs: float = 0.0
    provider: str = "kling"
    is_mock: bool = False
    error: Optional[str] = None

    def best_url(self) -> Optional[str]:
        return self.video_url_9x16 or self.video_url_1x1 or self.video_url_16x9


# ---------------------------------------------------------------------------
# fal.ai Kling Tool
# ---------------------------------------------------------------------------

class FalKlingTool:
    """
    Generates video scenes using Kling AI via fal.ai.

    Usage:
        tool = FalKlingTool(api_key="your_fal_key")

        # Image to video
        result = await tool.generate_scene(
            prompt="Shoe floating in forest, cinematic",
            image_url="https://cloudinary.com/shoe.jpg",
            duration=10,
            aspect_ratio="9:16",
            hook_type="problem",
            scene_number=1,
        )

        # All 3 ratios at once
        result = await tool.generate_all_ratios(
            prompt="Shoe floating in forest",
            image_url="https://cloudinary.com/shoe.jpg",
            duration=10,
            hook_type="problem",
            scene_number=2,
        )
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("FAL_API_KEY", "")

        if not self.api_key:
            logger.warning("FAL_API_KEY not set — will use mock mode")

    @property
    def is_mock(self) -> bool:
        return not bool(self.api_key)

    # ------------------------------------------------------------------
    # Generate single scene — one aspect ratio
    # ------------------------------------------------------------------

    async def generate_scene(
        self,
        prompt: str,
        duration: int,
        aspect_ratio: str,
        hook_type: str,
        scene_number: int,
        image_url: Optional[str] = None,
    ) -> KlingSceneResult:
        """
        Generates one video scene.
        If image_url provided → image-to-video
        If no image → text-to-video
        """
        if self.is_mock:
            return self._mock_scene(hook_type, scene_number, aspect_ratio, duration)

        try:
            import fal_client

            # Set API key
            os.environ["FAL_KEY"] = self.api_key

            # Choose model based on whether we have an image
            if image_url:
                model = DEFAULT_IMAGE_MODEL
                arguments = {
                    "prompt": prompt,
                    "image_url": image_url,
                    "duration": str(duration),
                    "aspect_ratio": aspect_ratio,
                }
            else:
                model = DEFAULT_TEXT_MODEL
                arguments = {
                    "prompt": prompt,
                    "duration": str(duration),
                    "aspect_ratio": aspect_ratio,
                }

            logger.info(
                f"Kling generating: {hook_type} scene {scene_number} "
                f"({aspect_ratio}, {duration}s) | "
                f"{'image' if image_url else 'text'}-to-video"
            )

            # Submit to fal.ai queue
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: fal_client.subscribe(
                    model,
                    arguments=arguments,
                    with_logs=False,
                )
            )

            # Extract video URL from result
            video_url = self._extract_url(result)

            if not video_url:
                raise ValueError("No video URL in fal.ai response")

            logger.info(
                f"Kling complete: {hook_type} scene {scene_number} "
                f"({aspect_ratio}) → {video_url[:60]}..."
            )

            return KlingSceneResult(
                hook_type=hook_type,
                scene_number=scene_number,
                video_url=video_url,
                duration_secs=float(duration),
                aspect_ratio=aspect_ratio,
                provider="kling",
                is_mock=False,
            )

        except Exception as e:
            logger.error(
                f"Kling failed: {hook_type} scene {scene_number} "
                f"({aspect_ratio}): {e}"
            )
            return KlingSceneResult(
                hook_type=hook_type,
                scene_number=scene_number,
                video_url="",
                duration_secs=float(duration),
                aspect_ratio=aspect_ratio,
                provider="kling",
                is_mock=True,
                error=str(e),
            )

    # ------------------------------------------------------------------
    # Generate for user-selected aspect ratio
    # ------------------------------------------------------------------

    async def generate_for_ratio(
        self,
        prompt: str,
        duration: int,
        hook_type: str,
        scene_number: int,
        aspect_ratio: str = "9:16",
        image_url: Optional[str] = None,
    ) -> KlingVideoResult:
        """
        Generates video for user-selected aspect ratio.

        aspect_ratio options:
            "9:16"  → TikTok / Reels / Shorts (default)
            "1:1"   → Instagram Feed / Facebook
            "16:9"  → YouTube / LinkedIn
            "all"   → all 3 formats (costs 3x — premium option)

        User chooses format before rendering to avoid unnecessary cost.
        """
        if self.is_mock:
            return KlingVideoResult(
                hook_type=hook_type,
                scene_number=scene_number,
                video_url_9x16=f"https://mock-kling.com/{hook_type}_scene{scene_number}_9x16.mp4" if aspect_ratio in ("9:16", "all") else None,
                video_url_1x1=f"https://mock-kling.com/{hook_type}_scene{scene_number}_1x1.mp4" if aspect_ratio in ("1:1", "all") else None,
                video_url_16x9=f"https://mock-kling.com/{hook_type}_scene{scene_number}_16x9.mp4" if aspect_ratio in ("16:9", "all") else None,
                duration_secs=float(duration),
                is_mock=True,
            )

        if aspect_ratio == "all":
            # Premium — generate all 3 in parallel
            results = await asyncio.gather(
                self.generate_scene(prompt, duration, "9:16", hook_type, scene_number, image_url),
                self.generate_scene(prompt, duration, "1:1", hook_type, scene_number, image_url),
                self.generate_scene(prompt, duration, "16:9", hook_type, scene_number, image_url),
                return_exceptions=True,
            )
            r_9x16 = results[0] if isinstance(results[0], KlingSceneResult) else None
            r_1x1  = results[1] if isinstance(results[1], KlingSceneResult) else None
            r_16x9 = results[2] if isinstance(results[2], KlingSceneResult) else None

            return KlingVideoResult(
                hook_type=hook_type,
                scene_number=scene_number,
                video_url_9x16=r_9x16.video_url if r_9x16 and r_9x16.success else None,
                video_url_1x1=r_1x1.video_url if r_1x1 and r_1x1.success else None,
                video_url_16x9=r_16x9.video_url if r_16x9 and r_16x9.success else None,
                duration_secs=float(duration),
                provider="kling",
                is_mock=False,
            )

        else:
            # Single format — user selected one ratio
            result = await self.generate_scene(
                prompt, duration, aspect_ratio,
                hook_type, scene_number, image_url,
            )
            return KlingVideoResult(
                hook_type=hook_type,
                scene_number=scene_number,
                video_url_9x16=result.video_url if aspect_ratio == "9:16" and result.success else None,
                video_url_1x1=result.video_url if aspect_ratio == "1:1" and result.success else None,
                video_url_16x9=result.video_url if aspect_ratio == "16:9" and result.success else None,
                duration_secs=float(duration),
                provider="kling",
                is_mock=result.is_mock,
                error=result.error,
            )

    # ------------------------------------------------------------------
    # Generate all scenes for a complete video brief
    # ------------------------------------------------------------------

    async def generate_scenes_for_brief(
        self,
        scenes: list[dict],
        hook_type: str,
        aspect_ratio: str = "9:16",
    ) -> list[KlingSceneResult]:
        """
        Generates all scenes for a video brief sequentially.
        Sequential to avoid fal.ai rate limits.

        Args:
            scenes: list of scene dicts from VideoBriefResult
            hook_type: problem/secret/etc
            aspect_ratio: which format to generate

        Returns:
            list of KlingSceneResult in scene order
        """
        results = []
        for scene in scenes:
            result = await self.generate_scene(
                prompt=scene.get("kling_prompt", ""),
                duration=scene.get("duration", 10),
                aspect_ratio=aspect_ratio,
                hook_type=hook_type,
                scene_number=scene.get("scene_number", 1),
                image_url=scene.get("product_image_url"),
            )
            results.append(result)

            # Small delay between scenes to be safe
            if len(results) < len(scenes):
                await asyncio.sleep(1)

        successful = sum(1 for r in results if r.success)
        logger.info(
            f"Kling scenes complete: {successful}/{len(results)} successful "
            f"for {hook_type}"
        )

        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_url(result) -> str:
        """Extracts video URL from fal.ai response."""
        if isinstance(result, dict):
            # fal.ai returns {"video": {"url": "..."}} or {"url": "..."}
            if "video" in result:
                video = result["video"]
                if isinstance(video, dict):
                    return video.get("url", "")
                return str(video)
            if "url" in result:
                return result["url"]
            # Sometimes nested under outputs
            if "outputs" in result:
                outputs = result["outputs"]
                if isinstance(outputs, list) and outputs:
                    first = outputs[0]
                    if isinstance(first, dict):
                        return first.get("url", "")
        return ""

    @staticmethod
    def _mock_scene(
        hook_type: str,
        scene_number: int,
        aspect_ratio: str,
        duration: int,
    ) -> KlingSceneResult:
        return KlingSceneResult(
            hook_type=hook_type,
            scene_number=scene_number,
            video_url=f"https://mock-kling.com/{hook_type}_scene{scene_number}_{aspect_ratio.replace(':', 'x')}.mp4",
            duration_secs=float(duration),
            aspect_ratio=aspect_ratio,
            provider="kling_mock",
            is_mock=True,
        )