# Frontend (Phase 3) — Design

## Purpose

Build the React frontend for the industrial machinery maintenance agent: a
chat interface for technicians to report errors (text or PDF), an inline
approval card for the human-in-the-loop parts-order gate, and a live
visualization of the LangGraph execution graph — completing the three-phase
plan (MCP server → LangGraph backend + API → **Frontend**).

**Spec:** docs/superpowers/specs/2026-09-10-industrial-maintenance-agent-design.md
(parent design — this spec implements its "Frontend / UI" section against
the backend contract actually built in Phase 2.)

**Plan 2 handoff (already built, on `main`):** `backend/` exposes a FastAPI
app (`backend.api.app:app`) with:
- `POST /upload` — multipart PDF upload. Returns `{"extracted_text": str}`
  on success; `400` with a `detail` message on unreadable/scanned PDFs.
- `WS /ws/{thread_id}?backend=local|cloud` — one socket per chat session.
  `thread_id` is a client-generated session id; `backend` selects the LLM
  (`local` = Ollama, `cloud` = Claude), read once at connect time.

## Goals

- Implement the spec's two-panel layout: chat (left) + live execution graph
  (right), backed by the real WebSocket event stream from Phase 2.
- Render the 5 fixed workflow nodes (Extract → RAG → Inventory → HITL Gate →
  Finalize) with idle/active/done/error styling driven by `node_update`
  events, plus a scrolling tool-call log.
- Render the HITL approval card inline in chat from `approval_request`
  events, and send the technician's decision back over the same socket.
- Support PDF upload (via `POST /upload`, then send extracted text as a
  chat message) alongside plain text chat input.
- Provide the LLM backend toggle (Local Gemma / Claude API) as a per-session
  setting sent at WebSocket connect time.
- Component tests for chat, approval card, and graph panel per the parent
  spec's testing approach.

## Non-Goals

- Auth/login, multi-user/multi-session management, or a separate
  supervisor UI — carried forward from the parent spec's non-goals.
