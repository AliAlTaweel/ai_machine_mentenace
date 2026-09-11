from backend.graph.nodes.hitl_gate import hitl_gate_node


def test_hitl_gate_node_passes_through_when_no_approval_needed():
    result = hitl_gate_node({"needs_approval": False})
    assert result == {}
