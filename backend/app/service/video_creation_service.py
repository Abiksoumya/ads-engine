"""
AdEngineAI — Video Creation Service
======================================
Business logic for the Video Creator flow (/create page).

Flow:
  create()           → user submits prompt + images
  get_creation()     → get creation with brief
  list_creations()   → list user's creations
  update_brief()     → user edits brief
  render()           → trigger Kling + FFmpeg via Celery

Used by video_creation_controller.py
"""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.video_creation import VideoCreationDAO
from app.dao.video_brief_dao import VideoBriefDAO
from app.models.video_creation import CreationStatus
from app.models.video_brief import BriefStatus
from app.core.exceptions import (
    NotFoundException,
    ValidationException,
)
from visual_director.agent import VisualDirectorAgent
from uuid import UUID as PyUUID


logger = logging.getLogger(__name__)


class VideoCreationService:

    def __init__(self, db: AsyncSession):
        self.db = db
        self.creation_dao = VideoCreationDAO(db)
        self.brief_dao = VideoBriefDAO(db)

    # ------------------------------------------------------------------
    # Create new video (Flow 2 entry point)
    # ------------------------------------------------------------------

    async def create(
        self,
        user_id: UUID,
        user_prompt: str,
        uploaded_images: list[str],
        scene_count: int = 3,
        aspect_ratio: str = "9:16",
        subtitles: bool = False,
        user_preferences: dict | None = None,
    ) -> dict:
        """
        Creates a new video creation and generates the video brief.

        Steps:
          1. Save creation to DB
          2. Call Visual Director Agent
          3. Save brief to DB
          4. Return creation + brief for user to review/edit
        """
        prefs = user_preferences or {}

        # Validate scene count
        if scene_count not in (1,3, 6):
            raise ValidationException("scene_count must be 3 or 6")

        # Create the creation record
        creation = await self.creation_dao.create({
            "user_id": user_id,
            "user_prompt": user_prompt,
            "uploaded_images": uploaded_images,
            "scene_count": scene_count,
            "aspect_ratio": aspect_ratio,
            "subtitles": subtitles,
            "preferred_tone": prefs.get("tone"),
            "preferred_palette": prefs.get("color_palette"),
            "preferred_pacing": prefs.get("pacing"),
            "preferred_background": prefs.get("background_style"),
            "status": CreationStatus.GENERATING_BRIEF,
        })

        await self.db.commit()

        logger.info(f"VideoCreation {creation.id} created for user {user_id}")

        # Generate brief using Visual Director
        try:
            agent = VisualDirectorAgent()
            result = await agent.creation_brief(
                user_prompt=user_prompt,
                uploaded_images=uploaded_images,
                scene_count=scene_count,
                user_preferences=prefs,
            )

            # Save brief
            brief = await self.brief_dao.create({
                "creation_id": creation.id,
                "script_id": None,
                "tone": result.tone,
                "color_palette": result.color_palette,
                "pacing": result.pacing,
                "music_mood": result.music_mood,
                "voiceover_script": result.voiceover_script,
                "scene_count": result.scene_count,
                "duration_secs": result.duration_secs,
                "aspect_ratio": aspect_ratio,
                "subtitles": subtitles,
                "scenes": [
                    {
                        "scene_number": s.scene_number,
                        "duration": s.duration,
                        "background": s.background,
                        "action": s.action,
                        "color_mood": s.color_mood,
                        "camera": s.camera,
                        "text_overlay": s.text_overlay,
                        "use_uploaded_image": s.use_uploaded_image,
                        "product_image_url": s.product_image_url,
                        "kling_prompt": s.kling_prompt,
                    }
                    for s in result.scenes
                ],
                "status": BriefStatus.DRAFT,
            })

            # Update creation status
            await self.creation_dao.update_status(
                PyUUID(str(creation.id)),
                CreationStatus.BRIEF_READY,
            )

            await self.db.commit()

            # Refresh to get brief
            creation = await self.creation_dao.get_by_id(PyUUID(str(creation.id)))

            return {
                "message": "Video brief generated. Review and edit before rendering.",
                "creation": creation.to_dict() if creation else {},
            }

        except Exception as e:
            logger.error(f"Brief generation failed for creation {creation.id}: {e}")
            await self.creation_dao.update_status(
                PyUUID(str(creation.id)),
                CreationStatus.FAILED,
                error_message=str(e),
            )
            await self.db.commit()
            raise

    # ------------------------------------------------------------------
    # Get creation
    # ------------------------------------------------------------------

    async def get_creation(
        self,
        creation_id: UUID,
        user_id: UUID,
    ) -> dict:
        creation = await self.creation_dao.get_by_id(creation_id)
        if not creation:
            raise NotFoundException("Video creation")

        if str(creation.user_id) != str(user_id):
            raise NotFoundException("Video creation")

        return {"creation": creation.to_dict()}

    # ------------------------------------------------------------------
    # List creations
    # ------------------------------------------------------------------

    async def list_creations(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 20,
    ) -> dict:
        creations = await self.creation_dao.get_by_user(
            user_id=user_id,
            skip=skip,
            limit=limit,
        )
        total = await self.creation_dao.count_by_user(user_id)

        return {
            "creations": [c.to_dict() for c in creations],
            "total": total,
            "skip": skip,
            "limit": limit,
        }

    # ------------------------------------------------------------------
    # Update brief (user edits)
    # ------------------------------------------------------------------

    async def update_brief(
        self,
        creation_id: UUID,
        user_id: UUID,
        updates: dict,
    ) -> dict:
        """User edits the video brief before rendering."""
        creation = await self.creation_dao.get_by_id(creation_id)
        if not creation:
            raise NotFoundException("Video creation")

        if str(creation.user_id) != str(user_id):
            raise NotFoundException("Video creation")

        brief = await self.brief_dao.get_by_creation_id(creation_id)
        if not brief:
            raise NotFoundException("Video brief")

        allowed = {
            "tone", "color_palette", "pacing",
            "voiceover_script", "scenes",
            "subtitles", "aspect_ratio",
        }
        clean = {k: v for k, v in updates.items() if k in allowed and v is not None}

        if not clean:
            raise ValidationException("No valid fields to update")

        updated = await self.brief_dao.update(PyUUID(str(brief.id)), clean)
        await self.db.commit()

        return {
            "message": "Brief updated successfully",
            "brief": updated.to_dict() if updated else {},
        }

    # ------------------------------------------------------------------
    # Trigger render
    # ------------------------------------------------------------------

    async def render(
        self,
        creation_id: UUID,
        user_id: UUID,
        aspect_ratio: str = "9:16",
        voice_style: str = "professional",
    ) -> dict:
        """
        Approves brief and triggers Celery render task.
        """
        creation = await self.creation_dao.get_by_id(creation_id)
        if not creation:
            raise NotFoundException("Video creation")

        if str(creation.user_id) != str(user_id):
            raise NotFoundException("Video creation")

        if str(creation.status) == CreationStatus.RENDERING.value:
            raise ValidationException("Already rendering")

        if str(creation.status) == CreationStatus.COMPLETE.value:
            raise ValidationException("Already complete. Use force=true to re-render")

        brief = await self.brief_dao.get_by_creation_id(creation_id)
        if not brief:
            raise NotFoundException("Video brief — generate brief first")

        # Update statuses
        await self.brief_dao.update_status(PyUUID(str(brief.id)), BriefStatus.APPROVED)

        await self.creation_dao.update_status(creation_id, CreationStatus.RENDERING)
        await self.db.commit()

        # Trigger Celery task
        from tasks.video_creation_tasks import render_creation_task
        render_creation_task.delay( # type: ignore
            str(creation_id),
            str(brief.id),
            aspect_ratio,
            voice_style,
        )

        logger.info(f"Render triggered for creation {creation_id}")

        return {
            "message": "Render started. Check status for updates.",
            "creation_id": str(creation_id),
            "status": "rendering",
        }