- A diagramming library for the graph panel — plain CSS/flexbox per parent
  spec (5 fixed nodes don't need one).
- Heavy e2e test suite — component tests only, per parent spec.
- Offline support, retries/reconnection beyond a visible error state,
  or persisting chat history client-side across page reloads.
- Streaming token-by-token LLM output — `node_update` events carry a node's
  full output once the node completes, not incremental text.

## Architecture

```
┌───────────────────────────────────────────────------────---──────┐
│ App (React + Vite + TypeScript)                                  │
│                                                                  │
│  ┌─────────────────---──┐   ┌─────────────────────────----──┐    │
│  │ ChatPanel            │   │ GraphPanel                    │    │
│  │  - MessageList       │   │  - 5 NodeBox components       │    │
│  │  - ApprovalCard      │   │    (idle/active/done/error)   │    │
│  │    (inline in list)  │   │  - ToolCallLog (scrolling)    │    │
│  │  - ChatInput         │   │                               │    │
│  │  - PdfUpload         │   │                               │    │
│  └──────────┬───────────┘   └──────────────┬───────────----─┘    │
│             │  dispatch actions            │  read state         │
│             ▼                              ▼                     │
│  ┌────────────────────────────────────────────────────-------─┐  │
│  │ Zustand store (sessionStore)                               │  │
│  │  - messages: ChatMessage[]                                 │  │
│  │  - pendingApproval: ApprovalRequest | null                 │  │
│  │  - nodeStatus: Record<NodeName, NodeState>                 │  │
│  │  - toolCallLog: ToolCallEntry[]                            │  │
│  │  - connectionStatus: 'connecting'|'open'|'closed'|'error'  │  │
│  │  - llmBackend: 'local' | 'cloud'                           │  │
│  └─────────────────────────────────────────────────────-------┘  │
│             ▲                              │                    │
│             │  events                       │  ws.send(json)     │
│  ┌──────────┴──────────────────────────────────────────┐       │
│  │ useSessionSocket (WebSocket hook)                     │       │
│  │  connects to /ws/{thread_id}?backend=...              │       │
│  └─────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────┘
        │ WebSocket (chat/approval in, node_update/                │ REST
        │ approval_request/error out)                                │ POST /upload
        ▼                                                            ▼
                      FastAPI backend (Phase 2, on main)
```

`thread_id` is generated client-side (`crypto.randomUUID()`) once per page
load and used for the socket's whole lifetime — no session persistence
across reloads (Non-Goals).

## Components

- **`App`** — top-level layout: `SettingsBar` + `ChatPanel` + `GraphPanel`
  as CSS grid columns. Owns the `useSessionSocket` hook and provides the
  Zustand store via its module-level singleton (no React Context needed —
  Zustand stores are importable directly).
- **`SettingsBar`** — LLM backend toggle (Local Gemma / Claude API radio or
  switch). Disabled after the socket connects (backend is read once at
  connect time server-side, so switching mid-session would silently do
  nothing — the UI must not imply it works).
- **`ChatPanel`**
  - `MessageList` — renders `messages` from the store in order; a message
    is either a chat bubble (`role: 'user' | 'assistant'`) or, when its
    `kind` is `'approval'`, renders `ApprovalCard` inline at that position
    in the transcript.
  - `ApprovalCard` — shows `required_parts` / `inventory_status` from the
    `approval_request` payload; Approve/Reject buttons send
    `{type: "approval", decision: "approve" | "reject"}` and then disable
    themselves (a decision is terminal for that request).
  - `ChatInput` — text input + send button; also accepts Enter-to-send.
    Sends `{type: "chat", content, pdf_text?}`.
  - `PdfUpload` — file input restricted to `.pdf`; on selection, POSTs to
    `/upload`, then either attaches `extracted_text` to the next chat send
    or auto-sends it with a placeholder message — resolved as an
    implementation task, not a spec ambiguity, since both are one line of
    behavior difference.
- **`GraphPanel`**
  - `NodeBox` × 5 (Extract, RAG lookup, Inventory check, HITL Gate,
    Finalize) — visual state from `nodeStatus[nodeName]`.
  - `ToolCallLog` — appends a line per relevant `node_update` (e.g. the
    inventory check node's MCP call result); scrolls, newest at bottom.

## Data Flow / WebSocket Contract

Client → server (JSON text frames):
```ts
{ type: "chat", content: string, pdf_text?: string }
{ type: "approval", decision: "approve" | "reject" }
```

Server → client:
```ts
{ type: "node_update", node: string, data: Partial<GraphState> }
{ type: "approval_request", payload: { required_parts: Part[], inventory_status: InventoryStatus[] } }
{ type: "error", message: string }
```

Node name → `NodeBox` mapping is a fixed lookup table (`extract`,
`rag_lookup`, `inventory_check`, `hitl_gate`, `finalize` — the LangGraph
node names from `backend/backend/graph/build.py` — to the 5 display boxes).
A `node_update` for a given node transitions it `idle → active → done`; a
subsequent `error`-type message transitions the **currently active** node
(tracked in store state) to `error` rather than guessing which node failed,
since the backend's error event carries no node name.

`approval_request` both (a) pushes an `ApprovalCard` message into
`messages` and (b) sets `pendingApproval`, so the HITL Gate `NodeBox` can
show "awaiting approval" without re-deriving it from the transcript.

On WebSocket connect, `App` sends nothing — the backend starts the graph
run only on receiving the first `chat` message, matching the existing
`websocket_chat` handler (it loops on `receive_text`, no greeting frame).

## Error Handling

- **Upload failure** (`400` from `/upload`): show the `detail` message as
  an inline system message in chat (not a toast) — keeps the error in the
  technician's workflow context, consistent with the backend's own
  chat-first error philosophy (parent spec's Error Handling section).
- **`{type: "error"}` over the socket** (setup failure, malformed client
  message, or a graph-run exception): render as a system message in chat
  and mark the active node `error` (see above). The socket is **not**
  closed by the backend for mid-run errors (only for unrecoverable setup
  failures, which close after sending the error) — the UI must handle
  both: a post-error socket that's still usable, and one that closes.
- **Socket closed/disconnected**: `connectionStatus` → `'closed'`; disable
  `ChatInput` and `ApprovalCard` buttons, show a system message. No
  auto-reconnect (Non-Goals) — the technician reloads the page to start a
  new session/`thread_id`.
- **Malformed/unexpected server frame** (JSON parse failure or unknown
  `type`): log to console and ignore the frame rather than crashing the
  UI — the backend contract is closed (3 message types) but defensive
  parsing costs nothing.

## Testing Approach

- **Vitest + React Testing Library**, per parent spec's "component tests
  for chat, approval card, graph panel" — no e2e suite.
- `ChatPanel`: renders messages in order, sends `chat` frames with correct
  shape on submit, renders `ApprovalCard` inline when a message has
  `kind: 'approval'`.
- `ApprovalCard`: renders parts/inventory data from a fixture payload,
  sends the correct `approval` frame on click, disables both buttons after
  a decision.
- `GraphPanel`: `NodeBox` state transitions (idle→active→done→error) given
  a sequence of fixture `node_update`/`error` events; `ToolCallLog` appends
  in order.
- `useSessionSocket`: tested against a mock `WebSocket` (e.g.
  `vitest`'s `vi.stubGlobal` or a small fake) verifying outgoing frame
  shape and store updates on each incoming message type.
- No test requires a live backend — all WebSocket/REST interaction is
  mocked at the boundary.

## Tech Stack

React 18, Vite, TypeScript, Tailwind CSS, Zustand, Vitest, React Testing
Library. Native `fetch`/`WebSocket` — no additional HTTP or WS client
library.

## File Structure (indicative — finalized in the implementation plan)

```
frontend/
  package.json
  vite.config.ts
  tailwind.config.js
  src/
    main.tsx
    App.tsx
    store/
      sessionStore.ts        # Zustand store + types
    hooks/
      useSessionSocket.ts
    components/
      SettingsBar.tsx
      ChatPanel/
        ChatPanel.tsx
        MessageList.tsx
        ApprovalCard.tsx
        ChatInput.tsx
        PdfUpload.tsx
      GraphPanel/
        GraphPanel.tsx
        NodeBox.tsx
        ToolCallLog.tsx
  tests/
    ChatPanel.test.tsx
    ApprovalCard.test.tsx
    GraphPanel.test.tsx
    useSessionSocket.test.ts
```

## Open Items For Implementation Planning

- Exact UX for PDF upload → chat send (auto-send extracted text vs.
  attach-and-let-user-press-send) — noted above as an implementation
  detail, to be decided while implementing `PdfUpload`.
- Dev-time CORS/proxy config (Vite dev server proxying `/upload` and
  `/ws` to the FastAPI backend) — standard Vite `server.proxy` config,
  detailed in the implementation plan rather than this spec.
