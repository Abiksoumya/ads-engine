"""
AdEngineAI — Video Brief Routes
==================================
POST /api/campaigns/{id}/scripts/{script_id}/brief   → generate brief
GET  /api/campaigns/{id}/scripts/{script_id}/brief   → get brief
PUT  /api/briefs/{brief_id}                          → update brief
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers.video_brief_controller import VideoBriefController
from app.core.dependencies import get_current_user, get_db_session, CurrentUser

router = APIRouter(tags=["Video Briefs"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GenerateBriefRequest(BaseModel):
    scene_count: int = Field(default=3, ge=3, le=6)
    preferences: dict = Field(default_factory=dict)


class UpdateBriefRequest(BaseModel):
    tone: str | None = None
    color_palette: str | None = None
    pacing: str | None = None
    voiceover_script: str | None = None
    scenes: list | None = None
    subtitles: bool | None = None
    aspect_ratio: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/api/campaigns/{campaign_id}/scripts/{script_id}/brief",
    summary="Generate video brief for a script",
)
async def generate_brief(
    campaign_id: UUID,
    script_id: UUID,
    body: GenerateBriefRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    controller = VideoBriefController(db)
    return await controller.generate(campaign_id, script_id, body.model_dump(), current_user)


@router.get(
    "/api/campaigns/{campaign_id}/scripts/{script_id}/brief",
    summary="Get video brief for a script",
)
async def get_brief(
    campaign_id: UUID,
    script_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    controller = VideoBriefController(db)
    return await controller.get(campaign_id, script_id, current_user)


@router.put(
    "/api/briefs/{brief_id}",
    summary="Update video brief (user edits)",
)
async def update_brief(
    brief_id: UUID,
    body: UpdateBriefRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    controller = VideoBriefController(db)
    return await controller.update(brief_id, body.model_dump(exclude_none=True), current_user)