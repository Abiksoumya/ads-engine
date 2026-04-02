"""
AdEngineAI — Video Brief Service
===================================
Business logic for video brief operations.

Campaign flow:
  generate_for_script()  → Visual Director generates brief for a script
  get_brief()            → get existing brief
  update_brief()         → user edits brief before rendering
  approve_and_render()   → user approves → trigger Kling + FFmpeg

Used by video_brief_controller.py
"""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.video_brief_dao import VideoBriefDAO
from app.dao.campaign_dao import CampaignDAO
from app.models.video_brief import BriefStatus
from app.core.exceptions import (
    NotFoundException,
    ValidationException,
    DatabaseException,
)
from visual_director.agent import VisualDirectorAgent

logger = logging.getLogger(__name__)


class VideoBriefService:

    def __init__(self, db: AsyncSession):
        self.db = db
        self.brief_dao = VideoBriefDAO(db)
        self.campaign_dao = CampaignDAO(db)

    # ------------------------------------------------------------------
    # Generate brief for a campaign script
    # ------------------------------------------------------------------

    async def generate_for_script(
        self,
        campaign_id: UUID,
        script_id: UUID,
        user_id: UUID,
        scene_count: int = 3,
        user_preferences: dict | None = None,
    ) -> dict:
        """
        Generates a video brief for a campaign script.
        Calls Visual Director Agent.
        """
        # Get campaign + script
        campaign = await self.campaign_dao.get_by_id(campaign_id)
        if not campaign:
            raise NotFoundException("Campaign")

        # Find the script
        script = next(
            (s for s in campaign.scripts if str(s.id) == str(script_id)),
            None,
        )
        if not script:
            raise NotFoundException("Script")

        # Check if brief already exists
        existing = await self.brief_dao.get_by_script_id(script_id)
        if existing:
            return {
                "message": "Brief already exists",
                "brief": existing.to_dict(),
                "already_exists": True,
            }

        # Get product images from campaign research
        product_images = []
        product_name = ""
        product_description = ""

        if campaign.research_result is not None:
            research = campaign.research_result
            product_images = research.get("images", [])[:3]
            product_name = research.get("product_name", "")
            product_description = research.get("product_description", "")

        # Call Visual Director
        agent = VisualDirectorAgent()
        result = await agent.campaign_brief(
            hook_type=str(script.hook_type),
            hook_line=str(script.hook_line),
            script_text=str(script.script_text),
            product_name=product_name,
            product_description=product_description,
            product_images=product_images,
            scene_count=scene_count,
            user_preferences=user_preferences or {},
        )

        # Save to DB
        brief_data = {
            "script_id": script_id,
            "creation_id": None,
            "tone": result.tone,
            "color_palette": result.color_palette,
            "pacing": result.pacing,
            "music_mood": result.music_mood,
            "voiceover_script": result.voiceover_script,
            "scene_count": result.scene_count,
            "duration_secs": result.duration_secs,
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
                    "product_image_url": s.product_image_url,
                    "kling_prompt": s.kling_prompt,
                }
                for s in result.scenes
            ],
            "status": BriefStatus.DRAFT,
        }

        brief = await self.brief_dao.create(brief_data)
        await self.db.commit()

        logger.info(f"Brief generated for script {script_id}")

        return {
            "message": "Video brief generated successfully",
            "brief": brief.to_dict(),
            "already_exists": False,
        }

    # ------------------------------------------------------------------
    # Get brief
    # ------------------------------------------------------------------

    async def get_brief(
        self,
        campaign_id: UUID,
        script_id: UUID,
        user_id: UUID,
    ) -> dict:
        """Gets existing brief for a script."""
        brief = await self.brief_dao.get_by_script_id(script_id)
        if not brief:
            raise NotFoundException("Video brief")

        return {"brief": brief.to_dict()}

    # ------------------------------------------------------------------
    # Update brief (user edits)
    # ------------------------------------------------------------------

    async def update_brief(
        self,
        brief_id: UUID,
        user_id: UUID,
        updates: dict,
    ) -> dict:
        """
        User edits the video brief before rendering.
        Can update: tone, palette, pacing, scenes, voiceover_script.
        """
        brief = await self.brief_dao.get_by_id(brief_id)
        if not brief:
            raise NotFoundException("Video brief")

        if brief.status not in (BriefStatus.DRAFT, BriefStatus.APPROVED):
            raise ValidationException(
                "Brief cannot be edited while rendering or after completion"
            )

        allowed = {
            "tone", "color_palette", "pacing",
            "voiceover_script", "scenes",
            "subtitles", "aspect_ratio",
        }
        clean = {k: v for k, v in updates.items() if k in allowed and v is not None}

        if not clean:
            raise ValidationException("No valid fields to update")

        updated = await self.brief_dao.update(brief_id, clean)
        await self.db.commit()

        return {
            "message": "Brief updated successfully",
            "brief": updated.to_dict() if updated else {},
        }