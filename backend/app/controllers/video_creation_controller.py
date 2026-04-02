"""
AdEngineAI — Video Creation Controller
"""

from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.service.video_creation_service import VideoCreationService
from app.core.dependencies import CurrentUser


class VideoCreationController:

    def __init__(self, db: AsyncSession):
        self.service = VideoCreationService(db)

    async def create(self, body: dict, current_user: CurrentUser) -> dict:
        result = await self.service.create(
            user_id=current_user.user_id,
            user_prompt=body["user_prompt"],
            uploaded_images=body.get("uploaded_images", []),
            scene_count=body.get("scene_count", 3),
            aspect_ratio=body.get("aspect_ratio", "9:16"),
            subtitles=body.get("subtitles", False),
            user_preferences=body.get("preferences", {}),
        )
        return {"success": True, **result}

    async def list(
        self,
        skip: int,
        limit: int,
        current_user: CurrentUser,
    ) -> dict:
        result = await self.service.list_creations(
            user_id=current_user.user_id,
            skip=skip,
            limit=limit,
        )
        return {"success": True, **result}

    async def get(self, creation_id: UUID, current_user: CurrentUser) -> dict:
        result = await self.service.get_creation(
            creation_id=creation_id,
            user_id=current_user.user_id,
        )
        return {"success": True, **result}

    async def update_brief(
        self,
        creation_id: UUID,
        body: dict,
        current_user: CurrentUser,
    ) -> dict:
        result = await self.service.update_brief(
            creation_id=creation_id,
            user_id=current_user.user_id,
            updates=body,
        )
        return {"success": True, **result}

    async def render(
        self,
        creation_id: UUID,
        body: dict,
        current_user: CurrentUser,
    ) -> dict:
        result = await self.service.render(
            creation_id=creation_id,
            user_id=current_user.user_id,
            aspect_ratio=body.get("aspect_ratio", "9:16"),
            voice_style=body.get("voice_style", "professional"),
        )
        return {"success": True, **result}