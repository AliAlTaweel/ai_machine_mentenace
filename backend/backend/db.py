import os

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

_client: MongoClient | None = None


def _get_default_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(os.environ["MONGODB_URI"], serverSelectionTimeoutMS=5000)
    return _client


def _resolve(client: MongoClient | None, db_name: str | None):
    if client is None:
        client = _get_default_client()
    resolved_db_name = db_name or os.environ.get("MONGODB_DB", "machine_repair")
    return client[resolved_db_name]


def get_manuals_collection(client: MongoClient | None = None, db_name: str | None = None):
    return _resolve(client, db_name)["manuals"]


def get_work_orders_collection(client: MongoClient | None = None, db_name: str | None = None):
    return _resolve(client, db_name)["work_orders"]


def get_checkpoint_client(client: MongoClient | None = None) -> MongoClient:
    return client if client is not None else _get_default_client()
