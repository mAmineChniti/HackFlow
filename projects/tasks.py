"""Celery tasks for the projects app.

``run_ai_evaluation`` executes the long Groq AI call outside the HTTP request
cycle (broker: Redis). The view writes a "pending" record in the Django cache
before enqueueing; the task replaces it with "done" (and the result payload)
or "failed". The browser polls ``projects:ai_analyze_status`` to read it.

Task state is intentionally stored in the Django cache rather than the Celery
result backend: the cache is already Redis-backed in production, and it keeps
authorization (``user_id``) and expiry in one place.
"""

import logging
import uuid
from time import perf_counter

from celery import shared_task
from django.core.cache import cache

from core.ai_metrics import record_ai_run

logger = logging.getLogger(__name__)

AI_TASK_PREFIX = "ai_eval_task:"
# Polling window: results stay readable for one hour after completion.
AI_TASK_TTL = 60 * 60
# How long the sync evaluation cache lives (mirrors the synchronous view).
AI_RESULT_CACHE_TTL = 600

STATUS_PENDING = "pending"
STATUS_DONE = "done"
STATUS_FAILED = "failed"


def new_task_id() -> str:
    """Random, URL-safe task id (generated here so the view owns it)."""
    return uuid.uuid4().hex


def task_cache_key(task_id: str) -> str:
    return f"{AI_TASK_PREFIX}{task_id}"


def get_task_state(task_id: str) -> dict | None:
    return cache.get(task_cache_key(task_id))


def set_task_state(task_id: str, state: dict) -> None:
    cache.set(task_cache_key(task_id), state, timeout=AI_TASK_TTL)


def discard_task_state(task_id: str) -> None:
    cache.delete(task_cache_key(task_id))


@shared_task(bind=True)
def run_ai_evaluation(
    self,
    task_id: str,
    user_id: int,
    project_id: int,
    title: str,
    tagline: str,
    description: str,
    category: str,
    result_cache_key: str = "",
):
    """Analyse a project with the AI service and publish the task state.

    Never raises: any failure is recorded as STATUS_FAILED with a generic
    message — raw exception text (endpoint URLs, credentials) must not reach
    the client, and the poller must always observe a terminal state.
    """
    from . import ai_service

    started = perf_counter()
    try:
        data = ai_service.analyse_project(
            title=title,
            tagline=tagline,
            description=description,
            category=category,
            mode="async",
        )
        # Never persist or return the raw exception text (see view comment).
        data.pop("error", None)

        if data.get("failed"):
            set_task_state(
                task_id,
                {
                    "status": STATUS_FAILED,
                    "user_id": user_id,
                    "project_id": project_id,
                },
            )
            return

        if result_cache_key:
            # Seed the synchronous cache so a later direct request is instant.
            cache.set(result_cache_key, data, timeout=AI_RESULT_CACHE_TTL)

        set_task_state(
            task_id,
            {
                "status": STATUS_DONE,
                "user_id": user_id,
                "project_id": project_id,
                "payload": data,
            },
        )
    except Exception:
        logger.exception("AI evaluation task %s failed for project %s", task_id, project_id)
        record_ai_run(
            "project_evaluation",
            "error",
            (perf_counter() - started) * 1000,
            mode="async",
            success=False,
        )
        set_task_state(
            task_id,
            {
                "status": STATUS_FAILED,
                "user_id": user_id,
                "project_id": project_id,
            },
        )
