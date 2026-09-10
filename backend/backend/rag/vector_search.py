VECTOR_INDEX_NAME = "manuals_vector_index"


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
