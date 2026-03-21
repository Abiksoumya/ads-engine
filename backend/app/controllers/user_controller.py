"""
AdEngineAI — User Controller
==============================
Handles HTTP request/response for user endpoints.
Calls UserService for business logic.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentUser
from app.models.user import RoleEnum
from app.service.user_service import UserService


class UserController:

    def __init__(self, db: AsyncSession):
        self.service = UserService(db)

    async def get_me(self, current_user: CurrentUser) -> dict:
        result = await self.service.get_my_profile(current_user.user_id)
        return {"success": True, "data": result}

    async def update_me(self, body: dict, current_user: CurrentUser) -> dict:
        result = await self.service.update_my_profile(
            user_id=current_user.user_id,
            full_name=body.get("full_name"),
            avatar_url=body.get("avatar_url"),
        )
        return {"success": True, "data": result}

    async def deactivate_me(self, current_user: CurrentUser) -> dict:
        result = await self.service.deactivate_my_account(current_user.user_id)
        return {"success": True, **result}

    async def get_user(self, user_id: UUID) -> dict:
        result = await self.service.get_user_by_id(user_id)
        return {"success": True, "data": result}

    async def list_users(self, skip: int, limit: int, is_active: bool | None) -> dict:
        result = await self.service.list_users(skip=skip, limit=limit, is_active=is_active)
        return {"success": True, **result}

    async def activate_user(self, user_id: UUID) -> dict:
        result = await self.service.activate_user(user_id)
        return {"success": True, **result}

    async def deactivate_user(self, user_id: UUID, current_user: CurrentUser) -> dict:
        result = await self.service.deactivate_user(
            target_user_id=user_id,
            requesting_user_id=current_user.user_id,
        )
        return {"success": True, **result}

    async def change_role(self, user_id: UUID, body: dict, current_user: CurrentUser) -> dict:
        result = await self.service.change_user_role(
            target_user_id=user_id,
            new_role=RoleEnum(body["role"]),
            assigned_by=current_user.user_id,
        )
        return {"success": True, **result}