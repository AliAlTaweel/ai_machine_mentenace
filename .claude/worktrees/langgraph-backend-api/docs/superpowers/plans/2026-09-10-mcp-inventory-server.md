# MCP Inventory Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone MCP server exposing spare-parts inventory tools (`check_stock`, `reserve_parts`) backed by MongoDB, with synthetic seed data, usable independently of the rest of the agent (plan 1 of 3: MCP server → LangGraph backend+API → Frontend).

**Architecture:** A Python package (`mcp_server/`) with pure functions for the inventory logic (`tools.py`), a thin MongoDB accessor (`db.py`), a synthetic data seeder (`seed_data.py`), and an MCP server entrypoint (`server.py`) built on the official MCP Python SDK's `FastMCP`, exposed over stdio transport. Business logic is tested directly against a `mongomock` collection so tests don't require a live database.

**Tech Stack:** Python 3.11+, `mcp` (official Python SDK), `pymongo`, `mongomock` (test-only), `pytest`.

**Spec:** docs/superpowers/specs/2026-09-10-industrial-maintenance-agent-design.md

## Global Constraints

- MCP server must be standalone (a separate process/server, not an in-process tool call) — per spec Approach A.
- Inventory collection schema: `part_id`, `name`, `qty_on_hand`, `reorder_threshold`, `machine_types[]` — per spec's Data Model section.
- Transport is stdio (local process, spawned by the LangGraph backend in plan 2) — no network transport needed for this demo.
- Seed data is synthetic (no real inventory system) — per spec Non-Goals.

---

## File Structure

```
mcp_server/
  pyproject.toml
  mcp_server/
    __init__.py
    db.py            # MongoDB connection + collection accessor
    tools.py          # check_stock, reserve_parts — pure logic, mongomock-testable
    seed_data.py       # synthetic parts list + seed() function
    server.py         # FastMCP server wiring stdio-exposed tools
  tests/
    conftest.py        # mongomock collection fixture
    test_tools.py
    test_seed_data.py
```

## Task 1: Project scaffolding + `check_stock`

**Files:**
- Create: `mcp_server/pyproject.toml`
- Create: `mcp_server/mcp_server/__init__.py`
- Create: `mcp_server/mcp_server/tools.py`
- Create: `mcp_server/tests/conftest.py`
- Test: `mcp_server/tests/test_tools.py`

**Interfaces:**
- Produces: `check_stock(collection, part_id: str) -> PartStatus` where `PartStatus` is a dataclass with fields `part_id: str, name: str, qty_on_hand: int, reorder_threshold: int, status: str` (`status` ∈ `"in_stock" | "low_stock" | "out_of_stock"`). Raises `ValueError` if `part_id` is unknown.

- [ ] **Step 1: Create the package scaffolding**

Create `mcp_server/pyproject.toml`:

```toml
[project]
name = "mcp-inventory-server"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.2.0",
    "pymongo>=4.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "mongomock>=4.1",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Create `mcp_server/mcp_server/__init__.py` (empty file).

- [ ] **Step 2: Install dependencies**

```bash
cd mcp_server && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

- [ ] **Step 3: Write the mongomock fixture**

Create `mcp_server/tests/conftest.py`:

```python
import mongomock
import pytest


@pytest.fixture
def inventory_collection():
    client = mongomock.MongoClient()
    collection = client["machine_repair"]["inventory"]
    collection.insert_many([
        {
            "part_id": "BEARING-X4",
            "name": "Bearing X4",
            "qty_on_hand": 12,
            "reorder_threshold": 5,
            "machine_types": ["CNC-Mill-200"],
        },
        {
            "part_id": "BELT-A7",
            "name": "Conveyor Belt A7",
            "qty_on_hand": 2,
            "reorder_threshold": 3,
            "machine_types": ["Conveyor-Belt-A7"],
        },
        {
            "part_id": "VALVE-H9",
            "name": "Hydraulic Valve H9",
            "qty_on_hand": 0,
            "reorder_threshold": 2,
            "machine_types": ["Hydraulic-Press-9"],
        },
    ])
    return collection
```

- [ ] **Step 4: Write the failing test for `check_stock`**

Create `mcp_server/tests/test_tools.py`:

