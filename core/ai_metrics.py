"""Shared, lightweight metrics for AI calls.

The rubric asks for measured AI performance, not just claims. This module keeps
a small ring buffer of recent AI calls in the configured Django cache:

* operation: project_evaluation, category_detection, evaluation_enqueue
* source: remote, heuristic, cache, queued, error
* mode: sync, async, cache
* duration in milliseconds and success flag

The cache is Redis in production and local memory in development/tests, so the
buffer never slows down an AI request and never touches the database. The
organizer-only AI metrics page reads this buffer and computes p50/p95 latency.
"""

from __future__ import annotations

import logging
import math
from collections import Counter, defaultdict
from typing import Iterable

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

AI_RUNS_CACHE_KEY = "ai_metrics:runs:v1"
AI_RUNS_MAX_EVENTS = 200
AI_RUNS_TTL_SECONDS = 60 * 60 * 24 * 7

OPERATION_LABELS = {
    "project_evaluation": "Project evaluation",
    "category_detection": "Category detection",
    "evaluation_enqueue": "Async enqueue",
}

SOURCE_LABELS = {
    "remote": "Groq",
    "heuristic": "Local fallback",
    "cache": "Cache hit",
    "queued": "Queued",
    "error": "Error",
    "broker_fallback": "Broker fallback",
}

MODE_LABELS = {
    "sync": "Synchronous",
    "async": "Celery / Redis",
    "cache": "Cache",
}


def record_ai_run(
    operation: str,
    source: str,
    duration_ms: float,
    *,
    mode: str = "sync",
    success: bool = True,
) -> None:
    """Append one AI call to the in-cache ring buffer.

    Metrics must never break the feature they are measuring, so every cache
    error is swallowed and only logged.
    """
    try:
        events = cache.get(AI_RUNS_CACHE_KEY)
        if not isinstance(events, list):
            events = []
        events.append(
            {
                "operation": operation,
                "source": source,
                "mode": mode,
                "duration_ms": round(max(float(duration_ms or 0), 0.0), 1),
                "success": bool(success),
                "timestamp": timezone.now().isoformat(timespec="seconds"),
            }
        )
        cache.set(
            AI_RUNS_CACHE_KEY,
            events[-AI_RUNS_MAX_EVENTS:],
            timeout=AI_RUNS_TTL_SECONDS,
        )
    except Exception:  # pragma: no cover - cache backends should not break AI
        logger.exception("Could not record AI metrics for operation %s", operation)


def get_ai_runs() -> list[dict]:
    """Return the recorded runs, newest last. Malformed entries are ignored."""
    try:
        events = cache.get(AI_RUNS_CACHE_KEY)
    except Exception:  # pragma: no cover - defensive against cache outages
        logger.exception("Could not read AI metrics")
        return []
    if not isinstance(events, list):
        return []
    return [event for event in events if isinstance(event, dict)]


def reset_ai_runs() -> None:
    """Clear recorded runs (used by tests and maintenance commands)."""
    cache.delete(AI_RUNS_CACHE_KEY)


def percentile(values: Iterable[float], percent: float) -> float | None:
    """Nearest-rank percentile, returning ``None`` for an empty sequence."""
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    rank = max(0, math.ceil((percent / 100.0) * len(ordered)) - 1)
    return round(ordered[min(rank, len(ordered) - 1)], 1)


def _percent(value: float) -> str:
    return f"{value:.1f}%"


def summarize_ai_runs(events: list[dict] | None = None) -> dict:
    """Aggregate live runs by operation for the metrics dashboard."""
    events = get_ai_runs() if events is None else list(events)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        operation = str(event.get("operation") or "unknown")
        grouped[operation].append(event)

    summaries = []
    for operation in sorted(grouped):
        items = grouped[operation]
        durations = [
            float(item["duration_ms"])
            for item in items
            if isinstance(item.get("duration_ms"), (int, float))
        ]
        successes = sum(1 for item in items if item.get("success"))
        sources = Counter(str(item.get("source") or "unknown") for item in items)
        modes = Counter(str(item.get("mode") or "unknown") for item in items)
        summaries.append(
            {
                "key": operation,
                "label": OPERATION_LABELS.get(operation, operation.replace("_", " ").title()),
                "runs": len(items),
                "success_rate": _percent(successes / len(items) * 100) if items else "—",
                "p50_ms": percentile(durations, 50),
                "p95_ms": percentile(durations, 95),
                "sources": [
                    {
                        "key": key,
                        "label": SOURCE_LABELS.get(key, key.replace("_", " ").title()),
                        "count": count,
                    }
                    for key, count in sources.most_common()
                ],
                "modes": [
                    {
                        "key": key,
                        "label": MODE_LABELS.get(key, key.replace("_", " ").title()),
                        "count": count,
                    }
                    for key, count in modes.most_common()
                ],
            }
        )

    recent = [
        {
            **event,
            "operation_label": OPERATION_LABELS.get(
                str(event.get("operation") or ""),
                str(event.get("operation") or "Unknown").replace("_", " ").title(),
            ),
            "source_label": SOURCE_LABELS.get(
                str(event.get("source") or ""),
                str(event.get("source") or "Unknown").replace("_", " ").title(),
            ),
            "mode_label": MODE_LABELS.get(
                str(event.get("mode") or ""),
                str(event.get("mode") or "Unknown").replace("_", " ").title(),
            ),
        }
        for event in reversed(events[-15:])
    ]

    return {
        "total": len(events),
        "summaries": summaries,
        "recent": recent,
        "cache_hits": sum(1 for event in events if event.get("source") == "cache"),
        "remote_runs": sum(1 for event in events if event.get("source") == "remote"),
        "fallback_runs": sum(1 for event in events if event.get("source") == "heuristic"),
    }
