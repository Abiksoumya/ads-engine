"""
AdEngineAI — Brand Controller
"""

from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.service.brand_service import BrandService
from app.core.dependencies import CurrentUser


class BrandController:

    def __init__(self, db: AsyncSession):
        self.service = BrandService(db)

    async def create(self, body: dict, current_user: CurrentUser) -> dict:
        result = await self.service.create(
            user_id=current_user.user_id,
            plan=current_user.plan,
            **body,
        )
        return {"success": True, "data": result}

    async def list_my_brands(self, current_user: CurrentUser) -> dict:
        result = await self.service.list_my_brands(current_user.user_id)
        return {"success": True, **result}

    async def get_brand(self, brand_id: UUID, current_user: CurrentUser) -> dict:
        result = await self.service.get_by_id(brand_id, current_user.user_id)
        return {"success": True, "data": result}

    async def update_brand(self, brand_id: UUID, body: dict, current_user: CurrentUser) -> dict:
        result = await self.service.update(brand_id, current_user.user_id, body)
        return {"success": True, "data": result}

    async def delete_brand(self, brand_id: UUID, current_user: CurrentUser) -> dict:
        result = await self.service.delete(brand_id, current_user.user_id)
        return {"success": True, **result}

    async def set_default(self, brand_id: UUID, current_user: CurrentUser) -> dict:
        result = await self.service.set_default(brand_id, current_user.user_id)
        return {"success": True, **result}