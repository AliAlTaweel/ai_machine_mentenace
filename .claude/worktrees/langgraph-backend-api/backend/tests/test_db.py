import mongomock

from backend.db import get_manuals_collection, get_work_orders_collection, get_checkpoint_client


def test_get_manuals_collection_uses_injected_client():
    client = mongomock.MongoClient()
    collection = get_manuals_collection(client=client, db_name="test_db")
    assert collection.name == "manuals"
    assert collection.database.name == "test_db"


def test_get_work_orders_collection_uses_injected_client():
    client = mongomock.MongoClient()
    collection = get_work_orders_collection(client=client, db_name="test_db")
    assert collection.name == "work_orders"
    assert collection.database.name == "test_db"


def test_get_checkpoint_client_returns_injected_client():
    client = mongomock.MongoClient()
    assert get_checkpoint_client(client=client) is client
