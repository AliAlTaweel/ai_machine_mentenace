import json
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

_SERVER_PARAMS = StdioServerParameters(
    command="mcp-inventory-server", args=["serve"], env=dict(os.environ)
)


def _parse_tool_result(result) -> dict:
    if result.isError:
        raise RuntimeError(result.content[0].text)
    return json.loads(result.content[0].text)


async def _call_tool(tool_name: str, arguments: dict) -> dict:
    async with stdio_client(_SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            return _parse_tool_result(result)


async def check_stock(part_id: str) -> dict:
    return await _call_tool("check_stock_tool", {"part_id": part_id})


async def reserve_parts(part_id: str, quantity: int) -> dict:
    return await _call_tool("reserve_parts_tool", {"part_id": part_id, "quantity": quantity})
