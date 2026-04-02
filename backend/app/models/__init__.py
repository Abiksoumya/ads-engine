"""
AdEngineAI — Models Package
==============================
Import all models here so SQLAlchemy's metadata knows about every table.
This is required for create_tables() and Alembic migrations to work.

Import order matters — models with foreign keys must come after
the models they reference.
"""

from app.models.base import Base, utcnow, new_uuid
from app.models.user import User, Role, UserRole, RoleEnum
from app.models.subscription import SubscriptionPlan, Subscription, PlanEnum, SubscriptionStatusEnum
from app.models.brand import BrandDNA
from app.models.campaign import Campaign, Script, RenderResult, CampaignStatusEnum
from app.models.publish import PublishJob, PlatformConnection, PublishStatusEnum
from app.models.audit import AuditLog
from app.models.video_creation import VideoCreation, CreationStatus
from app.models.video_brief import VideoBrief, BriefStatus

__all__ = [
    "Base", "utcnow", "new_uuid",
    "User", "Role", "UserRole", "RoleEnum",
    "SubscriptionPlan", "Subscription", "PlanEnum", "SubscriptionStatusEnum",
    "BrandDNA",
    "Campaign", "Script", "RenderResult", "CampaignStatusEnum",
    "PublishJob", "PlatformConnection", "PublishStatusEnum",
    "AuditLog",
    "VideoCreation", "CreationStatus",
    "VideoBrief", "BriefStatus",
]