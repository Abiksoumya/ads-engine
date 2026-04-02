"""
AdEngineAI — Video Brief Controller
"""

from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.service.video_brief_service import VideoBriefService
from app.core.dependencies import CurrentUser


class VideoBriefController:

    def __init__(self, db: AsyncSession):
        self.service = VideoBriefService(db)

    async def generate(
        self,
        campaign_id: UUID,
        script_id: UUID,
        body: dict,
        current_user: CurrentUser,
    ) -> dict:
        result = await self.service.generate_for_script(
            campaign_id=campaign_id,
            script_id=script_id,
            user_id=current_user.user_id,
            scene_count=body.get("scene_count", 3),
            user_preferences=body.get("preferences", {}),
        )
        return {"success": True, **result}

    async def get(
        self,
        campaign_id: UUID,
        script_id: UUID,
        current_user: CurrentUser,
    ) -> dict:
        result = await self.service.get_brief(
            campaign_id=campaign_id,
            script_id=script_id,
            user_id=current_user.user_id,
        )
        return {"success": True, **result}

    async def update(
        self,
        brief_id: UUID,
        body: dict,
        current_user: CurrentUser,
    ) -> dict:
        result = await self.service.update_brief(
            brief_id=brief_id,
            user_id=current_user.user_id,
            updates=body,
        )
        return {"success": True, **result}