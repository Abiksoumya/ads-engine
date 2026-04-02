"""
AdEngineAI — Script Edit + Video Render Routes
================================================
PUT  /api/campaigns/{id}/scripts/{script_id}  → edit a script before rendering
POST /api/campaigns/{id}/render               → trigger video rendering
GET  /api/campaigns/{id}/videos               → get all video URLs
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db_session, CurrentUser

router = APIRouter(prefix="/api/campaigns", tags=["Scripts & Videos"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class EditScriptRequest(BaseModel):
    script_text: str | None = Field(None, min_length=10, max_length=5000)
    hook_line: str | None = Field(None, min_length=3, max_length=500)
    ad_headline: str | None = Field(None, max_length=100)
    ad_description: str | None = Field(None, max_length=300)
    caption_instagram: str | None = None
    caption_tiktok: str | None = None
    caption_linkedin: str | None = None
    hashtags: list[str] | None = None


class RenderRequest(BaseModel):
    script_ids: list[UUID] | None = None
    voice_style: str = Field(
        default="professional",
        pattern="^(professional|casual|energetic|warm|authoritative)$",
    )
    aspect_ratio: str = Field(
        default="9:16",
        pattern="^(9:16|1:1|16:9|all)$",
        description="9:16=TikTok/Reels | 1:1=Instagram Feed | 16:9=YouTube | all=all 3 formats (3x cost)",
    )
    force: bool = False


# ---------------------------------------------------------------------------
# Edit script
# ---------------------------------------------------------------------------

@router.put(
    "/{campaign_id}/scripts/{script_id}",
    summary="Edit a script before rendering",
)
async def edit_script(
    campaign_id: UUID,
    script_id: UUID,
    body: EditScriptRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Edits a script before video rendering.
    Can update: script text, hook line, ad copy, captions, hashtags.
    Cannot change: hook_type (that's structural).
    """
    from app.service.script_service import ScriptService
    service = ScriptService(db)
    result = await service.edit_script(
        campaign_id=campaign_id,
        script_id=script_id,
        user_id=current_user.user_id,
        updates=body.model_dump(exclude_none=True),
    )
    return {"success": True, "data": result}


# ---------------------------------------------------------------------------
# Trigger rendering
# ---------------------------------------------------------------------------

@router.post(
    "/{campaign_id}/render",
    status_code=202,
    summary="Trigger video rendering",
)
async def render_videos(
    campaign_id: UUID,
    body: RenderRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Triggers video rendering for a campaign.
    Renders all 5 scripts by default, or specific ones if script_ids provided.

    Returns immediately — rendering runs in background.
    Poll GET /api/campaigns/{id}/status for progress.
    Takes 3-8 minutes for real D-ID renders.
    """
    from app.service.render_service import RenderService
    service = RenderService(db)
    result = await service.trigger_render(
        campaign_id=campaign_id,
        user_id=current_user.user_id,
        script_ids=body.script_ids,
        voice_style=body.voice_style,
    )
    return {"success": True, "data": result}


# ---------------------------------------------------------------------------
# Get videos
# ---------------------------------------------------------------------------

@router.get(
    "/{campaign_id}/videos",
    summary="Get all video URLs",
)
async def get_videos(
    campaign_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Returns all rendered video URLs for a campaign.
    Each script has 3 video variants: 9x16 (Reels), 1x1 (Feed), 16x9 (YouTube).
    """
    from app.service.render_service import RenderService
    service = RenderService(db)
    result = await service.get_videos(campaign_id, current_user.user_id)
    return {"success": True, "data": result}