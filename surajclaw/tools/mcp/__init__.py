"""MCP client integration.

Importing this package triggers ``register_mcp_tools()``, which discovers
tools from every server in ``settings.MCP_SERVERS`` and adds them to the
central tool registry with id ``mcp.<server>.<tool>``.
"""
from tools.mcp.client import register_mcp_tools

register_mcp_tools()
