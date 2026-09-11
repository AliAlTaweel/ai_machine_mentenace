from langgraph.graph import END, START, StateGraph

from backend.graph.nodes.extract import make_extract_node
from backend.graph.nodes.finalize import make_finalize_node
from backend.graph.nodes.hitl_gate import hitl_gate_node
from backend.graph.nodes.inventory_check import make_inventory_check_node
from backend.graph.nodes.rag_lookup import make_rag_lookup_node
from backend.graph.state import GraphState
from backend.mcp_client import check_stock, reserve_parts
from backend.rag.embeddings import embed_text
from backend.rag.vector_search import search_manuals


def route_after_extract(state: GraphState) -> str:
    return END if state.get("needs_clarification") else "rag_lookup"


def route_after_rag_lookup(state: GraphState) -> str:
    return END if state.get("no_procedure_found") else "inventory_check"


def build_graph(llm, manuals_collection, work_orders_collection, checkpointer):
    graph = StateGraph(GraphState)

    graph.add_node("extract", make_extract_node(llm))
    graph.add_node(
        "rag_lookup",
        make_rag_lookup_node(llm, manuals_collection, embed_fn=embed_text, search_fn=search_manuals),
    )
    graph.add_node("inventory_check", make_inventory_check_node(check_stock_fn=check_stock))
    graph.add_node("hitl_gate", hitl_gate_node)
    graph.add_node("finalize", make_finalize_node(work_orders_collection, reserve_parts_fn=reserve_parts))

    graph.add_edge(START, "extract")
    graph.add_conditional_edges("extract", route_after_extract, {END: END, "rag_lookup": "rag_lookup"})
    graph.add_conditional_edges("rag_lookup", route_after_rag_lookup, {END: END, "inventory_check": "inventory_check"})
    graph.add_edge("inventory_check", "hitl_gate")
    graph.add_edge("hitl_gate", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile(checkpointer=checkpointer)
