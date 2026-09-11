# Manual Document Ingestion — Design

## Purpose

Let a user upload a **real technical manual** PDF so it becomes part of the
searchable `manuals` knowledge base RAG lookup queries against — distinct
from the existing chat's PDF upload, which feeds a *problem description*
(an incident report) into the `Extract` node and is never stored. This
closes the gap where the only way to add repair procedures to the
knowledge base was the one-time `seed_manuals()` script.

**Spec:** builds on docs/superpowers/specs/2026-09-10-industrial-maintenance-agent-design.md
(parent design) and docs/superpowers/specs/2026-09-11-frontend-phase3-design.md
(frontend it extends).

## Goals

- Upload a manual PDF + its `machine_type`/`error_codes` metadata, and have
  it embedded and inserted into the `manuals` collection so RAG lookup
  finds it on the very next query — no separate reindex/restart step.
- Show which manuals have already been uploaded (filename list), sourced
  from MongoDB, not client-side state — works across sessions/browsers.
- Detect duplicate uploads by file content (not filename) and skip
  re-ingesting rather than erroring or creating redundant chunks.
- Keep this fully independent of the chat WebSocket session — usable
  before or after clicking Start Session.

## Non-Goals

- OCR for scanned/image-only manual PDFs — same constraint as the existing
  incident-report upload; text-extractable PDFs only.
- Editing or deleting an already-ingested manual — out of scope for this
  demo; re-uploading a changed version of the same file would need a new
  content hash (a different file) rather than an update path.
- Automatic machine_type/error_codes extraction via LLM — a small form is
  simpler and more reliable for a demo feature (per brainstorming decision);
  can be revisited later.
- Chunking strategies more sophisticated than one chunk per PDF page (e.g.
  semantic/overlapping chunking) — page-level chunking matches the
  existing seed data's grain closely enough and keeps this change small.

## Architecture

```
Frontend                                    Backend
┌─────────────────┐                        ┌──────────────────────────┐
│ SettingsBar      │  click "Manage         │ POST /manuals/upload      │
│  "Manage Manuals"│  Manuals"              │  -> ingest_manual_pdf()    │
│        │          │ ──────────────────►   │      - hash check (dupe?)  │
│        ▼          │                        │      - per-page extract    │
│ ManualsPanel       │  GET /manuals          │      - embed + upsert      │
│  - upload form      │ ◄──────────────────  │      - ensure_vector_index │
│  - filename list      │  list of uploaded    │                            │
└─────────────────┘  manuals               │ GET /manuals               │
                                             │  -> list_uploaded_manuals() │
                                             └──────────────────────────┘
                                                        │
                                                        ▼
                                             MongoDB `manuals` collection
                                             (existing collection + vector
                                              index; new fields: content_hash,
                                              source_filename, chunk_index,
                                              uploaded_at)
```

No WebSocket involvement — this is REST-only, independent of `thread_id`
and the chat session lifecycle.

## Data Model Changes

`manuals` collection gains three optional fields, present only on
user-uploaded documents (seeded documents from `seed_manuals()` never set
them, so existing data and existing `search_manuals()` queries are
unaffected):

| Field | Type | Notes |
|---|---|---|
| `content_hash` | `str` | SHA-256 hex digest of the raw uploaded PDF bytes; shared across every chunk from the same file |
| `source_filename` | `str` | Original uploaded filename, for display in the "already uploaded" list |
| `chunk_index` | `int` | Page number within the source PDF (0-based) |
| `uploaded_at` | `datetime` | UTC timestamp of ingestion |

`manual_id` for uploaded chunks is generated as `f"{content_hash[:12]}-p{chunk_index}"`
— deterministic and collision-resistant without needing a separate ID
scheme from the existing seeded `manual_id` values (e.g. `CNC-MILL-200-E101`).

## Backend

**New module `backend/backend/rag/manuals_ingest.py`:**

- `compute_content_hash(pdf_bytes: bytes) -> str` — `hashlib.sha256(pdf_bytes).hexdigest()`.
- `ingest_manual_pdf(collection, filename: str, pdf_bytes: bytes, machine_type: str, error_codes: list[str], embed_fn=embed_text) -> dict`:
  1. Compute the content hash.
  2. Query `collection.find_one({"content_hash": hash})` — if found, return
     `{"status": "duplicate", "filename": <existing source_filename>}`
     without touching the collection or calling `embed_fn` (no wasted
     embedding work on a file already ingested).
  3. Otherwise, read the PDF via `pypdf.PdfReader` (same library already
     used by the existing `/upload` endpoint), extract text per page,
     skip pages with no extractable text, and for each remaining page
     `upsert` a `manuals` document with `manual_id`, `chunk_text` (the
     page text), `embedding` (via `embed_fn`), `machine_type`,
     `error_codes`, `content_hash`, `source_filename`, `chunk_index`,
     `uploaded_at`.
  4. Call `ensure_vector_index(collection)` (already idempotent, added in
     the earlier vector-search-index fix) as a safety net for a
     from-scratch setup that skipped the manuals-seed step.
  5. If no page had extractable text, return
     `{"status": "error", "message": "This PDF has no extractable text..."}`
     — the route layer turns this into the same 400 pattern as the
     existing upload endpoint, not a differently-shaped error.
  6. On success, return `{"status": "ingested", "chunks": N}`.
