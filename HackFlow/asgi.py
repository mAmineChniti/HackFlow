"""
ASGI config for HackFlow project.

It exposes the ASGI callable as a module-level variable named ``application``.

It also mounts the Django MCP server alongside the Django application.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "HackFlow.settings")

django_application = get_asgi_application()

try:
    from django_mcp import mount_mcp_server

    application = mount_mcp_server(django_application)
except Exception:
    application = django_application
