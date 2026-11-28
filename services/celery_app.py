"""Celery application shared by the API producer and independent workers."""

from __future__ import annotations

import os
from pathlib import Path

from celery import Celery
from dotenv import load_dotenv
from kombu import Queue


REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0").strip()

celery_app = Celery(
    "trackflow",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["services.reporting.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=86400,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=900,
    task_soft_time_limit=840,
    broker_transport_options={"visibility_timeout": 3600},
    worker_prefetch_multiplier=1,
    task_queues=(Queue("celery"), Queue("dead_letter")),
)
