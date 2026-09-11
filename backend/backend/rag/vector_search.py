VECTOR_INDEX_NAME = "manuals_vector_index"


def ensure_vector_index(collection, dimensions: int = 384) -> bool:
    """Create the Atlas Vector Search index `search_manuals` depends on, if
    it doesn't already exist.

    `$vectorSearch` against a missing index returns an empty result set
    rather than raising, so a missing index fails silently as
    "no relevant procedure found" for every query — this makes the index a
    one-time, idempotent side effect of seeding rather than a manual Atlas
    UI step someone has to remember.

    Returns True if the index was created, False if it already existed or
    the collection doesn't support Atlas Search index management (e.g.
    mongomock in tests) — a no-op in that case, not an error.
    """
    try:
        existing_names = {idx["name"] for idx in collection.list_search_indexes()}
    except Exception:
        return False
    if VECTOR_INDEX_NAME in existing_names:
        return False

    from pymongo.operations import SearchIndexModel

    collection.create_search_index(
        SearchIndexModel(
            definition={
                "fields": [
                    {
                        "type": "vector",
                        "path": "embedding",
                        "numDimensions": dimensions,
                        "similarity": "cosine",
                    }
                ]
            },
            name=VECTOR_INDEX_NAME,
            type="vectorSearch",
        )
    )
    return True


def search_manuals(collection, query_embedding: list[float], top_k: int = 3) -> list[dict]:
    pipeline = [
        {
            "$vectorSearch": {
                "index": VECTOR_INDEX_NAME,
                "path": "embedding",
                "queryVector": query_embedding,
                "numCandidates": max(top_k * 10, 50),
                "limit": top_k,
            }
        },
        {"$project": {"_id": 0, "chunk_text": 1, "machine_type": 1, "error_codes": 1}},
    ]
    return list(collection.aggregate(pipeline))
