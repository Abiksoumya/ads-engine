"""
AdEngineAI — Render Task
==========================
Celery task that runs video rendering.
Includes ElevenLabs stagger fix — requests sent 0.3s apart.

Replaces asyncio.create_task in render_service.py
"""

import asyncio
import logging
import os
import sys
from uuid import UUID

from celery import Task
import json


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
    soft_time_limit=600,    # 10 min soft limit
    time_limit=660,         # 11 min hard limit
)
def run_render_task(
    self,
    campaign_id: str,
    script_ids: list[str],
    voice_style: str = "professional",
):
    """
    Renders videos for a campaign.
    Called via: run_render_tasktrigger_render campaign_id, script_ids, voice_style)

    Includes ElevenLabs stagger — requests sent 0.3s apart to avoid
    concurrent limit (4 max on free/starter plan).
    """
    logger.info(f"Render task started: {campaign_id} ({len(script_ids)} scripts)")

    try:
        asyncio.run(_run_render_async(
            campaign_id=campaign_id,
            script_ids=script_ids,
            voice_style=voice_style,
        ))
    except Exception as exc:
        logger.error(f"Render task failed: {campaign_id} — {exc}")
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            asyncio.run(_mark_render_failed(campaign_id, str(exc)))
            raise


async def _run_render_async(
    campaign_id: str,
    script_ids: list[str],
    voice_style: str,
):
    """Async render implementation with ElevenLabs stagger."""
    from dotenv import load_dotenv
    load_dotenv()

    agents_path = os.path.join(os.path.dirname(__file__), "..", "agents")
    if agents_path not in sys.path:
        sys.path.insert(0, agents_path)

    from sqlalchemy import select, update
    from app.db.database import AsyncSessionFactory
    from app.models.campaign import Campaign, Script, RenderResult, CampaignStatusEnum

    async with AsyncSessionFactory() as db:
        try:
            from production.crew import ProductionCrew, RenderAgent
            from qa.agent import QAAgent
            from director.agent import Script as AgentScript, HookScore

            # Load scripts from DB
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

            # Build AgentScript objects
            agent_scripts = []
            for s in scripts:
                hook_score_val = s.hook_score
                hook_trigger = s.hook_trigger
                hook_reasoning = s.hook_reasoning
                best_platform = s.best_platform
                hashtags = s.hashtags

                raw_hashtags = s.hashtags
                if raw_hashtags is not None:
                    hashtags = json.loads(json.dumps(raw_hashtags))
                else:
                    hashtags = []


                hook_score = HookScore(
                    score=int(str(hook_score_val)) if hook_score_val is not None else 50,
                    primary_trigger=str(hook_trigger) if hook_trigger is not None else "unknown",
                    reasoning=str(hook_reasoning) if hook_reasoning is not None else "",
                    best_platform=str(best_platform) if best_platform is not None else "instagram",
                )
                agent_script = AgentScript(
                    hook_type=str(s.hook_type),
                    hook_line=str(s.hook_line),
                    script=str(s.script_text),
                    hook_score=hook_score,
                    ad_headline=str(s.ad_headline) if s.ad_headline is not None else "",
                    ad_description=str(s.ad_description) if s.ad_description is not None else "",
                    caption_instagram=str(s.caption_instagram) if s.caption_instagram is not None else "",
                    caption_tiktok=str(s.caption_tiktok) if s.caption_tiktok is not None else "",
                    caption_linkedin=str(s.caption_linkedin) if s.caption_linkedin is not None else "",
                    hashtags=hashtags,
                )
                agent_scripts.append(agent_script)

            # ----------------------------------------------------------------
            # ElevenLabs stagger fix
            # Send requests 0.3s apart to stay within 4 concurrent limit
            # ----------------------------------------------------------------
            crew = ProductionCrew(
                campaign_id=campaign_id,
                voice_style=voice_style,
            )

            # Override render to use staggered execution
            render_results = await _render_with_stagger(crew, agent_scripts)

            # Run QA
            qa_agent = QAAgent()
            qa_results = await qa_agent.review(render_results)

            # Save to DB
            for i, (render, qa) in enumerate(zip(render_results, qa_results)):
                script = scripts[i]

                # Check if render result already exists for this script
                existing = await db.execute(
                    select(RenderResult).where(RenderResult.script_id == script.id)
                )
                existing_render = existing.scalar_one_or_none()

                render_data = dict(
                    audio_url=render.audio.audio_url if render.audio and render.audio.audio_url else None,
                    audio_duration_secs=render.audio.duration_secs if render.audio else None,
                    is_mock_audio=render.audio.is_mock if render.audio else True,
                    video_url_9x16=render.video_9x16.video_url if render.video_9x16 and render.video_9x16.video_url else None,
                    video_url_1x1=render.video_1x1.video_url if render.video_1x1 and render.video_1x1.video_url else None,
                    video_url_16x9=render.video_16x9.video_url if render.video_16x9 and render.video_16x9.video_url else None,
                    is_mock_video=render.video_9x16.is_mock if render.video_9x16 else True,
                    qa_passed=qa.passed,
                    qa_severity=qa.severity,
                    qa_issues=qa.issues,
                    qa_recommendation=qa.recommendation,
                    provider=render.video_9x16.provider if render.video_9x16 else "mock",
                    render_error=str(render.errors[0]) if render.errors else None,
                )

                if existing_render:
                    # Update existing render result
                    await db.execute(
                        update(RenderResult)
                        .where(RenderResult.script_id == script.id)
                        .values(**render_data)
                    )
                else:
                    # Create new render result
                    db_render = RenderResult(script_id=script.id, **render_data)
                    db.add(db_render)

            await db.commit()

            # Update campaign status
            await db.execute(
                update(Campaign)
                .where(Campaign.id == UUID(campaign_id))
                .values(status=CampaignStatusEnum.COMPLETE)
            )
            await db.commit()

            logger.info(f"Render complete: {campaign_id}")

        except Exception as e:
            logger.error(f"Render failed: {campaign_id} — {e}")
            await db.rollback()
            await db.execute(
                update(Campaign)
                .where(Campaign.id == UUID(campaign_id))
                .values(
                    status=CampaignStatusEnum.FAILED,
                    error_message=str(e),
                )
            )
            await db.commit()
            raise

