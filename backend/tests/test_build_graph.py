import mongomock
import pytest
from bson import ObjectId
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from backend.graph.build import build_graph
from backend.graph.nodes.extract import ExtractedError
from backend.graph.nodes.rag_lookup import DiagnosisResult, RequiredPart


def make_collections():
    client = mongomock.MongoClient()
    return client["machine_repair"]["manuals"], client["machine_repair"]["work_orders"]


@pytest.mark.asyncio
async def test_graph_ends_with_clarification_when_extraction_incomplete(fake_llm):
    llm = fake_llm(structured_responses=[ExtractedError(machine_id=None, error_code="E101", description="noise")])
    manuals, work_orders = make_collections()
    graph = build_graph(llm, manuals, work_orders, MemorySaver())
    config = {"configurable": {"thread_id": "t1"}}

    result = await graph.ainvoke({"user_input": "grinding noise, error E101"}, config)

    assert result["needs_clarification"] is True
    assert "work_order_id" not in result


@pytest.mark.asyncio
async def test_graph_completes_without_approval_when_parts_in_stock(fake_llm, monkeypatch):
    llm = fake_llm(structured_responses=[
        ExtractedError(machine_id="CNC-Mill-200", error_code="E101", description="grinding noise"),
        DiagnosisResult(
            diagnosis="Main spindle bearing wear",
            repair_steps=["Replace bearing"],
            required_parts=[RequiredPart(part_id="BEARING-X4", name="Bearing X4", quantity=1)],
        ),
    ])
    manuals, work_orders = make_collections()
    manuals.insert_one({"chunk_text": "bearing wear procedure", "machine_type": "CNC-Mill-200", "error_codes": ["E101"]})

    async def fake_check_stock(part_id):
        return {"part_id": part_id, "name": "Bearing X4", "qty_on_hand": 12, "reorder_threshold": 5, "status": "in_stock"}

    async def fake_reserve_parts(part_id, quantity):
        return {"part_id": part_id, "qty_on_hand": 11, "reserved": quantity, "shortfall": 0}

    monkeypatch.setattr("backend.graph.build.check_stock", fake_check_stock)
    monkeypatch.setattr("backend.graph.build.reserve_parts", fake_reserve_parts)
    monkeypatch.setattr("backend.graph.build.search_manuals", lambda collection, query_embedding, top_k=3, machine_type=None: [
        {"chunk_text": "bearing wear procedure", "machine_type": "CNC-Mill-200", "error_codes": ["E101"]}
    ])
    monkeypatch.setattr("backend.graph.build.embed_text", lambda text: [0.1, 0.2])

    graph = build_graph(llm, manuals, work_orders, MemorySaver())
    config = {"configurable": {"thread_id": "t2"}}

    result = await graph.ainvoke({"user_input": "CNC mill E101 grinding noise"}, config)

    assert result["work_order_status"] == "completed"
    assert result["needs_approval"] is False
    assert "__interrupt__" not in result
    stored = work_orders.find_one({"_id": ObjectId(result["work_order_id"])})
    assert stored["status"] == "completed"
    assert stored["parts_used"] == [{"part_id": "BEARING-X4", "name": "Bearing X4", "quantity": 1}]


