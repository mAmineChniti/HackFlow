"""Single Groq client used by every AI feature in HackFlow.

Keeping the external provider in one module guarantees that:

* every AI service uses the same API key (``GROQ_API_KEY``) and model
  (``AI_MODEL``);
* timeout, error handling and secret redaction stay consistent;
* there is no second external AI provider hidden in an app.

The client uses plain ``urllib`` (already a standard-library dependency) so the
project does not need an extra provider SDK. When the key is missing or the API
call fails, callers fall back to their local heuristic/template implementation.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

DEFAULT_AI_MODEL = "openai/gpt-oss-120b"  # Groq-hosted model id, not an OpenAI API call
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
API_TIMEOUT_SECONDS = 15


def get_api_key() -> str:
    """Return the configured Groq key, or an empty string for placeholders."""
    # Pass the Django setting as the os.getenv default (rather than using
    # ``or``) so tests that patch os.getenv to "" keep the no-key fallback.
    api_key = os.getenv("GROQ_API_KEY", getattr(settings, "GROQ_API_KEY", "")).strip()
    lowered = api_key.lower()
    if (
        not api_key
        or lowered in {"", "none", "null"}
        or "your_api_key" in lowered
        or "gsk_" not in api_key
    ):
        return ""
    return api_key


def get_model() -> str:
    """Return the model configured through ``AI_MODEL`` (or the default)."""
    model = os.getenv("AI_MODEL", getattr(settings, "AI_MODEL", DEFAULT_AI_MODEL)).strip()
    return model or DEFAULT_AI_MODEL


def is_configured() -> bool:
    """True when a usable Groq API key is configured."""
    return bool(get_api_key())


def _redact(text: str) -> str:
    """Remove the API key from an error message before logging it."""
    api_key = get_api_key()
    if api_key and api_key in text:
        return text.replace(api_key, "[REDACTED_API_KEY]")
    return text


def call_groq(
    prompt: str,
    *,
    system_prompt: str = "",
    max_tokens: int = 600,
    model: str | None = None,
) -> str | None:
    """Send a chat completion to Groq and return its text content.

    Returns ``None`` when the key is missing or the request fails so callers can
    use their local fallback. An empty response body is returned as ``""``.
    """
    api_key = get_api_key()
    if not api_key:
        logger.warning("GROQ_API_KEY not configured or contains placeholder - using fallback")
        return None

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    request_body = json.dumps(
        {
            "model": model or get_model(),
            "max_tokens": max_tokens,
            "messages": messages,
        }
    ).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "content-type": "application/json",
    }
    request = urllib.request.Request(
        GROQ_API_URL,
        data=request_body,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=API_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("Groq API call failed: %s", _redact(str(exc)))
        return None

    choices = data.get("choices", [])
    if not choices:
        return ""
    return choices[0].get("message", {}).get("content", "")
