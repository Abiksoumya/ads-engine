"""
AdEngineAI — Render Service
==============================
Triggers video rendering for a campaign.
Runs as a background task — API returns immediately.

Flow:
    1. Load scripts from DB
    2. Build Script objects for ProductionCrew
    3. Run ProductionCrew (ElevenLabs + D-ID) in background
    4. Save RenderResult to DB
    5. Update campaign status to complete
"""

import asyncio
import logging
import sys
import os
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign, Script, RenderResult, CampaignStatusEnum
from app.core.exceptions import (
    CampaignNotFoundException,
    ForbiddenException,
    ValidationException,
)

logger = logging.getLogger(__name__)


class RenderService:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def trigger_render(
        self,
        campaign_id: UUID,
        user_id: UUID,
        script_ids: list[UUID] | None = None,
        voice_style: str = "professional",
    ) -> dict:
        # Verify ownership
        campaign = await self._get_campaign(campaign_id, user_id)

        # Must have scripts before rendering
        if str(campaign.status.value) == "pending":
            raise ValidationException(
                "Campaign scripts are not ready yet. Wait for status 'complete' first."
            )

        # Load scripts
        query = select(Script).where(Script.campaign_id == campaign_id)
        if script_ids:
            query = query.where(Script.id.in_(script_ids))

        result = await self.db.execute(query)
        scripts = list(result.scalars().all())

        if not scripts:
            raise ValidationException("No scripts found for this campaign")

        # Update status to rendering
        await self.db.execute(
            update(Campaign)
            .where(Campaign.id == campaign_id)
            .values(status=CampaignStatusEnum.RENDERING)
        )

        # Dispatch to Celery queue
        from tasks.render_tasks import run_render_task
        run_render_task.delay(  # type: ignore[attr-defined]
            campaign_id=str(campaign_id),
            script_ids=[str(s.id) for s in scripts],
            voice_style=voice_style,
        )

        logger.info(f"Render queued: {campaign_id} ({len(scripts)} scripts)")

        return {
            "campaign_id": str(campaign_id),
            "scripts_queued": len(scripts),
            "status": "rendering",
            "message": f"Rendering {len(scripts)} videos. Check status for progress.",
        }

    # async def trigger_render(
    #     self,
    #     campaign_id: UUID,
    #     user_id: UUID,
    #     script_ids: list[UUID] | None = None,
    #     voice_style: str = "professional",
    # ) -> dict:
    #     """
    #     Triggers video rendering as a background task.
    #     Returns immediately.
    #     """
    #     # Verify ownership
    #     campaign = await self._get_campaign(campaign_id, user_id)

    #     # Must have scripts before rendering
    #     if str(campaign.status.value) == "pending":
    #         raise ValidationException(
    #             "Campaign scripts are not ready yet. Wait for status 'complete' first."
    #         )

    #     # Load scripts
    #     query = select(Script).where(Script.campaign_id == campaign_id)
    #     if script_ids:
    #         query = query.where(Script.id.in_(script_ids))

    #     result = await self.db.execute(query)
    #     scripts = list(result.scalars().all())

    #     if not scripts:
    #         raise ValidationException("No scripts found for this campaign")

    #     # Update status to rendering
    #     await self.db.execute(
    #         update(Campaign)
    #         .where(Campaign.id == campaign_id)
    #         .values(status=CampaignStatusEnum.RENDERING)
    #     )

    #     # Trigger background render
    #     asyncio.create_task(
    #         self._run_render(
    #             campaign_id=campaign_id,
    #             scripts=scripts,
    #             voice_style=voice_style,
    #         )
    #     )

    #     logger.info(f"Render triggered for campaign: {campaign_id} ({len(scripts)} scripts)")

    #     return {
    #         "campaign_id": str(campaign_id),
    #         "scripts_queued": len(scripts),
    #         "status": "rendering",
    #         "message": f"Rendering {len(scripts)} videos. Check status for progress. Takes 3-8 minutes.",
    #     }

    async def get_videos(self, campaign_id: UUID, user_id: UUID) -> dict:
        """Returns all video URLs for a campaign."""
        await self._get_campaign(campaign_id, user_id)

        # Get all scripts with render results
        result = await self.db.execute(
            select(Script).where(Script.campaign_id == campaign_id)
        )
        scripts = list(result.scalars().all())

        videos = []
        for script in scripts:
            render_result = await self.db.execute(
                select(RenderResult).where(RenderResult.script_id == script.id)
            )
            render = render_result.scalar_one_or_none()

            hook_score = script.hook_score
            audio_url = render.audio_url if render else None
            video_9x16 = render.video_url_9x16 if render else None
            video_1x1 = render.video_url_1x1 if render else None
            video_16x9 = render.video_url_16x9 if render else None
            thumbnail = render.thumbnail_url if render else None
            qa_passed = render.qa_passed if render else None
            qa_severity = render.qa_severity if render else None
            is_mock = render.is_mock_video if render else True

            videos.append({
                "script_id": str(script.id),
                "hook_type": str(script.hook_type),
                "hook_line": str(script.hook_line),
                "hook_score": int(str(hook_score)) if hook_score is not None else None,
                "audio_url": str(audio_url) if audio_url is not None else None,
                "video_9x16": str(video_9x16) if video_9x16 is not None else None,
                "video_1x1": str(video_1x1) if video_1x1 is not None else None,
                "video_16x9": str(video_16x9) if video_16x9 is not None else None,
                "thumbnail_url": str(thumbnail) if thumbnail is not None else None,
                "qa_passed": bool(qa_passed) if qa_passed is not None else None,
                "qa_severity": str(qa_severity) if qa_severity is not None else None,
                "is_mock": bool(is_mock) if is_mock is not None else True,
                "rendered": render is not None,
            })

        return {
            "campaign_id": str(campaign_id),
            "videos": videos,
            "total": len(videos),
            "rendered": sum(1 for v in videos if v["rendered"]),
        }

    # ------------------------------------------------------------------
    # Background render task
    # ------------------------------------------------------------------

    async def _run_render(
        self,
        campaign_id: UUID,
        scripts: list,
        voice_style: str,
    ) -> None:
        """
        Runs ProductionCrew + QA in background with its own DB session.
        """
        agents_path = os.path.join(os.path.dirname(__file__), "..", "..", "agents")
        if agents_path not in sys.path:
            sys.path.insert(0, agents_path)

        from app.db.database import AsyncSessionFactory

        async with AsyncSessionFactory() as db:
            try:
                from production.crew import ProductionCrew
                from qa.agent import QAAgent
                from director.agent import Script as AgentScript, HookScore

                # Build Script objects for ProductionCrew
                agent_scripts = []
                for s in scripts:
                    hook_score = HookScore(
                        score=int(s.hook_score) if s.hook_score is not None else 50,
                        primary_trigger=str(s.hook_trigger) if s.hook_trigger is not None else "unknown",
                        reasoning=str(s.hook_reasoning) if s.hook_reasoning is not None else "",
                        best_platform=str(s.best_platform) if s.best_platform is not None else "instagram",
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
                        hashtags=s.hashtags or [],
                    )
                    agent_scripts.append(agent_script)

                # Run ProductionCrew
                crew = ProductionCrew(
                    campaign_id=str(campaign_id),
                    voice_style=voice_style,
                )
                render_results = await crew.render(agent_scripts)

                # Run QA
                qa_agent = QAAgent()
                qa_results = await qa_agent.review(render_results)

                # Save render results to DB
                for i, (render, qa) in enumerate(zip(render_results, qa_results)):
                    script = scripts[i]

                    db_render = RenderResult(
                        script_id=script.id,
                        audio_url=render.audio.audio_url if render.audio else None,
                        audio_duration_secs=render.audio.duration_secs if render.audio else None,
                        is_mock_audio=render.audio.is_mock if render.audio else True,
                        video_url_9x16=render.video_9x16.video_url if render.video_9x16 else None,
                        video_url_1x1=render.video_1x1.video_url if render.video_1x1 else None,
                        video_url_16x9=render.video_16x9.video_url if render.video_16x9 else None,
                        is_mock_video=render.video_9x16.is_mock if render.video_9x16 else True,
                        qa_passed=qa.passed,
                        qa_severity=qa.severity,
                        qa_issues=qa.issues,
                        qa_recommendation=qa.recommendation,
                        provider=render.video_9x16.provider if render.video_9x16 else "mock",
                        render_error=str(render.errors[0]) if render.errors else None,
                    )
                    db.add(db_render)

                await db.commit()

                # Update campaign status
                await db.execute(
                    update(Campaign)
                    .where(Campaign.id == campaign_id)
                    .values(status=CampaignStatusEnum.COMPLETE)
                )
                await db.commit()

                logger.info(f"Render complete for campaign: {campaign_id}")

            except Exception as e:
                logger.error(f"Render failed for campaign {campaign_id}: {e}")
                try:
                    await db.rollback()
                    await db.execute(
                        update(Campaign)
                        .where(Campaign.id == campaign_id)
                        .values(
                            status=CampaignStatusEnum.FAILED,
                            error_message=str(e),
                        )
                    )
                    await db.commit()
                except Exception as db_err:
                    logger.error(f"Failed to update error status: {db_err}")

    async def _get_campaign(self, campaign_id: UUID, user_id: UUID) -> Campaign:
        result = await self.db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()
        if not campaign:
            raise CampaignNotFoundException()
        if str(campaign.user_id) != str(user_id):
            raise ForbiddenException("You don't have access to this campaign")
        return campaign