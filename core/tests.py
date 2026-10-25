import json
import os
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from core.groq import (
    DEFAULT_AI_MODEL,
    GROQ_API_URL,
    call_groq,
    get_api_key,
    get_model,
    is_configured,
)
from hackathons.models import Hackathon


class HomePageTests(TestCase):
    def test_home_page_renders(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "HackFlow")

    def test_home_page_lists_events_from_the_database(self):
        Hackathon.objects.create(
            name="Database Driven Hack",
            theme="Distributed systems",
            start_date=timezone.localdate() + timedelta(days=10),
            end_date=timezone.localdate() + timedelta(days=12),
        )

        response = self.client.get("/")

        self.assertContains(response, "Database Driven Hack")
        self.assertContains(response, "Distributed systems")


class GroqClientTests(SimpleTestCase):
    """The single external AI provider is Groq (see core/groq.py)."""

    def test_placeholder_key_is_rejected(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "your_api_key_here"}):
            self.assertEqual(get_api_key(), "")
            self.assertFalse(is_configured())

    def test_ai_model_env_override_is_honoured(self):
        with patch.dict(os.environ, {"AI_MODEL": "groq/custom-model"}):
            self.assertEqual(get_model(), "groq/custom-model")

    def test_ai_model_falls_back_to_default(self):
        with patch.dict(os.environ, {"AI_MODEL": ""}):
            self.assertEqual(get_model(), DEFAULT_AI_MODEL)

    def test_call_groq_uses_the_groq_endpoint_and_configured_model(self):
        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps(
            {"choices": [{"message": {"content": "hello from Groq"}}]}
        ).encode("utf-8")
        fake_response.__enter__.return_value = fake_response

        with patch.dict(
            os.environ,
            {"GROQ_API_KEY": "gsk_test_key", "AI_MODEL": "groq/custom-model"},
        ):
            with patch("urllib.request.urlopen", return_value=fake_response) as urlopen:
                self.assertEqual(call_groq("hello"), "hello from Groq")

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, GROQ_API_URL)
        payload = json.loads(request.data)
        self.assertEqual(payload["model"], "groq/custom-model")
        self.assertEqual(payload["messages"], [{"role": "user", "content": "hello"}])
