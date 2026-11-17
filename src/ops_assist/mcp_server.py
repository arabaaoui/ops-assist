"""Expose observation tools over MCP stdio using the installed official SDK."""

import logging
import os
import sys

from mcp.server.mcpserver import MCPServer

from .observability import source_from_env
from .tools import MCP_EXPOSED_TOOLS, make_tools


def serve() -> None:
    """Serve the four observation tools until the stdio client disconnects."""
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, force=True)
    logging.getLogger(__name__).info("Starting ops-assist MCP server")
    if "OPS_ASSIST_ALLOW_WRITES" in os.environ:
        logging.getLogger(__name__).warning("MCP always runs read-only; writes are disabled")
    source = source_from_env(os.environ.get("OPS_ASSIST_INCIDENT", "payment-latency"))
    server = MCPServer("ops-assist")
    available = {tool.__name__: tool for tool in make_tools(source)}
    missing = set(MCP_EXPOSED_TOOLS) - available.keys()
    if missing:
        raise ValueError(f"MCP server missing tools: {', '.join(sorted(missing))}")
    for name in MCP_EXPOSED_TOOLS:
        server.add_tool(available[name])
    server.run(transport="stdio")


if __name__ == "__main__":
    serve()
