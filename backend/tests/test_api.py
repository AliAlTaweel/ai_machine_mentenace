import io

import mongomock
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver
from pypdf import PdfWriter

from backend.api.app import create_app
from backend.graph.build import build_graph as real_build_graph
from backend.graph.nodes.extract import ExtractedError


def make_blank_pdf_bytes() -> bytes:
    """A structurally valid PDF with no extractable text.

    pypdf's PdfWriter can't embed arbitrary text without a layout library, so
    the upload tests verify a readable PDF yields an empty string (not an
    error) — the behaviour the Extract node depends on — and that an
    unreadable one yields a 400.
    """
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_fake_collection(name: str):
    return mongomock.MongoClient()["machine_repair"][name]


def test_upload_endpoint_returns_extracted_text():
    app = create_app(build_graph_fn=lambda *args, **kwargs: None)
    client = TestClient(app)

    response = client.post(
        "/upload",
        files={"file": ("log.pdf", make_blank_pdf_bytes(), "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json() == {"extracted_text": ""}


def test_upload_endpoint_returns_400_for_unreadable_pdf():
    app = create_app(build_graph_fn=lambda *args, **kwargs: None)
    client = TestClient(app)

    response = client.post(
        "/upload",
        files={"file": ("log.pdf", b"not a real pdf", "application/pdf")},
    )

    assert response.status_code == 400
    assert "detail" in response.json()


def make_app_with_real_graph(llm):
    def fake_build_graph(llm_arg, manuals, work_orders, checkpointer):
        return real_build_graph(llm_arg, manuals, work_orders, MemorySaver())

    return create_app(
        build_graph_fn=fake_build_graph,
        llm_factory=lambda backend_choice: llm,
        manuals_collection_factory=lambda: make_fake_collection("manuals"),
        work_orders_collection_factory=lambda: make_fake_collection("work_orders"),
        checkpoint_client_factory=lambda: None,
    )


def test_websocket_chat_streams_node_updates(fake_llm):
    llm = fake_llm(
        structured_responses=[
            ExtractedError(machine_id=None, error_code="E101", description="grinding noise")
        ]
    )
    client = TestClient(make_app_with_real_graph(llm))

    with client.websocket_connect("/ws/test-thread?backend=local") as websocket:
        websocket.send_json({"type": "chat", "content": "grinding noise, E101"})
        event = websocket.receive_json()

    assert event["type"] == "node_update"
    assert event["node"] == "extract"
    assert event["data"]["needs_clarification"] is True
    assert "machine ID" in event["data"]["clarification_message"]


def test_websocket_chat_forwards_pdf_text_to_the_graph(fake_llm):
    llm = fake_llm(
        structured_responses=[
            ExtractedError(machine_id=None, error_code="E101", description="grinding noise")
        ]
    )
    client = TestClient(make_app_with_real_graph(llm))

    with client.websocket_connect("/ws/pdf-thread?backend=local") as websocket:
        websocket.send_json(
            {"type": "chat", "content": "see attached", "pdf_text": "FAULT E101 AT SPINDLE"}
        )
        websocket.receive_json()

    assert "FAULT E101 AT SPINDLE" in llm.prompts[0]


def test_websocket_streams_approval_request_and_resumes_on_approval(fake_llm):
    """The graph interrupts at the HITL gate; an approval message resumes it."""
    llm = fake_llm()
    recorded = {}

    def build_interrupting_graph(llm_arg, manuals, work_orders, checkpointer):
        from langgraph.graph import END, START, StateGraph
        from langgraph.types import interrupt

        from backend.graph.state import GraphState

        def gate(state: GraphState) -> dict:
            decision = interrupt({"required_parts": [{"part_id": "SP-1"}], "inventory_status": []})
            return {"approval_decision": decision}

        def finalize(state: GraphState) -> dict:
            recorded["decision"] = state["approval_decision"]
            return {"work_order_id": "wo-1"}

        graph = StateGraph(GraphState)
        graph.add_node("hitl_gate", gate)
        graph.add_node("finalize", finalize)
        graph.add_edge(START, "hitl_gate")
        graph.add_edge("hitl_gate", "finalize")
        graph.add_edge("finalize", END)
        return graph.compile(checkpointer=MemorySaver())

    app = create_app(
        build_graph_fn=build_interrupting_graph,
        llm_factory=lambda backend_choice: llm,
        manuals_collection_factory=lambda: make_fake_collection("manuals"),
        work_orders_collection_factory=lambda: make_fake_collection("work_orders"),
        checkpoint_client_factory=lambda: None,
    )
    client = TestClient(app)

    with client.websocket_connect("/ws/approval-thread?backend=local") as websocket:
        websocket.send_json({"type": "chat", "content": "replace the spindle bearing"})
        request_event = websocket.receive_json()

        websocket.send_json({"type": "approval", "decision": "approved"})
        events = [websocket.receive_json(), websocket.receive_json()]

    assert request_event["type"] == "approval_request"
    assert request_event["payload"]["required_parts"] == [{"part_id": "SP-1"}]

    assert recorded["decision"] == "approved"
    assert [e["node"] for e in events] == ["hitl_gate", "finalize"]
    assert events[1]["data"]["work_order_id"] == "wo-1"


def test_websocket_sends_error_event_when_graph_run_raises(fake_llm):
    def failing_build_graph(llm_arg, manuals, work_orders, checkpointer):
        class ExplodingGraph:
            async def astream(self, *args, **kwargs):
                raise RuntimeError("MCP server unreachable")
                yield  # pragma: no cover - makes this an async generator

        return ExplodingGraph()

    app = create_app(
        build_graph_fn=failing_build_graph,
        llm_factory=lambda backend_choice: fake_llm(),
        manuals_collection_factory=lambda: object(),
        work_orders_collection_factory=lambda: object(),
        checkpoint_client_factory=lambda: None,
    )
    client = TestClient(app)

    with client.websocket_connect("/ws/test-thread-2?backend=local") as websocket:
        websocket.send_json({"type": "chat", "content": "anything"})
        error_event = websocket.receive_json()

        # The connection stays open so the technician can retry.
        websocket.send_json({"type": "chat", "content": "retry"})
        retry_event = websocket.receive_json()

    assert error_event["type"] == "error"
    assert "MCP server unreachable" in error_event["message"]
    assert retry_event["type"] == "error"


def test_websocket_ignores_unknown_message_types(fake_llm):
    llm = fake_llm(
        structured_responses=[
            ExtractedError(machine_id=None, error_code="E101", description="grinding noise")
        ]
    )
    client = TestClient(make_app_with_real_graph(llm))

    with client.websocket_connect("/ws/unknown-thread?backend=local") as websocket:
        websocket.send_json({"type": "ping"})
        websocket.send_json({"type": "chat", "content": "grinding noise, E101"})
        event = websocket.receive_json()

    assert event["node"] == "extract"
