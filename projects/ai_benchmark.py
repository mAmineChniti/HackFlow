"""Reproducible AI metrics for the project evaluation features.

The rubric asks for two kinds of evidence:

1. Classification metrics for category detection (precision, recall, F1 and a
   confusion matrix) on a labelled validation set.
2. A justified qualitative assessment for the generative project review, plus
   measured latency and the Celery/Redis asynchronous path.

The benchmark deliberately uses the local semantic fallback. It is deterministic,
makes no network call and can therefore be run by the jury without a Groq key or
a bill. When ``GROQ_API_KEY`` is configured, the production path uses the same
category labels and the same JSON schema, so the evaluation methodology stays
comparable.
"""

from __future__ import annotations

import math
from statistics import fmean
from time import perf_counter

from . import ai_service

CATEGORY_LABELS = tuple(ai_service.CATEGORY_CHOICES)
CATEGORY_DISPLAY = dict(ai_service.CATEGORY_CHOICES)

# Hand-labelled validation examples. They are intentionally spread over all
# seven categories, including one genuinely ambiguous cyber/web description so
# the confusion matrix has a realistic error to explain.
LABELED_CATEGORY_SAMPLES = (
    {
        "title": "Campus Marketplace",
        "description": "A Django and React web platform for students to buy and sell textbooks.",
        "expected": "web",
    },
    {
        "title": "EventHub",
        "description": "A SaaS web portal to manage conferences, tickets and attendee dashboards.",
        "expected": "web",
    },
    {
        "title": "DevBoard",
        "description": (
            "A collaborative website built with HTML, Django and React for open-source teams."
        ),
        "expected": "web",
    },
    {
        "title": "VolunteerHub",
        "description": (
            "A website with a Django backend for matching volunteers to local charities."
        ),
        "expected": "web",
    },
    {
        "title": "Transit Buddy",
        "description": (
            "A Flutter mobile app for Android and iOS that tracks bus arrivals in real time."
        ),
        "expected": "mobile",
    },
    {
        "title": "FitLoop",
        "description": (
            "A mobile application with React Native for daily workout tracking on smartphones."
        ),
        "expected": "mobile",
    },
    {
        "title": "CampusEats",
        "description": (
            "An Android and iOS app that lets students pre-order meals from the cafeteria."
        ),
        "expected": "mobile",
    },
    {
        "title": "StudyMate",
        "description": "A machine learning and NLP model that turns course notes into study plans.",
        "expected": "ai",
    },
    {
        "title": "VisionSort",
        "description": (
            "A deep learning computer vision model that sorts recyclable materials from photos."
        ),
        "expected": "ai",
    },
    {
        "title": "DocuChat",
        "description": (
            "An LLM chat assistant that answers questions about uploaded university documents."
        ),
        "expected": "ai",
    },
    {
        "title": "Smart Greenhouse",
        "description": (
            "Arduino sensors and a Raspberry Pi controller automate irrigation and monitor plants."
        ),
        "expected": "iot",
    },
    {
        "title": "FleetTrack",
        "description": (
            "IoT hardware with Bluetooth sensors that tracks delivery robots and "
            "warehouse equipment."
        ),
        "expected": "iot",
    },
    {
        "title": "HomeGuard",
        "description": "An embedded Arduino device with motion sensors and a Raspberry Pi camera.",
        "expected": "iot",
    },
    {
        "title": "PhishGuard",
        "description": (
            "A cybersecurity platform for phishing detection, encryption and strong authentication."
        ),
        "expected": "cyber",
    },
    {
        "title": "PentestLab",
        "description": (
            "A firewall and vulnerability scanner for teaching ethical hacking and pentesting."
        ),
        "expected": "cyber",
    },
    {
        "title": "SecureVault",
        "description": (
            "An authentication service with end-to-end encryption and vulnerability monitoring."
        ),
        "expected": "cyber",
    },
    {
        "title": "CyberRange",
        "description": "A web platform and mobile app for security awareness training.",
        "expected": "cyber",
    },
    {
        "title": "EcoRoute",
        "description": (
            "A green mobility dashboard that reduces carbon emissions and optimises energy use."
        ),
        "expected": "green",
    },
    {
        "title": "ReCycle",
        "description": (
            "A recycling platform that helps neighbourhoods reduce waste and track sustainability."
        ),
        "expected": "green",
    },
    {
        "title": "ClimateLens",
        "description": (
            "A climate analytics tool that measures carbon impact and promotes durable practices."
        ),
        "expected": "green",
    },
    {
        "title": "EcoShop",
        "description": "A mobile app and web dashboard for a sustainable marketplace.",
        "expected": "green",
    },
    {
        "title": "Podcast Studio",
        "description": (
            "A community podcast production service with booking, training and equipment rental."
        ),
        "expected": "other",
    },
    {
        "title": "Campus Quiz",
        "description": "A student club tool for organising trivia nights and publishing results.",
        "expected": "other",
    },
    {
        "title": "Local Bazaar",
        "description": "A community noticeboard for exchanging services, volunteering and events.",
        "expected": "other",
    },
    {
        "title": "Repair Cafe",
        "description": "A neighbourhood workshop for repairing household items and sharing tools.",
        "expected": "other",
    },
)

