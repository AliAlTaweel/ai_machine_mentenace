# Manual Document Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user upload a real technical manual PDF, chunk/embed it per page, and insert it into the existing `manuals` collection so RAG lookup finds it immediately — with content-hash duplicate detection and a filename list sourced from MongoDB, independent of the chat WebSocket session.

**Architecture:** A new backend module (`manuals_ingest.py`) with two pure functions (`ingest_manual_pdf`, `list_uploaded_manuals`) reusing the existing `manuals` collection, `embed_text`, and `ensure_vector_index`; two new REST routes wired into the existing `create_app()` factory using its existing `manuals_collection_factory` seam; and a new frontend `ManualsPanel` component, opened from a new button on `SettingsBar`, using plain `fetch` (no WebSocket, no Zustand store dependency).

**Tech Stack:** Same as the existing backend/frontend packages — FastAPI, pymongo, pypdf, sentence-transformers on the backend; React/TypeScript/Vitest on the frontend.

**Spec:** docs/superpowers/specs/2026-09-11-manual-ingestion-design.md

## Global Constraints

- `manuals` collection reused as-is; new fields (`content_hash`, `source_filename`, `chunk_index`, `uploaded_at`) are only ever set on uploaded documents — seeded documents from `seed_manuals()` never get them, so existing `search_manuals()` behavior is unaffected — per spec's Data Model section.
- `manual_id` for uploaded chunks is `f"{content_hash[:12]}-p{chunk_index}"` — per spec's Data Model section.
- Duplicate detection is by content hash (SHA-256 of the raw PDF bytes), not filename — per spec's Goals section.
- A duplicate upload returns `{"status": "duplicate", "filename": <existing>}` with **no re-embedding call** — per spec's backend section.
- Empty-text PDF returns a `400` with the same `{"detail": ...}` shape as the existing `/upload` endpoint — per spec's Error Handling section.
- `GET /manuals` excludes seeded manuals (those without `content_hash`) — per spec's Data Model section.
- No WebSocket/session dependency anywhere in this feature — per spec's Architecture section.
- `machine_type`/`error_codes` metadata is captured via a form, not LLM-inferred — per spec's Non-Goals.

---

## File Structure

```
backend/
  backend/
    rag/
      manuals_ingest.py         # NEW: compute_content_hash, ingest_manual_pdf, list_uploaded_manuals
    api/
      app.py                    # MODIFIED: add POST /manuals/upload, GET /manuals
  tests/
    test_manuals_ingest.py      # NEW
    test_manuals_api.py         # NEW

frontend/
  src/
    components/
      ManualsPanel/
        ManualsPanel.tsx         # NEW
      SettingsBar.tsx            # MODIFIED: add "Manage Manuals" button, onManageManuals prop
    App.tsx                      # MODIFIED: showManuals state, renders ManualsPanel
  tests/
    ManualsPanel.test.tsx        # NEW
    App.test.tsx                 # MODIFIED: add open/close manuals panel test
```

---

## Task 1: Backend manuals ingestion module

**Files:**
- Create: `backend/backend/rag/manuals_ingest.py`
- Test: `backend/tests/test_manuals_ingest.py`

