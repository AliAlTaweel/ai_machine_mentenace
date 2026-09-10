from mcp.server.fastmcp import FastMCP

from mcp_server.db import get_inventory_collection
from mcp_server.tools import check_stock, reserve_parts

server = FastMCP("inventory-server")


@server.tool()
def check_stock_tool(part_id: str) -> dict:
    """Check current stock level and status for a spare part by its part_id."""
    collection = get_inventory_collection()
    result = check_stock(collection, part_id)
    return {
        "part_id": result.part_id,
        "name": result.name,
        "qty_on_hand": result.qty_on_hand,
        "reorder_threshold": result.reorder_threshold,
        "status": result.status,
    }


@server.tool()
def reserve_parts_tool(part_id: str, quantity: int) -> dict:
    """Reserve (decrement stock for) a given quantity of a spare part."""
    collection = get_inventory_collection()
    return reserve_parts(collection, part_id, quantity)
