"""MCP smoke test: start `python -m starsnip --mcp`, list tools."""

import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import os as _os
SRC = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src")


async def main():
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC
    env["PYTHONIOENCODING"] = "utf-8"
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "starsnip", "--mcp"], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print("TOOLS:", names)
            assert "screen_capture_ocr" in names
    print("test_mcp OK")


if __name__ == "__main__":
    asyncio.run(main())
