"""
AdEngineAI — Brand Routes
===========================
POST   /api/brands              → create brand
GET    /api/brands              → list my brands
GET    /api/brands/{id}         → get brand by ID
PUT    /api/brands/{id}         → update brand
DELETE /api/brands/{id}         → delete brand
PUT    /api/brands/{id}/default → set as default brand
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers.brand_controller import BrandController
from app.core.dependencies import get_current_user, get_db_session, CurrentUser

router = APIRouter(prefix="/api/brands", tags=["Brand DNA"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CreateBrandRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    tone: str = Field(default="professional", max_length=255)
    audience: str | None = Field(None, max_length=500)
    colors: list[str] = Field(default_factory=list)
    avoid_topics: list[str] = Field(default_factory=list)
    preferred_actor: str = Field(default="professional", max_length=100)
    preferred_voice: str = Field(default="professional", max_length=100)


class UpdateBrandRequest(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=255)
    tone: str | None = Field(None, max_length=255)
    audience: str | None = Field(None, max_length=500)
    colors: list[str] | None = None
    avoid_topics: list[str] | None = None
    preferred_actor: str | None = Field(None, max_length=100)
    preferred_voice: str | None = Field(None, max_length=100)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", status_code=201, summary="Create a brand")
async def create_brand(
    body: CreateBrandRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    controller = BrandController(db)
    return await controller.create(body.model_dump(), current_user)


@router.get("", summary="List my brands")
async def list_brands(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    controller = BrandController(db)
    return await controller.list_my_brands(current_user)


@router.get("/{brand_id}", summary="Get brand by ID")
async def get_brand(
    brand_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    controller = BrandController(db)
    return await controller.get_brand(brand_id, current_user)


@router.put("/{brand_id}", summary="Update brand")
async def update_brand(
    brand_id: UUID,
    body: UpdateBrandRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    controller = BrandController(db)
    return await controller.update_brand(brand_id, body.model_dump(exclude_none=True), current_user)


@router.delete("/{brand_id}", summary="Delete brand")
async def delete_brand(
    brand_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    controller = BrandController(db)
    return await controller.delete_brand(brand_id, current_user)


@router.put("/{brand_id}/default", summary="Set as default brand")
async def set_default(
    brand_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    controller = BrandController(db)
    return await controller.set_default(brand_id, current_user)