# LangGraph Backend + API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the LangGraph agentic workflow (Extract → RAG lookup → Inventory check → HITL gate → Finalize) and the FastAPI/WebSocket API that drives it, so a technician's chat message or PDF error log produces a diagnosis, an inventory check via the Plan 1 MCP server, a human-approval pause when parts must be ordered, and a persisted work order — all reachable without a frontend (plan 2 of 3: MCP server → **LangGraph backend + API** → Frontend).

**Architecture:** A Python package (`backend/`) with a swappable `LLMClient` abstraction (local Ollama/Gemma default, Claude API alternative), a RAG layer (local sentence-transformers embeddings + MongoDB Atlas Vector Search), an MCP client that spawns Plan 1's `mcp-inventory-server` as a stdio subprocess, and a 5-node LangGraph `StateGraph` checkpointed to MongoDB so the HITL approval pause survives a process restart. A FastAPI app exposes a PDF-upload REST endpoint and a WebSocket that streams chat messages in, and node-update/approval-request events out, resuming the graph via LangGraph's `Command(resume=...)` primitive when the technician approves or rejects a parts order.

**Tech Stack:** Python 3.11+, LangGraph (`langgraph`, `langgraph-checkpoint-mongodb`), `pymongo`, `ollama` (Python client), `anthropic`, `sentence-transformers`, FastAPI + `uvicorn`, `pypdf`, `mcp` (client side), Pydantic.

**Spec:** docs/superpowers/specs/2026-09-10-industrial-maintenance-agent-design.md

**Plan 1 handoff (already built, on `main`):** `mcp_server/` exposes a `mcp-inventory-server` console script (`mcp-inventory-server seed` / `mcp-inventory-server serve`, stdio transport). Its tools:
- `check_stock_tool(part_id: str) -> {"part_id": str, "name": str, "qty_on_hand": int, "reorder_threshold": int, "status": "in_stock"|"low_stock"|"out_of_stock"}`
- `reserve_parts_tool(part_id: str, quantity: int) -> {"part_id": str, "qty_on_hand": int, "reserved": int, "shortfall": int}` (floors at 0 stock; `shortfall` is `quantity - reserved`, so `shortfall > 0` means the reservation was only partially fulfilled)

## Global Constraints

