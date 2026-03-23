"""
AdEngineAI — Campaign Service
================================
Business logic for campaign management.
Triggers the AI pipeline (Researcher → Director → Production → QA).

The pipeline runs as a Celery background task so the API returns immediately.
Progress is tracked via campaign status in the database.
"""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.campaign_dao import CampaignDAO
from app.dao.subscription_dao import SubscriptionDAO
from app.dao.brand_dao import BrandDAO
from app.models.campaign import CampaignStatusEnum
from app.core.exceptions import (
    CampaignNotFoundException,
    ForbiddenException,
    SubscriptionRequiredException,
    ValidationException,
)

logger = logging.getLogger(__name__)


class CampaignService:

    def __init__(self, db: AsyncSession):
        self.db = db
        self.campaign_dao = CampaignDAO(db)
        self.subscription_dao = SubscriptionDAO(db)
        self.brand_dao = BrandDAO(db)

    async def create(
        self,
        user_id: UUID,
        plan: str,
        product_url: str,
        brand_id: UUID | None = None,
        ugc_mode: bool = False,
        voice_style: str = "professional",
    ) -> dict:
        """
        Creates a campaign and triggers the AI pipeline via Celery.
        Returns immediately — pipeline runs in a worker process.
        """
        can_create, reason = await self.subscription_dao.can_create_campaign(user_id)
        if not can_create:
            raise SubscriptionRequiredException(reason)

        if not product_url.startswith(("http://", "https://")):
            raise ValidationException("Product URL must start with http:// or https://")

        brand_tone = ""
        brand_audience = ""
        if brand_id:
            brand = await self.brand_dao.get_by_id(brand_id)
            if brand and str(brand.user_id) == str(user_id):
                brand_tone = str(brand.tone) if brand.tone is not None else ""
                brand_audience = str(brand.audience) if brand.audience is not None else ""
        else:
            default_brand = await self.brand_dao.get_default(user_id)
            if default_brand:
                brand_id = UUID(str(default_brand.id))
                brand_tone = str(default_brand.tone) if default_brand.tone is not None else ""
                brand_audience = str(default_brand.audience) if default_brand.audience is not None else ""

        campaign = await self.campaign_dao.create(
            user_id=user_id,
            product_url=product_url,
            brand_id=brand_id,
            ugc_mode=ugc_mode,
            voice_style=voice_style,
        )

        campaign_id = UUID(str(campaign.id))

        await self.subscription_dao.increment_campaign_usage(user_id)

        # Dispatch to Celery pipeline worker
        from tasks.campaign_tasks import run_pipeline_task
        run_pipeline_task.delay(  # type: ignore[attr-defined]
            campaign_id=str(campaign_id),
            product_url=product_url,
            brand_tone=brand_tone,
            brand_audience=brand_audience,
        )

        logger.info(f"Campaign created: {campaign_id} for user {user_id}")

        return {
            "id": str(campaign_id),
            "status": "pending",
            "product_url": product_url,
            "message": "Campaign created. Pipeline is running — check status for progress.",
        }

    async def get_by_id(self, campaign_id: UUID, user_id: UUID) -> dict:
        campaign = await self._get_and_verify_owner(campaign_id, user_id)
        return self._to_dict(campaign, include_scripts=True)

    async def get_status(self, campaign_id: UUID, user_id: UUID) -> dict:
        campaign = await self._get_and_verify_owner(campaign_id, user_id)

        status = campaign.status
        confidence = campaign.confidence_score
        error = campaign.error_message
        created = campaign.created_at
        completed = campaign.completed_at

        return {
            "id": str(campaign.id),
            "status": status.value if status is not None else "pending",
            "confidence_score": float(str(confidence)) if confidence is not None else None,
            "error_message": str(error) if error is not None else None,
            "created_at": created.isoformat() if created is not None else None,
            "completed_at": completed.isoformat() if completed is not None else None,
        }

    async def list_my_campaigns(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 20,
    ) -> dict:
        campaigns = await self.campaign_dao.get_by_user(user_id, skip=skip, limit=limit)
        return {
            "campaigns": [self._to_dict(c) for c in campaigns],
            "skip": skip,
            "limit": limit,
            "count": len(campaigns),
        }

    async def delete(self, campaign_id: UUID, user_id: UUID) -> dict:
        await self._get_and_verify_owner(campaign_id, user_id)
        await self.campaign_dao.delete(campaign_id)
        logger.info(f"Campaign deleted: {campaign_id}")
        return {"message": "Campaign deleted successfully"}

    async def _get_and_verify_owner(self, campaign_id: UUID, user_id: UUID):
        campaign = await self.campaign_dao.get_by_id(campaign_id)
        if not campaign:
            raise CampaignNotFoundException()
        if str(campaign.user_id) != str(user_id):
            raise ForbiddenException("You don't have access to this campaign")
        return campaign

    @staticmethod
    def _to_dict(campaign, include_scripts: bool = False) -> dict:
        data: dict = {
            "id": str(campaign.id),
            "product_url": str(campaign.product_url),
            "status": str(campaign.status.value) if campaign.status else "pending",
            "confidence_score": float(str(campaign.confidence_score)) if campaign.confidence_score is not None else None,
            "ugc_mode": bool(campaign.ugc_mode),
            "voice_style": str(campaign.voice_style) if campaign.voice_style is not None else "professional",
            "error_message": str(campaign.error_message) if campaign.error_message is not None else None,
            "brand_id": str(campaign.brand_id) if campaign.brand_id is not None else None,
            "created_at": campaign.created_at.isoformat() if campaign.created_at is not None else None,
            "completed_at": campaign.completed_at.isoformat() if campaign.completed_at is not None else None,
        }

        if include_scripts and campaign.scripts:
            data["scripts"] = [
                {
                    "id": str(s.id),
                    "hook_type": str(s.hook_type),
                    "hook_line": str(s.hook_line),
                    "script_text": str(s.script_text),
                    "hook_score": int(str(s.hook_score)) if s.hook_score is not None else None,
                    "hook_trigger": str(s.hook_trigger) if s.hook_trigger is not None else None,
                    "hook_reasoning": str(s.hook_reasoning) if s.hook_reasoning is not None else None,
                    "best_platform": str(s.best_platform) if s.best_platform is not None else None,
                    "ad_headline": str(s.ad_headline) if s.ad_headline is not None else None,
                    "ad_description": str(s.ad_description) if s.ad_description is not None else None,
                    "caption_instagram": str(s.caption_instagram) if s.caption_instagram is not None else None,
                    "caption_tiktok": str(s.caption_tiktok) if s.caption_tiktok is not None else None,
                    "caption_linkedin": str(s.caption_linkedin) if s.caption_linkedin is not None else None,
                    "hashtags": s.hashtags or [],
                }
                for s in campaign.scripts
            ]

        return data