"""
AdEngineAI — Admin Service
============================
Business logic for admin operations.
Only accessible by admin and superadmin roles.
"""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.admin_dao import AdminDAO
from app.dao.user_dao import UserDAO
from app.models.subscription import PlanEnum
from app.models.user import RoleEnum
from app.core.exceptions import (
    UserNotFoundException,
    ValidationException,
    NotFoundException,
)

logger = logging.getLogger(__name__)


class AdminService:

    def __init__(self, db: AsyncSession):
        self.db = db
        self.admin_dao = AdminDAO(db)
        self.user_dao = UserDAO(db)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    async def get_stats(self) -> dict:
        total_users = await self.admin_dao.count_users()
        total_campaigns = await self.admin_dao.count_campaigns()
        subscription_stats = await self.admin_dao.get_subscription_stats()

        return {
            "total_users": total_users,
            "total_campaigns": total_campaigns,
            "subscriptions_by_plan": subscription_stats,
        }

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    async def list_users(
        self,
        skip: int = 0,
        limit: int = 50,
        search: str | None = None,
    ) -> dict:
        users = await self.admin_dao.get_all_users(skip=skip, limit=limit, search=search)
        total = await self.admin_dao.count_users()

        return {
            "users": [self._user_to_dict(u) for u in users],
            "total": total,
            "skip": skip,
            "limit": limit,
        }

    async def assign_plan(
        self,
        target_user_id: UUID,
        plan_name: str,
        assigned_by: UUID,
    ) -> dict:
        # Validate plan name
        try:
            plan_enum = PlanEnum(plan_name)
        except ValueError:
            raise ValidationException(
                f"Invalid plan '{plan_name}'. Must be one of: free, starter, pro, agency"
            )

        # Verify user exists
        user = await self.user_dao.get_by_id(target_user_id)
        if not user:
            raise UserNotFoundException()

        subscription = await self.admin_dao.assign_plan_to_user(
            user_id=target_user_id,
            plan_name=plan_enum,
            assigned_by=assigned_by,
        )

        logger.info(
            f"Plan '{plan_name}' assigned to user {target_user_id} "
            f"by admin {assigned_by}"
        )

        return {
            "message": f"Plan '{plan_name}' assigned successfully",
            "user_id": str(target_user_id),
            "plan": plan_name,
        }

    async def change_user_role(
        self,
        target_user_id: UUID,
        new_role: str,
        assigned_by: UUID,
    ) -> dict:
        try:
            role_enum = RoleEnum(new_role)
        except ValueError:
            raise ValidationException(
                f"Invalid role '{new_role}'. Must be one of: superadmin, admin, agency, user, viewer"
            )

        user = await self.user_dao.get_by_id(target_user_id)
        if not user:
            raise UserNotFoundException()

        # Remove existing roles and assign new one
        from sqlalchemy import delete
        from app.models.user import UserRole, Role
        from sqlalchemy import select

        role_result = await self.db.execute(
            select(Role).where(Role.name == role_enum)
        )
        role = role_result.scalar_one_or_none()
        if not role:
            raise ValidationException(f"Role '{new_role}' not found in database")

        await self.db.execute(
            delete(UserRole).where(UserRole.user_id == target_user_id)
        )
        await self.user_dao.assign_role(target_user_id, role_enum, assigned_by=assigned_by)

        logger.info(f"Role '{new_role}' assigned to user {target_user_id} by {assigned_by}")

        return {
            "message": f"Role '{new_role}' assigned successfully",
            "user_id": str(target_user_id),
            "role": new_role,
        }

    async def toggle_user_active(
        self,
        target_user_id: UUID,
        requesting_user_id: UUID,
    ) -> dict:
        if target_user_id == requesting_user_id:
            raise ValidationException("Cannot deactivate your own account")

        user = await self.user_dao.get_by_id(target_user_id)
        if not user:
            raise UserNotFoundException()

        from sqlalchemy import update
        from app.models.user import User

        new_status = not bool(user.is_active)
        await self.db.execute(
            update(User)
            .where(User.id == target_user_id)
            .values(is_active=new_status)
        )

        action = "activated" if new_status else "deactivated"
        logger.info(f"User {target_user_id} {action} by admin {requesting_user_id}")

        return {
            "message": f"User {action} successfully",
            "user_id": str(target_user_id),
            "is_active": new_status,
        }

    # ------------------------------------------------------------------
    # Plans
    # ------------------------------------------------------------------

    async def list_plans(self) -> dict:
        plans = await self.admin_dao.get_all_plans()
        return {
            "plans": [self._plan_to_dict(p) for p in plans],
            "count": len(plans),
        }

    async def update_plan(self, plan_name: str, updates: dict) -> dict:
        try:
            plan_enum = PlanEnum(plan_name)
        except ValueError:
            raise ValidationException(f"Invalid plan '{plan_name}'")

        plan = await self.admin_dao.get_plan_by_name(plan_enum)
        if not plan:
            raise NotFoundException("Plan")

        allowed = {
            "campaigns_per_month", "team_seats", "platforms_allowed",
            "ugc_mode", "white_label", "api_access",
            "price_monthly", "price_yearly",
            "stripe_price_id_monthly", "stripe_price_id_yearly",
        }
        clean = {k: v for k, v in updates.items() if k in allowed and v is not None}
        updated = await self.admin_dao.update_plan(UUID(str(plan.id)), clean)        
        logger.info(f"Plan '{plan_name}' updated by admin")

        return {
            "message": f"Plan '{plan_name}' updated successfully",
            "plan": self._plan_to_dict(updated) if updated else {},
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _user_to_dict(user) -> dict:
        role = "user"
        if user.user_roles:
            role = str(user.user_roles[0].role.name.value) if user.user_roles[0].role else "user"

        plan = "free"
        if user.subscription and user.subscription.plan:
            plan = str(user.subscription.plan.name.value)

        campaigns_used = 0
        if user.subscription:
            campaigns_used = int(user.subscription.campaigns_used_this_month or 0)

        return {
            "id": str(user.id),
            "email": str(user.email),
            "full_name": str(user.full_name),
            "is_active": bool(user.is_active),
            "is_verified": bool(user.is_verified),
            "role": role,
            "plan": plan,
            "campaigns_used_this_month": campaigns_used,
            "stripe_customer_id": str(user.stripe_customer_id) if user.stripe_customer_id is not None else None,
            "created_at": user.created_at.isoformat() if user.created_at is not None else None,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at is not None else None,
        }

    @staticmethod
    def _plan_to_dict(plan) -> dict:
        return {
            "id": str(plan.id),
            "name": str(plan.name.value),
            "display_name": str(plan.display_name),
            "price_monthly": float(plan.price_monthly),
            "price_yearly": float(plan.price_yearly),
            "campaigns_per_month": int(plan.campaigns_per_month) if plan.campaigns_per_month is not None else 3,
            "team_seats": int(plan.team_seats) if plan.team_seats is not None else 1,
            "platforms_allowed": int(plan.platforms_allowed) if plan.platforms_allowed is not None else 0,
            "ugc_mode": bool(plan.ugc_mode),
            "white_label": bool(plan.white_label),
            "api_access": bool(plan.api_access),
            "stripe_price_id_monthly": str(plan.stripe_price_id_monthly) if plan.stripe_price_id_monthly is not None else None,
            "stripe_price_id_yearly": str(plan.stripe_price_id_yearly) if plan.stripe_price_id_yearly is not None else None,
        }