"""
AdEngineAI — Campaign Routes
==============================
POST   /api/campaigns              → create campaign + trigger pipeline
GET    /api/campaigns              → list my campaigns
GET    /api/campaigns/{id}         → get campaign + scripts + videos
GET    /api/campaigns/{id}/status  → get pipeline status
DELETE /api/campaigns/{id}         → delete campaign
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers.campaign_controller import CampaignController
from app.core.dependencies import get_current_user, get_db_session, CurrentUser

router = APIRouter(prefix="/api/campaigns", tags=["Campaigns"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CreateCampaignRequest(BaseModel):
    product_url: str = Field(min_length=10, max_length=2000)
    brand_id: UUID | None = None
    ugc_mode: bool = False
    voice_style: str = Field(
        default="professional",
        pattern="^(professional|casual|energetic|warm|authoritative)$",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", status_code=201, summary="Create campaign + trigger AI pipeline")
async def create_campaign(
    body: CreateCampaignRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Creates a campaign and triggers the full AI pipeline:
    Researcher → Director → Production → QA

    Returns immediately — pipeline runs in the background.
    Poll GET /api/campaigns/{id}/status to track progress.
    """
    controller = CampaignController(db)
    return await controller.create(body.model_dump(), current_user)


@router.get("", summary="List my campaigns")
async def list_campaigns(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    controller = CampaignController(db)
    return await controller.list_campaigns(skip, limit, current_user)


@router.get("/{campaign_id}/status", summary="Get pipeline status")
async def get_status(
    campaign_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Returns the current pipeline status.
    Poll this every 5 seconds to track progress.

    Status values:
        pending      → queued, not started
        researching  → Researcher Agent running
        scripting    → Director Agent writing scripts
        rendering    → Production Crew rendering videos
        qa           → QA Agent checking quality
        complete     → all done, scripts + videos ready
        failed       → pipeline error — check error_message
    """
    controller = CampaignController(db)
    return await controller.get_status(campaign_id, current_user)


@router.get("/{campaign_id}", summary="Get campaign with scripts")
async def get_campaign(
    campaign_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Returns full campaign with all 5 scripts and video URLs."""
    controller = CampaignController(db)
    return await controller.get_campaign(campaign_id, current_user)


@router.delete("/{campaign_id}", summary="Delete campaign")
async def delete_campaign(
    campaign_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    controller = CampaignController(db)
    return await controller.delete_campaign(campaign_id, current_user)