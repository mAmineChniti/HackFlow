"""Tests for the asynchronous (Celery/Redis) AI evaluation flow.

Grille d'évaluation — BNF « Performance & asynchronisme »: the long Groq call
must not block the HTTP request. The endpoint enqueues a Celery task and
answers 202; the client polls a status endpoint.

Covers:
  * sync mode (default, no broker) keeps returning the payload directly;
  * async mode returns 202 + task_id + status_url and records pending state;
  * polling transitions pending -> done/failed and exposes the payload;
  * task state cannot be read by another user (no task-id enumeration);
  * broker failure degrades to the synchronous call instead of a 500;
  * the task seeds the synchronous result cache;
  * task failures are reported with a generic message (no exception leak).
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Profile
from projects import tasks
from projects.models import Project

User = get_user_model()

PASSWORD = "Sup3rSecret!pass"


class BaseAsyncTestCase(TestCase):
    def setUp(self):
        cache.clear()

        self.owner = User.objects.create_user(
            username="owner", email="owner@example.com", password=PASSWORD
        )
        self.owner.profile.role = Profile.Role.STUDENT
        self.owner.profile.save()

        self.other_student = User.objects.create_user(
            username="intruder", email="intruder@example.com", password=PASSWORD
        )
        self.other_student.profile.role = Profile.Role.STUDENT
        self.other_student.profile.save()

        # Organizer: has AI permission on every project, so reaching the task
        # state depends solely on task-id ownership.
        self.organizer = User.objects.create_user(
            username="organizer",
            email="organizer@example.com",
            password=PASSWORD,
            is_staff=True,
        )
        self.organizer.profile.role = Profile.Role.ORGANIZER
        self.organizer.profile.save()

        # Keep every test hermetic: never call the real Groq API.
        groq = mock.patch("projects.ai_service._call_groq_api", return_value=None)
        groq.start()
        self.addCleanup(groq.stop)

        self.project = Project.objects.create(
            title="Async Project",
            tagline="Deferred AI call",
            description="A description long enough to be evaluated by the engine.",
            created_by=self.owner,
            status=Project.Status.SUBMITTED,
        )
        self.analyze_url = reverse("projects:ai_analyze", args=[self.project.slug])

    def _enqueue(self):
        """POST the AI endpoint with apply_async mocked; return (response, mock)."""
        with mock.patch("projects.tasks.run_ai_evaluation.apply_async") as apply_async:
            response = self.client.post(self.analyze_url, HTTP_X_CSRFTOKEN="x")
        return response, apply_async


class SyncFallbackTests(BaseAsyncTestCase):
    """Without AI_ASYNC_ENABLED the historical synchronous contract holds."""

    def test_sync_mode_returns_payload_directly(self):
        self.client.force_login(self.owner)
        response = self.client.post(self.analyze_url)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("score", payload)
        self.assertNotIn("task_id", payload)

    def test_async_disabled_by_default_without_redis(self):
        from django.conf import settings

        # This test run has no REDIS_URL -> async off -> no worker needed.
        self.assertFalse(settings.AI_ASYNC_ENABLED)


@override_settings(AI_ASYNC_ENABLED=True)
class AsyncEnqueueTests(BaseAsyncTestCase):
    def test_enqueue_returns_202_with_task_id_and_status_url(self):
        self.client.force_login(self.owner)
        response, apply_async = self._enqueue()

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["status"], "queued")
        self.assertTrue(payload["task_id"])
        self.assertEqual(
            payload["status_url"],
            reverse(
                "projects:ai_analyze_status",
                args=[self.project.slug, payload["task_id"]],
            ),
        )
        apply_async.assert_called_once()
        self.assertEqual(apply_async.call_args.kwargs["task_id"], payload["task_id"])

    def test_pending_state_is_recorded_before_enqueue(self):
        self.client.force_login(self.owner)
        response, _ = self._enqueue()
        state = tasks.get_task_state(response.json()["task_id"])
        self.assertIsNotNone(state)
        self.assertEqual(state["status"], tasks.STATUS_PENDING)
        self.assertEqual(state["user_id"], self.owner.pk)
        self.assertEqual(state["project_id"], self.project.pk)

    def test_broker_failure_falls_back_to_sync_instead_of_500(self):
        self.client.force_login(self.owner)
        with mock.patch(
            "projects.tasks.run_ai_evaluation.apply_async",
            side_effect=RuntimeError("broker unavailable"),
        ):
            response = self.client.post(self.analyze_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("score", response.json())

    def test_enqueue_is_rate_limited_like_the_sync_path(self):
        with self.settings(AI_RATE_LIMIT_MAX=1, AI_RATE_LIMIT_WINDOW=60):
            self.client.force_login(self.owner)
            first, _ = self._enqueue()
            second, _ = self._enqueue()
        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 429)


@override_settings(AI_ASYNC_ENABLED=True)
class AsyncTaskStateTests(BaseAsyncTestCase):
    def _start_task(self, apply_async):
        """Run the task body inline (no broker) with the enqueued arguments."""
        kwargs = apply_async.call_args.kwargs["kwargs"]
        tasks.run_ai_evaluation(**kwargs)

    def test_poll_reports_pending_before_the_worker_runs(self):
        self.client.force_login(self.owner)
        response, _ = self._enqueue()
        status_url = response.json()["status_url"]

        poll = self.client.get(status_url)
        self.assertEqual(poll.status_code, 200)
        self.assertEqual(poll.json()["status"], tasks.STATUS_PENDING)

    def test_poll_reports_done_with_payload_after_the_worker_runs(self):
        self.client.force_login(self.owner)
        response, apply_async = self._enqueue()
        status_url = response.json()["status_url"]
        self._start_task(apply_async)

        poll = self.client.get(status_url)
        self.assertEqual(poll.status_code, 200)
        payload = poll.json()
        self.assertEqual(payload["status"], tasks.STATUS_DONE)
        self.assertIn("score", payload)
        self.assertIn("comment", payload)

    def test_completed_task_seeds_the_sync_cache(self):
        self.client.force_login(self.owner)
        _, apply_async = self._enqueue()
        self._start_task(apply_async)

        # A direct (non-async) request now hits the cache seeded by the worker.
        with self.settings(AI_ASYNC_ENABLED=False):
            cached = self.client.post(self.analyze_url)
        self.assertEqual(cached.status_code, 200)
        self.assertEqual(cached.json().get("source_key"), "cache")

    def test_failed_task_returns_generic_error_without_details(self):
        self.client.force_login(self.owner)
        response, apply_async = self._enqueue()
        status_url = response.json()["status_url"]

        with mock.patch(
            "projects.ai_service.analyse_project",
            return_value={"failed": True, "error": "secret internal detail"},
        ):
            self._start_task(apply_async)

        poll = self.client.get(status_url)
        self.assertEqual(poll.status_code, 200)
        payload = poll.json()
        self.assertEqual(payload["status"], tasks.STATUS_FAILED)
        self.assertNotIn("secret internal detail", poll.content.decode())

    def test_task_exception_is_recorded_as_failure_not_raised(self):
        self.client.force_login(self.owner)
        response, apply_async = self._enqueue()
        status_url = response.json()["status_url"]

        with mock.patch(
            "projects.ai_service.analyse_project",
            side_effect=RuntimeError("boom https://api.groq.com leaked"),
        ):
            self._start_task(apply_async)  # must not raise

        poll = self.client.get(status_url)
        payload = poll.json()
        self.assertEqual(payload["status"], tasks.STATUS_FAILED)
        self.assertNotIn("api.groq.com", poll.content.decode())

    def test_unknown_task_id_returns_404(self):
        self.client.force_login(self.owner)
        url = reverse("projects:ai_analyze_status", args=[self.project.slug, "deadbeef" * 4])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_another_user_cannot_read_your_task_state(self):
        self.client.force_login(self.owner)
        response, apply_async = self._enqueue()
        task_id = response.json()["task_id"]
        self._start_task(apply_async)

        # Same task id, different account -> 404 (not 200 with someone's data).
        self.client.force_login(self.organizer)
        url = reverse("projects:ai_analyze_status", args=[self.project.slug, task_id])
        poll = self.client.get(url)
        self.assertEqual(poll.status_code, 404)
        self.assertNotIn("score", poll.json())

    def test_status_endpoint_requires_permission_on_the_project(self):
        judge = User.objects.create_user(
            username="judge", email="judge@example.com", password=PASSWORD
        )
        judge.profile.role = Profile.Role.JUDGE
        judge.profile.save()

        self.client.force_login(self.owner)
        response, _ = self._enqueue()
        status_url = response.json()["status_url"]

        self.client.force_login(judge)
        poll = self.client.get(status_url)
        self.assertEqual(poll.status_code, 403)

    def test_status_endpoint_requires_authentication(self):
        response = self.client.get(
            reverse("projects:ai_analyze_status", args=[self.project.slug, "x" * 32])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)
