from typing import Awaitable, Callable

from backend.graph.state import GraphState
from backend.mcp_client import check_stock

LOW_STATUSES = {"low_stock", "out_of_stock"}


def make_inventory_check_node(check_stock_fn=check_stock) -> Callable[[GraphState], Awaitable[dict]]:
    async def inventory_check_node(state: GraphState) -> dict:
        inventory_status = []
        needs_approval = False
        for part in state.get("required_parts", []):
            status = await check_stock_fn(part["part_id"])
            inventory_status.append(status)
            if status["status"] in LOW_STATUSES:
                needs_approval = True
        return {"inventory_status": inventory_status, "needs_approval": needs_approval}

    return inventory_check_node
