"""
AdEngineAI — Campaign Pipeline Task
======================================
Celery task that runs the full AI pipeline.
Replaces asyncio.create_task in campaign_service.py

Each task runs in a separate worker process — completely isolated.
No shared state, no session conflicts.
"""

import asyncio
import logging
import os
import sys
from uuid import UUID

from celery import Task

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from celery_app import celery_app

logger = logging.getLogger(__name__)


class PipelineTask(Task):
    """Base task class with error handling."""
    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(f"Pipeline task {task_id} failed: {exc}")

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        logger.warning(f"Pipeline task {task_id} retrying: {exc}")

    def on_success(self, retval, task_id, args, kwargs):
        logger.info(f"Pipeline task {task_id} completed successfully")


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="tasks.campaign_tasks.run_pipeline_task",
    queue="pipeline",
    max_retries=2,
    default_retry_delay=30,
)
def run_pipeline_task(
    self,
    campaign_id: str,
    product_url: str,
    brand_tone: str = "",
    brand_audience: str = "",
):
    """
    Runs the full AI pipeline for a campaign.
    Called via: run_pipeline_task.delay(campaign_id, product_url, ...)

    Runs in a Celery worker process — has its own event loop and DB session.
    """
    logger.info(f"Pipeline task started: {campaign_id}")

    try:
        asyncio.run(_run_pipeline_async(
            campaign_id=campaign_id,
            product_url=product_url,
            brand_tone=brand_tone,
            brand_audience=brand_audience,
        ))
    except Exception as exc:
        logger.error(f"Pipeline task failed: {campaign_id} — {exc}")
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            # Mark campaign as failed in DB
            asyncio.run(_mark_failed(campaign_id, str(exc)))
            raise


async def _run_pipeline_async(
    campaign_id: str,
    product_url: str,
    brand_tone: str,
    brand_audience: str,
):
    """Async implementation of the pipeline."""
    from dotenv import load_dotenv
    load_dotenv()

    # Add agents to path
    agents_path = os.path.join(os.path.dirname(__file__), "..", "agents")
    if agents_path not in sys.path:
        sys.path.insert(0, agents_path)

    from app.db.database import AsyncSessionFactory
    from app.dao.campaign_dao import CampaignDAO
    from app.models.campaign import CampaignStatusEnum

    async with AsyncSessionFactory() as db:
        campaign_dao = CampaignDAO(db)

        try:
            from orchestrator.agent import Orchestrator

            # Update status
            await campaign_dao.update_status(
                UUID(campaign_id), CampaignStatusEnum.RESEARCHING
            )
            await db.commit()

            # Run orchestrator
            orchestrator = Orchestrator()
            result = await orchestrator.run(
                product_url=product_url,
                job_id=campaign_id,
                brand_tone=brand_tone,
                brand_audience=brand_audience,
            )

            if result.status == "failed":
                await campaign_dao.update_status(
                    UUID(campaign_id),
                    CampaignStatusEnum.FAILED,
                    error_message=str(result.errors),
                )
                await db.commit()
                return

            # Save research
            if result.research:
                await campaign_dao.update_status(
                    UUID(campaign_id), CampaignStatusEnum.SCRIPTING
                )
                await campaign_dao.save_research(
                    campaign_id=UUID(campaign_id),
                    research_result={
                        "product_name": result.research.product_name,
                        "product_category": result.research.product_category,
                        "pain_points": result.research.pain_points,
                        "selling_points": result.research.selling_points,
                        "social_proof": result.research.social_proof,
                        "target_audience": result.research.target_audience,
                        "key_differentiator": result.research.key_differentiator,
                    },
                    confidence_score=result.research.confidence_score,
                )
                await db.commit()

            # Save scripts
            if result.scripts:
                scripts_data = [
                    {
                        "hook_type": s.hook_type,
                        "hook_line": s.hook_line,
                        "script": s.script,
                        "hook_score": {
                            "score": s.hook_score.score,
                            "primary_trigger": s.hook_score.primary_trigger,
                            "reasoning": s.hook_score.reasoning,
                            "best_platform": s.hook_score.best_platform,
                        },
                        "ad_headline": s.ad_headline,
                        "ad_description": s.ad_description,
                        "caption_instagram": s.caption_instagram,
                        "caption_tiktok": s.caption_tiktok,
                        "caption_linkedin": s.caption_linkedin,
                        "hashtags": s.hashtags,
                    }
                    for s in result.scripts
                ]
                await campaign_dao.save_scripts(UUID(campaign_id), scripts_data)
                await db.commit()

            # Mark complete
            await campaign_dao.update_status(
                UUID(campaign_id), CampaignStatusEnum.COMPLETE
            )
            await db.commit()

            logger.info(f"Pipeline complete: {campaign_id}")

        except Exception as e:
            logger.error(f"Pipeline failed: {campaign_id} — {e}")
            await db.rollback()
            await campaign_dao.update_status(
                UUID(campaign_id),
                CampaignStatusEnum.FAILED,
                error_message=str(e),
            )
            await db.commit()
            raise


async def _mark_failed(campaign_id: str, error: str):
    """Marks campaign as failed after max retries exceeded."""
    from app.db.database import AsyncSessionFactory
    from app.dao.campaign_dao import CampaignDAO
    from app.models.campaign import CampaignStatusEnum

    async with AsyncSessionFactory() as db:
        dao = CampaignDAO(db)
        await dao.update_status(
            UUID(campaign_id),
            CampaignStatusEnum.FAILED,
            error_message=f"Max retries exceeded: {error}",
        )
        await db.commit()