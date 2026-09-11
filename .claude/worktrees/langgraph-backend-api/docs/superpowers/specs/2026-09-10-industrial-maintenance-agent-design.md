# Industrial Machinery Maintenance & Diagnostics Agent — Design

## Purpose

A portfolio/demo project showcasing an agentic AI architecture: a factory
technician reports a machine error (text or PDF log), and an agent diagnoses
the fault via RAG over technical manuals, checks spare-parts inventory
through an MCP server, pauses for human approval when parts must be ordered,
and generates a work order on approval.

This is a demo, not a production tool: correctness of "business logic" (real
manuals, real inventory) matters less than demonstrating the agentic
patterns — LangGraph state machine, RAG, MCP tool use, human-in-the-loop
pause/resume, and a live execution visualization — well.

## Goals

- Demonstrate a LangGraph-based agentic workflow with real checkpointed
  pause/resume for human-in-the-loop approval.
- Demonstrate MCP as a genuine client/server integration (standalone MCP
  server, not an in-process tool call).
- Demonstrate RAG via MongoDB Atlas Vector Search over synthetic technical
  manuals.
- Provide a swappable LLM backend (local Ollama/Gemma default, Claude API
  alternative) behind one interface.
- Provide a frontend with a chat interface and a real-time visualization of
  the agent's execution graph (active node, tool call log).

## Non-Goals

- Production concerns: auth/authorization, multi-tenant roles, audit
  compliance, horizontal scaling.
- OCR for scanned/image-based PDFs — only text-extractable PDFs are
  supported.
- Real technical manuals or a real inventory system — both are synthetic
  seed data generated for the demo.
- Separate supervisor login/role — the same chat session shows the approval
  card inline (single simulated user plays both roles).

## Architecture

```
React frontend (chat + live execution graph)
        │  WebSocket (chat + graph events + approve/reject) + REST (session, PDF upload)
        ▼
FastAPI backend
   ├─ LangGraph state machine, checkpointed to MongoDB (langgraph-checkpoint-mongodb)
   │     Node1: Extract → Node2: RAG lookup → Node3: Check inventory (MCP client)
   │     → Node4: HITL pause/resume → Node5: Finalize work order
   ├─ LLM interface: Ollama/Gemma (default) or Claude API, selected via
   │     per-session config, single abstraction (`LLMClient`) used by all nodes
   └─ Event emitter → WebSocket → frontend graph viz
        │
        ▼ MCP protocol (stdio transport)
MCP inventory server (Python, official MCP SDK)
   └─ tools: check_stock(part_id), reserve_parts(part_ids)
        │
        ▼
MongoDB Atlas
   - manuals            (chunked text + embedding vector + metadata; vector index)
   - inventory          (part_id, name, qty_on_hand, reorder_threshold, machine_types[])
   - work_orders        (machine_id, error_code, diagnosis, parts_used[], parts_ordered[], status, created_at)
   - checkpoints        (LangGraph checkpoint collection)
```

## Workflow Nodes

1. **Extract** — Input is chat text and/or an uploaded PDF (text parsed via
   `pypdf`). LLM extracts `{machine_id, error_code, description}` as
   structured output. Missing/ambiguous fields route back to the user via
   chat for clarification instead of failing.
2. **RAG lookup** — Embed the error description, query the `manuals` vector
   index for top-k procedure chunks, and have the LLM synthesize a
   diagnosis, repair steps, and a required-parts list. If no relevant
   procedure is found, the LLM must say so explicitly rather than
   fabricate a diagnosis (prompt-enforced fallback path).
3. **Inventory check** — For each required part, call the MCP server's
   `check_stock` tool. Produces a per-part status: in stock / low / out of
   stock.
4. **HITL gate** — If any part is low/out of stock, the graph interrupts
   (LangGraph `interrupt`), state is checkpointed, and an approval card
   (proposed parts order) is pushed into the chat UI. The graph resumes on
   approve/reject. If all parts are in stock, this node is a no-op passthrough.
5. **Finalize** — Writes a `work_order` document (diagnosis, parts
   used/ordered, status, timestamps). Status is `completed` if no approval
   was needed or it was approved, `pending_parts` if approved-but-awaiting
   delivery is modeled as immediate-complete for demo purposes, or
   `rejected` if the supervisor rejected the order.

## LLM Backend Abstraction

A single `LLMClient` interface (structured-output-capable: `.generate()`,
`.generate_structured(schema)`) with two implementations:
- `OllamaClient` (default) — talks to a local Ollama instance running
  `gemma:4b` (or closest available tag).
- `ClaudeClient` — Anthropic API, selected via the same interface.

Selection is a per-session setting, sent from the frontend at session start
and stored in the LangGraph run config; nodes never branch on backend
choice directly. Because local Gemma-4B is weaker at strict structured
output, extraction schemas are kept small (3 fields) and a
retry-with-reformatting-instructions step is added if the model returns
invalid JSON.

## Frontend / UI

- **Layout**: left panel = chat (messages, text input, PDF upload, inline
  approval cards with Approve/Reject buttons); right panel = live execution
  graph — 5 fixed boxes (Extract → RAG → Inventory → HITL Gate → Finalize)
  rendered with plain CSS/flexbox (no diagramming library — a fixed 5-node
  layout doesn't need one), state-driven styling (idle/active/done/error),
  plus a scrolling tool-call log beneath (e.g. `MCP: check_stock(part=Bearing-X4)
  → low stock`).
- **Settings**: LLM backend toggle (Local Gemma / Claude API), sent to the
  backend at session start.
- **Transport**: one WebSocket per chat session carries chat messages, graph
  state events, and approve/reject actions. REST endpoints handle session
  creation and PDF upload only.
- **Tech**: React + Vite.

## Data Model (MongoDB Atlas)

| Collection | Fields |
|---|---|
| `manuals` | `chunk_text`, `embedding`, `machine_type`, `error_codes[]` |
| `inventory` | `part_id`, `name`, `qty_on_hand`, `reorder_threshold`, `machine_types[]` |
| `work_orders` | `machine_id`, `error_code`, `diagnosis`, `parts_used[]`, `parts_ordered[]`, `status`, `created_at` |
| `checkpoints` | LangGraph's own schema, via `langgraph-checkpoint-mongodb` |

Seed data: a synthetic set of a few machine types, error codes, and repair
procedures (manuals) plus a matching inventory list, generated as part of
setup rather than sourced externally.

## Error Handling

- Extraction failure/ambiguity → clarifying question back to the user, not
  a hard failure.
- PDF parse failure (corrupt/scanned/image-only) → chat error asking for a
  text description instead; no OCR fallback.
- No matching manual found → explicit "no relevant procedure found"
  response rather than a fabricated diagnosis.
- MCP server unreachable → inventory node surfaces a tool error in the log
  panel and the graph halts in a visible error state rather than silently
  continuing.
- Invalid structured output from local Gemma → one retry with reformatting
  instructions before surfacing an error.

## Testing Approach

- **Backend**: unit tests per LangGraph node with mocked LLM/MCP calls; one
  integration test running the full graph end-to-end against a stubbed LLM
  and a seeded local/test MongoDB.
- **MCP server**: unit tests directly against its tool handlers.
- **Frontend**: component tests for chat, the approval card, and the graph
  panel. No heavy e2e suite given portfolio scope; a manual test script
  will be included instead.

## Open Items For Implementation Planning

- Exact Ollama model tag availability for "Gemma 4B" (confirm during setup).
- Choice of embedding model for vector search (must be available locally
  and compatible with Atlas Vector Search dimensions).