- `list_uploaded_manuals(collection) -> list[dict]`: aggregation pipeline
  grouping on `content_hash` (filtered to documents where `content_hash`
  exists), returning one row per uploaded manual:
  `{"filename": ..., "machine_type": ..., "error_codes": ..., "chunk_count": ..., "uploaded_at": ...}`,
  sorted by `uploaded_at` descending (newest first).

**New routes in `api/app.py`:**

- `POST /manuals/upload` — multipart form fields `file`, `machine_type`,
  `error_codes` (comma-separated string, split/trimmed into a list
  server-side). Reads the file, calls `ingest_manual_pdf`, translates its
  `status` into an HTTP response: `ingested`/`duplicate` → `200` with the
  dict as JSON; `error` → `400` with `{"detail": message}` (matching the
  existing `/upload` endpoint's error shape exactly, so the frontend's
  existing PDF-upload error handling pattern can be reused as-is).
- `GET /manuals` — calls `list_uploaded_manuals`, returns the list as JSON.

## Frontend

- **`SettingsBar`**: gains a "Manage Manuals" button, independent of the
  session-lock logic (manuals management isn't tied to `connectionStatus`
  — it's always available). Toggles a boolean in `App` that conditionally
  renders `ManualsPanel`.
- **`ManualsPanel`** (new, `frontend/src/components/ManualsPanel/ManualsPanel.tsx`):
  a self-contained panel (modal or inline, implementation's call) that:
  - On mount, `fetch('GET /manuals')` and renders the filename list (with
    `machine_type`, `error_codes`, `chunk_count` per row).
  - Renders an upload form: file input (`accept="application/pdf"`),
    `machine_type` text input, `error_codes` text input (comma-separated,
    matching the backend's expected format).
  - On submit, `POST`s to `/manuals/upload`; on `status: "ingested"` shows
    a success message and re-fetches the list; on `status: "duplicate"`
    shows "Already in the knowledge base as `<filename>`" (not an error
    state — the upload attempt is not a failure, just a no-op); on a 400
    response, shows the `detail` message as an inline error — same pattern
    `PdfUpload.tsx` already uses for its error case.
  - No dependency on `useSessionStore` or the WebSocket — plain local
    component state (`fetch`-driven), matching the REST-only nature of
    this feature.

## Error Handling

- Unreadable/empty-text PDF → same 400 + `detail` message shape as the
  existing incident-report upload, so the frontend's existing
  error-display pattern applies without a new code path.
- Duplicate content → explicit non-error `"duplicate"` status, distinct
  from `"error"` — never presented to the user as a failure.
- Network/fetch failure → generic inline error message in `ManualsPanel`,
  same fallback pattern as `PdfUpload.tsx`'s catch block.

## Testing Approach

- **Backend**: unit tests for `manuals_ingest.py` against `mongomock` —
  hash computation, first-upload-ingests, second-upload-of-same-bytes
  returns `duplicate` without re-embedding (assert the embed function's
  call count), multi-page PDF produces one chunk per page with correct
  `chunk_index` values, empty-text PDF returns an `error` status. One
  `test_api.py` case per new endpoint (`POST /manuals/upload` happy path
  + duplicate + 400; `GET /manuals` returns the aggregated list).
- **Frontend**: `ManualsPanel` component tests with mocked `fetch`,
  covering: renders the fetched list on mount, submits the form with
  correct multipart fields, shows the ingested-success message and
  re-fetches, shows the duplicate message (not styled as an error), shows
  the error message on a 400 response — mirroring `PdfUpload.test.tsx`'s
  existing structure.

## Open Items For Implementation Planning

- Exact visual treatment of `ManualsPanel` (modal overlay vs. inline
  expand/collapse below `SettingsBar`) — a CSS/UX detail, not a behavior
  decision, resolved during implementation.
- `error_codes` input validation (empty string vs. at least one code) —
  minor, resolved during implementation to match the existing incident
  report's permissive style (the app already tolerates missing
  machine_id/error_code by asking a clarifying question rather than
  rejecting input outright).
