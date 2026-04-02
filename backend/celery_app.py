"""
AdEngineAI — Celery Application
==================================
Celery configuration with Redis as broker and backend.

Queues:
    pipeline  — campaign research + scripting (high priority)
    render    — video rendering (normal priority)
    publish   — social media publishing (low priority)

Start workers:
    # All queues
    celery -A celery_app worker --loglevel=info -Q pipeline,render,publish

    # Separate workers per queue (recommended for production)
    celery -A celery_app worker --loglevel=info -Q pipeline -c 4 -n pipeline@%h
    celery -A celery_app worker --loglevel=info -Q render -c 2 -n render@%h
    celery -A celery_app worker --loglevel=info -Q publish -c 4 -n publish@%h

Monitor:
    celery -A celery_app flower --port=5555
"""

import os
import sys
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

# Add app to path
sys.path.insert(0, os.path.dirname(__file__))

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

celery_app = Celery(
    "adengineai",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "tasks.campaign_tasks",
        "tasks.render_tasks",
        "tasks.video_creation_tasks", 
                ],
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Queue routing
    task_routes={
        "tasks.campaign_tasks.run_pipeline_task": {"queue": "pipeline"},
        "tasks.render_tasks.run_render_task": {"queue": "render"},
    },

    # Retry settings
    task_acks_late=True,            # only ack after task completes
    task_reject_on_worker_lost=True,
    task_max_retries=3,
    task_default_retry_delay=60,    # 60 seconds between retries

    # Concurrency — ElevenLabs allows 4 concurrent
    # Each worker handles one campaign at a time
    worker_prefetch_multiplier=1,   # don't prefetch — fair distribution

    # Result expiry
    result_expires=86400,           # 24 hours

    # Rate limiting per task
    task_annotations={
        "tasks.render_tasks.run_render_task": {
            "rate_limit": "10/m",   # max 10 renders per minute
        },
    },
)