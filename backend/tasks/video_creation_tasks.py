"""
AdEngineAI — Video Creation Celery Tasks
==========================================
Celery tasks for the Video Creator flow (Flow 2).

Task: render_creation_task
  1. Load creation + brief from DB
  2. Generate voiceover (ElevenLabs)
  3. Generate video scenes (fal.ai Kling)
  4. Stitch everything (FFmpeg)
  5. Save final video URL to DB
  6. Update status to complete

Queue: render (same as campaign render queue)
"""

import asyncio
import logging
from uuid import UUID

from celery_app import celery_app
from app.db.database import AsyncSessionFactory
from app.dao.video_brief_dao import VideoBriefDAO
from app.models.video_creation import CreationStatus
from app.models.video_brief import BriefStatus
from mcp_tools.fal_kling_tools import FalKlingTool
from mcp_tools.ffmpeg_tools import FFmpegStitcher
from app.dao.video_creation import VideoCreationDAO

logger = logging.getLogger(__name__)


@celery_app.task(
    name="tasks.render_creation",
    queue="render",
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def render_creation_task(
    creation_id: str,
    brief_id: str,
    aspect_ratio: str = "9:16",
    voice_style: str = "professional",
):
    """
    Celery task to render a video creation.
    Runs in the render queue worker.
    """
    logger.info(f"render_creation_task started: {creation_id}")

    try:
        asyncio.run(_render_creation(
            creation_id=UUID(creation_id),
            brief_id=UUID(brief_id),
            aspect_ratio=aspect_ratio,
            voice_style=voice_style,
        ))
        logger.info(f"render_creation_task complete: {creation_id}")

    except Exception as e:
        logger.error(f"render_creation_task failed: {creation_id} — {e}")
        # Update status to failed
        asyncio.run(_mark_failed(UUID(creation_id), UUID(brief_id), str(e)))
        raise


async def _render_creation(
    creation_id: UUID,
    brief_id: UUID,
    aspect_ratio: str,
    voice_style: str,
) -> None:
    """
    Async render pipeline for Video Creator flow.
    """
    from dotenv import load_dotenv

    load_dotenv()
    async with AsyncSessionFactory() as db:
        creation_dao = VideoCreationDAO(db)
        brief_dao = VideoBriefDAO(db)

        # Load creation + brief
        creation = await creation_dao.get_by_id(creation_id)
        brief = await brief_dao.get_by_id(brief_id)

        if not creation or not brief:
            raise ValueError(f"Creation or brief not found: {creation_id}")

        scenes: list = brief.scenes if brief.scenes is not None else []  # type: ignore
        voiceover_script = str(brief.voiceover_script or "")
        subtitles = bool(creation.subtitles)

        # Get uploaded images for scenes
        uploaded_images: list = creation.uploaded_images if creation.uploaded_images is not None else []  # type: ignore
        primary_image = uploaded_images[0] if uploaded_images else None

        # ------------------------------------------------------------------
        # Step 1 — Generate voiceover (ElevenLabs)
        # ------------------------------------------------------------------
        logger.info(f"Generating voiceover for creation {creation_id}")

        audio_url = await _generate_voiceover(
            script=voiceover_script,
            voice_style=voice_style,
        )

        # ------------------------------------------------------------------
        # Step 2 — Generate video scenes (Kling)
        # ------------------------------------------------------------------
        scenes: list = brief.scenes if brief.scenes is not None else []  # type: ignore
        voiceover_script = str(brief.voiceover_script or "")
        subtitles = bool(creation.subtitles)
        logger.info(f"Generating {len(scenes)} scenes for creation {creation_id}")

        kling = FalKlingTool()
        scene_clips = []

        for scene in scenes:
            # Use uploaded image if scene requests it
            image_url = primary_image if scene.get("use_uploaded_image") else None

            result = await kling.generate_scene(
                prompt=scene.get("kling_prompt", ""),
                duration=scene.get("duration", 10),
                aspect_ratio=aspect_ratio if aspect_ratio != "all" else "9:16",
                hook_type="creation",
                scene_number=scene.get("scene_number", 1),
                image_url=image_url,
            )

            if result.video_url:
                scene_clips.append(result.video_url)
            else:
                logger.warning(
                    f"Scene {scene.get('scene_number')} failed: {result.error}"
                )

            # Small delay between scenes
            await asyncio.sleep(1)

        if not scene_clips:
            raise ValueError("No scenes generated successfully")

        # ------------------------------------------------------------------
        # Step 3 — Stitch with FFmpeg (or use raw Kling video if no audio)
        # ------------------------------------------------------------------
        logger.info(f"Stitching {len(scene_clips)} clips for creation {creation_id}")

        hook_text = ""
        cta_text = ""
        if scenes:
            hook_text = scenes[0].get("text_overlay") or ""
            cta_text = scenes[-1].get("text_overlay") or ""

        final_video_url = ""

        if scene_clips:
            if audio_url:
                stitcher = FFmpegStitcher()
                stitch_result = await stitcher.stitch(
                    scene_urls=scene_clips,
                    audio_url=audio_url,
                    hook_text=hook_text,
                    cta_text=cta_text,
                    aspect_ratio=aspect_ratio,
                    subtitles=subtitles,
                    voiceover_script=voiceover_script,
                )
                if stitch_result.success:
                    final_video_url = stitch_result.video_url
                else:
                    logger.error(f"Stitch failed: {stitch_result.error} — using raw Kling video")
                    final_video_url = scene_clips[0]
            else:
                logger.warning("No audio URL — using raw Kling video directly")
                final_video_url = scene_clips[0]

        # ------------------------------------------------------------------
        # Step 4 — Save to DB
        # ------------------------------------------------------------------
        await creation_dao.save_final_video(
            creation_id=creation_id,
            aspect_ratio=aspect_ratio,
            video_url=final_video_url,
            audio_url=audio_url,
        )
        await brief_dao.update_status(brief_id, BriefStatus.COMPLETE)
        await db.commit()

        logger.info(
            f"Creation {creation_id} render complete: {final_video_url[:60]}..."
        )


async def _generate_voiceover(script: str, voice_style: str) -> str:
    """Generates ElevenLabs voiceover for the script."""
    try:
        from mcp_tools.elevenlabs_tools import ElevenLabsTool
        tool = ElevenLabsTool()
        result = await tool.generate(
            script=script,
            hook_type="creation",
            voice_style=voice_style,
        )
        return result.audio_url or ""
    except Exception as e:
        logger.error(f"Voiceover generation failed: {e}")
        return ""


async def _mark_failed(
    creation_id: UUID,
    brief_id: UUID,
    error: str,
) -> None:
    """Marks creation and brief as failed in DB."""
    try:
        async with AsyncSessionFactory() as db:
            creation_dao = VideoCreationDAO(db)
            brief_dao = VideoBriefDAO(db)
            await creation_dao.update_status(
                creation_id,
                CreationStatus.FAILED,
                error_message=error,
            )
            await brief_dao.update_status(
                brief_id,
                BriefStatus.FAILED,
                error_message=error,
            )
            await db.commit()
    except Exception as e:
        logger.error(f"Failed to mark creation as failed: {e}")