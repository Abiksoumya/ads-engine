"""
AdEngineAI — Admin DAO
========================
Database queries for admin operations.
Used by AdminService only.
"""

import logging
from uuid import UUID

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User, UserRole, Role, RoleEnum
from app.models.subscription import Subscription, SubscriptionPlan, PlanEnum, SubscriptionStatusEnum
from app.models.campaign import Campaign
from app.core.exceptions import DatabaseException

logger = logging.getLogger(__name__)


class AdminDAO:

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    async def get_all_users(
        self,
        skip: int = 0,
        limit: int = 50,
        search: str | None = None,
    ) -> list[User]:
        try:
            query = (
                select(User)
                .options(
                    selectinload(User.user_roles).selectinload(UserRole.role),
                    selectinload(User.subscription).selectinload(Subscription.plan),
                )
                .order_by(User.created_at.desc())
                .offset(skip)
                .limit(limit)
            )
            if search:
                query = query.where(
                    User.email.ilike(f"%{search}%") |
                    User.full_name.ilike(f"%{search}%")
                )
            result = await self.db.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"get_all_users failed: {e}")
            raise DatabaseException()

    async def count_users(self) -> int:
        try:
            result = await self.db.execute(select(func.count(User.id)))
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"count_users failed: {e}")
            raise DatabaseException()

    async def count_campaigns(self) -> int:
        try:
            result = await self.db.execute(select(func.count(Campaign.id)))
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"count_campaigns failed: {e}")
            raise DatabaseException()

    # ------------------------------------------------------------------
    # Subscription plans
    # ------------------------------------------------------------------

    async def get_all_plans(self) -> list[SubscriptionPlan]:
        try:
            result = await self.db.execute(
                select(SubscriptionPlan).order_by(SubscriptionPlan.price_monthly)
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"get_all_plans failed: {e}")
            raise DatabaseException()

    async def get_plan_by_name(self, plan_name: PlanEnum) -> SubscriptionPlan | None:
        try:
            result = await self.db.execute(
                select(SubscriptionPlan).where(SubscriptionPlan.name == plan_name)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"get_plan_by_name failed: {e}")
            raise DatabaseException()

    async def create_plan(self, plan_data: dict) -> SubscriptionPlan:
        try:
            plan = SubscriptionPlan(**plan_data)
            self.db.add(plan)
            await self.db.flush()
            return plan
        except Exception as e:
            logger.error(f"create_plan failed: {e}")
            raise DatabaseException()

    async def update_plan(self, plan_id: UUID, values: dict) -> SubscriptionPlan | None:
        try:
            await self.db.execute(
                update(SubscriptionPlan)
                .where(SubscriptionPlan.id == plan_id)
                .values(**values)
            )
            result = await self.db.execute(
                select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"update_plan failed: {e}")
            raise DatabaseException()

    # ------------------------------------------------------------------
    # User subscription management
    # ------------------------------------------------------------------

    async def assign_plan_to_user(
        self,
        user_id: UUID,
        plan_name: PlanEnum,
        assigned_by: UUID,
    ) -> Subscription:
        try:
            plan = await self.get_plan_by_name(plan_name)
            if not plan:
                raise DatabaseException(f"Plan '{plan_name}' not found")

            # Check existing subscription
            existing = await self.db.execute(
                select(Subscription).where(Subscription.user_id == user_id)
            )
            subscription = existing.scalar_one_or_none()

            if subscription:
                # Update existing
                await self.db.execute(
                    update(Subscription)
                    .where(Subscription.user_id == user_id)
                    .values(
                        plan_id=plan.id,
                        status=SubscriptionStatusEnum.ACTIVE,
                        campaigns_used_this_month=0,
                    )
                )
                await self.db.flush()
                result = await self.db.execute(
                    select(Subscription)
                    .options(selectinload(Subscription.plan))
                    .where(Subscription.user_id == user_id)
                )
                return result.scalar_one()
            else:
                # Create new
                new_sub = Subscription(
                    user_id=user_id,
                    plan_id=plan.id,
                    status=SubscriptionStatusEnum.ACTIVE,
                )
                self.db.add(new_sub)
                await self.db.flush()
                return new_sub
        except DatabaseException:
            raise
        except Exception as e:
            logger.error(f"assign_plan_to_user failed: {e}")
            raise DatabaseException()

    async def get_subscription_stats(self) -> dict:
        """Returns subscription counts per plan."""
        try:
            result = await self.db.execute(
                select(SubscriptionPlan.name, func.count(Subscription.id))
                .join(Subscription, Subscription.plan_id == SubscriptionPlan.id)
                .group_by(SubscriptionPlan.name)
            )
            rows = result.fetchall()
            return {str(row[0].value): row[1] for row in rows}
        except Exception as e:
            logger.error(f"get_subscription_stats failed: {e}")
            raise DatabaseException()