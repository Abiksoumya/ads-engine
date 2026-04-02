"""
AdEngineAI — Admin Controller
"""

from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.service.admin_service import AdminService
from app.core.dependencies import CurrentUser


class AdminController:

    def __init__(self, db: AsyncSession):
        self.service = AdminService(db)

    async def get_stats(self) -> dict:
        result = await self.service.get_stats()
        return {"success": True, "data": result}

    async def list_users(self, skip: int, limit: int, search: str | None) -> dict:
        result = await self.service.list_users(skip=skip, limit=limit, search=search)
        return {"success": True, **result}

    async def assign_plan(self, user_id: UUID, body: dict, current_user: CurrentUser) -> dict:
        result = await self.service.assign_plan(
            target_user_id=user_id,
            plan_name=body["plan"],
            assigned_by=current_user.user_id,
        )
        return {"success": True, **result}

    async def change_role(self, user_id: UUID, body: dict, current_user: CurrentUser) -> dict:
        result = await self.service.change_user_role(
            target_user_id=user_id,
            new_role=body["role"],
            assigned_by=current_user.user_id,
        )
        return {"success": True, **result}

    async def toggle_active(self, user_id: UUID, current_user: CurrentUser) -> dict:
        result = await self.service.toggle_user_active(
            target_user_id=user_id,
            requesting_user_id=current_user.user_id,
        )
        return {"success": True, **result}

    async def list_plans(self) -> dict:
        result = await self.service.list_plans()
        return {"success": True, **result}

    async def update_plan(self, plan_name: str, body: dict) -> dict:
        result = await self.service.update_plan(plan_name=plan_name, updates=body)
        return {"success": True, **result}