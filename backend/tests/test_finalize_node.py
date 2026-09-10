import pytest
import mongomock

from backend.graph.nodes.finalize import make_finalize_node


@pytest.mark.asyncio
async def test_finalize_node_completes_work_order_when_all_parts_reserved():
    async def fake_reserve(part_id, quantity):
        return {"part_id": part_id, "qty_on_hand": 9, "reserved": quantity, "shortfall": 0}

    collection = mongomock.MongoClient()["machine_repair"]["work_orders"]
    node = make_finalize_node(collection, reserve_parts_fn=fake_reserve)

    result = await node({
        "machine_id": "CNC-Mill-200",
        "error_code": "E101",
        "diagnosis": "Main spindle bearing wear",
        "required_parts": [{"part_id": "BEARING-X4", "name": "Bearing X4", "quantity": 1}],
        "needs_approval": False,
    })

    assert result["work_order_status"] == "completed"
    doc = collection.find_one({"_id": __import__("bson").ObjectId(result["work_order_id"])})
    assert doc["parts_used"] == [{"part_id": "BEARING-X4", "name": "Bearing X4", "quantity": 1}]
    assert doc["parts_ordered"] == []
    assert doc["status"] == "completed"


@pytest.mark.asyncio
async def test_finalize_node_records_shortfall_as_parts_ordered():
    async def fake_reserve(part_id, quantity):
        return {"part_id": part_id, "qty_on_hand": 0, "reserved": 1, "shortfall": 2}

    collection = mongomock.MongoClient()["machine_repair"]["work_orders"]
    node = make_finalize_node(collection, reserve_parts_fn=fake_reserve)

    result = await node({
        "machine_id": "Hydraulic-Press-9",
        "error_code": "H33",
        "diagnosis": "Hydraulic valve failure",
        "required_parts": [{"part_id": "VALVE-H9", "name": "Hydraulic Valve H9", "quantity": 3}],
        "needs_approval": True,
        "approval_decision": "approved",
    })

    doc = collection.find_one({"_id": __import__("bson").ObjectId(result["work_order_id"])})
    assert doc["parts_used"] == []
    assert doc["parts_ordered"] == [{"part_id": "VALVE-H9", "name": "Hydraulic Valve H9", "quantity": 1, "shortfall": 2}]


@pytest.mark.asyncio
async def test_finalize_node_marks_rejected_when_approval_denied():
    async def fake_reserve(part_id, quantity):
        raise AssertionError("reserve_parts_fn should not be called when rejected")

    collection = mongomock.MongoClient()["machine_repair"]["work_orders"]
    node = make_finalize_node(collection, reserve_parts_fn=fake_reserve)

    result = await node({
        "machine_id": "CNC-Mill-200",
        "error_code": "E101",
        "diagnosis": "Main spindle bearing wear",
        "required_parts": [{"part_id": "BEARING-X4", "name": "Bearing X4", "quantity": 1}],
        "needs_approval": True,
        "approval_decision": "rejected",
    })

    assert result["work_order_status"] == "rejected"
    doc = collection.find_one({"_id": __import__("bson").ObjectId(result["work_order_id"])})
    assert doc["status"] == "rejected"
    assert doc["parts_used"] == []
    assert doc["parts_ordered"] == []
