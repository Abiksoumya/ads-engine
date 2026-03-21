"""
AdEngineAI — Brand Service
============================
Business logic for Brand DNA management.
"""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.brand_dao import BrandDAO
from app.core.exceptions import (
    BrandNotFoundException,
    ForbiddenException,
    ValidationException,
)

logger = logging.getLogger(__name__)

# Max brands per user per plan
MAX_BRANDS = {
    "free": 1,
    "starter": 3,
    "pro": 10,
    "agency": -1,   # unlimited
}


class BrandService:

    def __init__(self, db: AsyncSession):
        self.db = db
        self.brand_dao = BrandDAO(db)

    async def create(
        self,
        user_id: UUID,
        plan: str,
        name: str,
        tone: str = "professional",
        audience: str | None = None,
        colors: list | None = None,
        avoid_topics: list | None = None,
        preferred_actor: str = "professional",
        preferred_voice: str = "professional",
    ) -> dict:
        # Check brand limit for plan
        max_brands = MAX_BRANDS.get(plan, 1)
        if max_brands != -1:
            count = await self.brand_dao.count_by_user(user_id)
            if count >= max_brands:
                raise ValidationException(
                    f"Your '{plan}' plan allows up to {max_brands} brand(s). "
                    f"Upgrade to create more."
                )

        # First brand is automatically default
        existing = await self.brand_dao.get_by_user(user_id)
        is_default = len(existing) == 0

        brand = await self.brand_dao.create(
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

        logger.info(f"Brand created: {name} for user {user_id}")
        return self._to_dict(brand)

    async def get_by_id(self, brand_id: UUID, user_id: UUID) -> dict:
        brand = await self._get_and_verify_owner(brand_id, user_id)
        return self._to_dict(brand)

    async def list_my_brands(self, user_id: UUID) -> dict:
        brands = await self.brand_dao.get_by_user(user_id)
        return {
            "brands": [self._to_dict(b) for b in brands],
            "count": len(brands),
        }

    async def update(
        self,
        brand_id: UUID,
        user_id: UUID,
        updates: dict,
    ) -> dict:
        await self._get_and_verify_owner(brand_id, user_id)

        # Only allow updating these fields
        allowed = {
            "name", "tone", "audience", "colors",
            "avoid_topics", "preferred_actor", "preferred_voice",
        }
        clean = {k: v for k, v in updates.items() if k in allowed and v is not None}

        if not clean:
            raise ValidationException("No valid fields to update")

        brand = await self.brand_dao.update(brand_id, clean)
        if not brand:
            raise BrandNotFoundException()

        logger.info(f"Brand updated: {brand_id}")
        return self._to_dict(brand)

    async def delete(self, brand_id: UUID, user_id: UUID) -> dict:
        brand = await self._get_and_verify_owner(brand_id, user_id)

        # Don't allow deleting default brand if others exist
        if bool(brand.is_default):
            others = await self.brand_dao.get_by_user(user_id)
            if len(others) > 1:
                raise ValidationException(
                    "Cannot delete default brand. Set another brand as default first."
                )

        await self.brand_dao.delete(brand_id)
        logger.info(f"Brand deleted: {brand_id}")
        return {"message": "Brand deleted successfully"}

    async def set_default(self, brand_id: UUID, user_id: UUID) -> dict:
        await self._get_and_verify_owner(brand_id, user_id)
        await self.brand_dao.set_default(brand_id, user_id)
        logger.info(f"Default brand set: {brand_id}")
        return {"message": "Default brand updated successfully"}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_and_verify_owner(self, brand_id: UUID, user_id: UUID):
        brand = await self.brand_dao.get_by_id(brand_id)
        if not brand:
            raise BrandNotFoundException()
        if str(brand.user_id) != str(user_id):
            raise ForbiddenException("You don't have access to this brand")
        return brand

    @staticmethod
    def _to_dict(brand) -> dict:
        return {
            "id": str(brand.id),
            "user_id": str(brand.user_id),
            "name": str(brand.name),
            "tone": str(brand.tone),
            "audience": str(brand.audience) if brand.audience is not None else None,
            "colors": brand.colors or [],
            "avoid_topics": brand.avoid_topics or [],
            "preferred_actor": str(brand.preferred_actor),
            "preferred_voice": str(brand.preferred_voice),
            "top_hooks": brand.top_hooks or [],
            "avg_confidence": float(brand.avg_confidence) if brand.avg_confidence is not None else 0.0,
            "total_campaigns": int(brand.total_campaigns) if brand.total_campaigns is not None else 0,
            "is_default": bool(brand.is_default),
            "created_at": brand.created_at.isoformat() if brand.created_at is not None else None,
            "updated_at": brand.updated_at.isoformat() if brand.updated_at is not None else None,
        }