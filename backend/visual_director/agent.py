"""
AdEngineAI — Visual Director Agent
=====================================
Generates detailed video briefs from:
  1. Campaign scripts (product ads)
  2. Text descriptions (video creator)

Output: VideoBrief with scene-by-scene Kling prompts
that tell exactly how each scene should look.

Used by:
  - video_brief_service.py (campaign flow)
  - video_creation_service.py (creator flow)
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from config.llm import get_llm_config
from config.llm_client import complete_json
from .prompts import (
    VISUAL_DIRECTOR_SYSTEM,
    build_campaign_brief_prompt,
    build_creation_brief_prompt,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SceneBrief:
    """One scene in the video brief."""
    scene_number: int
    duration: int                    # seconds
    background: str
    action: str
    color_mood: str
    camera: str
    kling_prompt: str                # exact prompt for Kling AI
    text_overlay: Optional[str] = None
    use_product_image: bool = False
    use_uploaded_image: bool = False
    product_image_url: Optional[str] = None


@dataclass
class VideoBriefResult:
    """Complete video brief output from Visual Director."""
    # Overall settings
    tone: str
    color_palette: str
    pacing: str
    music_mood: str
    voiceover_script: str

    # Scenes
    scenes: list[SceneBrief] = field(default_factory=list)

    # Meta
    scene_count: int = 3
    duration_secs: int = 30
    success: bool = True
    error: Optional[str] = None

    @property
    def is_usable(self) -> bool:
        return self.success and len(self.scenes) > 0

    def to_dict(self) -> dict:
        return {
            "tone": self.tone,
            "color_palette": self.color_palette,
            "pacing": self.pacing,
            "music_mood": self.music_mood,
            "voiceover_script": self.voiceover_script,
            "scene_count": self.scene_count,
            "duration_secs": self.duration_secs,
            "scenes": [
                {
                    "scene_number": s.scene_number,
                    "duration": s.duration,
                    "background": s.background,
                    "action": s.action,
                    "color_mood": s.color_mood,
                    "camera": s.camera,
                    "text_overlay": s.text_overlay,
                    "use_product_image": s.use_product_image,
                    "use_uploaded_image": s.use_uploaded_image,
                    "product_image_url": s.product_image_url,
                    "kling_prompt": s.kling_prompt,
                }
                for s in self.scenes
            ],
        }


# ---------------------------------------------------------------------------
# Visual Director Agent
# ---------------------------------------------------------------------------

class VisualDirectorAgent:
    """
    Generates video briefs using an LLM.

    Two modes:
        campaign_brief() — for product ads from scripts
        creation_brief() — for any video from text description
    """

    def __init__(self):
        self.llm_cfg = get_llm_config("director")  # reuse director LLM config
        logger.info("VisualDirectorAgent initialized")

    # ------------------------------------------------------------------
    # Campaign brief (product ad)
    # ------------------------------------------------------------------

    async def campaign_brief(
        self,
        hook_type: str,
        hook_line: str,
        script_text: str,
        product_name: str,
        product_description: str,
        product_images: list[str],
        scene_count: int = 3,
        user_preferences: dict | None = None,
    ) -> VideoBriefResult:
        """
        Generates a video brief for a product ad script.
        Called after Director Agent generates scripts.

        Args:
            hook_type: problem / secret / social_proof / visual_first / emotional
            hook_line: the opening hook sentence
            script_text: full voiceover script
            product_name: name of the product
            product_description: what the product does
            product_images: list of scraped product image URLs
            scene_count: 3 or 6 scenes
            user_preferences: tone, palette, pacing overrides

        Returns:
            VideoBriefResult with scene-by-scene Kling prompts
        """
        logger.info(f"Generating campaign brief: {hook_type} | {scene_count} scenes")

        prompt = build_campaign_brief_prompt(
            hook_type=hook_type,
            hook_line=hook_line,
            script_text=script_text,
            product_name=product_name,
            product_description=product_description,
            product_images=product_images,
            scene_count=scene_count,
            user_preferences=user_preferences or {},
        )

        try:
            raw = await complete_json(
                cfg=self.llm_cfg,
                system=VISUAL_DIRECTOR_SYSTEM,
                user=prompt,
            )

            result = self._parse_brief(raw, scene_count, product_images)
            logger.info(f"Campaign brief generated: {len(result.scenes)} scenes")
            return result

        except Exception as e:
            logger.error(f"Campaign brief generation failed: {e}")
            return self._fallback_brief(
                hook_type=hook_type,
                hook_line=hook_line,
                scene_count=scene_count,
                error=str(e),
            )

    # ------------------------------------------------------------------
    # Creation brief (text to video)
    # ------------------------------------------------------------------

    async def creation_brief(
        self,
        user_prompt: str,
        uploaded_images: list[str],
        scene_count: int = 3,
        user_preferences: dict | None = None,
    ) -> VideoBriefResult:
        """
        Generates a video brief from a text description.
        Used in the Video Creator flow (/create page).

        Args:
            user_prompt: what the user wants to make
            uploaded_images: list of user-uploaded image URLs
            scene_count: 3 or 6 scenes
            user_preferences: tone, palette, pacing overrides

        Returns:
            VideoBriefResult with script + scene-by-scene Kling prompts
        """
        logger.info(f"Generating creation brief: '{user_prompt[:50]}...' | {scene_count} scenes")

        prompt = build_creation_brief_prompt(
            user_prompt=user_prompt,
            uploaded_images=uploaded_images,
            scene_count=scene_count,
            user_preferences=user_preferences or {},
        )

        try:
            raw = await complete_json(
                cfg=self.llm_cfg,
                system=VISUAL_DIRECTOR_SYSTEM,
                user=prompt,
            )

            result = self._parse_brief(raw, scene_count, uploaded_images)
            logger.info(f"Creation brief generated: {len(result.scenes)} scenes")
            return result

        except Exception as e:
            logger.error(f"Creation brief generation failed: {e}")
            return self._fallback_brief(
                hook_type="general",
                hook_line=user_prompt[:100],
                scene_count=scene_count,
                error=str(e),
            )

    # ------------------------------------------------------------------
    # Parse LLM response
    # ------------------------------------------------------------------

    def _parse_brief(
        self,
        raw: dict,
        scene_count: int,
        images: list[str],
    ) -> VideoBriefResult:
        """Parses LLM JSON response into VideoBriefResult."""

        overall = raw.get("overall", {})
        raw_scenes = raw.get("scenes", [])

        # Parse scenes
        scenes = []
        for i, s in enumerate(raw_scenes[:scene_count]):
            # Pick image URL for scenes that need product image
            image_url = images[0] if images and (
                s.get("use_product_image") or s.get("use_uploaded_image")
            ) else None

            scene = SceneBrief(
                scene_number=s.get("scene_number", i + 1),
                duration=s.get("duration", 10),
                background=s.get("background", ""),
                action=s.get("action", ""),
                color_mood=s.get("color_mood", ""),
                camera=s.get("camera", ""),
                kling_prompt=s.get("kling_prompt", ""),
                text_overlay=s.get("text_overlay"),
                use_product_image=bool(s.get("use_product_image", False)),
                use_uploaded_image=bool(s.get("use_uploaded_image", False)),
                product_image_url=image_url,
            )
            scenes.append(scene)

        # Fill missing scenes if LLM returned fewer than expected
        while len(scenes) < scene_count:
            scenes.append(self._default_scene(len(scenes) + 1))

        total_duration = sum(s.duration for s in scenes)

        return VideoBriefResult(
            tone=str(overall.get("tone", "professional")),
            color_palette=str(overall.get("color_palette", "vibrant")),
            pacing=str(overall.get("pacing", "medium")),
            music_mood=str(overall.get("music_mood", "none")),
            voiceover_script=str(overall.get("voiceover_script", "")),
            scenes=scenes,
            scene_count=len(scenes),
            duration_secs=total_duration,
            success=True,
        )

    # ------------------------------------------------------------------
    # Fallbacks
    # ------------------------------------------------------------------

    def _fallback_brief(
        self,
        hook_type: str,
        hook_line: str,
        scene_count: int,
        error: str,
    ) -> VideoBriefResult:
        """Returns a basic fallback brief when LLM fails."""
        scenes = [self._default_scene(i + 1) for i in range(scene_count)]
        return VideoBriefResult(
            tone="professional",
            color_palette="vibrant",
            pacing="medium",
            music_mood="none",
            voiceover_script=hook_line,
            scenes=scenes,
            scene_count=scene_count,
            duration_secs=scene_count * 10,
            success=False,
            error=error,
        )

    @staticmethod
    def _default_scene(scene_number: int) -> SceneBrief:
        """Default scene when LLM fails to generate one."""
        return SceneBrief(
            scene_number=scene_number,
            duration=10,
            background="Clean studio background, soft lighting",
            action="Product showcase with smooth camera movement",
            color_mood="Professional neutral tones",
            camera="Slow dolly forward",
            kling_prompt=(
                "Professional product showcase, clean studio background, "
                "soft diffused lighting, slow cinematic camera movement, "
                "4K quality, professional advertisement style"
            ),
            text_overlay=None,
            use_product_image=True,
        )