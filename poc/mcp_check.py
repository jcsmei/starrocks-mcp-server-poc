"""Use StarRocks's official MCP server as an AI agent would.

The server is started over stdio, connected as the read-only
`agent_reader` user, and asked to list its tools, describe a table and
answer a question.  Then it is asked to drop a table, which the
database must refuse: the server always offers `write_query`, so
governance has to come from the database user, not from the agent.
"""

import asyncio
import os

from mcp import Client, StdioServerParameters

import db

SERVER_VERSION = "0.4.0"
# Release 0.4.0 imports fastmcp.tools.tool, which fastmcp 3.2 removed,
# but it does not cap fastmcp's version, so a fresh install fails at
# startup.  The fix is on the server's main branch but not released
# yet.  3.1.1 is the newest fastmcp that still has the module.
FASTMCP_VERSION = "3.1.1"


def text_of(result):
    """Return the text an MCP tool call produced."""
    parts = [getattr(item, "text", "") for item in result.content]
    return " ".join(part for part in parts if part)


async def run_checks():
    """Return (step, outcome, detail) for each MCP step."""
    url = (f"{db.AGENT_USER}:{db.AGENT_PASSWORD}@{db.HOST}:"
           f"{db.QUERY_PORT}/{db.DATABASE}")
    params = StdioServerParameters(
        command="uv",
        args=["run", "--with", f"mcp-server-starrocks=={SERVER_VERSION}",
              "--with", f"fastmcp=={FASTMCP_VERSION}",
              "mcp-server-starrocks"],
        env={**os.environ, "STARROCKS_URL": url,
             "STARROCKS_QUERY_TIMEOUT": "10"},
    )
    steps = []
    async with Client(params) as client:
        tools = sorted(tool.name for tool in (await client.list_tools()).tools)
        steps.append(("List tools", "ok", ", ".join(tools)))

        overview = await client.call_tool(
            "table_overview", {"table": "fact_creative"})
        steps.append(("table_overview fact_creative",
                      "error" if overview.is_error else "ok",
                      text_of(overview)[:300]))

        answer = await client.call_tool("read_query", {
            "query": "SELECT COUNT(*) AS live FROM v_latest_creatives "
                     "WHERE platform = 'Reddit' AND status = 'Live'"})
        steps.append(("read_query: live creatives on Reddit",
                      "error" if answer.is_error else "ok",
                      text_of(answer)[:300]))

        attempt = await client.call_tool(
            "write_query", {"query": "DROP TABLE fact_creative"})
        detail = text_of(attempt)
        refused = attempt.is_error or "denied" in detail.lower()
        steps.append(("write_query: DROP TABLE, as the read-only user",
                      "refused" if refused else "NOT REFUSED",
                      detail[:300]))
    return steps


def mcp_checks():
    """Run the MCP steps from ordinary code."""
    return asyncio.run(run_checks())