```python
import pytest

from mcp_server.tools import check_stock


def test_check_stock_in_stock(inventory_collection):
    result = check_stock(inventory_collection, "BEARING-X4")
    assert result.part_id == "BEARING-X4"
    assert result.qty_on_hand == 12
    assert result.status == "in_stock"


def test_check_stock_low_stock(inventory_collection):
    result = check_stock(inventory_collection, "BELT-A7")
    assert result.status == "low_stock"


def test_check_stock_out_of_stock(inventory_collection):
    result = check_stock(inventory_collection, "VALVE-H9")
    assert result.status == "out_of_stock"


def test_check_stock_unknown_part_raises(inventory_collection):
    with pytest.raises(ValueError, match="Unknown part_id"):
        check_stock(inventory_collection, "NOPE-1")
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `cd mcp_server && .venv/bin/pytest tests/test_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mcp_server.tools'`

- [ ] **Step 6: Implement `check_stock`**

Create `mcp_server/mcp_server/tools.py`:

```python
from dataclasses import dataclass


@dataclass
class PartStatus:
    part_id: str
    name: str
    qty_on_hand: int
    reorder_threshold: int
    status: str


def check_stock(collection, part_id: str) -> PartStatus:
    doc = collection.find_one({"part_id": part_id})
    if doc is None:
        raise ValueError(f"Unknown part_id: {part_id}")

    qty = doc["qty_on_hand"]
    threshold = doc["reorder_threshold"]
    if qty <= 0:
        status = "out_of_stock"
    elif qty <= threshold:
        status = "low_stock"
    else:
        status = "in_stock"

    return PartStatus(
        part_id=doc["part_id"],
        name=doc["name"],
        qty_on_hand=qty,
        reorder_threshold=threshold,
        status=status,
    )
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd mcp_server && .venv/bin/pytest tests/test_tools.py -v`
Expected: PASS (4 passed)

- [ ] **Step 8: Commit**

```bash
git add mcp_server/pyproject.toml mcp_server/mcp_server/__init__.py mcp_server/mcp_server/tools.py mcp_server/tests/conftest.py mcp_server/tests/test_tools.py
git commit -m "feat(mcp-server): add check_stock inventory tool"
```

## Task 2: `reserve_parts`

**Files:**
- Modify: `mcp_server/mcp_server/tools.py`
- Test: `mcp_server/tests/test_tools.py`

**Interfaces:**
- Consumes: `inventory_collection` fixture from Task 1.
- Produces: `reserve_parts(collection, part_id: str, quantity: int) -> dict` returning `{"part_id": str, "qty_on_hand": int}` after decrementing stock (floored at 0). Raises `ValueError` if `part_id` is unknown.

- [ ] **Step 1: Write the failing test**

Append to `mcp_server/tests/test_tools.py`:

```python
from mcp_server.tools import reserve_parts


def test_reserve_parts_decrements_stock(inventory_collection):
    result = reserve_parts(inventory_collection, "BEARING-X4", 3)
    assert result == {"part_id": "BEARING-X4", "qty_on_hand": 9}


def test_reserve_parts_floors_at_zero(inventory_collection):
    result = reserve_parts(inventory_collection, "BELT-A7", 10)
    assert result == {"part_id": "BELT-A7", "qty_on_hand": 0}


def test_reserve_parts_unknown_part_raises(inventory_collection):
    with pytest.raises(ValueError, match="Unknown part_id"):
        reserve_parts(inventory_collection, "NOPE-1", 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp_server && .venv/bin/pytest tests/test_tools.py -v`
Expected: FAIL with `ImportError: cannot import name 'reserve_parts'`

- [ ] **Step 3: Implement `reserve_parts`**

Add to `mcp_server/mcp_server/tools.py`:

```python
def reserve_parts(collection, part_id: str, quantity: int) -> dict:
    doc = collection.find_one({"part_id": part_id})
    if doc is None:
        raise ValueError(f"Unknown part_id: {part_id}")

    new_qty = max(doc["qty_on_hand"] - quantity, 0)
    collection.update_one({"part_id": part_id}, {"$set": {"qty_on_hand": new_qty}})
    return {"part_id": part_id, "qty_on_hand": new_qty}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd mcp_server && .venv/bin/pytest tests/test_tools.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add mcp_server/mcp_server/tools.py mcp_server/tests/test_tools.py
git commit -m "feat(mcp-server): add reserve_parts inventory tool"
```

## Task 3: MongoDB accessor (`db.py`)