**Interfaces:**
- Consumes: `embed_text` from `backend.rag.embeddings` (`backend/backend/rag/embeddings.py`), `ensure_vector_index` from `backend.rag.vector_search` (`backend/backend/rag/vector_search.py`, already exists from a prior fix).
- Produces:
  - `compute_content_hash(pdf_bytes: bytes) -> str`
  - `ingest_manual_pdf(collection, filename: str, pdf_bytes: bytes, machine_type: str, error_codes: list[str], embed_fn=embed_text, reader_fn=PdfReader) -> dict` — returns `{"status": "ingested", "chunks": int}` | `{"status": "duplicate", "filename": str}` | `{"status": "error", "message": str}`. `reader_fn` is injectable (defaults to `pypdf.PdfReader`) so tests can supply fake pages without needing pypdf to write real extractable text (the existing test suite already established that pypdf's `PdfWriter` can't embed arbitrary text — see `backend/tests/test_api.py`'s `make_blank_pdf_bytes` docstring).
  - `list_uploaded_manuals(collection) -> list[dict]` — each row: `{"filename": str, "machine_type": str, "error_codes": list[str], "chunk_count": int, "uploaded_at": datetime}`, sorted newest first.
  - Consumed by Task 2's API routes.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_manuals_ingest.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_manuals_ingest.py -v`
Expected: FAIL with "No module named 'backend.rag.manuals_ingest'".

- [ ] **Step 3: Implement the module**

Create `backend/backend/rag/manuals_ingest.py`:

```python
import hashlib
import io
from datetime import datetime, timezone

from pypdf import PdfReader

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
) -> dict:
    content_hash = compute_content_hash(pdf_bytes)

    existing = collection.find_one({"content_hash": content_hash})
    if existing is not None:
        return {"status": "duplicate", "filename": existing["source_filename"]}

    reader = reader_fn(io.BytesIO(pdf_bytes))
    pages_with_text = []
    for index, page in enumerate(reader.pages):
        text = (page.extract_text() or "").strip()
        if text:
            pages_with_text.append((index, text))

    if not pages_with_text:
        return {
            "status": "error",
            "message": (
                "This PDF has no extractable text (scanned or image-only) — "
                "please upload a text-extractable manual instead."
            ),
        }

    uploaded_at = datetime.now(timezone.utc)
    for index, text in pages_with_text:
        manual_id = f"{content_hash[:12]}-p{index}"
        collection.update_one(
            {"manual_id": manual_id},
            {
                "$set": {
                    "manual_id": manual_id,
                    "chunk_text": text,
                    "embedding": embed_fn(text),
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

    ensure_vector_index(collection)

    return {"status": "ingested", "chunks": len(pages_with_text)}


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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_manuals_ingest.py -v`
Expected: PASS — all 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/backend/rag/manuals_ingest.py backend/tests/test_manuals_ingest.py
git commit -m "feat(backend): add manuals_ingest module for PDF-to-vector-DB ingestion"
```

---

## Task 2: Backend API routes

**Files:**
- Modify: `backend/backend/api/app.py`
- Create: `backend/tests/test_manuals_api.py`

**Interfaces:**
- Consumes: `ingest_manual_pdf`, `list_uploaded_manuals` from Task 1 (`backend.rag.manuals_ingest`); the existing `manuals_collection_factory` parameter already on `create_app()`.
- Produces: `POST /manuals/upload` (multipart: `file`, `machine_type`, `error_codes`) and `GET /manuals` routes — consumed by Task 3's frontend `ManualsPanel`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_manuals_api.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_manuals_api.py -v`
Expected: FAIL with 404s (routes don't exist yet).

- [ ] **Step 3: Add the routes**

In `backend/backend/api/app.py`, add the import near the top (alongside the existing `backend.db`/`backend.graph.build` imports):

```python
from backend.rag.manuals_ingest import ingest_manual_pdf, list_uploaded_manuals
```

Add `Form` to the existing `fastapi` import line:

```python
from fastapi import FastAPI, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
```

Inside `create_app()`, add the two new routes directly after the existing `/upload` route (before the `@app.websocket("/ws/{thread_id}")` line):

```python
    @app.post("/manuals/upload")
    async def upload_manual(
        file: UploadFile,
        machine_type: str = Form(...),
        error_codes: str = Form(...),
    ):
        contents = await file.read()
        parsed_error_codes = [code.strip() for code in error_codes.split(",") if code.strip()]
        result = ingest_manual_pdf(
            manuals_collection_factory(),
            filename=file.filename,
            pdf_bytes=contents,
            machine_type=machine_type,
            error_codes=parsed_error_codes,
        )
        if result["status"] == "error":
            logger.warning("Manual upload rejected: %s", result["message"])
            raise HTTPException(status_code=400, detail=result["message"])
        if result["status"] == "duplicate":
            logger.info("Manual upload duplicate: filename=%s", result["filename"])
        else:
            logger.info("Manual upload ingested: chunks=%d", result["chunks"])
        return result

    @app.get("/manuals")
    async def get_manuals():
        return list_uploaded_manuals(manuals_collection_factory())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_manuals_api.py -v`
Expected: PASS — all 4 tests pass.

- [ ] **Step 5: Run the full backend suite to check for regressions**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS — all tests pass (the existing suite plus the new ones).

- [ ] **Step 6: Commit**

```bash
git add backend/backend/api/app.py backend/tests/test_manuals_api.py
git commit -m "feat(backend): add POST /manuals/upload and GET /manuals routes"
```

---

## Task 3: Frontend `ManualsPanel` component

**Files:**
- Create: `frontend/src/components/ManualsPanel/ManualsPanel.tsx`
- Test: `frontend/tests/ManualsPanel.test.tsx`

**Interfaces:**
- Consumes: nothing from earlier tasks' frontend code — a self-contained component using `fetch` directly against `/manuals` and `/manuals/upload` (proxied to the backend by Vite's existing dev-server config, same as `PdfUpload.tsx`'s `/upload` call).
- Produces: `ManualsPanel({ onClose }: { onClose: () => void })` — consumed by `App` in Task 4.

- [ ] **Step 1: Write the failing tests**

Create `frontend/tests/ManualsPanel.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ManualsPanel } from '../src/components/ManualsPanel/ManualsPanel';

function makePdfFile() {
  return new File(['%PDF-1.4 fake'], 'press-manual.pdf', { type: 'application/pdf' });
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ManualsPanel', () => {
  it('fetches and renders the list of already-uploaded manuals on mount', async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => [
        {
          filename: 'press-manual.pdf',
          machine_type: 'Hydraulic-Press-9',
          error_codes: ['H33'],
          chunk_count: 3,
          uploaded_at: '2026-09-11T00:00:00Z',
        },
      ],
    });

    render(<ManualsPanel onClose={vi.fn()} />);

    expect(await screen.findByText(/press-manual\.pdf/)).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith('/manuals');
  });

  it('submits the upload form with the correct multipart fields and refreshes the list', async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock
      .mockResolvedValueOnce({ ok: true, json: async () => [] })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ status: 'ingested', chunks: 2 }) })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [
          {
            filename: 'press-manual.pdf',
            machine_type: 'Hydraulic-Press-9',
            error_codes: ['H33'],
            chunk_count: 2,
            uploaded_at: '2026-09-11T00:00:00Z',
          },
        ],
      });

    render(<ManualsPanel onClose={vi.fn()} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    await userEvent.upload(screen.getByLabelText('Manual PDF file'), makePdfFile());
    await userEvent.type(screen.getByPlaceholderText('Machine type'), 'Hydraulic-Press-9');
    await userEvent.type(screen.getByPlaceholderText('Error codes (comma-separated)'), 'H33');
    await userEvent.click(screen.getByRole('button', { name: 'Upload manual' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const uploadCall = fetchMock.mock.calls[1];
    expect(uploadCall[0]).toBe('/manuals/upload');
    const sentFormData = uploadCall[1].body as FormData;
    expect(sentFormData.get('machine_type')).toBe('Hydraulic-Press-9');
    expect(sentFormData.get('error_codes')).toBe('H33');
    expect(sentFormData.get('file')).toBeInstanceOf(File);

    expect(await screen.findByText(/Ingested 2 chunk/)).toBeInTheDocument();
  });

  it('shows the duplicate message without treating it as an error', async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock
      .mockResolvedValueOnce({ ok: true, json: async () => [] })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'duplicate', filename: 'press-manual.pdf' }),
      });

    render(<ManualsPanel onClose={vi.fn()} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    await userEvent.upload(screen.getByLabelText('Manual PDF file'), makePdfFile());
    await userEvent.type(screen.getByPlaceholderText('Machine type'), 'Hydraulic-Press-9');
    await userEvent.type(screen.getByPlaceholderText('Error codes (comma-separated)'), 'H33');
    await userEvent.click(screen.getByRole('button', { name: 'Upload manual' }));

    expect(
      await screen.findByText('Already in the knowledge base as press-manual.pdf')
    ).toBeInTheDocument();
  });

  it('shows the backend detail message on a 400 response', async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock
      .mockResolvedValueOnce({ ok: true, json: async () => [] })
      .mockResolvedValueOnce({
        ok: false,
        json: async () => ({ detail: 'This PDF has no extractable text' }),
      });

    render(<ManualsPanel onClose={vi.fn()} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    await userEvent.upload(screen.getByLabelText('Manual PDF file'), makePdfFile());
    await userEvent.type(screen.getByPlaceholderText('Machine type'), 'Hydraulic-Press-9');
    await userEvent.type(screen.getByPlaceholderText('Error codes (comma-separated)'), 'H33');
    await userEvent.click(screen.getByRole('button', { name: 'Upload manual' }));

    expect(await screen.findByText('This PDF has no extractable text')).toBeInTheDocument();
  });

  it('calls onClose when the close button is clicked', async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue({ ok: true, json: async () => [] });
    const onClose = vi.fn();

    render(<ManualsPanel onClose={onClose} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    await userEvent.click(screen.getByLabelText('Close'));
    expect(onClose).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test -- ManualsPanel`
Expected: FAIL with "Cannot find module '../src/components/ManualsPanel/ManualsPanel'".

- [ ] **Step 3: Implement `ManualsPanel`**

Create `frontend/src/components/ManualsPanel/ManualsPanel.tsx`:

```tsx
import { useEffect, useState, type FormEvent } from 'react';

interface ManualEntry {
  filename: string;
  machine_type: string;
  error_codes: string[];
  chunk_count: number;
  uploaded_at: string;
}

export interface ManualsPanelProps {
  onClose: () => void;
}

export function ManualsPanel({ onClose }: ManualsPanelProps) {
  const [manuals, setManuals] = useState<ManualEntry[]>([]);
  const [machineType, setMachineType] = useState('');
  const [errorCodes, setErrorCodes] = useState('');
  const [status, setStatus] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const fetchManuals = async () => {
    const response = await fetch('/manuals');
    const data = await response.json();
    setManuals(data);
  };

  useEffect(() => {
    fetchManuals();
  }, []);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const fileInput = form.elements.namedItem('file') as HTMLInputElement;
    const file = fileInput.files?.[0];
    if (!file) return;

    setUploading(true);
    setStatus(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('machine_type', machineType);
      formData.append('error_codes', errorCodes);
      const response = await fetch('/manuals/upload', { method: 'POST', body: formData });
      const body = await response.json();
      if (!response.ok) {
        setStatus(body.detail ?? 'Could not process this manual.');
      } else if (body.status === 'duplicate') {
        setStatus(`Already in the knowledge base as ${body.filename}`);
      } else {
        setStatus(`Ingested ${body.chunks} chunk(s).`);
        await fetchManuals();
        form.reset();
        setMachineType('');
        setErrorCodes('');
      }
    } catch {
      setStatus('Could not reach the server to upload this manual.');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded bg-white p-4 shadow-lg">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Manage Manuals</h2>
          <button type="button" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        <ul
          data-testid="manuals-list"
          className="mt-3 max-h-40 space-y-1 overflow-y-auto text-sm"
        >
          {manuals.map((manual) => (
            <li key={manual.filename}>
              {manual.filename} — {manual.machine_type} ({manual.error_codes.join(', ')},{' '}
              {manual.chunk_count} chunks)
            </li>
          ))}
        </ul>

        <form onSubmit={handleSubmit} className="mt-4 space-y-2">
          <input
            type="file"
            name="file"
            accept="application/pdf"
            aria-label="Manual PDF file"
            required
          />
          <input
            type="text"
            placeholder="Machine type"
            value={machineType}
            onChange={(event) => setMachineType(event.target.value)}
            required
            className="w-full rounded border px-2 py-1 text-sm"
          />
          <input
            type="text"
            placeholder="Error codes (comma-separated)"
            value={errorCodes}
            onChange={(event) => setErrorCodes(event.target.value)}
            required
            className="w-full rounded border px-2 py-1 text-sm"
          />
          <button
            type="submit"
            disabled={uploading}
            className="rounded bg-blue-600 px-3 py-1 text-sm text-white disabled:opacity-50"
          >
            {uploading ? 'Uploading…' : 'Upload manual'}
          </button>
        </form>

        {status && (
          <p data-testid="manuals-status" className="mt-2 text-xs text-gray-600">
            {status}
          </p>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm test -- ManualsPanel`
Expected: PASS — all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ManualsPanel frontend/tests/ManualsPanel.test.tsx
git commit -m "feat(frontend): add ManualsPanel for uploading and listing technical manuals"
```

---

## Task 4: Wire `ManualsPanel` into `SettingsBar` and `App`

**Files:**
- Modify: `frontend/src/components/SettingsBar.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/tests/App.test.tsx`

**Interfaces:**
- Consumes: `ManualsPanel` from Task 3.
- Produces: `SettingsBar({ onManageManuals }: { onManageManuals: () => void })` (signature change — previously took no props) — this is the last task, nothing downstream consumes its output.

- [ ] **Step 1: Write the failing test**

Add to `frontend/tests/App.test.tsx`, inside the existing `describe('App', ...)` block (after the last existing `it(...)`):

```tsx
  it('opens the manuals panel from Settings and closes it', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => [] }));
    render(<App />);

    expect(screen.queryByTestId('manuals-list')).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Manage Manuals' }));
    expect(await screen.findByTestId('manuals-list')).toBeInTheDocument();

    await userEvent.click(screen.getByLabelText('Close'));
    expect(screen.queryByTestId('manuals-list')).not.toBeInTheDocument();
  });
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- App`
Expected: FAIL — no "Manage Manuals" button exists yet.

- [ ] **Step 3: Update `SettingsBar`**

Replace `frontend/src/components/SettingsBar.tsx`:

```tsx
import { useSessionStore } from '../store/sessionStore';