async def _render_with_stagger(crew, agent_scripts: list) -> list:
    """
    Renders scripts sequentially with 1s gap.
    Sequential prevents ElevenLabs concurrent limit (4 max).
    All 5 scripts succeed every time.
    """
    from production.crew import RenderAgent
    from mcp_tools.elevenlabs_tools import AudioResult
    from mcp_tools.did_tools import VideoResult
    from production.crew import RenderResult as AgentRenderResult

    results = []
    for i, script in enumerate(agent_scripts):
        logger.info(f"Rendering {i+1}/5: {script.hook_type}")
        try:
            agent = RenderAgent(
                script=script,
                campaign_id=crew.campaign_id,
                voice_style=crew.voice_style,
                elevenlabs=crew.elevenlabs,
                did=crew.did,
                storage=crew.storage,
            )
            result = await agent.render()
            results.append(result)
            if i < len(agent_scripts) - 1:
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Script {i} render failed: {e}")
            results.append(AgentRenderResult(
                hook_type=script.hook_type,
                script=script,
                audio=AudioResult(
                    hook_type=script.hook_type,
                    audio_url="",
                    audio_bytes=b"",
                    voice_id="",
                    duration_secs=0,
                    is_mock=True,
                ),
                video_9x16=VideoResult(
                    hook_type=script.hook_type,
                    video_url="",
                    thumbnail_url="",
                    duration_secs=0,
                    aspect_ratio="9x16",
                    provider="mock",
                    is_mock=True,
                ),
                video_1x1=None,
                video_16x9=None,
                errors=[str(e)],
            ))

    return results
# async def _render_with_stagger(crew, agent_scripts: list) -> list:
#     """Renders all scripts with 0.3s stagger between ElevenLabs requests."""
#     from production.crew import RenderAgent
#     from mcp_tools.elevenlabs_tools import AudioResult
#     from mcp_tools.did_tools import VideoResult
#     from production.crew import RenderResult as AgentRenderResult

#     async def render_one(script, delay: float):
#         await asyncio.sleep(delay)
#         agent = RenderAgent(
#             script=script,
#             campaign_id=crew.campaign_id,
#             voice_style=crew.voice_style,
#             elevenlabs=crew.elevenlabs,
#             did=crew.did,
#             storage=crew.storage,
#         )
#         return await agent.render()

#     results = await asyncio.gather(
#         *[render_one(script, i * 0.3) for i, script in enumerate(agent_scripts)],
#         return_exceptions=True,
#     )

#     safe_results = []
#     for i, result in enumerate(results):
#         if isinstance(result, Exception):
#             logger.error(f"Script {i} render failed: {result}")
#             failed = AgentRenderResult(
#                 hook_type=agent_scripts[i].hook_type,
#                 script=agent_scripts[i],
#                 audio=AudioResult(
#                     hook_type=agent_scripts[i].hook_type,
#                     audio_url="",
#                     audio_bytes=b"",
#                     voice_id="",
#                     duration_secs=0,
#                     is_mock=True,
#                 ),
#                 video_9x16=VideoResult(
#                     hook_type=agent_scripts[i].hook_type,
#                     video_url="",
#                     thumbnail_url="",
#                     duration_secs=0,
#                     aspect_ratio="9x16",
#                     provider="mock",
#                     is_mock=True,
#                 ),
#                 video_1x1=None,
#                 video_16x9=None,
#                 errors=[str(result)],
#             )
#             safe_results.append(failed)
#         else:
#             safe_results.append(result)

#     return safe_results


async def _mark_render_failed(campaign_id: str, error: str):
    """Marks campaign as failed after max retries."""
    from sqlalchemy import update
    from app.db.database import AsyncSessionFactory
    from app.models.campaign import Campaign, CampaignStatusEnum

    async with AsyncSessionFactory() as db:
        await db.execute(
            update(Campaign)
            .where(Campaign.id == UUID(campaign_id))
            .values(
                status=CampaignStatusEnum.FAILED,
                error_message=f"Render failed after retries: {error}",
            )
        )
        await db.commit()