**Files:**
- Create: `mcp_server/mcp_server/db.py`
- Test: `mcp_server/tests/test_db.py`

**Interfaces:**
- Consumes: environment variables `MONGODB_URI` (required), `MONGODB_DB` (optional, default `"machine_repair"`).
- Produces: `get_inventory_collection(client: pymongo.MongoClient | None = None)` returning the `inventory` collection of the configured database. If `client` is not passed, constructs one from `MONGODB_URI`.

- [ ] **Step 1: Write the failing test**

Create `mcp_server/tests/test_db.py`:

```python
import mongomock

from mcp_server.db import get_inventory_collection


def test_get_inventory_collection_uses_injected_client():
    client = mongomock.MongoClient()
    collection = get_inventory_collection(client=client, db_name="test_db")
    assert collection.name == "inventory"
    assert collection.database.name == "test_db"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp_server && .venv/bin/pytest tests/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mcp_server.db'`

- [ ] **Step 3: Implement `db.py`**

Create `mcp_server/mcp_server/db.py`:

```python
import os

from pymongo import MongoClient


def get_inventory_collection(client: MongoClient | None = None, db_name: str | None = None):
    if client is None:
        client = MongoClient(os.environ["MONGODB_URI"])
    resolved_db_name = db_name or os.environ.get("MONGODB_DB", "machine_repair")
    return client[resolved_db_name]["inventory"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd mcp_server && .venv/bin/pytest tests/test_db.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add mcp_server/mcp_server/db.py mcp_server/tests/test_db.py
git commit -m "feat(mcp-server): add MongoDB inventory collection accessor"
```

## Task 4: Synthetic seed data

**Files:**
- Create: `mcp_server/mcp_server/seed_data.py`
- Test: `mcp_server/tests/test_seed_data.py`

**Interfaces:**
- Consumes: `get_inventory_collection` from Task 3 (via dependency injection of a collection, not by importing `db.py` directly, to keep the function testable with `mongomock`).
- Produces: `SAMPLE_PARTS: list[dict]` (module-level constant, each dict matching the `inventory` schema) and `seed(collection, parts: list[dict] = SAMPLE_PARTS) -> int` which upserts every part by `part_id` and returns the count seeded.

- [ ] **Step 1: Write the failing test**

Create `mcp_server/tests/test_seed_data.py`:

```python
import mongomock

from mcp_server.seed_data import SAMPLE_PARTS, seed


def test_seed_inserts_all_sample_parts():
    client = mongomock.MongoClient()
    collection = client["machine_repair"]["inventory"]

    count = seed(collection)

    assert count == len(SAMPLE_PARTS)
    assert collection.count_documents({}) == len(SAMPLE_PARTS)


def test_seed_is_idempotent():
    client = mongomock.MongoClient()
    collection = client["machine_repair"]["inventory"]

    seed(collection)
    seed(collection)

    assert collection.count_documents({}) == len(SAMPLE_PARTS)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp_server && .venv/bin/pytest tests/test_seed_data.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mcp_server.seed_data'`

- [ ] **Step 3: Implement `seed_data.py`**

Create `mcp_server/mcp_server/seed_data.py`:

```python
SAMPLE_PARTS = [
    {
        "part_id": "BEARING-X4",
        "name": "Bearing X4",
        "qty_on_hand": 12,
        "reorder_threshold": 5,
        "machine_types": ["CNC-Mill-200"],
    },
    {
        "part_id": "BELT-A7",
        "name": "Conveyor Belt A7",
        "qty_on_hand": 2,
        "reorder_threshold": 3,
        "machine_types": ["Conveyor-Belt-A7"],
    },
    {
        "part_id": "VALVE-H9",
        "name": "Hydraulic Valve H9",
        "qty_on_hand": 0,
        "reorder_threshold": 2,
        "machine_types": ["Hydraulic-Press-9"],
    },
    {
        "part_id": "MOTOR-C2",
        "name": "Drive Motor C2",
        "qty_on_hand": 4,
        "reorder_threshold": 1,
        "machine_types": ["CNC-Mill-200", "Conveyor-Belt-A7"],
    },
    {
        "part_id": "SEAL-K1",
        "name": "Hydraulic Seal Kit K1",
        "qty_on_hand": 1,
        "reorder_threshold": 2,
        "machine_types": ["Hydraulic-Press-9"],
    },
]


def seed(collection, parts: list[dict] = SAMPLE_PARTS) -> int:
    count = 0
    for part in parts:
        collection.update_one(
            {"part_id": part["part_id"]},
            {"$set": part},
            upsert=True,
        )
        count += 1
    return count
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd mcp_server && .venv/bin/pytest tests/test_seed_data.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add mcp_server/mcp_server/seed_data.py mcp_server/tests/test_seed_data.py
git commit -m "feat(mcp-server): add synthetic inventory seed data"
```