export interface SettingsBarProps {
  onManageManuals: () => void;
}

export function SettingsBar({ onManageManuals }: SettingsBarProps) {
  const llmBackend = useSessionStore((s) => s.llmBackend);
  const setLlmBackend = useSessionStore((s) => s.setLlmBackend);
  const connectionStatus = useSessionStore((s) => s.connectionStatus);
  const locked = connectionStatus !== 'connecting';

  return (
    <div className="flex items-center gap-3 border-b p-3 text-sm">
      <span className="font-medium">LLM backend:</span>
      <label className="flex items-center gap-1">
        <input
          type="radio"
          name="llmBackend"
          checked={llmBackend === 'local'}
          disabled={locked}
          onChange={() => setLlmBackend('local')}
        />
        Local Gemma
      </label>
      <label className="flex items-center gap-1">
        <input
          type="radio"
          name="llmBackend"
          checked={llmBackend === 'cloud'}
          disabled={locked}
          onChange={() => setLlmBackend('cloud')}
        />
        Claude API
      </label>
      <button
        type="button"
        onClick={onManageManuals}
        className="ml-auto rounded border px-3 py-1 text-xs"
      >
        Manage Manuals
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Update `App`**

Replace `frontend/src/App.tsx`:

```tsx
import { useMemo, useState } from 'react';
import { useSessionStore } from './store/sessionStore';
import { useSessionSocket } from './hooks/useSessionSocket';
import { SettingsBar } from './components/SettingsBar';
import { ChatPanel } from './components/ChatPanel/ChatPanel';
import { GraphPanel } from './components/GraphPanel/GraphPanel';
import { ManualsPanel } from './components/ManualsPanel/ManualsPanel';

function ActiveSession({
  threadId,
  llmBackend,
}: {
  threadId: string;
  llmBackend: 'local' | 'cloud';
}) {
  const { sendChat, sendApproval } = useSessionSocket(threadId, llmBackend);
  return (
    <div className="grid flex-1 grid-cols-2 overflow-hidden">
      <ChatPanel onSend={sendChat} onDecide={sendApproval} />
      <GraphPanel />
    </div>
  );
}

export default function App() {
  const llmBackend = useSessionStore((s) => s.llmBackend);
  const threadId = useMemo(() => crypto.randomUUID(), []);
  const [started, setStarted] = useState(false);
  const [showManuals, setShowManuals] = useState(false);

  return (
    <div className="flex h-screen flex-col">
      <SettingsBar onManageManuals={() => setShowManuals(true)} />
      {started ? (
        <ActiveSession threadId={threadId} llmBackend={llmBackend} />
      ) : (
        <div className="flex flex-1 items-center justify-center">
          <button
            type="button"
            onClick={() => setStarted(true)}
            className="rounded bg-blue-600 px-6 py-3 text-white"
          >
            Start Session
          </button>
        </div>
      )}
      {showManuals && <ManualsPanel onClose={() => setShowManuals(false)} />}
    </div>
  );
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npm test`
Expected: PASS — full suite passes, including the new `App` test.

- [ ] **Step 6: Run `tsc` to check for type errors**

Run: `cd frontend && npx tsc --noEmit`
Expected: no output (clean).

- [ ] **Step 7: Manually verify against the real backend (optional but recommended)**

With both `backend` and `frontend` dev servers running (see README), click "Manage Manuals", upload one of the sample incident-report PDFs from `examples/` (or any text-extractable PDF) with a `machine_type` and `error_codes`, confirm it appears in the list, then try uploading the exact same file again and confirm the "Already in the knowledge base" message appears instead of a duplicate list entry.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/SettingsBar.tsx frontend/src/App.tsx frontend/tests/App.test.tsx
git commit -m "feat(frontend): wire ManualsPanel into SettingsBar and App"
```
