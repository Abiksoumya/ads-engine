"""
AdEngineAI — Video Creation Routes
=====================================
POST /api/creations                      → create new video
GET  /api/creations                      → list user's creations
GET  /api/creations/{id}                 → get creation + brief
PUT  /api/creations/{id}/brief           → update brief
POST /api/creations/{id}/render          → trigger render
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers.video_creation_controller import VideoCreationController
from app.core.dependencies import get_current_user, get_db_session, CurrentUser

router = APIRouter(prefix="/api/creations", tags=["Video Creations"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CreateVideoRequest(BaseModel):
    user_prompt: str = Field(..., min_length=10, max_length=2000)
    uploaded_images: list[str] = Field(default_factory=list)
    scene_count: int = Field(default=3, ge=1, le=6)
    aspect_ratio: str = Field(
        default="9:16",
        pattern="^(9:16|1:1|16:9)$",
    )
    subtitles: bool = False
    preferences: dict = Field(default_factory=dict)


class UpdateBriefRequest(BaseModel):
    tone: str | None = None
    color_palette: str | None = None
    pacing: str | None = None
    voiceover_script: str | None = None
    scenes: list | None = None
    subtitles: bool | None = None
    aspect_ratio: str | None = None


class RenderCreationRequest(BaseModel):
    aspect_ratio: str = Field(
        default="9:16",
        pattern="^(9:16|1:1|16:9|all)$",
    )
    voice_style: str = Field(
        default="professional",
        pattern="^(professional|casual|energetic|warm|authoritative)$",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", summary="Create new video (Video Creator flow)")
async def create_video(
    body: CreateVideoRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    User submits a video description + optional images.
    AI generates script + video brief automatically.
    User reviews and edits before rendering.
    """
    controller = VideoCreationController(db)
    return await controller.create(body.model_dump(), current_user)


@router.get("", summary="List user's video creations")
async def list_creations(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    controller = VideoCreationController(db)
    return await controller.list(skip, limit, current_user)


@router.get("/{creation_id}", summary="Get video creation with brief")
async def get_creation(
    creation_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    controller = VideoCreationController(db)
    return await controller.get(creation_id, current_user)


@router.put("/{creation_id}/brief", summary="Update video brief")
async def update_brief(
    creation_id: UUID,
    body: UpdateBriefRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    User edits tone, palette, pacing, scenes, voiceover before rendering.
    """
    controller = VideoCreationController(db)
    return await controller.update_brief(
        creation_id,
        body.model_dump(exclude_none=True),
        current_user,
    )


@router.post("/{creation_id}/render", summary="Trigger video render")
async def render_creation(
    creation_id: UUID,
    body: RenderCreationRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    User approves brief and triggers Kling + FFmpeg render.
    """
    controller = VideoCreationController(db)
    return await controller.render(creation_id, body.model_dump(), current_user)