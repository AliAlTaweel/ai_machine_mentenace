import hashlib
import io

import mongomock
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from backend.api.app import create_app


def make_blank_pdf_bytes() -> bytes:
    """A structurally valid PDF with no extractable text — see
    backend/tests/test_api.py's identical helper for why PdfWriter can't
    embed real text for a positive-path test."""
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_manuals_collection():
    return mongomock.MongoClient()["machine_repair"]["manuals"]


def make_app(collection):
    return create_app(
        build_graph_fn=lambda *args, **kwargs: None,
        manuals_collection_factory=lambda: collection,
    )


def test_manuals_upload_returns_400_for_unreadable_pdf():
    client = TestClient(make_app(make_manuals_collection()))

    response = client.post(
        "/manuals/upload",
        data={"machine_type": "CNC-Mill-200", "error_codes": "E101"},
        files={"file": ("manual.pdf", b"not a real pdf", "application/pdf")},
    )

    assert response.status_code == 400
    assert "detail" in response.json()


def test_manuals_upload_returns_400_for_pdf_with_no_extractable_text():
    client = TestClient(make_app(make_manuals_collection()))

    response = client.post(
        "/manuals/upload",
        data={"machine_type": "CNC-Mill-200", "error_codes": "E101"},
        files={"file": ("manual.pdf", make_blank_pdf_bytes(), "application/pdf")},
    )

    assert response.status_code == 400
    assert "detail" in response.json()


def test_get_manuals_returns_previously_ingested_manuals():
    collection = make_manuals_collection()
    collection.insert_one(
        {
            "manual_id": "abc123def456-p0",
            "chunk_text": "hydraulic valve procedure",
            "embedding": [0.1, 0.2],
            "machine_type": "Hydraulic-Press-9",
            "error_codes": ["H33"],
            "content_hash": "abc123def456",
            "source_filename": "press-manual.pdf",
            "chunk_index": 0,
            "uploaded_at": "2026-09-11T00:00:00+00:00",
        }
    )
    client = TestClient(make_app(collection))

    response = client.get("/manuals")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["filename"] == "press-manual.pdf"
    assert body[0]["machine_type"] == "Hydraulic-Press-9"
    assert body[0]["error_codes"] == ["H33"]
    assert body[0]["chunk_count"] == 1


def test_get_manuals_returns_empty_list_when_nothing_uploaded():
    client = TestClient(make_app(make_manuals_collection()))

    response = client.get("/manuals")

    assert response.status_code == 200
    assert response.json() == []


def test_manuals_upload_returns_duplicate_status_for_already_ingested_content():
    collection = make_manuals_collection()
    pdf_bytes = b"same exact bytes uploaded twice"
    content_hash = hashlib.sha256(pdf_bytes).hexdigest()
    collection.insert_one(
        {
            "manual_id": f"{content_hash[:12]}-p0",
            "chunk_text": "existing chunk",
            "embedding": [0.1],
            "machine_type": "CNC-Mill-200",
            "error_codes": ["E101"],
            "content_hash": content_hash,
            "source_filename": "already-uploaded.pdf",
            "chunk_index": 0,
            "uploaded_at": "2026-09-11T00:00:00+00:00",
        }
    )
    client = TestClient(make_app(collection))

    response = client.post(
        "/manuals/upload",
        data={"machine_type": "CNC-Mill-200", "error_codes": "E101"},
        files={"file": ("re-upload.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "duplicate", "filename": "already-uploaded.pdf"}
