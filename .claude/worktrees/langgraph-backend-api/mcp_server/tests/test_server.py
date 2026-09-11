import asyncio
import json

import mcp_server.server as server_mod
from mcp_server.server import server


def test_server_registers_expected_tools():
    tools = asyncio.run(server.list_tools())
    tool_names = {tool.name for tool in tools}
    assert tool_names == {"check_stock_tool", "reserve_parts_tool"}


def test_check_stock_tool_invocation(monkeypatch, inventory_collection):
    monkeypatch.setattr(
        server_mod, "get_inventory_collection", lambda: inventory_collection
    )

    result = asyncio.run(
        server.call_tool("check_stock_tool", {"part_id": "BEARING-X4"})
    )
    payload = json.loads(result[0].text)

    assert payload == {
        "part_id": "BEARING-X4",
        "name": "Bearing X4",
        "qty_on_hand": 12,
        "reorder_threshold": 5,
        "status": "in_stock",
    }


def test_reserve_parts_tool_invocation(monkeypatch, inventory_collection):
    monkeypatch.setattr(
        server_mod, "get_inventory_collection", lambda: inventory_collection
    )

    result = asyncio.run(
        server.call_tool(
            "reserve_parts_tool", {"part_id": "BEARING-X4", "quantity": 3}
        )
    )
    payload = json.loads(result[0].text)

    assert payload == {
        "part_id": "BEARING-X4",
        "qty_on_hand": 9,
        "reserved": 3,
        "shortfall": 0,
    }
