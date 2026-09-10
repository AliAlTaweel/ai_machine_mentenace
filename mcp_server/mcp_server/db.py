import os

from pymongo import MongoClient


def get_inventory_collection(client: MongoClient | None = None, db_name: str | None = None):
    if client is None:
        client = MongoClient(os.environ["MONGODB_URI"])
    resolved_db_name = db_name or os.environ.get("MONGODB_DB", "machine_repair")
    return client[resolved_db_name]["inventory"]
