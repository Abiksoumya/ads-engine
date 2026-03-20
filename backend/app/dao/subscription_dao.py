"""
AdEngineAI — Subscription DAO
================================
All subscription-related database queries.
"""

import logging
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.subscription import Subscription, SubscriptionPlan, PlanEnum, SubscriptionStatusEnum
from app.core.exceptions import DatabaseException

logger = logging.getLogger(__name__)


class SubscriptionDAO:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_plan_by_name(self, plan_name: PlanEnum) -> SubscriptionPlan | None:
        try:
            result = await self.db.execute(
                select(SubscriptionPlan).where(SubscriptionPlan.name == plan_name)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"get_plan_by_name failed: {e}")
            raise DatabaseException()

    async def get_by_user_id(self, user_id: UUID) -> Subscription | None:
        try:
            result = await self.db.execute(
                select(Subscription)
                .options(selectinload(Subscription.plan))
                .where(Subscription.user_id == user_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"get_by_user_id failed: {e}")
            raise DatabaseException()

    async def create_free_subscription(self, user_id: UUID) -> Subscription:
        """Creates a free subscription for a new user."""
        try:
            plan = await self.get_plan_by_name(PlanEnum.FREE)
            if not plan:
                raise DatabaseException("Free plan not found — run seed data first")

            subscription = Subscription(
                user_id=user_id,
                plan_id=plan.id,
                status=SubscriptionStatusEnum.ACTIVE,
            )
            self.db.add(subscription)
            await self.db.flush()
            return subscription
        except DatabaseException:
            raise
        except Exception as e:
            logger.error(f"create_free_subscription failed: {e}")
            raise DatabaseException()

    async def update_stripe_data(
        self,
        user_id: UUID,
        stripe_subscription_id: str,
        plan_name: PlanEnum,
        status: SubscriptionStatusEnum,
        period_start,
        period_end,
    ) -> None:
        try:
            plan = await self.get_plan_by_name(plan_name)
            if not plan:
                raise DatabaseException(f"Plan '{plan_name}' not found")

            await self.db.execute(
                update(Subscription)
                .where(Subscription.user_id == user_id)
                .values(
                    plan_id=plan.id,
                    stripe_subscription_id=stripe_subscription_id,
                    status=status,
                    stripe_current_period_start=period_start,
                    stripe_current_period_end=period_end,
                )
            )
        except DatabaseException:
            raise
        except Exception as e:
            logger.error(f"update_stripe_data failed: {e}")
            raise DatabaseException()

    async def increment_campaign_usage(self, user_id: UUID) -> None:
        """Increments campaigns_used_this_month counter."""
        try:
            subscription = await self.get_by_user_id(user_id)
            if subscription:
                await self.db.execute(
                    update(Subscription)
                    .where(Subscription.user_id == user_id)
                    .values(
                        campaigns_used_this_month=Subscription.campaigns_used_this_month + 1
                    )
                )
        except Exception as e:
            logger.error(f"increment_campaign_usage failed: {e}")
            raise DatabaseException()

    async def can_create_campaign(self, user_id: UUID) -> tuple[bool, str]:
        """
        Checks if user can create a new campaign based on their plan limits.
        Returns (allowed, reason).
        """
        try:
            subscription = await self.get_by_user_id(user_id)
            if not subscription or not subscription.plan:
                return False, "No active subscription found"

            if subscription.status not in [
                SubscriptionStatusEnum.ACTIVE,
                SubscriptionStatusEnum.TRIALING,
            ]:
                return False, "Subscription is not active"

            limit = subscription.plan.campaigns_per_month
            if limit == -1:
                return True, "Unlimited"

            if subscription.campaigns_used_this_month >= limit:
                return False, f"Monthly limit of {limit} campaigns reached"

            return True, "OK"
        except Exception as e:
            logger.error(f"can_create_campaign failed: {e}")
            return False, "Could not verify subscription"