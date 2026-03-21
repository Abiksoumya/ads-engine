"""
AdEngineAI — Campaign Service
================================
Business logic for campaign management.
Triggers the AI pipeline (Researcher → Director → Production → QA).

The pipeline runs as a background task so the API returns immediately.
Progress is tracked via campaign status in the database.
"""

import asyncio
import logging
import sys
import os
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

    # ------------------------------------------------------------------
    # Create campaign + trigger pipeline
    # ------------------------------------------------------------------

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
        Creates a campaign and triggers the AI pipeline as a background task.
        Returns immediately — pipeline runs async.
        """
        # Check subscription limit
        can_create, reason = await self.subscription_dao.can_create_campaign(user_id)
        if not can_create:
            raise SubscriptionRequiredException(reason)

        # Validate URL
        if not product_url.startswith(("http://", "https://")):
            raise ValidationException("Product URL must start with http:// or https://")

        # Get brand context
        brand_tone = ""
        brand_audience = ""
        if brand_id:
            brand = await self.brand_dao.get_by_id(brand_id)
            if brand and str(brand.user_id) == str(user_id):
                brand_tone = str(brand.tone) if brand.tone is not None else ""
                brand_audience = str(brand.audience) if brand.audience is not None else ""
        else:
            # Use default brand if exists
            default_brand = await self.brand_dao.get_default(user_id)
            if default_brand:
                brand_id = UUID(str(default_brand.id))
                brand_tone = str(default_brand.tone) if default_brand.tone is not None else ""
                brand_audience = str(default_brand.audience) if default_brand.audience is not None else ""

        # Create campaign record
        campaign = await self.campaign_dao.create(
            user_id=user_id,
            product_url=product_url,
            brand_id=brand_id,
            ugc_mode=ugc_mode,
            voice_style=voice_style,
        )

        campaign_id = UUID(str(campaign.id))

        # Increment usage counter
        await self.subscription_dao.increment_campaign_usage(user_id)

        # Trigger pipeline as background task
        asyncio.create_task(
            self._run_pipeline(
                campaign_id=campaign_id,
                product_url=product_url,
                brand_tone=brand_tone,
                brand_audience=brand_audience,
            )
        )

        logger.info(f"Campaign created: {campaign_id} for user {user_id}")

        return {
            "id": str(campaign_id),
            "status": "pending",
            "product_url": product_url,
            "message": "Campaign created. Pipeline is running — check status for progress.",
        }

    # ------------------------------------------------------------------
    # Pipeline runner (background task)
    # ------------------------------------------------------------------

    async def _run_pipeline(
        self,
        campaign_id: UUID,
        product_url: str,
        brand_tone: str,
        brand_audience: str,
    ) -> None:
        """
        Runs as a background task with its own database session.
        Never uses the request session — that's already closed.
        """
        import sys
        import os
        from app.db.database import AsyncSessionFactory

        agents_path = os.path.join(os.path.dirname(__file__), "..", "..", "agents")
        if agents_path not in sys.path:
            sys.path.insert(0, agents_path)

        async with AsyncSessionFactory() as db:
            campaign_dao = CampaignDAO(db)

            try:
                from orchestrator.agent import Orchestrator

                await campaign_dao.update_status(campaign_id, CampaignStatusEnum.RESEARCHING)
                await db.commit()

                orchestrator = Orchestrator()
                result = await orchestrator.run(
                    product_url=product_url,
                    job_id=str(campaign_id),
                    brand_tone=brand_tone,
                    brand_audience=brand_audience,
                )

                if result.status == "failed":
                    await campaign_dao.update_status(
                        campaign_id,
                        CampaignStatusEnum.FAILED,
                        error_message=str(result.errors),
                    )
                    await db.commit()
                    return

                if result.research:
                    await campaign_dao.save_research(
                        campaign_id=campaign_id,
                        research_result={
                            "product_name": result.research.product_name,
                            "product_category": result.research.product_category,
                            "pain_points": result.research.pain_points,
                            "selling_points": result.research.selling_points,
                            "social_proof": result.research.social_proof,
                            "target_audience": result.research.target_audience,
                            "key_differentiator": result.research.key_differentiator,
                        },
                        confidence_score=result.research.confidence_score,
                    )
                    await db.commit()

                if result.scripts:
                    await campaign_dao.update_status(campaign_id, CampaignStatusEnum.SCRIPTING)
                    scripts_data = [
                        {
                            "hook_type": s.hook_type,
                            "hook_line": s.hook_line,
                            "script": s.script,
                            "hook_score": {
                                "score": s.hook_score.score,
                                "primary_trigger": s.hook_score.primary_trigger,
                                "reasoning": s.hook_score.reasoning,
                                "best_platform": s.hook_score.best_platform,
                            },
                            "ad_headline": s.ad_headline,
                            "ad_description": s.ad_description,
                            "caption_instagram": s.caption_instagram,
                            "caption_tiktok": s.caption_tiktok,
                            "caption_linkedin": s.caption_linkedin,
                            "hashtags": s.hashtags,
                        }
                        for s in result.scripts
                    ]
                    await campaign_dao.save_scripts(campaign_id, scripts_data)
                    await db.commit()

                await campaign_dao.update_status(campaign_id, CampaignStatusEnum.COMPLETE)
                await db.commit()
                logger.info(f"Pipeline complete for campaign: {campaign_id}")

            except Exception as e:
                logger.error(f"Pipeline failed for campaign {campaign_id}: {e}")
                try:
                    await db.rollback()
                    await campaign_dao.update_status(
                        campaign_id,
                        CampaignStatusEnum.FAILED,
                        error_message=str(e),
                    )
                    await db.commit()
                except Exception as db_err:
                    logger.error(f"Failed to update error status: {db_err}")

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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
            "confidence_score": float(campaign.confidence_score) if campaign.confidence_score is not None else None,
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
                    "hook_score": int(s.hook_score) if s.hook_score is not None else None,
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