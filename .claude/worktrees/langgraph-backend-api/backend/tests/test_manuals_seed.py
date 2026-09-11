import mongomock

from backend.rag.manuals_seed import SAMPLE_MANUALS, seed_manuals


def fake_embed(text: str) -> list[float]:
    return [float(len(text))]


def test_seed_manuals_inserts_all_sample_manuals():
    client = mongomock.MongoClient()
    collection = client["machine_repair"]["manuals"]

    count = seed_manuals(collection, embed_fn=fake_embed)

    assert count == len(SAMPLE_MANUALS)
    assert collection.count_documents({}) == len(SAMPLE_MANUALS)
    doc = collection.find_one({"manual_id": SAMPLE_MANUALS[0]["manual_id"]})
    assert doc["embedding"] == fake_embed(SAMPLE_MANUALS[0]["chunk_text"])
    assert doc["machine_type"] == SAMPLE_MANUALS[0]["machine_type"]


def test_seed_manuals_is_idempotent():
    client = mongomock.MongoClient()
    collection = client["machine_repair"]["manuals"]

    seed_manuals(collection, embed_fn=fake_embed)
    seed_manuals(collection, embed_fn=fake_embed)

    assert collection.count_documents({}) == len(SAMPLE_MANUALS)
