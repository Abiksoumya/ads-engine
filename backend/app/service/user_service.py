"""
AdEngineAI — User Service
===========================
Business logic for user management.
Calls UserDAO for DB operations.
"""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.user_dao import UserDAO
from app.core.exceptions import (
    UserNotFoundException,
    ForbiddenException,
    ValidationException,
)
from app.models.user import RoleEnum

logger = logging.getLogger(__name__)


class UserService:

    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_dao = UserDAO(db)

    # ------------------------------------------------------------------
    # Own profile
    # ------------------------------------------------------------------

    async def get_my_profile(self, user_id: UUID) -> dict:
        user = await self.user_dao.get_by_id(user_id)
        if not user:
            raise UserNotFoundException()
        return self._to_dict(user)

    async def update_my_profile(
        self,
        user_id: UUID,
        full_name: str | None = None,
        avatar_url: str | None = None,
    ) -> dict:
        if full_name is not None and not full_name.strip():
            raise ValidationException("Full name cannot be empty")

        user = await self.user_dao.update_profile(
            user_id=user_id,
            full_name=full_name,
            avatar_url=avatar_url,
        )
        if not user:
            raise UserNotFoundException()

        logger.info(f"Profile updated: {user_id}")
        return self._to_dict(user)

    async def deactivate_my_account(self, user_id: UUID) -> dict:
        user = await self.user_dao.get_by_id(user_id)
        if not user:
            raise UserNotFoundException()

        await self.user_dao.deactivate(user_id)
        logger.info(f"Account deactivated by user: {user_id}")
        return {"message": "Account deactivated successfully"}

    # ------------------------------------------------------------------
    # Admin operations
    # ------------------------------------------------------------------

    async def get_user_by_id(self, user_id: UUID) -> dict:
        """Admin — get any user by ID."""
        user = await self.user_dao.get_by_id(user_id)
        if not user:
            raise UserNotFoundException()
        return self._to_dict(user, include_admin_fields=True)

    async def list_users(
        self,
        skip: int = 0,
        limit: int = 50,
        is_active: bool | None = None,
    ) -> dict:
        """Admin — paginated list of all users."""
        users = await self.user_dao.get_all(skip=skip, limit=limit, is_active=is_active)
        return {
            "users": [self._to_dict(u, include_admin_fields=True) for u in users],
            "skip": skip,
            "limit": limit,
            "count": len(users),
        }

    async def activate_user(self, target_user_id: UUID) -> dict:
        """Admin — activate a deactivated user."""
        from sqlalchemy import update
        from app.models.user import User

        user = await self.user_dao.get_by_id(target_user_id)
        if not user:
            raise UserNotFoundException()

        await self.db.execute(
            update(User).where(User.id == target_user_id).values(is_active=True)
        )
        logger.info(f"User activated by admin: {target_user_id}")
        return {"message": "User activated successfully"}

    async def deactivate_user(
        self,
        target_user_id: UUID,
        requesting_user_id: UUID,
    ) -> dict:
        """Admin — deactivate any user. Cannot deactivate yourself."""
        if target_user_id == requesting_user_id:
            raise ForbiddenException("Use /api/users/me DELETE to deactivate your own account")

        user = await self.user_dao.get_by_id(target_user_id)
        if not user:
            raise UserNotFoundException()

        await self.user_dao.deactivate(target_user_id)
        logger.info(f"User deactivated by admin: {target_user_id}")
        return {"message": "User deactivated successfully"}

    async def change_user_role(
        self,
        target_user_id: UUID,
        new_role: RoleEnum,
        assigned_by: UUID,
    ) -> dict:
        """Superadmin — change a user's role."""
        user = await self.user_dao.get_by_id(target_user_id)
        if not user:
            raise UserNotFoundException()

        # Remove existing roles and assign new one
        from sqlalchemy import delete
        from app.models.user import UserRole, Role
        from sqlalchemy import select

        # Get role ID
        role_result = await self.db.execute(
            select(Role).where(Role.name == new_role)
        )
        role = role_result.scalar_one_or_none()
        if not role:
            raise ValidationException(f"Role '{new_role}' not found")

        # Delete existing roles
        await self.db.execute(
            delete(UserRole).where(UserRole.user_id == target_user_id)
        )

        # Assign new role
        await self.user_dao.assign_role(target_user_id, new_role, assigned_by=assigned_by)

        logger.info(f"Role changed to {new_role} for user: {target_user_id}")
        return {"message": f"Role updated to '{new_role}' successfully"}

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    @staticmethod
    def _to_dict(user, include_admin_fields: bool = False) -> dict:
        data: dict = {
            "id": str(user.id),
            "email": str(user.email),
            "full_name": str(user.full_name),
            "is_active": bool(user.is_active),
            "is_verified": bool(user.is_verified),
            "avatar_url": str(user.avatar_url) if user.avatar_url is not None else None,
            "created_at": user.created_at.isoformat() if user.created_at is not None else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at is not None else None,
        }
        if include_admin_fields:
            data["last_login_at"] = (
                user.last_login_at.isoformat()
                if user.last_login_at is not None else None
            )
            data["stripe_customer_id"] = (
                str(user.stripe_customer_id)
                if user.stripe_customer_id is not None else None
            )
        return data