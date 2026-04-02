"""
AdEngineAI — Render Task (Updated)
=====================================
Celery task for Campaign video rendering (Flow 1).

Pipeline:
  1. Load campaign scripts + video briefs from DB
  2. Generate voiceover per script (ElevenLabs)
  3. Generate video scenes per script (fal.ai Kling)
  4. Stitch scenes + audio (FFmpeg)
  5. Run QA review
  6. Save final video URLs to DB
  7. Update campaign status to complete

Replaces D-ID with fal.ai Kling + FFmpeg.
Queue: render
"""

import asyncio
import logging
import os
import sys
from uuid import UUID

from celery import Task

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from celery_app import celery_app

logger = logging.getLogger(__name__)


class RenderTask(Task):
    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(f"Render task {task_id} failed: {exc}")

    def on_success(self, retval, task_id, args, kwargs):
        logger.info(f"Render task {task_id} completed successfully")


@celery_app.task(
    bind=True,
    base=RenderTask,
    name="tasks.render_tasks.run_render_task",
    queue="render",
    max_retries=1,
    default_retry_delay=60,
    soft_time_limit=900,
    time_limit=960,
)
def run_render_task(
    self,
    campaign_id: str,
    script_ids: list[str],
    voice_style: str = "professional",
    aspect_ratio: str = "9:16",
):
    logger.info(f"Render task started: {campaign_id} ({len(script_ids)} scripts, {aspect_ratio})")
    try:
        asyncio.run(_run_render_async(
            campaign_id=campaign_id,
            script_ids=script_ids,
            voice_style=voice_style,
            aspect_ratio=aspect_ratio,
        ))
    except Exception as exc:
        logger.error(f"Render task failed: {campaign_id} — {exc}")
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            asyncio.run(_mark_render_failed(campaign_id, str(exc)))
            raise


async def _run_render_async(campaign_id, script_ids, voice_style, aspect_ratio):
    from dotenv import load_dotenv
    load_dotenv()

    from sqlalchemy import select, update
    from app.db.database import AsyncSessionFactory
    from app.models.campaign import Campaign, Script, RenderResult, CampaignStatusEnum
    from app.dao.video_brief_dao import VideoBriefDAO
    from app.models.video_brief import BriefStatus
    from mcp_tools.fal_kling_tools import FalKlingTool
    from mcp_tools.ffmpeg_tools import FFmpegStitcher
    from mcp_tools.elevenlabs_tools import ElevenLabsTool

    async with AsyncSessionFactory() as db:
        try:
            brief_dao = VideoBriefDAO(db)

            result = await db.execute(
                select(Script).where(
                    Script.campaign_id == UUID(campaign_id),
                    Script.id.in_([UUID(sid) for sid in script_ids]),
                )
            )
            scripts = list(result.scalars().all())

            if not scripts:
                logger.error(f"No scripts found for campaign {campaign_id}")
                return

            kling = FalKlingTool()
            stitcher = FFmpegStitcher()
            elevenlabs = ElevenLabsTool()

            for script in scripts:
                try:
                    await _render_one_script(
                        db=db,
                        script=script,
                        brief_dao=brief_dao,
                        kling=kling,
                        stitcher=stitcher,
                        elevenlabs=elevenlabs,
                        voice_style=voice_style,
                        aspect_ratio=aspect_ratio,
                    )
                except Exception as e:
                    logger.error(f"Script {script.id} render failed: {e} — continuing")
                    await _save_failed_render(db, script.id, str(e))

                await asyncio.sleep(2)

            await db.execute(
                update(Campaign)
                .where(Campaign.id == UUID(campaign_id))
                .values(status=CampaignStatusEnum.COMPLETE)
            )
            await db.commit()
            logger.info(f"Campaign render complete: {campaign_id}")

        except Exception as e:
            logger.error(f"Campaign render failed: {campaign_id} — {e}")
            await db.rollback()
            await db.execute(
                update(Campaign)
                .where(Campaign.id == UUID(campaign_id))
                .values(status=CampaignStatusEnum.FAILED, error_message=str(e))
            )
            await db.commit()
            raise


