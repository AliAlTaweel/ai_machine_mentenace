import pytest

from mcp_server.tools import check_stock


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
