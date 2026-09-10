from datetime import datetime, timezone
from typing import Awaitable, Callable

from backend.graph.state import GraphState
from backend.mcp_client import reserve_parts


def make_finalize_node(work_orders_collection, reserve_parts_fn=reserve_parts) -> Callable[[GraphState], Awaitable[dict]]:
    async def finalize_node(state: GraphState) -> dict:
        base_doc = {
            "machine_id": state["machine_id"],
            "error_code": state["error_code"],
            "diagnosis": state.get("diagnosis"),
            "created_at": datetime.now(timezone.utc),
        }

        if state.get("needs_approval") and state.get("approval_decision") != "approved":
            work_order = {**base_doc, "parts_used": [], "parts_ordered": [], "status": "rejected"}
            result = work_orders_collection.insert_one(work_order)
            return {"work_order_id": str(result.inserted_id), "work_order_status": "rejected"}

        parts_used = []
        parts_ordered = []
        for part in state.get("required_parts", []):
            reservation = await reserve_parts_fn(part["part_id"], part["quantity"])
            if reservation["shortfall"] > 0:
                parts_ordered.append({
                    "part_id": part["part_id"],
                    "name": part["name"],
                    "quantity": reservation["reserved"],
                    "shortfall": reservation["shortfall"],
                })
            else:
                parts_used.append({
                    "part_id": part["part_id"],
                    "name": part["name"],
                    "quantity": reservation["reserved"],
                })

        work_order = {**base_doc, "parts_used": parts_used, "parts_ordered": parts_ordered, "status": "completed"}
        result = work_orders_collection.insert_one(work_order)
        return {"work_order_id": str(result.inserted_id), "work_order_status": "completed"}

    return finalize_node
