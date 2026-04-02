"""
AdEngineAI — Video Creation DAO
=================================
Database queries for video creations (Flow 2).
"""

import logging
from uuid import UUID

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.video_creation import VideoCreation, CreationStatus
from app.models.video_brief import VideoBrief
from app.core.exceptions import DatabaseException

logger = logging.getLogger(__name__)


class VideoCreationDAO:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: dict) -> VideoCreation:
        try:
            creation = VideoCreation(**data)
            self.db.add(creation)
            await self.db.flush()
            await self.db.refresh(creation)
            return creation
        except Exception as e:
            logger.error(f"create video creation failed: {e}")
            raise DatabaseException()

    async def get_by_id(self, creation_id: UUID) -> VideoCreation | None:
        try:
            result = await self.db.execute(
                select(VideoCreation)
                .options(selectinload(VideoCreation.video_brief))
                .where(VideoCreation.id == creation_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"get video creation failed: {e}")
            raise DatabaseException()

    async def get_by_user(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 20,
    ) -> list[VideoCreation]:
        try:
            result = await self.db.execute(
                select(VideoCreation)
                .options(selectinload(VideoCreation.video_brief))
                .where(VideoCreation.user_id == user_id)
                .order_by(VideoCreation.created_at.desc())
                .offset(skip)
                .limit(limit)
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"get creations by user failed: {e}")
            raise DatabaseException()

    async def count_by_user(self, user_id: UUID) -> int:
        try:
            result = await self.db.execute(
                select(func.count(VideoCreation.id))
                .where(VideoCreation.user_id == user_id)
            )
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"count creations failed: {e}")
            raise DatabaseException()

    async def update_status(
        self,
        creation_id: UUID,
        status: CreationStatus,
        error_message: str | None = None,
    ) -> None:
        try:
            values: dict = {"status": status}
            if error_message is not None:
                values["error_message"] = error_message
            await self.db.execute(
                update(VideoCreation)
                .where(VideoCreation.id == creation_id)
                .values(**values)
            )
        except Exception as e:
            logger.error(f"update creation status failed: {e}")
            raise DatabaseException()

    async def save_final_video(
        self,
        creation_id: UUID,
        aspect_ratio: str,
        video_url: str,
        audio_url: str | None = None,
    ) -> None:
        try:
            values: dict = {
                "status": CreationStatus.COMPLETE,
                "final_video_url": video_url,
            }
            if audio_url:
                values["audio_url"] = audio_url
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
                update(VideoCreation)
                .where(VideoCreation.id == creation_id)
                .values(**values)
            )
        except Exception as e:
            logger.error(f"save final video failed: {e}")
            raise DatabaseException()