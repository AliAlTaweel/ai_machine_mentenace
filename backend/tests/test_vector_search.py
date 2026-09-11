from backend.rag.vector_search import VECTOR_INDEX_NAME, ensure_vector_index, search_manuals


class FakeManualsCollection:
    def __init__(self, results):
        self._results = results
        self.last_pipeline = None

    def aggregate(self, pipeline):
        self.last_pipeline = pipeline
        return iter(self._results)


class FakeSearchIndexCollection:
    """Mimics the subset of the Atlas Search index management API
    `ensure_vector_index` uses, so its create/skip logic can be tested
    without a real Atlas cluster.
    """

    def __init__(self, existing_index_names: list[str] | None = None):
        self._indexes = [{"name": name} for name in (existing_index_names or [])]
        self.created_models = []

    def list_search_indexes(self):
        return iter(self._indexes)

    def create_search_index(self, model):
        self.created_models.append(model)
        self._indexes.append({"name": model.document["name"]})


class NoSearchIndexSupportCollection:
    """Mimics mongomock: accessing `list_search_indexes` doesn't raise
    AttributeError, but calling it does (mongomock treats unknown
    attributes as nested-collection access, so the failure surfaces as a
    TypeError on call, not a missing attribute)."""

    def list_search_indexes(self):
        raise TypeError("'Collection' object is not callable")


def test_search_manuals_returns_results_from_aggregate():
    fake_docs = [
        {"chunk_text": "bearing wear procedure", "machine_type": "CNC-Mill-200", "error_codes": ["E101"]},
        {"chunk_text": "belt slippage procedure", "machine_type": "Conveyor-Belt-A7", "error_codes": ["B12"]},
    ]
    collection = FakeManualsCollection(fake_docs)

    results = search_manuals(collection, query_embedding=[0.1, 0.2, 0.3], top_k=2)

    assert results == fake_docs
    stage = collection.last_pipeline[0]["$vectorSearch"]
    assert stage["path"] == "embedding"
    assert stage["queryVector"] == [0.1, 0.2, 0.3]
    assert stage["limit"] == 2
    assert stage["index"] == "manuals_vector_index"


def test_search_manuals_returns_empty_list_when_no_matches():
    collection = FakeManualsCollection([])
    assert search_manuals(collection, query_embedding=[0.1], top_k=3) == []


def test_ensure_vector_index_creates_index_when_missing():
    collection = FakeSearchIndexCollection(existing_index_names=[])

    created = ensure_vector_index(collection, dimensions=384)

    assert created is True
    assert len(collection.created_models) == 1
    document = collection.created_models[0].document
    assert document["name"] == VECTOR_INDEX_NAME
    assert document["type"] == "vectorSearch"
    assert document["definition"]["fields"][0]["numDimensions"] == 384
    assert document["definition"]["fields"][0]["path"] == "embedding"


def test_ensure_vector_index_skips_when_already_present():
    collection = FakeSearchIndexCollection(existing_index_names=[VECTOR_INDEX_NAME])

    created = ensure_vector_index(collection)

    assert created is False
    assert collection.created_models == []


def test_ensure_vector_index_is_a_noop_for_unsupported_collections():
    collection = NoSearchIndexSupportCollection()

    created = ensure_vector_index(collection)

    assert created is False
