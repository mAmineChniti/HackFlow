"""Celery application — background processing for long-running AI calls.

Why: the Groq HTTP call inside ``projects.ai_service`` can take up to 15s.
Running it inside the request would block a worker slot and hurt response
times (grille d'évaluation → « Performance & asynchronisme »). Instead the
view enqueues ``projects.tasks.run_ai_evaluation`` and the browser polls the
status endpoint until the result is cached.

Broker: Redis (``REDIS_URL``). When Redis is not configured the project falls
back to synchronous AI calls (``AI_ASYNC_ENABLED=False``), so development and
the test suite keep working without a broker.

Usage:
    celery -A HackFlow worker --loglevel=info
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "HackFlow.settings")

app = Celery("HackFlow")
# Reads the CELERY_* namespace from Django settings (see HackFlow/settings.py).
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    """Smoke-test task: celery -A HackFlow call HackFlow.celery.debug_task."""
    print(f"task {self.request.id} ran")
