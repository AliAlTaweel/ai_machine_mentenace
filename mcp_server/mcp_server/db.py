import os

from pymongo import MongoClient

_client: MongoClient | None = None


def _get_default_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(os.environ["MONGODB_URI"], serverSelectionTimeoutMS=5000)
    return _client


def get_inventory_collection(client: MongoClient | None = None, db_name: str | None = None):
    if client is None:
        client = _get_default_client()
    resolved_db_name = db_name or os.environ.get("MONGODB_DB", "machine_repair")
    return client[resolved_db_name]["inventory"]
