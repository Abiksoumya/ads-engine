"""
AdEngineAI — Campaign Controller
"""

from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.service.campaign_service import CampaignService
from app.core.dependencies import CurrentUser


class CampaignController:

    def __init__(self, db: AsyncSession):
        self.service = CampaignService(db)

    async def create(self, body: dict, current_user: CurrentUser) -> dict:
        result = await self.service.create(
            user_id=current_user.user_id,
            plan=current_user.plan,
            product_url=body["product_url"],
            brand_id=body.get("brand_id"),
            ugc_mode=body.get("ugc_mode", False),
            voice_style=body.get("voice_style", "professional"),
        )
        return {"success": True, "data": result}

    async def list_campaigns(
        self, skip: int, limit: int, current_user: CurrentUser
    ) -> dict:
        result = await self.service.list_my_campaigns(
            user_id=current_user.user_id,
            skip=skip,
            limit=limit,
        )
        return {"success": True, **result}

    async def get_campaign(self, campaign_id: UUID, current_user: CurrentUser) -> dict:
        result = await self.service.get_by_id(campaign_id, current_user.user_id)
        return {"success": True, "data": result}

    async def get_status(self, campaign_id: UUID, current_user: CurrentUser) -> dict:
        result = await self.service.get_status(campaign_id, current_user.user_id)
        return {"success": True, "data": result}

    async def delete_campaign(self, campaign_id: UUID, current_user: CurrentUser) -> dict:
        result = await self.service.delete(campaign_id, current_user.user_id)
        return {"success": True, **result}