async def _render_one_script(db, script, brief_dao, kling, stitcher, elevenlabs, voice_style, aspect_ratio):
    from sqlalchemy import select, update
    from app.models.campaign import RenderResult
    from app.models.video_brief import BriefStatus

    script_id = UUID(str(script.id))
    logger.info(f"Rendering script {script_id} ({script.hook_type})")

    brief = await brief_dao.get_by_script_id(script_id)

    if not brief:
        scenes = _default_scenes_from_script(script)
        voiceover_script = str(script.script_text)
        hook_text = str(script.hook_line)
        cta_text = "Shop now"
    else:
        scenes = brief.scenes or []
        voiceover_script = str(brief.voiceover_script or script.script_text)
        hook_text = scenes[0].get("text_overlay", "") if scenes else str(script.hook_line)
        cta_text = scenes[-1].get("text_overlay", "Shop now") if scenes else "Shop now"

    # Generate voiceover
    audio_result = await elevenlabs.generate_audio(text=voiceover_script, voice_style=voice_style)
    audio_url = audio_result.audio_url or ""

    # Generate Kling scenes
    scene_clips = []
    for scene in scenes:
        image_url = scene.get("product_image_url") if scene.get("use_product_image") else None
        result = await kling.generate_scene(
            prompt=scene.get("kling_prompt", ""),
            duration=scene.get("duration", 10),
            aspect_ratio=aspect_ratio if aspect_ratio != "all" else "9:16",
            hook_type=str(script.hook_type),
            scene_number=scene.get("scene_number", 1),
            image_url=image_url,
        )
        if result.video_url:
            scene_clips.append(result.video_url)
        else:
            logger.warning(f"Scene {scene.get('scene_number')} failed: {result.error}")
        await asyncio.sleep(1)

    # Stitch
    final_video_url = ""
    if scene_clips and audio_url:
        stitch_result = await stitcher.stitch(
            scene_urls=scene_clips,
            audio_url=audio_url,
            hook_text=hook_text,
            cta_text=cta_text,
            aspect_ratio=aspect_ratio if aspect_ratio != "all" else "9:16",
            subtitles=False,
            voiceover_script=voiceover_script,
        )
        if stitch_result.success:
            final_video_url = stitch_result.video_url
        else:
            logger.error(f"Stitch failed: {stitch_result.error}")

    # QA
    qa_passed = bool(final_video_url and audio_url)
    qa_severity = "none" if qa_passed else "critical"
    qa_issues = [] if qa_passed else ["Video or audio generation failed"]
    qa_recommendation = "Approved" if qa_passed else "Re-render required"

    # Save render result
    video_9x16 = final_video_url if aspect_ratio in ("9:16", "all") else None
    video_1x1 = final_video_url if aspect_ratio in ("1:1", "all") else None
    video_16x9 = final_video_url if aspect_ratio in ("16:9", "all") else None

    render_data = dict(
        audio_url=audio_url or None,
        audio_duration_secs=None,
        is_mock_audio=getattr(audio_result, 'is_mock', False),
        video_url_9x16=video_9x16,
        video_url_1x1=video_1x1,
        video_url_16x9=video_16x9,
        is_mock_video=kling.is_mock,
        qa_passed=qa_passed,
        qa_severity=qa_severity,
        qa_issues=qa_issues,
        qa_recommendation=qa_recommendation,
        provider="kling",
        render_error=None,
    )

    existing = await db.execute(select(RenderResult).where(RenderResult.script_id == script.id))
    existing_render = existing.scalar_one_or_none()

    if existing_render:
        await db.execute(update(RenderResult).where(RenderResult.script_id == script.id).values(**render_data))
    else:
        db.add(RenderResult(script_id=script.id, **render_data))

    if brief:
        await brief_dao.update_status(
            UUID(str(brief.id)),
            BriefStatus.COMPLETE if final_video_url else BriefStatus.FAILED,
        )

    await db.commit()
    logger.info(f"Script {script_id} render saved")


def _default_scenes_from_script(script) -> list[dict]:
    hook_line = str(script.hook_line)
    hook_type = str(script.hook_type)
    return [
        {
            "scene_number": 1, "duration": 10,
            "text_overlay": hook_line, "use_product_image": True, "product_image_url": None,
            "kling_prompt": f"Professional product advertisement, {hook_type} hook, clean studio, cinematic lighting, slow camera, 4K, advertisement style",
        },
        {
            "scene_number": 2, "duration": 10,
            "text_overlay": None, "use_product_image": True, "product_image_url": None,
            "kling_prompt": "Product lifestyle shot, natural environment, golden hour lighting, cinematic slow motion, 4K, advertisement style",
        },
        {
            "scene_number": 3, "duration": 10,
            "text_overlay": "Shop now", "use_product_image": True, "product_image_url": None,
            "kling_prompt": "Clean product hero shot, white background, professional studio lighting, sharp focus, 4K, advertisement style",
        },
    ]


async def _save_failed_render(db, script_id, error: str) -> None:
    from sqlalchemy import select, update
    from app.models.campaign import RenderResult

    existing = await db.execute(select(RenderResult).where(RenderResult.script_id == script_id))
    existing_render = existing.scalar_one_or_none()
    render_data = dict(
        is_mock_video=True, is_mock_audio=True,
        qa_passed=False, qa_severity="critical",
        qa_issues=[f"Render failed: {error}"],
        qa_recommendation="Re-render required",
        provider="kling", render_error=error,
    )
    if existing_render:
        await db.execute(update(RenderResult).where(RenderResult.script_id == script_id).values(**render_data))
    else:
        db.add(RenderResult(script_id=script_id, **render_data))
    await db.commit()


async def _mark_render_failed(campaign_id: str, error: str) -> None:
    from sqlalchemy import update
    from app.db.database import AsyncSessionFactory
    from app.models.campaign import Campaign, CampaignStatusEnum

    async with AsyncSessionFactory() as db:
        await db.execute(
            update(Campaign)
            .where(Campaign.id == UUID(campaign_id))
            .values(status=CampaignStatusEnum.FAILED, error_message=f"Render failed after retries: {error}")
        )
        await db.commit()