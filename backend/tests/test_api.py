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
    this stands in for a scanned/image-only PDF: parsing succeeds but yields
    no text, which must be rejected with a 400 (no OCR fallback) rather than
    silently flowing an empty description into the graph.
    """
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_fake_collection(name: str):
    return mongomock.MongoClient()["machine_repair"][name]


def test_upload_endpoint_returns_400_for_scanned_pdf_with_no_text():
    app = create_app(build_graph_fn=lambda *args, **kwargs: None)
    client = TestClient(app)

    response = client.post(
        "/upload",
        files={"file": ("log.pdf", make_blank_pdf_bytes(), "application/pdf")},
    )

    assert response.status_code == 400
    assert "detail" in response.json()


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


def test_websocket_chat_recovers_from_clarification_using_full_transcript(fake_llm):
    """Turn 1 gives machine_id only; turn 2 gives just the error_code.

    Extraction must succeed on turn 2 using BOTH turns' info — proving the
    transcript channel (not the overwritten single-turn user_input) is what
    extract_node reasons over. Before the fix, turn 2 would re-run extract
    with only "E101" as input and ask for machine_id again (infinite
    ping-pong).
    """
    llm = fake_llm(
        structured_responses=[
            ExtractedError(machine_id="CNC-Mill-200", error_code=None, description="needs error code"),
            ExtractedError(machine_id="CNC-Mill-200", error_code="E101", description="grinding noise"),
        ]
    )
    client = TestClient(make_app_with_real_graph(llm))

    with client.websocket_connect("/ws/clarify-thread?backend=local") as websocket:
        websocket.send_json({"type": "chat", "content": "CNC-Mill-200 is grinding"})
        turn1_event = websocket.receive_json()

        websocket.send_json({"type": "chat", "content": "E101"})
        turn2_event = websocket.receive_json()

    assert turn1_event["data"]["needs_clarification"] is True
    assert "error code" in turn1_event["data"]["clarification_message"]

    assert turn2_event["node"] == "extract"
    assert turn2_event["data"]["needs_clarification"] is False
    assert turn2_event["data"]["machine_id"] == "CNC-Mill-200"
    assert turn2_event["data"]["error_code"] == "E101"

    # The turn-2 extraction prompt must contain turn 1's original text, proving
    # the full transcript (not just "E101") was used.
    assert "CNC-Mill-200 is grinding" in llm.prompts[1]


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


def test_websocket_sends_error_event_for_malformed_json(fake_llm):
    llm = fake_llm(
        structured_responses=[
            ExtractedError(machine_id="CNC-Mill-200", error_code="E101", description="grinding noise")
        ]
    )
    client = TestClient(make_app_with_real_graph(llm))

    with client.websocket_connect("/ws/bad-json-thread?backend=local") as websocket:
        websocket.send_text("not valid json{{{")
        error_event = websocket.receive_json()

        # The socket stays open for a subsequent valid message.
        websocket.send_json({"type": "chat", "content": "CNC-Mill-200 throwing E101"})
        retry_event = websocket.receive_json()

    assert error_event["type"] == "error"
    assert retry_event["type"] == "node_update"


def test_websocket_sends_error_event_for_chat_message_missing_content(fake_llm):
    client = TestClient(make_app_with_real_graph(fake_llm()))

    with client.websocket_connect("/ws/missing-content-thread?backend=local") as websocket:
        websocket.send_json({"type": "chat"})
        error_event = websocket.receive_json()

        # The socket stays open — it did not silently disconnect.
        websocket.send_json({"type": "ping"})
        websocket.send_json({"type": "chat", "content": "still alive"})
        # Reaching here without an exception proves the socket is still open.

    assert error_event["type"] == "error"


def test_websocket_sends_error_event_and_closes_on_setup_failure():
    def failing_llm_factory(backend_choice):
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    app = create_app(
        build_graph_fn=lambda *args, **kwargs: None,
        llm_factory=failing_llm_factory,
        manuals_collection_factory=lambda: object(),
        work_orders_collection_factory=lambda: object(),
        checkpoint_client_factory=lambda: None,
    )
    client = TestClient(app)

    with client.websocket_connect("/ws/setup-fail-thread?backend=cloud") as websocket:
        error_event = websocket.receive_json()
        assert error_event["type"] == "error"
        assert "ANTHROPIC_API_KEY" in error_event["message"]


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
