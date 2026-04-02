"""
AdEngineAI — Video Brief DAO
==============================
Database queries for video briefs.
"""

import logging
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.video_brief import VideoBrief, BriefStatus
from app.core.exceptions import DatabaseException

logger = logging.getLogger(__name__)


class VideoBriefDAO:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: dict) -> VideoBrief:
        try:
            brief = VideoBrief(**data)
            self.db.add(brief)
            await self.db.flush()
            await self.db.refresh(brief)
            return brief
        except Exception as e:
            logger.error(f"create video brief failed: {e}")
            raise DatabaseException()

    async def get_by_id(self, brief_id: UUID) -> VideoBrief | None:
        try:
            result = await self.db.execute(
                select(VideoBrief).where(VideoBrief.id == brief_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"get video brief failed: {e}")
            raise DatabaseException()

    async def get_by_script_id(self, script_id: UUID) -> VideoBrief | None:
        try:
            result = await self.db.execute(
                select(VideoBrief).where(VideoBrief.script_id == script_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"get brief by script failed: {e}")
            raise DatabaseException()

    async def get_by_creation_id(self, creation_id: UUID) -> VideoBrief | None:
        try:
            result = await self.db.execute(
                select(VideoBrief).where(VideoBrief.creation_id == creation_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"get brief by creation failed: {e}")
            raise DatabaseException()

    async def update(self, brief_id: UUID, values: dict) -> VideoBrief | None:
        try:
            await self.db.execute(
                update(VideoBrief)
                .where(VideoBrief.id == brief_id)
                .values(**values)
            )
            return await self.get_by_id(brief_id)
        except Exception as e:
            logger.error(f"update video brief failed: {e}")
            raise DatabaseException()

    async def update_status(
        self,
        brief_id: UUID,
        status: BriefStatus,
        error_message: str | None = None,
    ) -> None:
        try:
            values: dict = {"status": status}
            if error_message is not None:
                values["error_message"] = error_message
            await self.db.execute(
                update(VideoBrief)
                .where(VideoBrief.id == brief_id)
                .values(**values)
            )
        except Exception as e:
            logger.error(f"update brief status failed: {e}")
            raise DatabaseException()

    async def save_final_videos(
        self,
        brief_id: UUID,
        aspect_ratio: str,
        video_url: str,
    ) -> None:
        try:
            values: dict = {
                "status": BriefStatus.COMPLETE,
                "final_video_url": video_url,
            }
            if aspect_ratio == "9:16":
                values["final_video_9x16"] = video_url
            elif aspect_ratio == "1:1":
                values["final_video_1x1"] = video_url
            elif aspect_ratio == "16:9":
                values["final_video_16x9"] = video_url
            elif aspect_ratio == "all":
                values["final_video_9x16"] = video_url
                values["final_video_1x1"] = video_url
                values["final_video_16x9"] = video_url

            await self.db.execute(
                update(VideoBrief)
                .where(VideoBrief.id == brief_id)
                .values(**values)
            )
        except Exception as e:
            logger.error(f"save final videos failed: {e}")
            raise DatabaseException()