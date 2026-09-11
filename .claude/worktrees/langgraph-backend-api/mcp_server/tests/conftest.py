import mongomock
import pytest


@pytest.fixture
def inventory_collection():
    client = mongomock.MongoClient()
    collection = client["machine_repair"]["inventory"]
    collection.insert_many([
        {
            "part_id": "BEARING-X4",
            "name": "Bearing X4",
            "qty_on_hand": 12,
            "reorder_threshold": 5,
            "machine_types": ["CNC-Mill-200"],
        },
        {
            "part_id": "BELT-A7",
            "name": "Conveyor Belt A7",
            "qty_on_hand": 2,
            "reorder_threshold": 3,
            "machine_types": ["Conveyor-Belt-A7"],
        },
        {
            "part_id": "VALVE-H9",
            "name": "Hydraulic Valve H9",
            "qty_on_hand": 0,
            "reorder_threshold": 2,
            "machine_types": ["Hydraulic-Press-9"],
        },
    ])
    return collection