GENERATIVE_SAMPLES = (
    {
        "title": "Smart Greenhouse",
        "tagline": "Autonomous irrigation for small urban farms",
        "description": (
            "A greenhouse kit using Arduino sensors and a Raspberry Pi. It monitors "
            "soil moisture, temperature and light, then schedules irrigation through "
            "a Django dashboard. The project targets schools and urban farms that "
            "need affordable automation, with a prototype and a clear deployment plan."
        ),
        "category": "IoT & Embedded Systems",
    },
    {
        "title": "Campus Marketplace",
        "tagline": "A trusted second-hand market for students",
        "description": (
            "A Django and React web platform where students buy and sell textbooks "
            "and dorm supplies. The solution includes verified student profiles, "
            "search filters, a moderation queue and a dashboard for campus admins. "
            "The team validated the problem with 40 students and built a working MVP."
        ),
        "category": "Web Development",
    },
    {
        "title": "StudyMate",
        "tagline": "Personalised revision plans from course notes",
        "description": (
            "A machine learning and NLP assistant that reads lecture notes and builds "
            "a weekly revision plan. It uses a classifier to identify weak topics and "
            "an LLM to generate practice questions. The project includes an API, a "
            "privacy page and an evaluation set of 120 labelled study sessions."
        ),
        "category": "Artificial Intelligence & Data",
    },
)

QUALITATIVE_CRITERIA = (
    {
        "criterion": "Relevance",
        "question": "Does the review address the project's category, problem and solution?",
        "evidence": (
            "The comment names the category and repeats the problem/feasibility "
            "signals extracted from the submission."
        ),
    },
    {
        "criterion": "Groundedness",
        "question": "Are strengths and weaknesses tied to the submitted text?",
        "evidence": (
            "The fallback uses description completeness, stack keywords and "
            "problem/impact keywords; it does not invent external facts."
        ),
    },
    {
        "criterion": "Actionability",
        "question": "Can the team act on the feedback?",
        "evidence": (
            "Every weakness is an instruction to add, clarify or emphasise a "
            "specific part of the submission."
        ),
    },
    {
        "criterion": "Consistency",
        "question": "Does the same input keep the same schema and score?",
        "evidence": (
            "The benchmark runs each sample twice and compares the full result; "
            "the local fallback is deterministic."
        ),
    },
)


