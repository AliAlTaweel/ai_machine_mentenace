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
                    },
                    {
                        "type": "filter",
                        "path": "machine_type",
                    },
                ]
            },
            name=VECTOR_INDEX_NAME,
            type="vectorSearch",
        )
    )
    return True


def _build_pipeline(query_embedding: list[float], top_k: int, machine_type: str | None) -> list[dict]:
    vector_search_stage = {
        "index": VECTOR_INDEX_NAME,
        "path": "embedding",
        "queryVector": query_embedding,
        "numCandidates": max(top_k * 10, 50),
        "limit": top_k,
    }
    if machine_type:
        vector_search_stage["filter"] = {"machine_type": machine_type}
    return [
        {"$vectorSearch": vector_search_stage},
        {"$project": {"_id": 0, "chunk_text": 1, "machine_type": 1, "error_codes": 1}},
    ]


def search_manuals(
    collection,
    query_embedding: list[float],
    top_k: int = 3,
    machine_type: str | None = None,
) -> list[dict]:
    """Search manual chunks by vector similarity, optionally narrowed to a
    machine_type.

    machine_id (chat-extracted) and machine_type (upload-provided) are both
    free text with no shared vocabulary, so the filter is best-effort: if it
    matches nothing, fall back to an unfiltered search rather than let a
    string mismatch surface as "no procedure found". The filtered attempt can
    also raise instead of returning empty — e.g. Atlas rejects the `filter`
    clause with a PlanExecutor error if the index predates the `machine_type`
    filter field (see `ensure_vector_index`) — so that's caught too rather
    than only handling the empty-result case.
    """
    if machine_type:
        try:
            filtered = list(collection.aggregate(_build_pipeline(query_embedding, top_k, machine_type)))
        except Exception:
            filtered = []
        if filtered:
            return filtered
    return list(collection.aggregate(_build_pipeline(query_embedding, top_k, None)))
