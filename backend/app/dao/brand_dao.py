"""
AdEngineAI — Brand DAO
========================
All BrandDNA database queries.
No business logic — only DB operations.
"""

import logging
from uuid import UUID

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import BrandDNA
from app.core.exceptions import DatabaseException

logger = logging.getLogger(__name__)


class BrandDAO:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, brand_id: UUID) -> BrandDNA | None:
        try:
            result = await self.db.execute(
                select(BrandDNA).where(BrandDNA.id == brand_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"get_by_id failed: {e}")
            raise DatabaseException()

    async def get_by_user(self, user_id: UUID) -> list[BrandDNA]:
        try:
            result = await self.db.execute(
                select(BrandDNA)
                .where(BrandDNA.user_id == user_id)
                .order_by(BrandDNA.is_default.desc(), BrandDNA.created_at.desc())
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"get_by_user failed: {e}")
            raise DatabaseException()

    async def get_default(self, user_id: UUID) -> BrandDNA | None:
        try:
            result = await self.db.execute(
                select(BrandDNA).where(
                    BrandDNA.user_id == user_id,
                    BrandDNA.is_default == True,
                )
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"get_default failed: {e}")
            raise DatabaseException()

    async def create(
        self,
        user_id: UUID,
        name: str,
        tone: str = "professional",
        audience: str | None = None,
        colors: list | None = None,
        avoid_topics: list | None = None,
        preferred_actor: str = "professional",
        preferred_voice: str = "professional",
        is_default: bool = False,
    ) -> BrandDNA:
        try:
            brand = BrandDNA(
                user_id=user_id,
                name=name,
                tone=tone,
                audience=audience,
                colors=colors or [],
                avoid_topics=avoid_topics or [],
                preferred_actor=preferred_actor,
                preferred_voice=preferred_voice,
                is_default=is_default,
            )
            self.db.add(brand)
            await self.db.flush()
            return brand
        except Exception as e:
            logger.error(f"create brand failed: {e}")
            raise DatabaseException()

    async def update(self, brand_id: UUID, values: dict) -> BrandDNA | None:
        try:
            await self.db.execute(
                update(BrandDNA).where(BrandDNA.id == brand_id).values(**values)
            )
            return await self.get_by_id(brand_id)
        except Exception as e:
            logger.error(f"update brand failed: {e}")
            raise DatabaseException()

    async def delete(self, brand_id: UUID) -> None:
        try:
            await self.db.execute(
                delete(BrandDNA).where(BrandDNA.id == brand_id)
            )
        except Exception as e:
            logger.error(f"delete brand failed: {e}")
            raise DatabaseException()

    async def clear_default(self, user_id: UUID) -> None:
        """Removes default flag from all user's brands."""
        try:
            await self.db.execute(
                update(BrandDNA)
                .where(BrandDNA.user_id == user_id)
                .values(is_default=False)
            )
        except Exception as e:
            logger.error(f"clear_default failed: {e}")
            raise DatabaseException()

    async def set_default(self, brand_id: UUID, user_id: UUID) -> None:
        """Sets one brand as default — clears all others first."""
        try:
            await self.clear_default(user_id)
            await self.db.execute(
                update(BrandDNA)
                .where(BrandDNA.id == brand_id)
                .values(is_default=True)
            )
        except Exception as e:
            logger.error(f"set_default failed: {e}")
            raise DatabaseException()

    async def count_by_user(self, user_id: UUID) -> int:
        try:
            from sqlalchemy import func
            result = await self.db.execute(
                select(func.count()).where(BrandDNA.user_id == user_id)
            )
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"count_by_user failed: {e}")
            raise DatabaseException()