import asyncio

from mcp_server.server import mcp


def test_server_registers_expected_tools():
    tools = asyncio.run(mcp.list_tools())
    tool_names = {tool.name for tool in tools}
    assert tool_names == {"check_stock_tool", "reserve_parts_tool"}
