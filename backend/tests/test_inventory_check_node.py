import pytest

from backend.graph.nodes.inventory_check import make_inventory_check_node


@pytest.mark.asyncio
async def test_inventory_check_node_no_approval_needed_when_in_stock():
    async def fake_check_stock(part_id):
        return {"part_id": part_id, "name": "Bearing X4", "qty_on_hand": 12, "reorder_threshold": 5, "status": "in_stock"}

    node = make_inventory_check_node(check_stock_fn=fake_check_stock)
    result = await node({"required_parts": [{"part_id": "BEARING-X4", "name": "Bearing X4", "quantity": 1}]})

    assert result["needs_approval"] is False
    assert result["inventory_status"][0]["status"] == "in_stock"


@pytest.mark.asyncio
async def test_inventory_check_node_needs_approval_when_low_stock():
    async def fake_check_stock(part_id):
        return {"part_id": part_id, "name": "Belt A7", "qty_on_hand": 2, "reorder_threshold": 3, "status": "low_stock"}

    node = make_inventory_check_node(check_stock_fn=fake_check_stock)
    result = await node({"required_parts": [{"part_id": "BELT-A7", "name": "Belt A7", "quantity": 1}]})

    assert result["needs_approval"] is True


@pytest.mark.asyncio
async def test_inventory_check_node_checks_every_required_part():
    calls = []

    async def fake_check_stock(part_id):
        calls.append(part_id)
        return {"part_id": part_id, "name": part_id, "qty_on_hand": 10, "reorder_threshold": 1, "status": "in_stock"}

    node = make_inventory_check_node(check_stock_fn=fake_check_stock)
    await node({"required_parts": [
        {"part_id": "BEARING-X4", "name": "Bearing X4", "quantity": 1},
        {"part_id": "MOTOR-C2", "name": "Motor C2", "quantity": 1},
    ]})

    assert calls == ["BEARING-X4", "MOTOR-C2"]
