import mongomock

from backend.rag.manuals_ingest import (
    compute_content_hash,
    ingest_manual_pdf,
    list_uploaded_manuals,
)


class FakePage:
    def __init__(self, text: str):
        self._text = text

    def extract_text(self):
        return self._text


class FakeReader:
    def __init__(self, pages: list[str]):
        self.pages = [FakePage(text) for text in pages]


def fake_embed(text: str) -> list[float]:
    return [float(len(text))]


def make_collection():
    return mongomock.MongoClient()["machine_repair"]["manuals"]


def test_compute_content_hash_is_deterministic_and_content_sensitive():
    assert compute_content_hash(b"hello") == compute_content_hash(b"hello")
    assert compute_content_hash(b"hello") != compute_content_hash(b"world")


def test_ingest_manual_pdf_creates_one_chunk_per_page():
    collection = make_collection()

    result = ingest_manual_pdf(
        collection,
        filename="press-manual.pdf",
        pdf_bytes=b"fake pdf bytes",
        machine_type="Hydraulic-Press-9",
        error_codes=["H33"],
        embed_fn=fake_embed,
        reader_fn=lambda _: FakeReader(["page one text", "page two text"]),
    )

    assert result == {"status": "ingested", "chunks": 2}
    content_hash = compute_content_hash(b"fake pdf bytes")
    docs = list(collection.find({"content_hash": content_hash}))
    assert len(docs) == 2
    assert {doc["chunk_index"] for doc in docs} == {0, 1}
    assert all(doc["source_filename"] == "press-manual.pdf" for doc in docs)
    assert all(doc["machine_type"] == "Hydraulic-Press-9" for doc in docs)
    assert all(doc["error_codes"] == ["H33"] for doc in docs)
    assert all(doc["manual_id"] == f"{content_hash[:12]}-p{doc['chunk_index']}" for doc in docs)


def test_ingest_manual_pdf_skips_pages_with_no_extractable_text():
    collection = make_collection()

    result = ingest_manual_pdf(
        collection,
        filename="mixed.pdf",
        pdf_bytes=b"mixed content",
        machine_type="CNC-Mill-200",
        error_codes=["E101"],
        embed_fn=fake_embed,
        reader_fn=lambda _: FakeReader(["real text", "", "   "]),
    )

    assert result == {"status": "ingested", "chunks": 1}


def test_ingest_manual_pdf_returns_error_when_no_page_has_text():
    collection = make_collection()

    result = ingest_manual_pdf(
        collection,
        filename="scanned.pdf",
        pdf_bytes=b"scanned content",
        machine_type="CNC-Mill-200",
        error_codes=["E101"],
        embed_fn=fake_embed,
        reader_fn=lambda _: FakeReader(["", ""]),
    )

    assert result["status"] == "error"
    assert collection.count_documents({}) == 0


def test_ingest_manual_pdf_detects_duplicate_by_content_hash_without_reembedding():
    collection = make_collection()
    embed_calls = []

    def counting_embed(text: str) -> list[float]:
        embed_calls.append(text)
        return fake_embed(text)

    ingest_manual_pdf(
        collection,
        filename="first-upload.pdf",
        pdf_bytes=b"same bytes",
        machine_type="CNC-Mill-200",
        error_codes=["E101"],
        embed_fn=counting_embed,
        reader_fn=lambda _: FakeReader(["page text"]),
    )
    calls_after_first_upload = len(embed_calls)

    result = ingest_manual_pdf(
        collection,
        filename="second-upload-same-file.pdf",
        pdf_bytes=b"same bytes",
        machine_type="CNC-Mill-200",
        error_codes=["E101"],
        embed_fn=counting_embed,
        reader_fn=lambda _: FakeReader(["page text"]),
    )

    assert result == {"status": "duplicate", "filename": "first-upload.pdf"}
    assert len(embed_calls) == calls_after_first_upload
    assert collection.count_documents({}) == 1


def test_list_uploaded_manuals_returns_one_row_per_manual_newest_first():
    collection = make_collection()
    ingest_manual_pdf(
        collection,
        "older.pdf",
        b"older bytes",
        "CNC-Mill-200",
        ["E101"],
        embed_fn=fake_embed,
        reader_fn=lambda _: FakeReader(["p1", "p2"]),
    )
    ingest_manual_pdf(
        collection,
        "newer.pdf",
        b"newer bytes",
        "Hydraulic-Press-9",
        ["H33"],
        embed_fn=fake_embed,
        reader_fn=lambda _: FakeReader(["p1"]),
    )

    rows = list_uploaded_manuals(collection)

    assert [row["filename"] for row in rows] == ["newer.pdf", "older.pdf"]
    assert rows[0]["chunk_count"] == 1
    assert rows[1]["chunk_count"] == 2


def test_list_uploaded_manuals_excludes_seeded_manuals_without_content_hash():
    collection = make_collection()
    collection.insert_one(
        {
            "manual_id": "SEEDED-1",
            "chunk_text": "seeded text",
            "embedding": [0.1],
            "machine_type": "CNC-Mill-200",
            "error_codes": ["E101"],
        }
    )

    assert list_uploaded_manuals(collection) == []
