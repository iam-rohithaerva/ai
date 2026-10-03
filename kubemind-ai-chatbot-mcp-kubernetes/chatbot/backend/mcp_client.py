import os
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# MCP server address (where server.py runs)
MCP_URL = os.getenv("MCP_URL", "http://localhost:8000/mcp")


async def get_tools():
    """Fetch the list of tools from the MCP server."""
    async with streamablehttp_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return result.tools


async def run_tool(name, args):
    """Execute a tool on the MCP server."""
    async with streamablehttp_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, args)
            return result.content[0].text