- LLM backend is a per-session choice behind one `LLMClient` interface; default is local Ollama running model tag `gemma3:4b`; alternative is the Claude API — per spec's local/cloud toggle requirement.
- Embedding model is `sentence-transformers`'s `all-MiniLM-L6-v2` (384-dim vectors), run locally — decided during brainstorming for this plan.
- `manuals` collection schema: `chunk_text`, `embedding`, `machine_type`, `error_codes[]` (plus a `manual_id` upsert key) — per spec's Data Model section.
- `work_orders` collection schema: `machine_id`, `error_code`, `diagnosis`, `parts_used[]`, `parts_ordered[]`, `status`, `created_at` — per spec's Data Model section.
- Graph checkpointing uses `langgraph-checkpoint-mongodb`'s `MongoDBSaver` so HITL pause/resume survives a restart — per spec's Approach A.
- The 5 workflow nodes are Extract → RAG lookup → Inventory check → HITL gate → Finalize, in that order — per spec's Workflow Nodes section.
- HITL uses LangGraph's `interrupt()`/`Command(resume=...)` primitives, not an in-memory queue — per spec's Approach A decision.
- MCP calls to the Plan 1 server use stdio transport, spawning `mcp-inventory-server serve` as a subprocess — per Plan 1's Global Constraints, carried forward.
- Error handling per spec: ambiguous extraction → ask the user for clarification, don't fail; PDF parse failure → ask for a text description; no matching manual → say so explicitly, never fabricate a diagnosis; MCP unreachable → visible error, not silent failure; invalid structured output from the local model → one retry with reformatting instructions before surfacing an error.
- This is a portfolio/demo project (see spec's Non-Goals): no auth, no production-scale concurrency, no OCR, no real technical manuals or inventory data.

---

## File Structure

```
backend/
  pyproject.toml
  backend/
    __init__.py
    db.py                        # MongoDB accessor: manuals/work_orders collections, checkpoint client
    mcp_client.py                # spawns mcp-inventory-server over stdio, calls check_stock/reserve_parts
    llm/
      __init__.py
      base.py                    # LLMClient abstract interface
      ollama_client.py           # OllamaClient (local, default)
      claude_client.py           # ClaudeClient (cloud alternative)
    rag/
      __init__.py
      embeddings.py               # embed_text() via sentence-transformers, lazily cached model
      manuals_seed.py              # synthetic manuals + seed_manuals()
      vector_search.py             # search_manuals() Atlas Vector Search query
    graph/
      __init__.py
      state.py                    # GraphState TypedDict
      nodes/
        __init__.py
        extract.py                 # Node 1
        rag_lookup.py               # Node 2
        inventory_check.py          # Node 3
        hitl_gate.py                 # Node 4
        finalize.py                  # Node 5
      build.py                     # wires nodes into a compiled, checkpointed StateGraph
    api/
      __init__.py
      app.py                       # FastAPI app: PDF upload REST endpoint, WebSocket chat/approval
  tests/
    conftest.py                    # shared fixtures: mongomock collections, fake LLM client
    test_llm_clients.py
    test_db.py
    test_embeddings.py
    test_manuals_seed.py
    test_vector_search.py
    test_mcp_client.py
    test_extract_node.py
    test_rag_lookup_node.py
    test_inventory_check_node.py
    test_hitl_gate_node.py
    test_finalize_node.py
    test_build_graph.py            # full graph integration tests (happy path, clarification, HITL pause/resume)
    test_api.py
```

---

## Task 1: LLM client abstraction

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/backend/__init__.py`
- Create: `backend/backend/llm/__init__.py`
- Create: `backend/backend/llm/base.py`
- Create: `backend/backend/llm/ollama_client.py`
- Create: `backend/backend/llm/claude_client.py`
- Test: `backend/tests/test_llm_clients.py`

**Interfaces:**
- Produces: `LLMClient` (ABC) with `generate(self, prompt: str) -> str` and `generate_structured(self, prompt: str, schema: type[T]) -> T` (`T` bound to `pydantic.BaseModel`).
- Produces: `OllamaClient(LLMClient)`, `__init__(self, model: str = "gemma3:4b", host: str | None = None)`.
- Produces: `ClaudeClient(LLMClient)`, `__init__(self, model: str = "claude-sonnet-5", api_key: str | None = None)`.
- Both `generate_structured` implementations retry exactly once with a reformatting instruction appended to the prompt if the first attempt raises `pydantic.ValidationError` or `json.JSONDecodeError`; a second failure propagates.

Verified against real installed library APIs (do not re-derive from memory): `ollama.Client().chat(model=..., messages=[...], format=<json schema dict>)` returns a response whose `.message.content` is a JSON string when `format` is a schema dict — pass `schema.model_json_schema()` as `format`. `anthropic.Anthropic().beta.messages.parse(model=..., max_tokens=..., messages=[...], output_format=<pydantic model class>)` returns a message whose `.parsed_output` is already an instance of that model class — no manual JSON parsing needed for Claude. **Before writing code, verify both signatures against the actually-installed `ollama` and `anthropic` package versions** (e.g. `pip show ollama anthropic`, inspect the installed source) the same way Plan 1's Task 5 verified the `mcp` SDK — if either differs mechanically from what's described here, adjust only the mechanics, keep the same `LLMClient` interface and retry behavior.

- [ ] **Step 1: Scaffold the package**

Create `backend/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "ollama>=0.4",
    "anthropic>=0.40",
    "pydantic>=2.7",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

Create `backend/backend/__init__.py` and `backend/backend/llm/__init__.py` (both empty).

- [ ] **Step 2: Install dependencies and verify the two SDK signatures**

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

Then, in a Python shell using `.venv/bin/python`, inspect `ollama.Client.chat`'s signature and `anthropic.Anthropic().beta.messages.parse`'s signature/return shape against the installed versions, per the verification note above. Record what you found in your report even if it matches exactly.

- [ ] **Step 3: Write the failing tests**

Create `backend/backend/llm/base.py`:

```python
from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMClient(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str: ...

    @abstractmethod
    def generate_structured(self, prompt: str, schema: type[T]) -> T: ...
```

Create `backend/tests/test_llm_clients.py`:

```python
import json

import pytest
from pydantic import BaseModel

from backend.llm.ollama_client import OllamaClient
from backend.llm.claude_client import ClaudeClient


class Person(BaseModel):
    name: str
    age: int


class FakeOllamaMessage:
    def __init__(self, content):
        self.content = content


class FakeOllamaResponse:
    def __init__(self, content):
        self.message = FakeOllamaMessage(content)


def test_ollama_generate_returns_message_content(monkeypatch):
    client = OllamaClient(model="gemma3:4b")
    monkeypatch.setattr(
        client._client, "chat", lambda **kwargs: FakeOllamaResponse("hello there")
    )
    assert client.generate("hi") == "hello there"


def test_ollama_generate_structured_parses_json(monkeypatch):
    client = OllamaClient(model="gemma3:4b")
    calls = []

    def fake_chat(**kwargs):
        calls.append(kwargs)
        return FakeOllamaResponse(json.dumps({"name": "Ada", "age": 30}))

    monkeypatch.setattr(client._client, "chat", fake_chat)
    result = client.generate_structured("describe a person", Person)
    assert result == Person(name="Ada", age=30)
    assert calls[0]["format"] == Person.model_json_schema()


def test_ollama_generate_structured_retries_once_on_bad_json(monkeypatch):
    client = OllamaClient(model="gemma3:4b")
    responses = [
        FakeOllamaResponse("not json"),
        FakeOllamaResponse(json.dumps({"name": "Ada", "age": 30})),
    ]

    def fake_chat(**kwargs):
        return responses.pop(0)

    monkeypatch.setattr(client._client, "chat", fake_chat)
    result = client.generate_structured("describe a person", Person)
    assert result == Person(name="Ada", age=30)


def test_ollama_generate_structured_raises_after_second_failure(monkeypatch):
    client = OllamaClient(model="gemma3:4b")
    monkeypatch.setattr(
        client._client, "chat", lambda **kwargs: FakeOllamaResponse("still not json")
    )
    with pytest.raises(json.JSONDecodeError):
        client.generate_structured("describe a person", Person)


class FakeClaudeTextBlock:
    def __init__(self, text):
        self.text = text


class FakeClaudeMessage:
    def __init__(self, text):
        self.content = [FakeClaudeTextBlock(text)]


class FakeClaudeParsedMessage:
    def __init__(self, parsed_output):
        self.parsed_output = parsed_output


def test_claude_generate_returns_first_text_block(monkeypatch):
    client = ClaudeClient(model="claude-sonnet-5", api_key="test-key")
    monkeypatch.setattr(
        client._client.messages, "create", lambda **kwargs: FakeClaudeMessage("hi back")
    )
    assert client.generate("hi") == "hi back"


def test_claude_generate_structured_returns_parsed_output(monkeypatch):
    client = ClaudeClient(model="claude-sonnet-5", api_key="test-key")
    expected = Person(name="Ada", age=30)
    monkeypatch.setattr(
        client._client.beta.messages,
        "parse",
        lambda **kwargs: FakeClaudeParsedMessage(expected),
    )
    result = client.generate_structured("describe a person", Person)
    assert result == expected
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_llm_clients.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.llm.ollama_client'`

- [ ] **Step 5: Implement `OllamaClient`**

Create `backend/backend/llm/ollama_client.py` (adjust the exact `format=`/response-shape mechanics per your Step 2 verification if the installed version differs):

```python
import json

import ollama

from backend.llm.base import LLMClient, T


class OllamaClient(LLMClient):
    def __init__(self, model: str = "gemma3:4b", host: str | None = None):
        self._model = model
        self._client = ollama.Client(host=host) if host else ollama.Client()

    def generate(self, prompt: str) -> str:
        response = self._client.chat(
            model=self._model, messages=[{"role": "user", "content": prompt}]
        )
        return response.message.content

    def generate_structured(self, prompt: str, schema: type[T]) -> T:
        try:
            return self._generate_structured_once(prompt, schema)
        except (json.JSONDecodeError, __import__("pydantic").ValidationError):
            retry_prompt = (
                f"{prompt}\n\nYour previous response was not valid JSON matching the "
                "required schema. Respond with ONLY valid JSON matching the schema."
            )
            return self._generate_structured_once(retry_prompt, schema)

    def _generate_structured_once(self, prompt: str, schema: type[T]) -> T:
        response = self._client.chat(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            format=schema.model_json_schema(),
        )
        data = json.loads(response.message.content)
        return schema.model_validate(data)
```

- [ ] **Step 6: Implement `ClaudeClient`**

Create `backend/backend/llm/claude_client.py`:

```python
import json

import anthropic
import pydantic

from backend.llm.base import LLMClient, T


class ClaudeClient(LLMClient):
    def __init__(self, model: str = "claude-sonnet-5", api_key: str | None = None):
        self._model = model
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    def generate(self, prompt: str) -> str:
        message = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    def generate_structured(self, prompt: str, schema: type[T]) -> T:
        try:
            return self._generate_structured_once(prompt, schema)
        except (json.JSONDecodeError, pydantic.ValidationError):
            retry_prompt = (
                f"{prompt}\n\nYour previous response did not match the required schema. "
                "Respond with output matching the schema exactly."
            )
            return self._generate_structured_once(retry_prompt, schema)

    def _generate_structured_once(self, prompt: str, schema: type[T]) -> T:
        result = self._client.beta.messages.parse(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            output_format=schema,
        )
        return result.parsed_output
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_llm_clients.py -v`
Expected: PASS (8 passed)

- [ ] **Step 8: Commit**

```bash
git add backend/pyproject.toml backend/backend/__init__.py backend/backend/llm/ backend/tests/test_llm_clients.py
git commit -m "feat(backend): add swappable LLMClient abstraction (Ollama + Claude)"
```

## Task 2: Backend MongoDB accessor

**Files:**
- Create: `backend/backend/db.py`
- Test: `backend/tests/test_db.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `get_manuals_collection(client=None, db_name=None)`, `get_work_orders_collection(client=None, db_name=None)`, `get_checkpoint_client(client=None)` — the last returns a raw `pymongo.MongoClient` (not a collection), since `MongoDBSaver` takes a client. All three accept an injected `client` for tests and otherwise resolve a lazily-constructed, module-level singleton `MongoClient` built from `MONGODB_URI`/`MONGODB_DB` env vars (`MONGODB_DB` defaults to `"machine_repair"`), with `serverSelectionTimeoutMS=5000` — this mirrors the connection-leak fix applied to Plan 1's `mcp_server/mcp_server/db.py`; do not repeat that bug here.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_db.py`:

```python
import mongomock

from backend.db import get_manuals_collection, get_work_orders_collection, get_checkpoint_client


def test_get_manuals_collection_uses_injected_client():
    client = mongomock.MongoClient()
    collection = get_manuals_collection(client=client, db_name="test_db")
    assert collection.name == "manuals"
    assert collection.database.name == "test_db"


def test_get_work_orders_collection_uses_injected_client():
    client = mongomock.MongoClient()
    collection = get_work_orders_collection(client=client, db_name="test_db")
    assert collection.name == "work_orders"
    assert collection.database.name == "test_db"


def test_get_checkpoint_client_returns_injected_client():
    client = mongomock.MongoClient()
    assert get_checkpoint_client(client=client) is client
```

Add `mongomock>=4.1` and `pymongo>=4.9` to `backend/pyproject.toml`'s `dependencies` (pymongo) and `dev` optional deps (mongomock), then reinstall: `.venv/bin/pip install -e ".[dev]"`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.db'`

- [ ] **Step 3: Implement `db.py`**

Create `backend/backend/db.py`:

```python
import os

from pymongo import MongoClient

_client: MongoClient | None = None


def _get_default_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(os.environ["MONGODB_URI"], serverSelectionTimeoutMS=5000)
    return _client


def _resolve(client: MongoClient | None, db_name: str | None):
    if client is None:
        client = _get_default_client()
    resolved_db_name = db_name or os.environ.get("MONGODB_DB", "machine_repair")
    return client[resolved_db_name]


def get_manuals_collection(client: MongoClient | None = None, db_name: str | None = None):
    return _resolve(client, db_name)["manuals"]


def get_work_orders_collection(client: MongoClient | None = None, db_name: str | None = None):
    return _resolve(client, db_name)["work_orders"]


def get_checkpoint_client(client: MongoClient | None = None) -> MongoClient:
    return client if client is not None else _get_default_client()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_db.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/backend/db.py backend/tests/test_db.py backend/pyproject.toml
git commit -m "feat(backend): add MongoDB accessor with connection singleton"
```

## Task 3: Local embeddings + synthetic manuals seed data

**Files:**
- Create: `backend/backend/rag/__init__.py`
- Create: `backend/backend/rag/embeddings.py`
- Create: `backend/backend/rag/manuals_seed.py`
- Test: `backend/tests/test_embeddings.py`
- Test: `backend/tests/test_manuals_seed.py`

**Interfaces:**
- Produces: `EMBEDDING_DIM = 384` (module constant in `embeddings.py`); `embed_text(text: str) -> list[float]`, length `EMBEDDING_DIM`, using a lazily-loaded module-level `SentenceTransformer("all-MiniLM-L6-v2")` singleton (load the model once, not per call — this is the same per-call-construction mistake Plan 1's review caught with `MongoClient`, avoid repeating it here).
- Produces: `SAMPLE_MANUALS: list[dict]` (each `{"manual_id": str, "machine_type": str, "error_codes": list[str], "chunk_text": str}`), `seed_manuals(collection, embed_fn=embed_text, manuals=SAMPLE_MANUALS) -> int` — idempotent upsert by `manual_id`, storing `chunk_text`, `machine_type`, `error_codes`, and an `embedding` computed via `embed_fn(chunk_text)`.

- [ ] **Step 1: Add the dependency**

Add `"sentence-transformers>=3.0"` to `backend/pyproject.toml`'s `dependencies`, then `cd backend && .venv/bin/pip install -e ".[dev]"` (this downloads the `all-MiniLM-L6-v2` model on first use — needs network access once, then it's cached locally).

- [ ] **Step 2: Write the failing embeddings test**

Create `backend/tests/test_embeddings.py`:

```python
from backend.rag.embeddings import embed_text, EMBEDDING_DIM


def test_embed_text_returns_correct_dimension():
    vector = embed_text("bearing failure on the main spindle")
    assert len(vector) == EMBEDDING_DIM
    assert all(isinstance(x, float) for x in vector)


def test_embed_text_is_deterministic():
    text = "hydraulic pressure loss"
    assert embed_text(text) == embed_text(text)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_embeddings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.rag'`

- [ ] **Step 4: Implement `embeddings.py`**

Create `backend/backend/rag/__init__.py` (empty) and `backend/backend/rag/embeddings.py`:

```python
from sentence_transformers import SentenceTransformer

EMBEDDING_DIM = 384

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def embed_text(text: str) -> list[float]:
    return _get_model().encode(text, convert_to_numpy=True).tolist()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_embeddings.py -v`
Expected: PASS (2 passed) — first run may take longer while the model downloads.

- [ ] **Step 6: Write the failing seed-data tests**

Create `backend/tests/test_manuals_seed.py`:

```python
import mongomock

from backend.rag.manuals_seed import SAMPLE_MANUALS, seed_manuals


def fake_embed(text: str) -> list[float]:
    return [float(len(text))]


def test_seed_manuals_inserts_all_sample_manuals():
    client = mongomock.MongoClient()
    collection = client["machine_repair"]["manuals"]

    count = seed_manuals(collection, embed_fn=fake_embed)

    assert count == len(SAMPLE_MANUALS)
    assert collection.count_documents({}) == len(SAMPLE_MANUALS)
    doc = collection.find_one({"manual_id": SAMPLE_MANUALS[0]["manual_id"]})
    assert doc["embedding"] == fake_embed(SAMPLE_MANUALS[0]["chunk_text"])
    assert doc["machine_type"] == SAMPLE_MANUALS[0]["machine_type"]


def test_seed_manuals_is_idempotent():
    client = mongomock.MongoClient()
    collection = client["machine_repair"]["manuals"]

    seed_manuals(collection, embed_fn=fake_embed)
    seed_manuals(collection, embed_fn=fake_embed)

    assert collection.count_documents({}) == len(SAMPLE_MANUALS)
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_manuals_seed.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.rag.manuals_seed'`

- [ ] **Step 8: Implement `manuals_seed.py`**

Create `backend/backend/rag/manuals_seed.py`. Use these five synthetic manuals, matching the three machine types seeded into inventory by Plan 1 (`CNC-Mill-200`, `Conveyor-Belt-A7`, `Hydraulic-Press-9`) so a demo run can find both a diagnosis and matching spare parts:

```python
from backend.rag.embeddings import embed_text

SAMPLE_MANUALS = [
    {
        "manual_id": "CNC-MILL-200-E101",
        "machine_type": "CNC-Mill-200",
        "error_codes": ["E101"],
        "chunk_text": (
            "Error E101 on the CNC-Mill-200 indicates main spindle bearing wear, "
            "usually presenting as excessive vibration and a grinding noise above "
            "2000 RPM. Diagnosis: inspect the main spindle bearing (part BEARING-X4) "
            "for pitting or discoloration. Repair: power down the mill, remove the "
            "spindle housing cover, replace the worn bearing with BEARING-X4, "
            "repack with the specified grease, and reassemble. Run a 10-minute "
            "no-load test before returning to production."
        ),
    },
    {
        "manual_id": "CNC-MILL-200-E204",
        "machine_type": "CNC-Mill-200",
        "error_codes": ["E204"],
        "chunk_text": (
            "Error E204 on the CNC-Mill-200 signals drive motor overcurrent, "
            "typically caused by a failing drive motor (part MOTOR-C2) under load. "
            "Diagnosis: check motor winding resistance and look for overheating "
            "discoloration on the housing. Repair: isolate power, remove the drive "
            "motor assembly, replace with MOTOR-C2, and verify current draw is "
            "within spec before resuming operation."
        ),
    },
    {
        "manual_id": "CONVEYOR-A7-B12",
        "machine_type": "Conveyor-Belt-A7",
        "error_codes": ["B12"],
        "chunk_text": (
            "Error B12 on the Conveyor-Belt-A7 indicates belt slippage or tearing, "
            "usually from a worn conveyor belt (part BELT-A7). Diagnosis: inspect "
            "the belt surface for fraying, cracking, or uneven wear along the edges. "
            "Repair: release belt tension, remove the worn belt, install a "
            "replacement BELT-A7, and re-tension to the manufacturer's spec before "
            "restarting."
        ),
    },
    {
        "manual_id": "CONVEYOR-A7-B20",
        "machine_type": "Conveyor-Belt-A7",
        "error_codes": ["B20"],
        "chunk_text": (
            "Error B20 on the Conveyor-Belt-A7 indicates drive motor stall, often "
            "caused by the same drive motor part (MOTOR-C2) used on the CNC-Mill-200. "
            "Diagnosis: check for excessive load or jammed rollers before assuming a "
            "motor fault. Repair: clear any jam first; if the stall persists, replace "
            "the drive motor with MOTOR-C2."
        ),
    },
    {
        "manual_id": "HYDRAULIC-PRESS-9-H33",
        "machine_type": "Hydraulic-Press-9",
        "error_codes": ["H33"],
        "chunk_text": (
            "Error H33 on the Hydraulic-Press-9 indicates loss of hydraulic pressure, "
            "commonly from a failed hydraulic valve (part VALVE-H9) or a worn seal kit "
            "(part SEAL-K1). Diagnosis: check for visible fluid leaks around the valve "
            "body and seals first. Repair: if the valve is leaking internally, replace "
            "VALVE-H9; if the leak is at a seal interface, replace the seal kit SEAL-K1. "
            "Bleed the hydraulic system and verify pressure holds before returning to "
            "service."
        ),
    },
]


def seed_manuals(collection, embed_fn=embed_text, manuals: list[dict] = SAMPLE_MANUALS) -> int:
    count = 0
    for manual in manuals:
        collection.update_one(
            {"manual_id": manual["manual_id"]},
            {
                "$set": {
                    "manual_id": manual["manual_id"],
                    "machine_type": manual["machine_type"],
                    "error_codes": manual["error_codes"],
                    "chunk_text": manual["chunk_text"],
                    "embedding": embed_fn(manual["chunk_text"]),
                }
            },
            upsert=True,
        )
        count += 1
    return count
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_manuals_seed.py -v`
Expected: PASS (2 passed)

- [ ] **Step 10: Commit**

```bash
git add backend/backend/rag/embeddings.py backend/backend/rag/manuals_seed.py backend/backend/rag/__init__.py backend/tests/test_embeddings.py backend/tests/test_manuals_seed.py backend/pyproject.toml
git commit -m "feat(backend): add local embeddings and synthetic manuals seed data"
```

## Task 4: Vector search query

**Files:**
- Create: `backend/backend/rag/vector_search.py`
- Test: `backend/tests/test_vector_search.py`

**Interfaces:**
- Consumes: nothing at import time; called with a collection-like object exposing `.aggregate(pipeline) -> Iterable[dict]`.
- Produces: `search_manuals(collection, query_embedding: list[float], top_k: int = 3) -> list[dict]`, each result dict having at least `chunk_text`, `machine_type`, `error_codes`.

**Note:** `mongomock` does not implement the `$vectorSearch` aggregation stage, so this task's test uses a hand-written fake collection whose `.aggregate()` returns a scripted list — it verifies the pipeline shape and result mapping, not real Atlas vector ranking. A real Atlas Vector Search index (named `manuals_vector_index` in this plan) must be created on the `manuals` collection's `embedding` field before this runs against production data; that index creation is an Atlas console/CLI step outside this codebase and is called out again in this task's manual-verification step.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_vector_search.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_vector_search.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.rag.vector_search'`

- [ ] **Step 3: Implement `vector_search.py`**

Create `backend/backend/rag/vector_search.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_vector_search.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/backend/rag/vector_search.py backend/tests/test_vector_search.py
git commit -m "feat(backend): add Atlas Vector Search query for manuals"
```

## Task 5: MCP client wrapper

**Files:**
- Create: `backend/backend/mcp_client.py`
- Test: `backend/tests/test_mcp_client.py`

**Interfaces:**
- Consumes: nothing at import time; spawns Plan 1's `mcp-inventory-server` console script as a subprocess when called.
- Produces: `async def check_stock(part_id: str) -> dict` (matches `check_stock_tool`'s payload), `async def reserve_parts(part_id: str, quantity: int) -> dict` (matches `reserve_parts_tool`'s payload, including `reserved`/`shortfall`), and `_parse_tool_result(result) -> dict` (raises `RuntimeError` if `result.is_error`).

Add `"mcp>=1.2.0,<2.0"` to `backend/pyproject.toml`'s dependencies — same pin as Plan 1's `mcp_server`, for the same reason (mcp 2.x renamed the client/server API surface this plan is built against).

**Verify before writing code** (same discipline as Plan 1's Task 5 and this plan's Task 1): inspect the installed `mcp` package's `mcp.client.stdio.stdio_client`, `mcp.ClientSession`, and `mcp.StdioServerParameters` to confirm `stdio_client(params)` yields `(read, write)` streams passed to `ClientSession(read, write)`, that `session.initialize()` must be awaited before calling tools, and that `session.call_tool(name, arguments)` returns an object with `.is_error: bool` and `.content: list` where `.content[0].text` is a JSON string of the tool's return value (this is the same result shape Plan 1's `test_check_stock_tool_invocation` verified against the FastMCP server side). Adjust only the mechanics if what you find differs.

**Testing scope:** this task's automated tests cover `_parse_tool_result` (the parsing logic) directly, without spawning a real subprocess — spawning `mcp-inventory-server` requires a reachable `MONGODB_URI`, which may not exist in this environment. A live subprocess round-trip against a real MongoDB is deferred to Task 9's end-to-end verification note, mirroring Plan 1's documented CLI-verification gap.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_mcp_client.py`:

```python
import pytest

from backend.mcp_client import _parse_tool_result


class FakeTextContent:
    def __init__(self, text):
        self.text = text


class FakeCallToolResult:
    def __init__(self, content_text, is_error=False):
        self.content = [FakeTextContent(content_text)]
        self.is_error = is_error


def test_parse_tool_result_returns_parsed_json():
    result = FakeCallToolResult('{"part_id": "BEARING-X4", "status": "in_stock"}')
    assert _parse_tool_result(result) == {"part_id": "BEARING-X4", "status": "in_stock"}


def test_parse_tool_result_raises_on_error():
    result = FakeCallToolResult("Unknown part_id: NOPE-1", is_error=True)
    with pytest.raises(RuntimeError, match="Unknown part_id: NOPE-1"):
        _parse_tool_result(result)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_mcp_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.mcp_client'`

- [ ] **Step 3: Implement `mcp_client.py`**

Create `backend/backend/mcp_client.py` (adjust import paths/method names per your Step-0 verification if the installed `mcp` version differs mechanically):

```python
import json
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

_SERVER_PARAMS = StdioServerParameters(
    command="mcp-inventory-server", args=["serve"], env=dict(os.environ)
)


def _parse_tool_result(result) -> dict:
    if result.is_error:
        raise RuntimeError(result.content[0].text)
    return json.loads(result.content[0].text)


async def _call_tool(tool_name: str, arguments: dict) -> dict:
    async with stdio_client(_SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            return _parse_tool_result(result)


async def check_stock(part_id: str) -> dict:
    return await _call_tool("check_stock_tool", {"part_id": part_id})


async def reserve_parts(part_id: str, quantity: int) -> dict:
    return await _call_tool("reserve_parts_tool", {"part_id": part_id, "quantity": quantity})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_mcp_client.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/backend/mcp_client.py backend/tests/test_mcp_client.py backend/pyproject.toml
git commit -m "feat(backend): add MCP client wrapper for the inventory server"
```

## Task 6: Graph state + Extract node

**Files:**
- Create: `backend/backend/graph/__init__.py`
- Create: `backend/backend/graph/state.py`
- Create: `backend/backend/graph/nodes/__init__.py`
- Create: `backend/backend/graph/nodes/extract.py`
- Test: `backend/tests/test_extract_node.py`
- Test: `backend/tests/conftest.py`

**Interfaces:**
- Consumes: `LLMClient` from Task 1 (`backend.llm.base.LLMClient`).
- Produces: `GraphState` (`TypedDict, total=False`) with fields `user_input: str`, `pdf_text: str | None`, `machine_id: str | None`, `error_code: str | None`, `error_description: str | None`, `needs_clarification: bool`, `clarification_message: str | None`, `diagnosis: str | None`, `repair_steps: list[str] | None`, `no_procedure_found: bool`, `required_parts: list[dict] | None`, `inventory_status: list[dict] | None`, `needs_approval: bool`, `approval_decision: str | None`, `work_order_id: str | None`, `work_order_status: str | None`.
- Produces: `ExtractedError(BaseModel)` with `machine_id: str | None = None`, `error_code: str | None = None`, `description: str`.
- Produces: `make_extract_node(llm: LLMClient) -> Callable[[GraphState], dict]` — the returned node function reads `state["user_input"]` (and `state.get("pdf_text")` if present), calls `llm.generate_structured(...)` with `ExtractedError`, and returns a partial state update: either `{"machine_id", "error_code", "error_description", "needs_clarification": False}` or `{"needs_clarification": True, "clarification_message": str}` if `machine_id` or `error_code` came back `None`.

- [ ] **Step 1: Create the shared test fixture**

Create `backend/tests/conftest.py`:

```python
import pytest
from pydantic import BaseModel


class FakeLLMClient:
    """Test double for LLMClient: returns pre-scripted structured responses in order."""

    def __init__(self, structured_responses: list[BaseModel] | None = None, text_responses: list[str] | None = None):
        self._structured_responses = list(structured_responses or [])
        self._text_responses = list(text_responses or [])
        self.prompts = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._text_responses.pop(0)

    def generate_structured(self, prompt: str, schema):
        self.prompts.append(prompt)
        return self._structured_responses.pop(0)


@pytest.fixture
def fake_llm():
    return FakeLLMClient
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_extract_node.py`:

```python
from backend.graph.nodes.extract import make_extract_node, ExtractedError


def test_extract_node_returns_fields_when_complete(fake_llm):
    llm = fake_llm(structured_responses=[
        ExtractedError(machine_id="CNC-Mill-200", error_code="E101", description="loud grinding noise")
    ])
    node = make_extract_node(llm)

    result = node({"user_input": "CNC mill throwing E101, grinding noise from spindle"})

    assert result == {
        "machine_id": "CNC-Mill-200",
        "error_code": "E101",
        "error_description": "loud grinding noise",
        "needs_clarification": False,
    }


def test_extract_node_asks_for_clarification_when_machine_id_missing(fake_llm):
    llm = fake_llm(structured_responses=[
        ExtractedError(machine_id=None, error_code="E101", description="grinding noise")
    ])
    node = make_extract_node(llm)

    result = node({"user_input": "something is making a grinding noise, error E101"})

    assert result["needs_clarification"] is True
    assert "machine ID" in result["clarification_message"]


def test_extract_node_includes_pdf_text_in_prompt(fake_llm):
    llm = fake_llm(structured_responses=[
        ExtractedError(machine_id="CNC-Mill-200", error_code="E101", description="grinding noise")
    ])
    node = make_extract_node(llm)

    node({"user_input": "see attached log", "pdf_text": "ERROR LOG: E101 detected at 14:02"})

    assert "ERROR LOG: E101 detected at 14:02" in llm.prompts[0]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_extract_node.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.graph'`

- [ ] **Step 4: Implement `state.py` and `extract.py`**

Create `backend/backend/graph/__init__.py`, `backend/backend/graph/nodes/__init__.py` (both empty), and `backend/backend/graph/state.py`:

```python
from typing import TypedDict


class GraphState(TypedDict, total=False):
    user_input: str
    pdf_text: str | None
    machine_id: str | None
    error_code: str | None
    error_description: str | None
    needs_clarification: bool
    clarification_message: str | None
    diagnosis: str | None
    repair_steps: list[str] | None
    no_procedure_found: bool
    required_parts: list[dict] | None
    inventory_status: list[dict] | None
    needs_approval: bool
    approval_decision: str | None
    work_order_id: str | None
    work_order_status: str | None
```

Create `backend/backend/graph/nodes/extract.py`:

```python
from typing import Callable

from pydantic import BaseModel

from backend.graph.state import GraphState
from backend.llm.base import LLMClient


class ExtractedError(BaseModel):
    machine_id: str | None = None
    error_code: str | None = None
    description: str


def make_extract_node(llm: LLMClient) -> Callable[[GraphState], dict]:
    def extract_node(state: GraphState) -> dict:
        text = state["user_input"]
        if state.get("pdf_text"):
            text = f"{text}\n\nError log:\n{state['pdf_text']}"

        prompt = (
            "Extract the machine ID, error code, and a short description of the "
            "problem from this maintenance report. If the machine ID or error code "
            "is not clearly stated, leave that field null rather than guessing.\n\n"
            f"Report:\n{text}"
        )
        extracted = llm.generate_structured(prompt, ExtractedError)

        missing = []
        if extracted.machine_id is None:
            missing.append("machine ID")
        if extracted.error_code is None:
            missing.append("error code")
        if missing:
            return {
                "needs_clarification": True,
                "clarification_message": (
                    f"I need the {' and '.join(missing)} to continue — could you provide it?"
                ),
            }

        return {
            "machine_id": extracted.machine_id,
            "error_code": extracted.error_code,
            "error_description": extracted.description,
            "needs_clarification": False,
        }

    return extract_node
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_extract_node.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/backend/graph/ backend/tests/test_extract_node.py backend/tests/conftest.py
git commit -m "feat(backend): add graph state and Extract node"
```

## Task 7: RAG lookup node + Inventory check node

**Files:**
- Create: `backend/backend/graph/nodes/rag_lookup.py`
- Create: `backend/backend/graph/nodes/inventory_check.py`
- Test: `backend/tests/test_rag_lookup_node.py`
- Test: `backend/tests/test_inventory_check_node.py`

**Interfaces:**
- Consumes: `LLMClient` (Task 1), `embed_text` (Task 3, as default), `search_manuals` (Task 4, as default), `check_stock` (Task 5, as default), `GraphState` (Task 6).
- Produces: `RequiredPart(BaseModel)` with `part_id: str`, `name: str`, `quantity: int`; `DiagnosisResult(BaseModel)` with `diagnosis: str`, `repair_steps: list[str]`, `required_parts: list[RequiredPart]`, `no_procedure_found: bool = False`.
- Produces: `make_rag_lookup_node(llm, manuals_collection, embed_fn=embed_text, search_fn=search_manuals) -> node_fn` returning `{"no_procedure_found", "diagnosis", "repair_steps", "required_parts"}` (the last as `list[dict]`, from `RequiredPart.model_dump()`).
- Produces: `make_inventory_check_node(check_stock_fn=check_stock) -> async node_fn` — for each entry in `state["required_parts"]`, awaits `check_stock_fn(part["part_id"])`, appends its full return payload to `inventory_status`, and sets `needs_approval = True` if any part's `"status"` is `"low_stock"` or `"out_of_stock"`. Returns `{"inventory_status": list[dict], "needs_approval": bool}`.

- [ ] **Step 1: Write the failing RAG lookup test**

Create `backend/tests/test_rag_lookup_node.py`:

```python
from backend.graph.nodes.rag_lookup import make_rag_lookup_node, DiagnosisResult, RequiredPart


def fake_embed(text: str) -> list[float]:
    return [0.1, 0.2]


def test_rag_lookup_node_returns_diagnosis_when_manual_found(fake_llm):
    def fake_search(collection, query_embedding, top_k=3):
        return [{"chunk_text": "bearing wear procedure", "machine_type": "CNC-Mill-200", "error_codes": ["E101"]}]

    llm = fake_llm(structured_responses=[
        DiagnosisResult(
            diagnosis="Main spindle bearing wear",
            repair_steps=["Power down", "Replace bearing"],
            required_parts=[RequiredPart(part_id="BEARING-X4", name="Bearing X4", quantity=1)],
        )
    ])
    node = make_rag_lookup_node(llm, manuals_collection=object(), embed_fn=fake_embed, search_fn=fake_search)

    result = node({"machine_id": "CNC-Mill-200", "error_code": "E101", "error_description": "grinding noise"})

    assert result["no_procedure_found"] is False
    assert result["diagnosis"] == "Main spindle bearing wear"
    assert result["required_parts"] == [{"part_id": "BEARING-X4", "name": "Bearing X4", "quantity": 1}]


def test_rag_lookup_node_reports_no_procedure_found_when_no_chunks(fake_llm):
    def fake_search(collection, query_embedding, top_k=3):
        return []

    llm = fake_llm()  # generate_structured should never be called
    node = make_rag_lookup_node(llm, manuals_collection=object(), embed_fn=fake_embed, search_fn=fake_search)

    result = node({"machine_id": "CNC-Mill-200", "error_code": "Z999", "error_description": "unknown issue"})

    assert result["no_procedure_found"] is True
    assert result["required_parts"] == []
    assert llm.prompts == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_rag_lookup_node.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.graph.nodes.rag_lookup'`

- [ ] **Step 3: Implement `rag_lookup.py`**

Create `backend/backend/graph/nodes/rag_lookup.py`:

```python
from typing import Callable

from pydantic import BaseModel

from backend.graph.state import GraphState
from backend.llm.base import LLMClient
from backend.rag.embeddings import embed_text
from backend.rag.vector_search import search_manuals


class RequiredPart(BaseModel):
    part_id: str
    name: str
    quantity: int


class DiagnosisResult(BaseModel):
    diagnosis: str
    repair_steps: list[str]
    required_parts: list[RequiredPart]
    no_procedure_found: bool = False


def make_rag_lookup_node(
    llm: LLMClient,
    manuals_collection,
    embed_fn=embed_text,
    search_fn=search_manuals,
) -> Callable[[GraphState], dict]:
    def rag_lookup_node(state: GraphState) -> dict:
        query_embedding = embed_fn(state["error_description"])
        chunks = search_fn(manuals_collection, query_embedding, top_k=3)

        if not chunks:
            return {
                "no_procedure_found": True,
                "diagnosis": "No relevant repair procedure was found in the technical manuals for this error.",
                "repair_steps": [],
                "required_parts": [],
            }

        context = "\n\n".join(c["chunk_text"] for c in chunks)
        prompt = (
            "Using ONLY the following excerpts from technical repair manuals, diagnose "
            f"the fault and list the repair steps and required spare parts for error "
            f"{state['error_code']} on machine {state['machine_id']}.\n\n"
            f"Manual excerpts:\n{context}\n\n"
            "If the excerpts do not actually cover this error, set no_procedure_found "
            "to true and leave diagnosis/repair_steps/required_parts empty rather than "
            "guessing."
        )
        result = llm.generate_structured(prompt, DiagnosisResult)

        return {
            "no_procedure_found": result.no_procedure_found,
            "diagnosis": result.diagnosis,
            "repair_steps": result.repair_steps,
            "required_parts": [p.model_dump() for p in result.required_parts],
        }

    return rag_lookup_node
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_rag_lookup_node.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Write the failing inventory-check test**

Create `backend/tests/test_inventory_check_node.py`:

```python
import pytest

from backend.graph.nodes.inventory_check import make_inventory_check_node


@pytest.mark.asyncio
async def test_inventory_check_node_no_approval_needed_when_in_stock():
    async def fake_check_stock(part_id):
        return {"part_id": part_id, "name": "Bearing X4", "qty_on_hand": 12, "reorder_threshold": 5, "status": "in_stock"}

    node = make_inventory_check_node(check_stock_fn=fake_check_stock)
    result = await node({"required_parts": [{"part_id": "BEARING-X4", "name": "Bearing X4", "quantity": 1}]})

    assert result["needs_approval"] is False
    assert result["inventory_status"][0]["status"] == "in_stock"


@pytest.mark.asyncio
async def test_inventory_check_node_needs_approval_when_low_stock():
    async def fake_check_stock(part_id):
        return {"part_id": part_id, "name": "Belt A7", "qty_on_hand": 2, "reorder_threshold": 3, "status": "low_stock"}

    node = make_inventory_check_node(check_stock_fn=fake_check_stock)
    result = await node({"required_parts": [{"part_id": "BELT-A7", "name": "Belt A7", "quantity": 1}]})

    assert result["needs_approval"] is True


@pytest.mark.asyncio
async def test_inventory_check_node_checks_every_required_part():
    calls = []

    async def fake_check_stock(part_id):
        calls.append(part_id)
        return {"part_id": part_id, "name": part_id, "qty_on_hand": 10, "reorder_threshold": 1, "status": "in_stock"}

    node = make_inventory_check_node(check_stock_fn=fake_check_stock)
    await node({"required_parts": [
        {"part_id": "BEARING-X4", "name": "Bearing X4", "quantity": 1},
        {"part_id": "MOTOR-C2", "name": "Motor C2", "quantity": 1},
    ]})

    assert calls == ["BEARING-X4", "MOTOR-C2"]
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_inventory_check_node.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.graph.nodes.inventory_check'`

- [ ] **Step 7: Implement `inventory_check.py`**

Create `backend/backend/graph/nodes/inventory_check.py`:

```python
from typing import Awaitable, Callable

from backend.graph.state import GraphState
from backend.mcp_client import check_stock

LOW_STATUSES = {"low_stock", "out_of_stock"}


def make_inventory_check_node(check_stock_fn=check_stock) -> Callable[[GraphState], Awaitable[dict]]:
    async def inventory_check_node(state: GraphState) -> dict:
        inventory_status = []
        needs_approval = False
        for part in state.get("required_parts", []):
            status = await check_stock_fn(part["part_id"])
            inventory_status.append(status)
            if status["status"] in LOW_STATUSES:
                needs_approval = True
        return {"inventory_status": inventory_status, "needs_approval": needs_approval}

    return inventory_check_node
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_inventory_check_node.py -v`
Expected: PASS (3 passed)

- [ ] **Step 9: Add `pytest-asyncio` config and run the full task's tests**

Confirm `backend/pyproject.toml` already has `asyncio_mode = "auto"` under `[tool.pytest.ini_options]` (set in Task 1) and `pytest-asyncio` in `dev` deps — if either is missing, add them and reinstall.

Run: `cd backend && .venv/bin/pytest tests/test_rag_lookup_node.py tests/test_inventory_check_node.py -v`
Expected: PASS (5 passed)

- [ ] **Step 10: Commit**

```bash
git add backend/backend/graph/nodes/rag_lookup.py backend/backend/graph/nodes/inventory_check.py backend/tests/test_rag_lookup_node.py backend/tests/test_inventory_check_node.py
git commit -m "feat(backend): add RAG lookup and inventory check nodes"
```

## Task 8: HITL gate node + Finalize node

**Files:**
- Create: `backend/backend/graph/nodes/hitl_gate.py`
- Create: `backend/backend/graph/nodes/finalize.py`
- Test: `backend/tests/test_hitl_gate_node.py`
- Test: `backend/tests/test_finalize_node.py`

**Interfaces:**
- Consumes: `GraphState` (Task 6), `reserve_parts` (Task 5, as default).
- Produces: `hitl_gate_node(state: GraphState) -> dict` — if `not state.get("needs_approval")`, returns `{}` (no-op passthrough); otherwise calls `langgraph.types.interrupt({"required_parts": ..., "inventory_status": ...})` and returns `{"approval_decision": <resume value>}`. **Verify** `from langgraph.types import interrupt` against the installed `langgraph` version before writing code (same verification discipline as prior tasks) — this plan was designed against the documented pattern where a node calls `interrupt(value)` to pause and `Command(resume=...)` resumes it with that value returned from the same `interrupt()` call.
- Produces: `make_finalize_node(work_orders_collection, reserve_parts_fn=reserve_parts) -> async node_fn` — if the parts order was needed but not approved (`needs_approval` True and `approval_decision != "approved"`), inserts a `work_orders` document with `status="rejected"`, empty `parts_used`/`parts_ordered`. Otherwise, for each `required_parts` entry, awaits `reserve_parts_fn(part_id, quantity)`; entries with `shortfall == 0` go to `parts_used`, entries with `shortfall > 0` go to `parts_ordered` (carrying the shortfall), and the work order is inserted with `status="completed"`. Returns `{"work_order_id": str(inserted_id), "work_order_status": status}`.

**Testing scope for `hitl_gate_node`:** `interrupt()` raises a control-flow exception when called outside an active LangGraph run with a checkpointer, so this task's test only covers the no-op passthrough path (`needs_approval` is falsy) directly. The actual pause/resume behavior is verified in Task 9's full-graph integration test, where a real checkpointer and graph run provide the context `interrupt()` needs.

- [ ] **Step 1: Write the failing HITL gate test**

Create `backend/tests/test_hitl_gate_node.py`:

```python
from backend.graph.nodes.hitl_gate import hitl_gate_node


def test_hitl_gate_node_passes_through_when_no_approval_needed():
    result = hitl_gate_node({"needs_approval": False})
    assert result == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_hitl_gate_node.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.graph.nodes.hitl_gate'`

- [ ] **Step 3: Implement `hitl_gate.py`**

Add `"langgraph>=0.6"` to `backend/pyproject.toml`'s dependencies and reinstall (`.venv/bin/pip install -e ".[dev]"`). Verify `langgraph.types.interrupt`'s import path against the installed version, then create `backend/backend/graph/nodes/hitl_gate.py`:

```python
from langgraph.types import interrupt

from backend.graph.state import GraphState


def hitl_gate_node(state: GraphState) -> dict:
    if not state.get("needs_approval"):
        return {}

    decision = interrupt({
        "required_parts": state.get("required_parts"),
        "inventory_status": state.get("inventory_status"),
    })
    return {"approval_decision": decision}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_hitl_gate_node.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Write the failing finalize tests**

Create `backend/tests/test_finalize_node.py`:

```python
import pytest
import mongomock

from backend.graph.nodes.finalize import make_finalize_node


@pytest.mark.asyncio
async def test_finalize_node_completes_work_order_when_all_parts_reserved():
    async def fake_reserve(part_id, quantity):
        return {"part_id": part_id, "qty_on_hand": 9, "reserved": quantity, "shortfall": 0}

    collection = mongomock.MongoClient()["machine_repair"]["work_orders"]
    node = make_finalize_node(collection, reserve_parts_fn=fake_reserve)

    result = await node({
        "machine_id": "CNC-Mill-200",
        "error_code": "E101",
        "diagnosis": "Main spindle bearing wear",
        "required_parts": [{"part_id": "BEARING-X4", "name": "Bearing X4", "quantity": 1}],
        "needs_approval": False,
    })

    assert result["work_order_status"] == "completed"
    doc = collection.find_one({"_id": __import__("bson").ObjectId(result["work_order_id"])})
    assert doc["parts_used"] == [{"part_id": "BEARING-X4", "name": "Bearing X4", "quantity": 1}]
    assert doc["parts_ordered"] == []
    assert doc["status"] == "completed"


@pytest.mark.asyncio
async def test_finalize_node_records_shortfall_as_parts_ordered():
    async def fake_reserve(part_id, quantity):
        return {"part_id": part_id, "qty_on_hand": 0, "reserved": 1, "shortfall": 2}

    collection = mongomock.MongoClient()["machine_repair"]["work_orders"]
    node = make_finalize_node(collection, reserve_parts_fn=fake_reserve)

    result = await node({
        "machine_id": "Hydraulic-Press-9",
        "error_code": "H33",
        "diagnosis": "Hydraulic valve failure",
        "required_parts": [{"part_id": "VALVE-H9", "name": "Hydraulic Valve H9", "quantity": 3}],
        "needs_approval": True,
        "approval_decision": "approved",
    })

    doc = collection.find_one({"_id": __import__("bson").ObjectId(result["work_order_id"])})
    assert doc["parts_used"] == []
    assert doc["parts_ordered"] == [{"part_id": "VALVE-H9", "name": "Hydraulic Valve H9", "quantity": 1, "shortfall": 2}]


@pytest.mark.asyncio
async def test_finalize_node_marks_rejected_when_approval_denied():
    async def fake_reserve(part_id, quantity):
        raise AssertionError("reserve_parts_fn should not be called when rejected")

    collection = mongomock.MongoClient()["machine_repair"]["work_orders"]
    node = make_finalize_node(collection, reserve_parts_fn=fake_reserve)

    result = await node({
        "machine_id": "CNC-Mill-200",
        "error_code": "E101",
        "diagnosis": "Main spindle bearing wear",
        "required_parts": [{"part_id": "BEARING-X4", "name": "Bearing X4", "quantity": 1}],
        "needs_approval": True,
        "approval_decision": "rejected",
    })

    assert result["work_order_status"] == "rejected"
    doc = collection.find_one({"_id": __import__("bson").ObjectId(result["work_order_id"])})
    assert doc["status"] == "rejected"
    assert doc["parts_used"] == []
    assert doc["parts_ordered"] == []
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_finalize_node.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.graph.nodes.finalize'`

- [ ] **Step 7: Implement `finalize.py`**

Create `backend/backend/graph/nodes/finalize.py`:

```python
from datetime import datetime, timezone
from typing import Awaitable, Callable

from backend.graph.state import GraphState
from backend.mcp_client import reserve_parts


def make_finalize_node(work_orders_collection, reserve_parts_fn=reserve_parts) -> Callable[[GraphState], Awaitable[dict]]:
    async def finalize_node(state: GraphState) -> dict:
        base_doc = {
            "machine_id": state["machine_id"],
            "error_code": state["error_code"],
            "diagnosis": state.get("diagnosis"),
            "created_at": datetime.now(timezone.utc),
        }

        if state.get("needs_approval") and state.get("approval_decision") != "approved":
            work_order = {**base_doc, "parts_used": [], "parts_ordered": [], "status": "rejected"}
            result = work_orders_collection.insert_one(work_order)
            return {"work_order_id": str(result.inserted_id), "work_order_status": "rejected"}

        parts_used = []
        parts_ordered = []
        for part in state.get("required_parts", []):
            reservation = await reserve_parts_fn(part["part_id"], part["quantity"])
            if reservation["shortfall"] > 0:
                parts_ordered.append({
                    "part_id": part["part_id"],
                    "name": part["name"],
                    "quantity": reservation["reserved"],
                    "shortfall": reservation["shortfall"],
                })
            else:
                parts_used.append({
                    "part_id": part["part_id"],
                    "name": part["name"],
                    "quantity": reservation["reserved"],
                })

        work_order = {**base_doc, "parts_used": parts_used, "parts_ordered": parts_ordered, "status": "completed"}
        result = work_orders_collection.insert_one(work_order)
        return {"work_order_id": str(result.inserted_id), "work_order_status": "completed"}

    return finalize_node
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_finalize_node.py -v`
Expected: PASS (3 passed)

- [ ] **Step 9: Commit**

```bash
git add backend/backend/graph/nodes/hitl_gate.py backend/backend/graph/nodes/finalize.py backend/tests/test_hitl_gate_node.py backend/tests/test_finalize_node.py backend/pyproject.toml
git commit -m "feat(backend): add HITL gate and finalize nodes"
```

## Task 9: Graph builder (wiring + checkpointing + full integration tests)

**Files:**
- Create: `backend/backend/graph/build.py`
- Test: `backend/tests/test_build_graph.py`

**Interfaces:**
- Consumes: `GraphState`, `make_extract_node`, `make_rag_lookup_node`, `make_inventory_check_node`, `hitl_gate_node`, `make_finalize_node` (Tasks 6-8); `LLMClient` (Task 1).
- Produces: `build_graph(llm, manuals_collection, work_orders_collection, checkpointer) -> CompiledStateGraph` — a `langgraph.graph.StateGraph(GraphState)` with all 5 nodes wired `START → extract →(conditional)→ rag_lookup →(conditional)→ inventory_check → hitl_gate → finalize → END`, compiled with the given `checkpointer`. Conditional edges: after `extract`, route to `END` if `needs_clarification` else `rag_lookup`; after `rag_lookup`, route to `END` if `no_procedure_found` else `inventory_check`.

This task's tests are the plan's integration tests (per the spec's Testing Approach): they run the **compiled graph end-to-end** with a `FakeLLMClient`, `mongomock` collections, and an **in-memory** checkpointer (`langgraph.checkpoint.memory.MemorySaver` — fast for tests; Task 10 wires the real `MongoDBSaver` for the API). **Verify** `MemorySaver`'s import path and `StateGraph`/`add_conditional_edges` signatures against the installed `langgraph` version first.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_build_graph.py`:

```python
import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
import mongomock

from backend.graph.build import build_graph
from backend.graph.nodes.extract import ExtractedError
from backend.graph.nodes.rag_lookup import DiagnosisResult, RequiredPart


def make_collections():
    client = mongomock.MongoClient()
    return client["machine_repair"]["manuals"], client["machine_repair"]["work_orders"]


@pytest.mark.asyncio
async def test_graph_ends_with_clarification_when_extraction_incomplete(fake_llm):
    llm = fake_llm(structured_responses=[ExtractedError(machine_id=None, error_code="E101", description="noise")])
    manuals, work_orders = make_collections()
    graph = build_graph(llm, manuals, work_orders, MemorySaver())
    config = {"configurable": {"thread_id": "t1"}}

    result = await graph.ainvoke({"user_input": "grinding noise, error E101"}, config)

    assert result["needs_clarification"] is True
    assert "work_order_id" not in result


@pytest.mark.asyncio
async def test_graph_completes_without_approval_when_parts_in_stock(fake_llm, monkeypatch):
    llm = fake_llm(structured_responses=[
        ExtractedError(machine_id="CNC-Mill-200", error_code="E101", description="grinding noise"),
        DiagnosisResult(
            diagnosis="Main spindle bearing wear",
            repair_steps=["Replace bearing"],
            required_parts=[RequiredPart(part_id="BEARING-X4", name="Bearing X4", quantity=1)],
        ),
    ])
    manuals, work_orders = make_collections()
    manuals.insert_one({"chunk_text": "bearing wear procedure", "machine_type": "CNC-Mill-200", "error_codes": ["E101"]})

    async def fake_check_stock(part_id):
        return {"part_id": part_id, "name": "Bearing X4", "qty_on_hand": 12, "reorder_threshold": 5, "status": "in_stock"}

    async def fake_reserve_parts(part_id, quantity):
        return {"part_id": part_id, "qty_on_hand": 11, "reserved": quantity, "shortfall": 0}

    monkeypatch.setattr("backend.graph.build.check_stock", fake_check_stock)
    monkeypatch.setattr("backend.graph.build.reserve_parts", fake_reserve_parts)
    monkeypatch.setattr("backend.graph.build.search_manuals", lambda collection, query_embedding, top_k=3: [
        {"chunk_text": "bearing wear procedure", "machine_type": "CNC-Mill-200", "error_codes": ["E101"]}
    ])
    monkeypatch.setattr("backend.graph.build.embed_text", lambda text: [0.1, 0.2])

    graph = build_graph(llm, manuals, work_orders, MemorySaver())
    config = {"configurable": {"thread_id": "t2"}}

    result = await graph.ainvoke({"user_input": "CNC mill E101 grinding noise"}, config)

    assert result["work_order_status"] == "completed"
    assert result["needs_approval"] is False


@pytest.mark.asyncio
async def test_graph_pauses_for_approval_and_resumes_when_approved(fake_llm, monkeypatch):
    llm = fake_llm(structured_responses=[
        ExtractedError(machine_id="Hydraulic-Press-9", error_code="H33", description="pressure loss"),
        DiagnosisResult(
            diagnosis="Hydraulic valve failure",
            repair_steps=["Replace valve"],
            required_parts=[RequiredPart(part_id="VALVE-H9", name="Hydraulic Valve H9", quantity=1)],
        ),
    ])
    manuals, work_orders = make_collections()

    async def fake_check_stock(part_id):
        return {"part_id": part_id, "name": "Hydraulic Valve H9", "qty_on_hand": 0, "reorder_threshold": 2, "status": "out_of_stock"}

    async def fake_reserve_parts(part_id, quantity):
        return {"part_id": part_id, "qty_on_hand": 0, "reserved": 0, "shortfall": quantity}

    monkeypatch.setattr("backend.graph.build.check_stock", fake_check_stock)
    monkeypatch.setattr("backend.graph.build.reserve_parts", fake_reserve_parts)
    monkeypatch.setattr("backend.graph.build.search_manuals", lambda collection, query_embedding, top_k=3: [
        {"chunk_text": "valve failure procedure", "machine_type": "Hydraulic-Press-9", "error_codes": ["H33"]}
    ])
    monkeypatch.setattr("backend.graph.build.embed_text", lambda text: [0.1, 0.2])

    graph = build_graph(llm, manuals, work_orders, MemorySaver())
    config = {"configurable": {"thread_id": "t3"}}

    first = await graph.ainvoke({"user_input": "press losing pressure, H33"}, config)
    assert "__interrupt__" in first
    interrupt_payload = first["__interrupt__"][0].value
    assert interrupt_payload["inventory_status"][0]["status"] == "out_of_stock"

    resumed = await graph.ainvoke(Command(resume="approved"), config)
    assert resumed["work_order_status"] == "completed"
    assert resumed["work_order_id"]


@pytest.mark.asyncio
async def test_graph_marks_rejected_when_approval_denied(fake_llm, monkeypatch):
    llm = fake_llm(structured_responses=[
        ExtractedError(machine_id="Hydraulic-Press-9", error_code="H33", description="pressure loss"),
        DiagnosisResult(
            diagnosis="Hydraulic valve failure",
            repair_steps=["Replace valve"],
            required_parts=[RequiredPart(part_id="VALVE-H9", name="Hydraulic Valve H9", quantity=1)],
        ),
    ])
    manuals, work_orders = make_collections()

    async def fake_check_stock(part_id):
        return {"part_id": part_id, "name": "Hydraulic Valve H9", "qty_on_hand": 0, "reorder_threshold": 2, "status": "out_of_stock"}

    async def fake_reserve_parts(part_id, quantity):
        raise AssertionError("must not reserve parts when rejected")

    monkeypatch.setattr("backend.graph.build.check_stock", fake_check_stock)
    monkeypatch.setattr("backend.graph.build.reserve_parts", fake_reserve_parts)
    monkeypatch.setattr("backend.graph.build.search_manuals", lambda collection, query_embedding, top_k=3: [
        {"chunk_text": "valve failure procedure", "machine_type": "Hydraulic-Press-9", "error_codes": ["H33"]}
    ])
    monkeypatch.setattr("backend.graph.build.embed_text", lambda text: [0.1, 0.2])

    graph = build_graph(llm, manuals, work_orders, MemorySaver())
    config = {"configurable": {"thread_id": "t4"}}

    await graph.ainvoke({"user_input": "press losing pressure, H33"}, config)
    resumed = await graph.ainvoke(Command(resume="rejected"), config)

    assert resumed["work_order_status"] == "rejected"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_build_graph.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.graph.build'`

- [ ] **Step 3: Implement `build.py`**

Create `backend/backend/graph/build.py` (note the module-level imports of `check_stock`, `reserve_parts`, `search_manuals`, `embed_text` — the tests above monkeypatch these exact names on `backend.graph.build`, so the node factories must be called with them as explicit defaults sourced from this module, not re-imported inside the node functions themselves):

```python
from langgraph.graph import END, START, StateGraph

from backend.graph.nodes.extract import make_extract_node
from backend.graph.nodes.finalize import make_finalize_node
from backend.graph.nodes.hitl_gate import hitl_gate_node
from backend.graph.nodes.inventory_check import make_inventory_check_node
from backend.graph.nodes.rag_lookup import make_rag_lookup_node
from backend.graph.state import GraphState
from backend.mcp_client import check_stock, reserve_parts
from backend.rag.embeddings import embed_text
from backend.rag.vector_search import search_manuals


def route_after_extract(state: GraphState) -> str:
    return END if state.get("needs_clarification") else "rag_lookup"


def route_after_rag_lookup(state: GraphState) -> str:
    return END if state.get("no_procedure_found") else "inventory_check"


def build_graph(llm, manuals_collection, work_orders_collection, checkpointer):
    graph = StateGraph(GraphState)

    graph.add_node("extract", make_extract_node(llm))
    graph.add_node(
        "rag_lookup",
        make_rag_lookup_node(llm, manuals_collection, embed_fn=embed_text, search_fn=search_manuals),
    )
    graph.add_node("inventory_check", make_inventory_check_node(check_stock_fn=check_stock))
    graph.add_node("hitl_gate", hitl_gate_node)
    graph.add_node("finalize", make_finalize_node(work_orders_collection, reserve_parts_fn=reserve_parts))

    graph.add_edge(START, "extract")
    graph.add_conditional_edges("extract", route_after_extract, {END: END, "rag_lookup": "rag_lookup"})
    graph.add_conditional_edges("rag_lookup", route_after_rag_lookup, {END: END, "inventory_check": "inventory_check"})
    graph.add_edge("inventory_check", "hitl_gate")
    graph.add_edge("hitl_gate", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile(checkpointer=checkpointer)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_build_graph.py -v`
Expected: PASS (4 passed). If `graph.ainvoke` on an interrupted run returns the interrupt differently than `{"__interrupt__": (Interrupt(...),)}` (e.g. raises instead of returning), adjust the test's assertion mechanics to match the verified real behavior — the graph wiring in `build.py` itself does not change either way.

- [ ] **Step 5: Run the full backend test suite**

Run: `cd backend && .venv/bin/pytest -v`
Expected: PASS (all tests from Tasks 1-9)

- [ ] **Step 6: Commit**

```bash
git add backend/backend/graph/build.py backend/tests/test_build_graph.py
git commit -m "feat(backend): wire graph nodes into a compiled, checkpointed StateGraph"
```

## Task 10: FastAPI app (PDF upload + WebSocket chat/approval)

**Files:**
- Create: `backend/backend/api/__init__.py`
- Create: `backend/backend/api/app.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: `build_graph` (Task 9), `OllamaClient`/`ClaudeClient` (Task 1), `get_manuals_collection`/`get_work_orders_collection`/`get_checkpoint_client` (Task 2).
- Produces: FastAPI `app` with `POST /upload` (multipart PDF upload, returns `{"extracted_text": str}` or a `400` with `{"detail": str}` if the PDF can't be read) and `WebSocket /ws/{thread_id}` (query param `backend: str = "local"`, chat/approval message loop, streams `node_update`/`approval_request`/`error` JSON events — an `error` event is sent, and the loop continues rather than crashing the connection, if the graph run raises (e.g. the MCP subprocess is unreachable), per the spec's "MCP unreachable → visible error, not silent failure" requirement).

**Verify** `langgraph.checkpoint.mongodb.MongoDBSaver`'s constructor against the installed `langgraph-checkpoint-mongodb` package before writing `app.py` — specifically whether it accepts a `db_name` parameter to keep checkpoints in the `machine_repair` database alongside `manuals`/`work_orders`, or whether it always manages its own database name. If there's no `db_name` parameter, use the package's default and note the actual checkpoint database name you observed in your report — this is informational for Plan 3's deployment notes, not a blocker.

Add to `backend/pyproject.toml`'s `dependencies`: `"langgraph-checkpoint-mongodb>=0.4.0"`, `"fastapi>=0.115"`, `"uvicorn[standard]>=0.32"`, `"python-multipart>=0.0.9"`, `"pypdf>=5.0"`. Add `"httpx>=0.27"` and `"pytest-httpx>=0.30"` (or equivalent, per FastAPI's `TestClient`/`websockets` testing docs — verify the current recommended test-client dependency for the installed `fastapi` version) to `dev` deps for testing the WebSocket endpoint.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_api.py`. This test suite builds the FastAPI app with fakes substituted for the graph's real dependencies (no live Ollama/Claude, MongoDB, or MCP subprocess), verifying the upload endpoint and the WebSocket message loop's shape:

```python
import io

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from backend.api.app import create_app
from backend.graph.nodes.extract import ExtractedError


def make_test_pdf_bytes(text: str) -> bytes:
    # pypdf's PdfWriter can't embed arbitrary text easily without reportlab;
    # this test instead verifies extraction handles an empty/blank PDF
    # gracefully (returns an empty string, not an error), which is the
    # behavior the graph's Extract node depends on.
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_upload_endpoint_returns_extracted_text():
    app = create_app(build_graph_fn=lambda *args, **kwargs: None)
    client = TestClient(app)

    pdf_bytes = make_test_pdf_bytes("irrelevant")
    response = client.post("/upload", files={"file": ("log.pdf", pdf_bytes, "application/pdf")})

    assert response.status_code == 200
    assert response.json() == {"extracted_text": ""}


def test_upload_endpoint_returns_400_for_unreadable_pdf():
    app = create_app(build_graph_fn=lambda *args, **kwargs: None)
    client = TestClient(app)

    response = client.post("/upload", files={"file": ("log.pdf", b"not a real pdf", "application/pdf")})

    assert response.status_code == 400
    assert "detail" in response.json()


def test_websocket_chat_streams_node_updates_and_final_result(fake_llm):
    llm = fake_llm(structured_responses=[
        ExtractedError(machine_id=None, error_code="E101", description="noise")
    ])

    def fake_build_graph(llm_arg, manuals, work_orders, checkpointer):
        from langgraph.checkpoint.memory import MemorySaver
        from backend.graph.build import build_graph as real_build_graph
        return real_build_graph(llm, manuals, work_orders, MemorySaver())

    app = create_app(
        build_graph_fn=fake_build_graph,
        llm_factory=lambda backend_choice: llm,
        manuals_collection_factory=lambda: __import__("mongomock").MongoClient()["machine_repair"]["manuals"],
        work_orders_collection_factory=lambda: __import__("mongomock").MongoClient()["machine_repair"]["work_orders"],
        checkpoint_client_factory=lambda: None,
    )
    client = TestClient(app)

    with client.websocket_connect("/ws/test-thread?backend=local") as websocket:
        websocket.send_json({"type": "chat", "content": "grinding noise, E101"})
        events = []
        while True:
            event = websocket.receive_json()
            events.append(event)
            if event["node"] == "extract" and event["data"].get("needs_clarification"):
                break

    assert any(e["node"] == "extract" for e in events)


def test_websocket_sends_error_event_when_graph_run_raises(fake_llm):
    def failing_build_graph(llm_arg, manuals, work_orders, checkpointer):
        class ExplodingGraph:
            async def astream(self, *args, **kwargs):
                raise RuntimeError("MCP server unreachable")
                yield  # pragma: no cover - makes this an async generator

        return ExplodingGraph()

    app = create_app(
        build_graph_fn=failing_build_graph,
        llm_factory=lambda backend_choice: fake_llm(),
        manuals_collection_factory=lambda: object(),
        work_orders_collection_factory=lambda: object(),
        checkpoint_client_factory=lambda: None,
    )
    client = TestClient(app)

    with client.websocket_connect("/ws/test-thread-2?backend=local") as websocket:
        websocket.send_json({"type": "chat", "content": "anything"})
        event = websocket.receive_json()

    assert event["type"] == "error"
    assert "MCP server unreachable" in event["message"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.api.app'`

- [ ] **Step 3: Implement `app.py`**

Create `backend/backend/api/__init__.py` (empty) and `backend/backend/api/app.py`. The `create_app` factory takes dependency-injected factories so tests can substitute fakes, while the default arguments wire the real Task 1/2/9 implementations for actual runs:

```python
import io
import json

from fastapi import FastAPI, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from langgraph.checkpoint.mongodb import MongoDBSaver
from langgraph.types import Command
from pypdf import PdfReader

from backend.db import get_checkpoint_client, get_manuals_collection, get_work_orders_collection
from backend.graph.build import build_graph as default_build_graph
from backend.llm.claude_client import ClaudeClient
from backend.llm.ollama_client import OllamaClient


def default_llm_factory(backend_choice: str):
    if backend_choice == "cloud":
        return ClaudeClient()
    return OllamaClient()


def create_app(
    build_graph_fn=default_build_graph,
    llm_factory=default_llm_factory,
    manuals_collection_factory=get_manuals_collection,
    work_orders_collection_factory=get_work_orders_collection,
    checkpoint_client_factory=get_checkpoint_client,
):
    app = FastAPI()

    @app.post("/upload")
    async def upload_pdf(file: UploadFile):
        contents = await file.read()
        try:
            reader = PdfReader(io.BytesIO(contents))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Could not read this PDF — please paste the error description as text instead. ({exc})",
            )
        return {"extracted_text": text}

    @app.websocket("/ws/{thread_id}")
    async def websocket_chat(websocket: WebSocket, thread_id: str, backend: str = "local"):
        await websocket.accept()
        llm = llm_factory(backend)
        checkpoint_client = checkpoint_client_factory()
        checkpointer = MongoDBSaver(checkpoint_client) if checkpoint_client is not None else __import__(
            "langgraph.checkpoint.memory", fromlist=["MemorySaver"]
        ).MemorySaver()
        graph = build_graph_fn(
            llm, manuals_collection_factory(), work_orders_collection_factory(), checkpointer
        )
        config = {"configurable": {"thread_id": thread_id}}

        try:
            while True:
                raw = await websocket.receive_text()
                message = json.loads(raw)

                if message["type"] == "chat":
                    graph_input = {"user_input": message["content"], "pdf_text": message.get("pdf_text")}
                elif message["type"] == "approval":
                    graph_input = Command(resume=message["decision"])
                else:
                    continue

                try:
                    async for chunk in graph.astream(graph_input, config, stream_mode="updates"):
                        if "__interrupt__" in chunk:
                            payload = chunk["__interrupt__"][0].value
                            await websocket.send_json({"type": "approval_request", "payload": payload})
                        else:
                            for node_name, update in chunk.items():
                                await websocket.send_json({"type": "node_update", "node": node_name, "data": update})
                except Exception as exc:
                    await websocket.send_json({"type": "error", "message": str(exc)})
        except WebSocketDisconnect:
            pass

    return app


app = create_app()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_api.py -v`
Expected: PASS (4 passed). If `TestClient`'s WebSocket testing API differs from what's used above for the installed `fastapi`/`starlette` version, adjust the test's mechanics only — verify against the installed version's docs first.

- [ ] **Step 5: Run the full backend test suite one more time**

Run: `cd backend && .venv/bin/pytest -v`
Expected: PASS (all tests, all 10 tasks)

- [ ] **Step 6: Manually verify the live path (requires a reachable MongoDB and either Ollama running locally or an Anthropic API key)**

```bash
# Terminal 1: seed and leave the MCP server reachable via PATH
cd mcp_server && MONGODB_URI="<uri>" .venv/bin/mcp-inventory-server seed

# Terminal 2: seed manuals
cd backend && MONGODB_URI="<uri>" .venv/bin/python -c "
from backend.db import get_manuals_collection
from backend.rag.manuals_seed import seed_manuals
print(seed_manuals(get_manuals_collection()))
"

# Terminal 3: run the API (ensure mcp-inventory-server's venv is on PATH, or install both packages into one shared venv)
cd backend && MONGODB_URI="<uri>" .venv/bin/uvicorn backend.api.app:app --reload
```

Then connect a WebSocket client (e.g. `websocat` or a short Python script) to `ws://localhost:8000/ws/demo-1?backend=local`, send `{"type": "chat", "content": "CNC mill throwing error E101, loud grinding noise from the spindle"}`, and confirm `node_update` events stream back, ending in either a `work_order_id` or an `approval_request`. This exercises the real Ollama call, real Atlas Vector Search (requires the `manuals_vector_index` to exist on the `manuals` collection — create it via the Atlas UI/CLI first, indexing the `embedding` field, 384 dimensions, cosine similarity), and the real MCP subprocess — note any gaps found in your report, mirroring Plan 1's documented live-verification gap.

- [ ] **Step 7: Commit**

```bash
git add backend/backend/api/ backend/tests/test_api.py backend/pyproject.toml
git commit -m "feat(backend): add FastAPI app with PDF upload and WebSocket chat/approval"
```

---

## Handoff to Plan 3

Plan 3 (frontend) will connect to `POST /upload` for PDF error logs and `WebSocket /ws/{thread_id}?backend=local|cloud` for chat. WebSocket message shapes:
- Client → server: `{"type": "chat", "content": str, "pdf_text"?: str}` or `{"type": "approval", "decision": "approved"|"rejected"}`.
- Server → client: `{"type": "node_update", "node": str, "data": dict}` (one per graph superstep — the live execution graph panel should light up `node` and show `data`'s contents in its tool-call log), `{"type": "approval_request", "payload": {"required_parts": [...], "inventory_status": [...]}}`, or `{"type": "error", "message": str}` (the graph run failed — e.g. the MCP subprocess was unreachable; show this in the log panel as a visible error rather than a silent stall, and the connection stays open so the technician can retry).

`MONGODB_URI`, `MONGODB_DB` (optional, defaults to `machine_repair`), and `ANTHROPIC_API_KEY` (only needed when a session selects `backend=cloud`) must be set in the environment the API server runs in. `mcp-inventory-server` must be on `PATH` (installing both `mcp_server` and `backend` packages into one shared virtualenv is the simplest way to achieve this for local development).