def _percentile(values: list[float], percent: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    rank = max(0, math.ceil((percent / 100.0) * len(ordered)) - 1)
    return round(ordered[min(rank, len(ordered) - 1)], 2)


def _percent(value: float) -> float:
    return round(value * 100, 1)


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def evaluate_category_classifier(
    samples=LABELED_CATEGORY_SAMPLES, *, use_remote: bool = False
) -> dict:
    """Run the category classifier and return classification metrics.

    The default local fallback is free and deterministic. ``use_remote=True``
    sends the same examples through the configured Groq model and may incur
    API cost or rate limiting.
    """
    y_true: list[str] = []
    y_pred: list[str] = []
    durations: list[float] = []
    confidences: dict[str, int] = {}
    errors: list[dict] = []

    for sample in samples:
        started = perf_counter()
        if use_remote:
            result = ai_service.detect_category(sample["title"], sample["description"])
        else:
            result = ai_service._fallback_detect_category(sample["title"], sample["description"])
        durations.append((perf_counter() - started) * 1000)

        expected = sample["expected"]
        predicted = result.get("category", "other")
        y_true.append(expected)
        y_pred.append(predicted)
        confidence = result.get("confidence", "unknown")
        confidences[confidence] = confidences.get(confidence, 0) + 1
        if expected != predicted:
            errors.append(
                {
                    "title": sample["title"],
                    "expected": CATEGORY_DISPLAY.get(expected, expected),
                    "predicted": CATEGORY_DISPLAY.get(predicted, predicted),
                    "confidence": confidence,
                }
            )

    per_class = []
    for label in CATEGORY_LABELS:
        true_positive = sum(
            1 for actual, predicted in zip(y_true, y_pred) if actual == label and predicted == label
        )
        false_positive = sum(
            1 for actual, predicted in zip(y_true, y_pred) if actual != label and predicted == label
        )
        false_negative = sum(
            1 for actual, predicted in zip(y_true, y_pred) if actual == label and predicted != label
        )
        precision = _ratio(true_positive, true_positive + false_positive)
        recall = _ratio(true_positive, true_positive + false_negative)
        f1 = _ratio(2 * precision * recall, precision + recall)
        per_class.append(
            {
                "code": label,
                "label": CATEGORY_DISPLAY[label],
                "support": y_true.count(label),
                "predicted": y_pred.count(label),
                "precision": round(precision, 3),
                "recall": round(recall, 3),
                "f1": round(f1, 3),
            }
        )

    matrix_rows = []
    for actual in CATEGORY_LABELS:
        cells = []
        for predicted in CATEGORY_LABELS:
            count = sum(
                1
                for true_label, predicted_label in zip(y_true, y_pred)
                if true_label == actual and predicted_label == predicted
            )
            cells.append(
                {
                    "code": predicted,
                    "label": CATEGORY_DISPLAY[predicted],
                    "count": count,
                    "is_correct": actual == predicted and count > 0,
                }
            )
        matrix_rows.append(
            {
                "code": actual,
                "label": CATEGORY_DISPLAY[actual],
                "cells": cells,
                "total": sum(cell["count"] for cell in cells),
            }
        )

    correct = sum(1 for actual, predicted in zip(y_true, y_pred) if actual == predicted)
    macro_precision = fmean(item["precision"] for item in per_class)
    macro_recall = fmean(item["recall"] for item in per_class)
    macro_f1 = fmean(item["f1"] for item in per_class)
    total_support = len(y_true)

    return {
        "sample_count": len(samples),
        "correct_count": correct,
        "accuracy": round(_ratio(correct, total_support), 3),
        "accuracy_percent": _percent(_ratio(correct, total_support)),
        "macro_precision": round(macro_precision, 3),
        "macro_recall": round(macro_recall, 3),
        "macro_f1": round(macro_f1, 3),
        "per_class": per_class,
        "labels": [{"code": code, "label": CATEGORY_DISPLAY[code]} for code in CATEGORY_LABELS],
        "confusion_matrix": matrix_rows,
        "errors": errors,
        "confidences": [
            {"label": key.title(), "count": value} for key, value in sorted(confidences.items())
        ],
        "latency_p50_ms": _percentile(durations, 50),
        "latency_p95_ms": _percentile(durations, 95),
        "latency_mean_ms": round(fmean(durations), 2) if durations else None,
        "benchmark_source": "remote" if use_remote else "local-fallback",
        "method": (
            "Remote Groq model on a hand-labelled validation set; calls may be "
            "rate-limited or billed."
            if use_remote
            else "Local semantic fallback on a hand-labelled validation set; no "
            "network call, no Groq key required."
        ),
    }


def evaluate_generative_quality(samples=GENERATIVE_SAMPLES, *, use_remote: bool = False) -> dict:
    """Validate the generative review schema and show one representative output.

    A generative model has no single numeric ground truth, so the rubric is
    qualitative (relevance, groundedness, actionability, consistency). The
    benchmark still measures what can be checked automatically: schema
    completeness, score range, determinism, fallback source and output shape.

    The default local fallback keeps the page free and reproducible. Set
    ``use_remote=True`` to send the same samples through Groq; this doubles the
    number of API calls because the determinism check runs twice.
    """
    results = []
    durations: list[float] = []
    for sample in samples:
        started = perf_counter()
        if use_remote:
            first = ai_service.analyse_project(
                title=sample["title"],
                tagline=sample["tagline"],
                description=sample["description"],
                category=sample["category"],
            )
        else:
            first = ai_service._fallback_analyse(
                sample["title"],
                sample["tagline"],
                sample["description"],
                sample["category"],
            )
        elapsed = (perf_counter() - started) * 1000
        if use_remote:
            second = ai_service.analyse_project(
                title=sample["title"],
                tagline=sample["tagline"],
                description=sample["description"],
                category=sample["category"],
            )
        else:
            second = ai_service._fallback_analyse(
                sample["title"],
                sample["tagline"],
                sample["description"],
                sample["category"],
            )
        durations.append(elapsed)

        required = ("score", "comment", "strengths", "weaknesses", "source", "source_key")
        complete = all(first.get(field) for field in required)
        score = first.get("score")
        score_valid = isinstance(score, int) and 1 <= score <= 10
        strengths = first.get("strengths") or []
        weaknesses = first.get("weaknesses") or []
        results.append(
            {
                "title": sample["title"],
                "tagline": sample["tagline"],
                "category": sample["category"],
                "score": score,
                "comment": first.get("comment", ""),
                "strengths": strengths,
                "weaknesses": weaknesses,
                "complete": complete,
                "score_valid": score_valid,
                "consistent": first == second,
                "source": first.get("source", ""),
                "source_key": first.get("source_key", ""),
            }
        )

    complete_count = sum(1 for result in results if result["complete"])
    valid_score_count = sum(1 for result in results if result["score_valid"])
    consistent_count = sum(1 for result in results if result["consistent"])
    total = len(results)
    average_score = fmean(result["score"] for result in results if result["score_valid"])

    return {
        "sample_count": total,
        "results": results,
        "sample": results[0] if results else None,
        "completeness_percent": _percent(_ratio(complete_count, total)),
        "score_range_percent": _percent(_ratio(valid_score_count, total)),
        "consistency_percent": _percent(_ratio(consistent_count, total)),
        "average_score": round(average_score, 1) if results else None,
        "latency_p50_ms": _percentile(durations, 50),
        "latency_p95_ms": _percentile(durations, 95),
        "criteria": QUALITATIVE_CRITERIA,
        "benchmark_source": "remote" if use_remote else "local-fallback",
        "method": (
            "Qualitative rubric applied to remote Groq outputs; the determinism "
            "check may legitimately vary between calls."
            if use_remote
            else "Qualitative rubric applied to local fallback outputs; the "
            "local checks are deterministic and free to reproduce."
        ),
    }