@pytest.mark.asyncio
async def test_graph_pauses_for_approval_and_resumes_when_approved(fake_llm, monkeypatch):
    llm = fake_llm(structured_responses=[
        ExtractedError(machine_id="Hydraulic-Press-9", error_code="H33", description="pressure loss"),
        DiagnosisResult(
            diagnosis="Hydraulic valve failure",
            repair_steps=["Replace valve"],
            required_parts=[RequiredPart(part_id="VALVE-H9", name="Hydraulic Valve H9", quantity=1)],
        ),
    ])
    manuals, work_orders = make_collections()

    async def fake_check_stock(part_id):
        return {"part_id": part_id, "name": "Hydraulic Valve H9", "qty_on_hand": 0, "reorder_threshold": 2, "status": "out_of_stock"}

    reserved_calls = []

    async def fake_reserve_parts(part_id, quantity):
        reserved_calls.append((part_id, quantity))
        return {"part_id": part_id, "qty_on_hand": 0, "reserved": 0, "shortfall": quantity}

    monkeypatch.setattr("backend.graph.build.check_stock", fake_check_stock)
    monkeypatch.setattr("backend.graph.build.reserve_parts", fake_reserve_parts)
    monkeypatch.setattr("backend.graph.build.search_manuals", lambda collection, query_embedding, top_k=3, machine_type=None: [
        {"chunk_text": "valve failure procedure", "machine_type": "Hydraulic-Press-9", "error_codes": ["H33"]}
    ])
    monkeypatch.setattr("backend.graph.build.embed_text", lambda text: [0.1, 0.2])

    graph = build_graph(llm, manuals, work_orders, MemorySaver())
    config = {"configurable": {"thread_id": "t3"}}

    first = await graph.ainvoke({"user_input": "press losing pressure, H33"}, config)

    # The run paused at hitl_gate: no work order was written and nothing reserved yet.
    assert "__interrupt__" in first
    interrupt_payload = first["__interrupt__"][0].value
    assert interrupt_payload["inventory_status"][0]["status"] == "out_of_stock"
    assert interrupt_payload["required_parts"][0]["part_id"] == "VALVE-H9"
    assert "work_order_id" not in first
    assert reserved_calls == []
    snapshot = await graph.aget_state(config)
    assert snapshot.next == ("hitl_gate",)

    resumed = await graph.ainvoke(Command(resume="approved"), config)

    assert resumed["approval_decision"] == "approved"
    assert resumed["work_order_status"] == "completed"
    assert resumed["work_order_id"]
    assert reserved_calls == [("VALVE-H9", 1)]
    stored = work_orders.find_one({"_id": ObjectId(resumed["work_order_id"])})
    assert stored["status"] == "completed"
    assert stored["parts_ordered"] == [
        {"part_id": "VALVE-H9", "name": "Hydraulic Valve H9", "quantity": 0, "shortfall": 1}
    ]


@pytest.mark.asyncio
async def test_graph_marks_rejected_when_approval_denied(fake_llm, monkeypatch):
    llm = fake_llm(structured_responses=[
        ExtractedError(machine_id="Hydraulic-Press-9", error_code="H33", description="pressure loss"),
        DiagnosisResult(
            diagnosis="Hydraulic valve failure",
            repair_steps=["Replace valve"],
            required_parts=[RequiredPart(part_id="VALVE-H9", name="Hydraulic Valve H9", quantity=1)],
        ),
    ])
    manuals, work_orders = make_collections()

    async def fake_check_stock(part_id):
        return {"part_id": part_id, "name": "Hydraulic Valve H9", "qty_on_hand": 0, "reorder_threshold": 2, "status": "out_of_stock"}

    async def fake_reserve_parts(part_id, quantity):
        raise AssertionError("must not reserve parts when rejected")

    monkeypatch.setattr("backend.graph.build.check_stock", fake_check_stock)
    monkeypatch.setattr("backend.graph.build.reserve_parts", fake_reserve_parts)
    monkeypatch.setattr("backend.graph.build.search_manuals", lambda collection, query_embedding, top_k=3, machine_type=None: [
        {"chunk_text": "valve failure procedure", "machine_type": "Hydraulic-Press-9", "error_codes": ["H33"]}
    ])
    monkeypatch.setattr("backend.graph.build.embed_text", lambda text: [0.1, 0.2])

    graph = build_graph(llm, manuals, work_orders, MemorySaver())
    config = {"configurable": {"thread_id": "t4"}}

    first = await graph.ainvoke({"user_input": "press losing pressure, H33"}, config)
    assert "__interrupt__" in first

    resumed = await graph.ainvoke(Command(resume="rejected"), config)

    assert resumed["approval_decision"] == "rejected"
    assert resumed["work_order_status"] == "rejected"
    stored = work_orders.find_one({"_id": ObjectId(resumed["work_order_id"])})
    assert stored["status"] == "rejected"
    assert stored["parts_used"] == []
