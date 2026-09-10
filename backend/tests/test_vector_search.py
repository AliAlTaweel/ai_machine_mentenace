from backend.rag.vector_search import search_manuals


class FakeManualsCollection:
    def __init__(self, results):
        self._results = results
        self.last_pipeline = None

    def aggregate(self, pipeline):
        self.last_pipeline = pipeline
        return iter(self._results)


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
