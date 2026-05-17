"""``python manage.py mcp_serve`` -- run SurajClaw as an MCP server (stdio).

Thin wrapper around :func:`mcp_server.main` so Django apps are loaded before
the FastMCP server starts. Run this from any MCP client config:

    {
      "mcpServers": {
        "surajclaw": {
          "command": "/path/to/.venv/bin/python",
          "args": ["/path/to/surajclaw/manage.py", "mcp_serve"]
        }
      }
    }
"""
from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run SurajClaw as an MCP server over stdio."

    def handle(self, *args, **opts):
        from mcp_server import main

        main()
