"""
AdEngineAI — Script Service
==============================
Business logic for script editing.
Users can edit scripts before rendering to improve quality.
"""

import logging
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Script, Campaign
from app.core.exceptions import (
    NotFoundException,
    ForbiddenException,
    ValidationException,
)

logger = logging.getLogger(__name__)


class ScriptService:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def edit_script(
        self,
        campaign_id: UUID,
        script_id: UUID,
        user_id: UUID,
        updates: dict,
    ) -> dict:
        # Verify campaign ownership
        campaign_result = await self.db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = campaign_result.scalar_one_or_none()
        if not campaign:
            raise NotFoundException("Campaign")
        if str(campaign.user_id) != str(user_id):
            raise ForbiddenException("You don't have access to this campaign")

        # Verify script belongs to campaign
        script_result = await self.db.execute(
            select(Script).where(
                Script.id == script_id,
                Script.campaign_id == campaign_id,
            )
        )
        script = script_result.scalar_one_or_none()
        if not script:
            raise NotFoundException("Script")

        # Only allow editing these fields
        allowed = {
            "script_text", "hook_line", "ad_headline",
            "ad_description", "caption_instagram",
            "caption_tiktok", "caption_linkedin", "hashtags",
        }
        clean = {k: v for k, v in updates.items() if k in allowed}

        if not clean:
            raise ValidationException("No valid fields to update")

        await self.db.execute(
            update(Script).where(Script.id == script_id).values(**clean)
        )

        # Refresh and return
        updated = await self.db.execute(
            select(Script).where(Script.id == script_id)
        )
        script = updated.scalar_one()

        logger.info(f"Script edited: {script_id} in campaign {campaign_id}")

        return self._to_dict(script)

    @staticmethod
    def _to_dict(script) -> dict:
        return {
            "id": str(script.id),
            "hook_type": str(script.hook_type),
            "hook_line": str(script.hook_line),
            "script_text": str(script.script_text),
            "hook_score": int(script.hook_score) if script.hook_score is not None else None,
            "hook_trigger": str(script.hook_trigger) if script.hook_trigger is not None else None,
            "hook_reasoning": str(script.hook_reasoning) if script.hook_reasoning is not None else None,
            "best_platform": str(script.best_platform) if script.best_platform is not None else None,
            "ad_headline": str(script.ad_headline) if script.ad_headline is not None else None,
            "ad_description": str(script.ad_description) if script.ad_description is not None else None,
            "caption_instagram": str(script.caption_instagram) if script.caption_instagram is not None else None,
            "caption_tiktok": str(script.caption_tiktok) if script.caption_tiktok is not None else None,
            "caption_linkedin": str(script.caption_linkedin) if script.caption_linkedin is not None else None,
            "hashtags": script.hashtags or [],
        }