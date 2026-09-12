import hashlib
import io
from datetime import datetime, timezone

from pypdf import PdfReader

from backend.rag.chunking import chunk_text
from backend.rag.embeddings import embed_text
from backend.rag.vector_search import ensure_vector_index


def compute_content_hash(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()


def ingest_manual_pdf(
    collection,
    filename: str,
    pdf_bytes: bytes,
    machine_type: str,
    error_codes: list[str],
    embed_fn=embed_text,
    reader_fn=PdfReader,
    chunk_fn=chunk_text,
) -> dict:
    content_hash = compute_content_hash(pdf_bytes)

    existing = collection.find_one({"content_hash": content_hash})
    if existing is not None:
        return {"status": "duplicate", "filename": existing["source_filename"]}

    try:
        reader = reader_fn(io.BytesIO(pdf_bytes))
        pages_with_text = []
        for index, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()
            if text:
                pages_with_text.append((index, text))
    except Exception as exc:
        return {
            "status": "error",
            "message": (
                "Could not read this PDF — please upload a text-extractable "
                f"manual instead. ({exc})"
            ),
        }

    if not pages_with_text:
        return {
            "status": "error",
            "message": (
                "This PDF has no extractable text (scanned or image-only) — "
                "please upload a text-extractable manual instead."
            ),
        }

    # Join pages with a paragraph break so chunking can span a page boundary
    # instead of truncating a procedure that continues onto the next page.
    full_text = "\n\n".join(text for _, text in pages_with_text)
    chunks = chunk_fn(full_text)

    uploaded_at = datetime.now(timezone.utc)
    try:
        for index, chunk in enumerate(chunks):
            manual_id = f"{content_hash[:12]}-c{index}"
            collection.update_one(
                {"manual_id": manual_id},
                {
                    "$set": {
                        "manual_id": manual_id,
                        "chunk_text": chunk,
                        "embedding": embed_fn(chunk),
                        "machine_type": machine_type,
                        "error_codes": error_codes,
                        "content_hash": content_hash,
                        "source_filename": filename,
                        "chunk_index": index,
                        "uploaded_at": uploaded_at,
                    }
                },
                upsert=True,
            )
    except Exception:
        # Don't leave a partial set of chunks tagged with this content_hash —
        # that would make every future upload of this exact file return
        # "duplicate" against incomplete/corrupt data, forever. Clean up and
        # let the caller retry from a clean slate.
        collection.delete_many({"content_hash": content_hash})
        raise

    ensure_vector_index(collection)

    return {"status": "ingested", "chunks": len(chunks)}


def list_uploaded_manuals(collection) -> list[dict]:
    pipeline = [
        {"$match": {"content_hash": {"$exists": True}}},
        {
            "$group": {
                "_id": "$content_hash",
                "filename": {"$first": "$source_filename"},
                "machine_type": {"$first": "$machine_type"},
                "error_codes": {"$first": "$error_codes"},
                "chunk_count": {"$sum": 1},
                "uploaded_at": {"$first": "$uploaded_at"},
            }
        },
        {"$sort": {"uploaded_at": -1}},
        {
            "$project": {
                "_id": 0,
                "filename": 1,
                "machine_type": 1,
                "error_codes": 1,
                "chunk_count": 1,
                "uploaded_at": 1,
            }
        },
    ]
    return list(collection.aggregate(pipeline))
