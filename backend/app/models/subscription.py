"""
AdEngineAI — Subscription Models
===================================
Tables:
    subscription_plans  — plan definitions (free/starter/pro/agency)
    subscriptions       — user subscription state + Stripe data
"""

import enum

from sqlalchemy import (
    Boolean, Column, DateTime, Enum,
    Float, ForeignKey, Integer, String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import Base, utcnow, new_uuid


class PlanEnum(str, enum.Enum):
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    AGENCY = "agency"


class SubscriptionStatusEnum(str, enum.Enum):
    ACTIVE = "active"
    TRIALING = "trialing"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    INCOMPLETE = "incomplete"


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    name = Column(Enum(PlanEnum), unique=True, nullable=False)
    display_name = Column(String(100), nullable=False)
    price_monthly = Column(Float, nullable=False)
    price_yearly = Column(Float, nullable=False)
    stripe_price_id_monthly = Column(String(255), nullable=True)
    stripe_price_id_yearly = Column(String(255), nullable=True)

    # Feature limits
    campaigns_per_month = Column(Integer, default=3)    # -1 = unlimited
    team_seats = Column(Integer, default=1)
    platforms_allowed = Column(Integer, default=0)      # 0 = no publishing
    ugc_mode = Column(Boolean, default=False)
    white_label = Column(Boolean, default=False)
    api_access = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), default=utcnow)

    subscriptions = relationship("Subscription", back_populates="plan")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    plan_id = Column(UUID(as_uuid=True), ForeignKey("subscription_plans.id"), nullable=False)

    # Stripe
    stripe_subscription_id = Column(String(255), unique=True, nullable=True)
    stripe_current_period_start = Column(DateTime(timezone=True), nullable=True)
    stripe_current_period_end = Column(DateTime(timezone=True), nullable=True)
    status = Column(
        Enum(SubscriptionStatusEnum),
        default=SubscriptionStatusEnum.TRIALING,
    )
    cancel_at_period_end = Column(Boolean, default=False)

    # Usage tracking
    campaigns_used_this_month = Column(Integer, default=0)
    usage_reset_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="subscription")
    plan = relationship("SubscriptionPlan", back_populates="subscriptions")