"""
AdEngineAI — Campaign DAO
===========================
All campaign-related database queries.
"""

import logging
from uuid import UUID

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.campaign import Campaign, Script, RenderResult, CampaignStatusEnum
from app.core.exceptions import DatabaseException

logger = logging.getLogger(__name__)


class CampaignDAO:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, campaign_id: UUID) -> Campaign | None:
        try:
            result = await self.db.execute(
                select(Campaign)
                .options(
                    selectinload(Campaign.scripts).selectinload(Script.render_results),
                    selectinload(Campaign.brand),
                )
                .where(Campaign.id == campaign_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"get_by_id failed: {e}")
            raise DatabaseException()

    async def get_by_user(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Campaign]:
        try:
            result = await self.db.execute(
                select(Campaign)
                .where(Campaign.user_id == user_id)
                .order_by(Campaign.created_at.desc())
                .offset(skip)
                .limit(limit)
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"get_by_user failed: {e}")
            raise DatabaseException()

    async def create(
        self,
        user_id: UUID,
        product_url: str,
        brand_id: UUID | None = None,
        ugc_mode: bool = False,
        voice_style: str = "professional",
    ) -> Campaign:
        try:
            campaign = Campaign(
                user_id=user_id,
                brand_id=brand_id,
                product_url=product_url,
                ugc_mode=ugc_mode,
                voice_style=voice_style,
                status=CampaignStatusEnum.PENDING,
            )
            self.db.add(campaign)
            await self.db.flush()
            return campaign
        except Exception as e:
            logger.error(f"create campaign failed: {e}")
            raise DatabaseException()

    async def update_status(
        self,
        campaign_id: UUID,
        status: CampaignStatusEnum,
        error_message: str | None = None,
    ) -> None:
        try:
            values: dict = {"status": status}
            if error_message:
                values["error_message"] = error_message
            if status == CampaignStatusEnum.COMPLETE:
                from datetime import datetime, timezone
                values["completed_at"] = datetime.now(timezone.utc)
            await self.db.execute(
                update(Campaign).where(Campaign.id == campaign_id).values(**values)
            )
        except Exception as e:
            logger.error(f"update_status failed: {e}")
            raise DatabaseException()

    async def save_research(
        self,
        campaign_id: UUID,
        research_result: dict,
        confidence_score: float,
    ) -> None:
        try:
            await self.db.execute(
                update(Campaign)
                .where(Campaign.id == campaign_id)
                .values(
                    research_result=research_result,
                    confidence_score=confidence_score,
                )
            )
        except Exception as e:
            logger.error(f"save_research failed: {e}")
            raise DatabaseException()

    async def save_scripts(
        self,
        campaign_id: UUID,
        scripts: list[dict],
    ) -> list[Script]:
        try:
            db_scripts = []
            for s in scripts:
                hook_score = s.get("hook_score", {})
                script = Script(
                    campaign_id=campaign_id,
                    hook_type=s.get("hook_type", ""),
                    hook_line=s.get("hook_line", ""),
                    script_text=s.get("script", ""),
                    hook_score=hook_score.get("score"),
                    hook_trigger=hook_score.get("primary_trigger"),
                    hook_reasoning=hook_score.get("reasoning"),
                    best_platform=hook_score.get("best_platform"),
                    ad_headline=s.get("ad_headline", ""),
                    ad_description=s.get("ad_description", ""),
                    caption_instagram=s.get("caption_instagram", ""),
                    caption_tiktok=s.get("caption_tiktok", ""),
                    caption_linkedin=s.get("caption_linkedin", ""),
                    hashtags=s.get("hashtags", []),
                )
                self.db.add(script)
                db_scripts.append(script)
            await self.db.flush()
            return db_scripts
        except Exception as e:
            logger.error(f"save_scripts failed: {e}")
            raise DatabaseException()

    async def delete(self, campaign_id: UUID) -> None:
        try:
            await self.db.execute(
                delete(Campaign).where(Campaign.id == campaign_id)
            )
        except Exception as e:
            logger.error(f"delete campaign failed: {e}")
            raise DatabaseException()

    async def count_by_user(self, user_id: UUID) -> int:
        try:
            from sqlalchemy import func
            result = await self.db.execute(
                select(func.count()).where(Campaign.user_id == user_id)
            )
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"count_by_user failed: {e}")
            raise DatabaseException()