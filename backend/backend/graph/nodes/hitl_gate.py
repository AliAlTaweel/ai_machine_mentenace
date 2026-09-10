from langgraph.types import interrupt

from backend.graph.state import GraphState


def hitl_gate_node(state: GraphState) -> dict:
    if not state.get("needs_approval"):
        return {}

    decision = interrupt({
        "required_parts": state.get("required_parts"),
        "inventory_status": state.get("inventory_status"),
    })
    return {"approval_decision": decision}
