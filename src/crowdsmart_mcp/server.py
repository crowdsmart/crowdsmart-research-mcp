"""MCP server for CrowdSmart: Knowledge Agents, Jams and Knowledge Model Agents.

The server offers a small set of tools for the Knowledge Agent, Jam and Knowledge
Model Agent workflows of the CrowdSmart platform. See README.md for its scope.
"""

import os
import sys

from crowdsmart_mcp import jams, kmas, knowledge_agents
from crowdsmart_mcp.api import MISSING_KEY
from crowdsmart_mcp.app import mcp

# Importing these modules registers their tools with the server.
TOOL_MODULES = (knowledge_agents, jams, kmas)

__all__ = ["TOOL_MODULES", "main", "mcp"]


def main() -> None:
    """Run the server over stdio."""
    if not os.environ.get("CROWDSMART_API_KEY"):
        sys.exit(MISSING_KEY)
    mcp.run(transport="stdio")
