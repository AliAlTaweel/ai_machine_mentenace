import mongomock

from mcp_server.db import get_inventory_collection


def test_get_inventory_collection_uses_injected_client():
    client = mongomock.MongoClient()
    collection = get_inventory_collection(client=client, db_name="test_db")
    assert collection.name == "inventory"
    assert collection.database.name == "test_db"