## Task 5: MCP server entrypoint

**Files:**
- Create: `mcp_server/mcp_server/server.py`
- Create: `mcp_server/mcp_server/cli.py`
- Test: `mcp_server/tests/test_server.py`

**Interfaces:**
- Consumes: `check_stock`, `reserve_parts` from Task 1/2 (`mcp_server.tools`); `get_inventory_collection` from Task 3 (`mcp_server.db`).
- Produces: module-level `mcp = FastMCP("inventory-server")` instance in `server.py` with two registered tools, `check_stock_tool(part_id: str) -> dict` and `reserve_parts_tool(part_id: str, quantity: int) -> dict`; `cli.py` provides a `main()` that runs the server over stdio and a `seed()` subcommand that seeds the database (invoked as `python -m mcp_server.cli seed` or `python -m mcp_server.cli serve`).

- [ ] **Step 1: Write the failing test**

Create `mcp_server/tests/test_server.py`:

```python
import asyncio

from mcp_server.server import mcp


def test_server_registers_expected_tools():
    tools = asyncio.run(mcp.list_tools())
    tool_names = {tool.name for tool in tools}
    assert tool_names == {"check_stock_tool", "reserve_parts_tool"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp_server && .venv/bin/pytest tests/test_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mcp_server.server'`

- [ ] **Step 3: Implement `server.py`**

Create `mcp_server/mcp_server/server.py`:

```python
from mcp.server.fastmcp import FastMCP

from mcp_server.db import get_inventory_collection
from mcp_server.tools import check_stock, reserve_parts

mcp = FastMCP("inventory-server")


@mcp.tool()
def check_stock_tool(part_id: str) -> dict:
    """Check current stock level and status for a spare part by its part_id."""
    collection = get_inventory_collection()
    result = check_stock(collection, part_id)
    return {
        "part_id": result.part_id,
        "name": result.name,
        "qty_on_hand": result.qty_on_hand,
        "reorder_threshold": result.reorder_threshold,
        "status": result.status,
    }


@mcp.tool()
def reserve_parts_tool(part_id: str, quantity: int) -> dict:
    """Reserve (decrement stock for) a given quantity of a spare part."""
    collection = get_inventory_collection()
    return reserve_parts(collection, part_id, quantity)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd mcp_server && .venv/bin/pytest tests/test_server.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Implement the CLI entrypoint (no test — thin wiring, exercised manually in Step 6)**

Create `mcp_server/mcp_server/cli.py`:

```python
import sys

from mcp_server.db import get_inventory_collection
from mcp_server.seed_data import seed
from mcp_server.server import mcp


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "seed":
        collection = get_inventory_collection()
        count = seed(collection)
        print(f"Seeded {count} parts into the inventory collection.")
        return

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Manually verify the CLI runs (requires a local MongoDB or Atlas URI in `MONGODB_URI`)**

```bash
cd mcp_server && MONGODB_URI="<your-mongodb-uri>" .venv/bin/python -m mcp_server.cli seed
```

Expected output: `Seeded 5 parts into the inventory collection.`

- [ ] **Step 7: Run the full test suite**

Run: `cd mcp_server && .venv/bin/pytest -v`
Expected: PASS (all tests from Tasks 1-5)

- [ ] **Step 8: Commit**

```bash
git add mcp_server/mcp_server/server.py mcp_server/mcp_server/cli.py mcp_server/tests/test_server.py
git commit -m "feat(mcp-server): add FastMCP stdio server entrypoint and CLI"
```

---

## Handoff to Plan 2

Plan 2 (LangGraph backend + API) will spawn this server as a subprocess via
`python -m mcp_server.cli` (stdio transport) and use an MCP client to call
`check_stock_tool` / `reserve_parts_tool` from the Inventory Check and
Finalize nodes. `MONGODB_URI` and `MONGODB_DB` must be set in the
environment the backend spawns this process in.
