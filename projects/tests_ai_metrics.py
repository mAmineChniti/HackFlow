"""Tests for the AI metrics dashboard and benchmark.

These cover the rubric's "Métriques d'évaluation" and "Performance &
asynchronisme" evidence:

* classifier metrics are computed on the labelled set and the confusion matrix
  totals match the number of examples;
* generative structural checks are complete and deterministic;
* the live metrics buffer computes p50/p95 without storing prompts or secrets;
* only organizers/admins can open the metrics page.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from accounts.models import Profile
from core.ai_metrics import (
    percentile,
    record_ai_run,
    reset_ai_runs,
    summarize_ai_runs,
)
from projects.ai_benchmark import (
    LABELED_CATEGORY_SAMPLES,
    evaluate_category_classifier,
    evaluate_generative_quality,
)

User = get_user_model()
PASSWORD = "Sup3rSecret!pass"


class CategoryBenchmarkTests(SimpleTestCase):
    def test_classifier_metrics_are_complete(self):
        metrics = evaluate_category_classifier()

        self.assertEqual(metrics["sample_count"], len(LABELED_CATEGORY_SAMPLES))
        self.assertGreaterEqual(metrics["accuracy"], 0)
        self.assertLessEqual(metrics["accuracy"], 1)
        self.assertEqual(
            sum(item["support"] for item in metrics["per_class"]),
            metrics["sample_count"],
        )
        self.assertEqual(
            sum(row["total"] for row in metrics["confusion_matrix"]),
            metrics["sample_count"],
        )
        self.assertGreaterEqual(metrics["macro_f1"], 0)
        self.assertLessEqual(metrics["macro_f1"], 1)
        self.assertIsNotNone(metrics["latency_p95_ms"])

    def test_confusion_matrix_marks_the_known_ambiguous_example(self):
        metrics = evaluate_category_classifier()
        errors = {item["title"]: item for item in metrics["errors"]}

        self.assertIn("EcoShop", errors)
        self.assertEqual(errors["EcoShop"]["predicted"], "Web Development")

    @mock.patch("projects.ai_benchmark.ai_service.detect_category")
    def test_remote_mode_uses_the_configured_service(self, mock_detect):
        mock_detect.return_value = {"category": "web", "confidence": "high"}

        metrics = evaluate_category_classifier(use_remote=True)

        self.assertEqual(metrics["benchmark_source"], "remote")
        self.assertEqual(mock_detect.call_count, len(LABELED_CATEGORY_SAMPLES))
        self.assertIn("Remote Groq", metrics["method"])


class GenerativeBenchmarkTests(SimpleTestCase):
    def test_structural_checks_and_determinism(self):
        metrics = evaluate_generative_quality()

        self.assertEqual(metrics["sample_count"], len(metrics["results"]))
        self.assertEqual(metrics["completeness_percent"], 100.0)
        self.assertEqual(metrics["score_range_percent"], 100.0)
        self.assertEqual(metrics["consistency_percent"], 100.0)
        self.assertIsNotNone(metrics["sample"])
        self.assertGreaterEqual(metrics["average_score"], 1)
        self.assertLessEqual(metrics["average_score"], 10)


class LiveMetricsTests(SimpleTestCase):
    def setUp(self):
        reset_ai_runs()

    def tearDown(self):
        reset_ai_runs()

    def test_percentile_uses_nearest_rank(self):
        self.assertIsNone(percentile([], 50))
        self.assertEqual(percentile([10], 95), 10)
        self.assertEqual(percentile([10, 20, 30, 40], 50), 20)
        self.assertEqual(percentile([10, 20, 30, 40], 95), 40)

    def test_summary_groups_operations_and_sources(self):
        record_ai_run("project_evaluation", "heuristic", 12.5, mode="sync")
        record_ai_run("project_evaluation", "remote", 400.0, mode="async")
        record_ai_run("category_detection", "heuristic", 0.4)

        summary = summarize_ai_runs()

        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["fallback_runs"], 2)
        self.assertEqual(summary["remote_runs"], 1)
        by_operation = {item["key"]: item for item in summary["summaries"]}
        self.assertEqual(by_operation["project_evaluation"]["runs"], 2)
        self.assertEqual(by_operation["project_evaluation"]["p95_ms"], 400.0)
        self.assertEqual(by_operation["category_detection"]["runs"], 1)
        self.assertEqual(len(summary["recent"]), 3)

    def test_metrics_do_not_store_prompts_or_user_data(self):
        record_ai_run("project_evaluation", "heuristic", 1.0)
        event = summarize_ai_runs()["recent"][0]

        self.assertEqual(
            set(event),
            {
                "operation",
                "source",
                "mode",
                "duration_ms",
                "success",
                "timestamp",
                "operation_label",
                "source_label",
                "mode_label",
            },
        )


class AiMetricsAccessTests(TestCase):
    def setUp(self):
        cache.clear()
        self.student = User.objects.create_user(
            username="student-metrics",
            email="student-metrics@example.com",
            password=PASSWORD,
        )
        self.student.profile.role = Profile.Role.STUDENT
        self.student.profile.save()

        self.organizer = User.objects.create_user(
            username="organizer-metrics",
            email="organizer-metrics@example.com",
            password=PASSWORD,
            is_staff=True,
        )
        self.organizer.profile.role = Profile.Role.ORGANIZER
        self.organizer.profile.save()

        self.url = reverse("projects:ai_metrics")

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_student_is_forbidden(self):
        self.client.force_login(self.student)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_organizer_can_open_the_metrics_page(self):
        self.client.force_login(self.organizer)
        with self.settings(AI_ASYNC_ENABLED=True):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI Evaluation Metrics")
        self.assertContains(response, "Macro F1")
        self.assertContains(response, "Confusion matrix")
        self.assertContains(response, "Async enabled")


class AiInstrumentationTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    @mock.patch("projects.ai_service._call_groq_api", return_value=None)
    def test_category_detection_records_a_fallback_run(self, _mock_groq):
        from projects.ai_service import detect_category

        result = detect_category("StudyMate", "An NLP model for study plans.")
        summary = summarize_ai_runs()

        self.assertEqual(result["source_key"], "heuristic")
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["fallback_runs"], 1)
        self.assertEqual(summary["summaries"][0]["key"], "category_detection")

    @mock.patch("projects.ai_service._call_groq_api", return_value=None)
    def test_project_evaluation_records_the_async_mode(self, _mock_groq):
        from projects.ai_service import analyse_project

        analyse_project(
            title="StudyMate",
            tagline="Revision plans",
            description="An NLP model that builds revision plans for students.",
            category="Artificial Intelligence & Data",
            mode="async",
        )
        summary = summarize_ai_runs()

        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["summaries"][0]["key"], "project_evaluation")
        self.assertEqual(summary["recent"][0]["mode"], "async")
