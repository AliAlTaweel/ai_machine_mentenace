import pytest

from mcp_server.tools import check_stock, reserve_parts


def test_check_stock_in_stock(inventory_collection):
    result = check_stock(inventory_collection, "BEARING-X4")
    assert result.part_id == "BEARING-X4"
    assert result.qty_on_hand == 12
    assert result.status == "in_stock"


def test_check_stock_low_stock(inventory_collection):
    result = check_stock(inventory_collection, "BELT-A7")
    assert result.status == "low_stock"


def test_check_stock_out_of_stock(inventory_collection):
    result = check_stock(inventory_collection, "VALVE-H9")
    assert result.status == "out_of_stock"


def test_check_stock_unknown_part_raises(inventory_collection):
    with pytest.raises(ValueError, match="Unknown part_id"):
        check_stock(inventory_collection, "NOPE-1")


def test_reserve_parts_decrements_stock(inventory_collection):
    result = reserve_parts(inventory_collection, "BEARING-X4", 3)
    assert result == {
        "part_id": "BEARING-X4",
        "qty_on_hand": 9,
        "reserved": 3,
        "shortfall": 0,
    }


def test_reserve_parts_floors_at_zero(inventory_collection):
    result = reserve_parts(inventory_collection, "BELT-A7", 10)
    assert result == {
        "part_id": "BELT-A7",
        "qty_on_hand": 0,
        "reserved": 2,
        "shortfall": 8,
    }


def test_reserve_parts_unknown_part_raises(inventory_collection):
    with pytest.raises(ValueError, match="Unknown part_id"):
        reserve_parts(inventory_collection, "NOPE-1", 1)


def test_reserve_parts_negative_quantity_raises(inventory_collection):
    with pytest.raises(ValueError, match="quantity must be non-negative"):
        reserve_parts(inventory_collection, "BEARING-X4", -1)
