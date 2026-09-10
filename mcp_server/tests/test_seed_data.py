import mongomock

from mcp_server.seed_data import SAMPLE_PARTS, seed


def test_seed_inserts_all_sample_parts():
    client = mongomock.MongoClient()
    collection = client["machine_repair"]["inventory"]

    count = seed(collection)

    assert count == len(SAMPLE_PARTS)
    assert collection.count_documents({}) == len(SAMPLE_PARTS)


def test_seed_is_idempotent():
    client = mongomock.MongoClient()
    collection = client["machine_repair"]["inventory"]

    seed(collection)
    seed(collection)

    assert collection.count_documents({}) == len(SAMPLE_PARTS)
