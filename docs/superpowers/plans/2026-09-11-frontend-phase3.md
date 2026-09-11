# Frontend (Phase 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the React/Vite/TypeScript frontend — chat + PDF upload, inline HITL approval card, and a live 5-node execution graph with tool-call log — against the Phase 2 FastAPI backend's real WebSocket/REST contract, completing the three-phase plan (MCP server → LangGraph backend + API → **Frontend**).

**Architecture:** A single-page React app (`frontend/`) with one Zustand store (`sessionStore`) as the source of truth for chat messages, per-node graph state, the tool-call log, and connection status. A `useSessionSocket` hook owns the single WebSocket connection and translates server frames into store updates / user actions into client frames. Presentational components (`ChatPanel`, `GraphPanel`, `SettingsBar`) read from the store and never touch the socket directly.

**Tech Stack:** React 18, Vite 5, TypeScript 5, Tailwind CSS 3, Zustand 4, Vitest 2 + React Testing Library 16. Native `fetch`/`WebSocket` — no additional HTTP/WS client library.

**Spec:** docs/superpowers/specs/2026-09-11-frontend-phase3-design.md

## Global Constraints

- Two-panel layout: chat (left) + live execution graph (right) — per spec's Architecture section.
- Exactly 5 fixed graph nodes (`extract`, `rag_lookup`, `inventory_check`, `hitl_gate`, `finalize`) rendered with plain CSS/Tailwind, no diagramming library — per spec's Non-Goals.
- One WebSocket per session at `/ws/{thread_id}?backend=local|cloud`; REST is used only for `POST /upload` — per spec's Data Flow section and Phase 2's `backend/backend/api/app.py`.
- `thread_id` is generated client-side once per page load (`crypto.randomUUID()`); no session persistence across reloads — per spec's Architecture section.
- LLM backend is a per-session setting read once at WS connect time; the toggle is disabled once the socket leaves the `connecting` state — per spec's Components section (`SettingsBar`).
- No auto-reconnect: on socket close, disable chat input and approval buttons and show a system message — per spec's Error Handling section.
- `{type: "error"}` frames mark the store's `activeNode` as `error` and render as an inline chat system message, not a toast — per spec's Error Handling section.
- Component tests only (Vitest + React Testing Library), no e2e suite — per spec's Testing Approach section.
- PDF upload attaches extracted text to the chat input rather than auto-sending it, so the technician can add context before sending — per spec's Open Items resolution.

---

## File Structure

```
frontend/
  package.json
  vite.config.ts
  tsconfig.json
  tsconfig.node.json
  tailwind.config.js
  postcss.config.js
  index.html
  tests/
    setup.ts
    App.test.tsx
    sessionStore.test.ts
    useSessionSocket.test.tsx
    NodeBox.test.tsx
    ToolCallLog.test.tsx
    GraphPanel.test.tsx
    ApprovalCard.test.tsx
    MessageList.test.tsx
    ChatInput.test.tsx
    PdfUpload.test.tsx
  src/
    main.tsx
    App.tsx
    index.css
    store/
      sessionStore.ts
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
```

---

## Task 1: Project scaffolding

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/index.css`
- Create: `frontend/tests/setup.ts`
- Test: `frontend/tests/App.test.tsx`

**Interfaces:**
- Produces: `App` (default export from `src/App.tsx`) — a placeholder component in this task, replaced with the full integration in Task 7.
- Produces: dev server proxy for `/upload` and `/ws` to `http://localhost:8000` / `ws://localhost:8000` — later tasks' fetch/WebSocket calls use relative paths and rely on this proxy in dev.

- [ ] **Step 1: Create `frontend/package.json`**

```json
{
  "name": "frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "zustand": "^4.5.4"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.4.8",
    "@testing-library/react": "^16.0.0",
    "@testing-library/user-event": "^14.5.2",
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "autoprefixer": "^10.4.19",
    "jsdom": "^24.1.1",
    "postcss": "^8.4.40",
    "tailwindcss": "^3.4.7",
    "typescript": "^5.5.4",
    "vite": "^5.4.0",
    "vitest": "^2.0.5"
  }
}
```

- [ ] **Step 2: Create `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src", "tests"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **Step 3: Create `frontend/tsconfig.node.json`**

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 4: Create `frontend/vite.config.ts`**

```ts
/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/upload': 'http://localhost:8000',
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './tests/setup.ts',
  },
});
```

- [ ] **Step 5: Create `frontend/tailwind.config.js` and `frontend/postcss.config.js`**

`frontend/tailwind.config.js`:

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {},
  },
  plugins: [],
};
```

`frontend/postcss.config.js`:

```js
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 6: Create `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/index.css`**

`frontend/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Machine Repair AI</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`frontend/src/index.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

`frontend/src/main.tsx`:

```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

- [ ] **Step 7: Create the placeholder `frontend/src/App.tsx`**

```tsx
export default function App() {
  return (
    <div className="flex h-screen items-center justify-center text-lg font-medium">
      Machine Repair AI
    </div>
  );
}
```

- [ ] **Step 8: Create `frontend/tests/setup.ts`**

```ts
import '@testing-library/jest-dom/vitest';
```

- [ ] **Step 9: Write the failing smoke test**

Create `frontend/tests/App.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import App from '../src/App';

describe('App', () => {
  it('renders the app title', () => {
    render(<App />);
    expect(screen.getByText('Machine Repair AI')).toBeInTheDocument();
  });
});
```

- [ ] **Step 10: Install dependencies**

```bash
cd frontend && npm install
```

- [ ] **Step 11: Run the test to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS — 1 test passed.

- [ ] **Step 12: Commit**

```bash
git add frontend/
git commit -m "chore(frontend): scaffold Vite + React + TypeScript + Tailwind + Vitest"
```

---

## Task 2: Session store

**Files:**
- Create: `frontend/src/store/sessionStore.ts`
- Test: `frontend/tests/sessionStore.test.ts`

**Interfaces:**
- Consumes: nothing (pure Zustand store, no dependency on other app code).
- Produces:
  - `NodeName = 'extract' | 'rag_lookup' | 'inventory_check' | 'hitl_gate' | 'finalize'`
  - `NODE_ORDER: NodeName[]` (fixed order, used by `GraphPanel` in Task 4)
  - `NodeState = 'idle' | 'active' | 'done' | 'error'`
  - `ConnectionStatus = 'connecting' | 'open' | 'closed' | 'error'`
  - `ApprovalRequestPayload { required_parts: Record<string, unknown>[]; inventory_status: Array<{ part_id: string; status: string; [key: string]: unknown }> }`
  - `ChatMessage { id: string; kind: 'user' | 'assistant' | 'system' | 'approval'; content?: string; approval?: ApprovalRequestPayload; decision?: 'approve' | 'reject' }`
  - `ToolCallEntry { id: string; text: string }`
  - `ServerEvent` — discriminated union of `node_update` / `approval_request` / `error`, matching the backend's WS frames.
  - `useSessionStore` — Zustand hook exposing `SessionState` (`messages`, `nodeStatus`, `activeNode`, `pendingApproval`, `toolCallLog`, `connectionStatus`, `llmBackend`, and actions `setLlmBackend`, `setConnectionStatus`, `addUserMessage`, `handleServerEvent`, `setApprovalDecision`) — consumed by `useSessionSocket` (Task 3) and every UI component (Tasks 4-7).

- [ ] **Step 1: Write the failing tests**

Create `frontend/tests/sessionStore.test.ts`:

```ts
import { beforeEach, describe, expect, it } from 'vitest';
import { NODE_ORDER, useSessionStore } from '../src/store/sessionStore';

const initialState = useSessionStore.getState();

beforeEach(() => {
  useSessionStore.setState(initialState, true);
});

describe('sessionStore', () => {
  it('addUserMessage appends a user message and activates extract', () => {
    useSessionStore.getState().addUserMessage('bearing is grinding');

    const state = useSessionStore.getState();
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0]).toMatchObject({ kind: 'user', content: 'bearing is grinding' });
    expect(state.nodeStatus.extract).toBe('active');
    expect(state.activeNode).toBe('extract');
  });

  it('node_update marks the node done and advances the next node to active', () => {
    useSessionStore.getState().addUserMessage('bearing is grinding');

    useSessionStore.getState().handleServerEvent({
      type: 'node_update',
      node: 'extract',
      data: {},
    });

    const state = useSessionStore.getState();
    expect(state.nodeStatus.extract).toBe('done');
    expect(state.nodeStatus.rag_lookup).toBe('active');
    expect(state.activeNode).toBe('rag_lookup');
  });

  it('node_update for inventory_check appends tool call log entries', () => {
    useSessionStore.getState().addUserMessage('bearing is grinding');

    useSessionStore.getState().handleServerEvent({
      type: 'node_update',
      node: 'inventory_check',
      data: {
        inventory_status: [{ part_id: 'BEARING-X4', status: 'low_stock' }],
      },
    });

    const state = useSessionStore.getState();
    expect(state.toolCallLog).toHaveLength(1);
    expect(state.toolCallLog[0].text).toBe(
      'MCP: check_stock(part=BEARING-X4) → low_stock'
    );
  });

  it('node_update for finalize leaves no active node', () => {
    useSessionStore.getState().addUserMessage('bearing is grinding');

    useSessionStore.getState().handleServerEvent({
      type: 'node_update',
      node: 'finalize',
      data: {},
    });

    const state = useSessionStore.getState();
    NODE_ORDER.forEach((node) => expect(state.nodeStatus[node]).toBe('done'));
    expect(state.activeNode).toBeNull();
  });

  it('approval_request sets hitl_gate active, pendingApproval, and an approval message', () => {
    const payload = {
      required_parts: [{ part_id: 'BEARING-X4', quantity: 2 }],
      inventory_status: [{ part_id: 'BEARING-X4', status: 'low_stock' }],
    };

    useSessionStore.getState().handleServerEvent({ type: 'approval_request', payload });

    const state = useSessionStore.getState();
    expect(state.pendingApproval).toEqual(payload);
    expect(state.nodeStatus.hitl_gate).toBe('active');
    expect(state.activeNode).toBe('hitl_gate');
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0]).toMatchObject({ kind: 'approval', approval: payload });
  });

  it('error marks the active node as error and adds a system message', () => {
    useSessionStore.getState().addUserMessage('bearing is grinding');

    useSessionStore.getState().handleServerEvent({ type: 'error', message: 'MCP unreachable' });

    const state = useSessionStore.getState();
    expect(state.nodeStatus.extract).toBe('error');
    expect(state.messages[1]).toMatchObject({ kind: 'system', content: 'MCP unreachable' });
  });

  it('setApprovalDecision resolves pendingApproval and records the decision on the message', () => {
    const payload = { required_parts: [], inventory_status: [] };
    useSessionStore.getState().handleServerEvent({ type: 'approval_request', payload });

    useSessionStore.getState().setApprovalDecision('approve');

    const state = useSessionStore.getState();
    expect(state.pendingApproval).toBeNull();
    expect(state.messages[0].decision).toBe('approve');
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test`
Expected: FAIL with "Cannot find module '../src/store/sessionStore'".

- [ ] **Step 3: Implement the store**

Create `frontend/src/store/sessionStore.ts`:

```ts
import { create } from 'zustand';

export type NodeName = 'extract' | 'rag_lookup' | 'inventory_check' | 'hitl_gate' | 'finalize';

export const NODE_ORDER: NodeName[] = [
  'extract',
  'rag_lookup',
  'inventory_check',
  'hitl_gate',
  'finalize',
];

export type NodeState = 'idle' | 'active' | 'done' | 'error';
export type ConnectionStatus = 'connecting' | 'open' | 'closed' | 'error';

export interface ApprovalRequestPayload {
  required_parts: Record<string, unknown>[];
  inventory_status: Array<{ part_id: string; status: string; [key: string]: unknown }>;
}

export interface ChatMessage {
  id: string;
  kind: 'user' | 'assistant' | 'system' | 'approval';
  content?: string;
  approval?: ApprovalRequestPayload;
  decision?: 'approve' | 'reject';
}

export interface ToolCallEntry {
  id: string;
  text: string;
}

export type ServerEvent =
  | { type: 'node_update'; node: string; data: Record<string, unknown> }
  | { type: 'approval_request'; payload: ApprovalRequestPayload }
  | { type: 'error'; message: string };

let nextId = 0;
function newId(): string {
  nextId += 1;
  return `msg-${nextId}`;
}

function initialNodeStatus(): Record<NodeName, NodeState> {
  return {
    extract: 'idle',
    rag_lookup: 'idle',
    inventory_check: 'idle',
    hitl_gate: 'idle',
    finalize: 'idle',
  };
}

export interface SessionState {
  messages: ChatMessage[];
  nodeStatus: Record<NodeName, NodeState>;
  activeNode: NodeName | null;
  pendingApproval: ApprovalRequestPayload | null;
  toolCallLog: ToolCallEntry[];
  connectionStatus: ConnectionStatus;
  llmBackend: 'local' | 'cloud';

  setLlmBackend: (backend: 'local' | 'cloud') => void;
  setConnectionStatus: (status: ConnectionStatus) => void;
  addUserMessage: (content: string) => void;
  handleServerEvent: (event: ServerEvent) => void;
  setApprovalDecision: (decision: 'approve' | 'reject') => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  messages: [],
  nodeStatus: initialNodeStatus(),
  activeNode: null,
  pendingApproval: null,
  toolCallLog: [],
  connectionStatus: 'connecting',
  llmBackend: 'local',

  setLlmBackend: (backend) => set({ llmBackend: backend }),

  setConnectionStatus: (status) => set({ connectionStatus: status }),

  addUserMessage: (content) => {
    set((state) => ({
      messages: [...state.messages, { id: newId(), kind: 'user', content }],
      nodeStatus: { ...initialNodeStatus(), extract: 'active' },
      activeNode: 'extract',
      pendingApproval: null,
      toolCallLog: [],
    }));
  },

  handleServerEvent: (event) => {
    if (event.type === 'node_update') {
      const node = event.node as NodeName;
      if (!NODE_ORDER.includes(node)) return;

      set((state) => {
        const fromIndex = state.activeNode ? NODE_ORDER.indexOf(state.activeNode) : 0;
        const toIndex = NODE_ORDER.indexOf(node);
        const nodeStatus = { ...state.nodeStatus };
        for (let i = fromIndex; i <= toIndex; i += 1) {
          nodeStatus[NODE_ORDER[i]] = 'done';
        }
        const nextIndex = toIndex + 1;
        const nextNode = nextIndex < NODE_ORDER.length ? NODE_ORDER[nextIndex] : null;
        if (nextNode) nodeStatus[nextNode] = 'active';

        const inventoryStatus = event.data.inventory_status;
        const toolCallLog =
          node === 'inventory_check' && Array.isArray(inventoryStatus)
            ? [
                ...state.toolCallLog,
                ...(inventoryStatus as Array<{ part_id: string; status: string }>).map((item) => ({
                  id: newId(),
                  text: `MCP: check_stock(part=${item.part_id}) → ${item.status}`,
                })),
              ]
            : state.toolCallLog;

        return { nodeStatus, activeNode: nextNode, toolCallLog };
      });
      return;
    }

    if (event.type === 'approval_request') {
      set((state) => ({
        pendingApproval: event.payload,
        nodeStatus: { ...state.nodeStatus, hitl_gate: 'active' },
        activeNode: 'hitl_gate',
        messages: [...state.messages, { id: newId(), kind: 'approval', approval: event.payload }],
      }));
      return;
    }

    set((state) => ({
      messages: [...state.messages, { id: newId(), kind: 'system', content: event.message }],
      nodeStatus: state.activeNode
        ? { ...state.nodeStatus, [state.activeNode]: 'error' }
        : state.nodeStatus,
    }));
  },

  setApprovalDecision: (decision) => {
    set((state) => {
      const messages = [...state.messages];
      for (let i = messages.length - 1; i >= 0; i -= 1) {
        if (messages[i].kind === 'approval' && messages[i].decision === undefined) {
          messages[i] = { ...messages[i], decision };
          break;
        }
      }
      return { messages, pendingApproval: null };
    });
  },
}));
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm test`
Expected: PASS — all `sessionStore` tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/store/sessionStore.ts frontend/tests/sessionStore.test.ts
git commit -m "feat(frontend): add session store with graph-state and chat-message transitions"
```

---

## Task 3: `useSessionSocket` hook

**Files:**
- Create: `frontend/src/hooks/useSessionSocket.ts`
- Test: `frontend/tests/useSessionSocket.test.tsx`

**Interfaces:**
- Consumes: `useSessionStore`, `ServerEvent` from Task 2 (`src/store/sessionStore.ts`).
- Produces: `useSessionSocket(threadId: string, backend: 'local' | 'cloud'): { sendChat: (content: string, pdfText?: string) => void; sendApproval: (decision: 'approve' | 'reject') => void }` — consumed by `App` in Task 7.

- [ ] **Step 1: Write the failing tests**

Create `frontend/tests/useSessionSocket.test.tsx`:

```tsx
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useSessionStore } from '../src/store/sessionStore';
import { useSessionSocket } from '../src/hooks/useSessionSocket';

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.onclose?.();
  }
}

const initialState = useSessionStore.getState();

beforeEach(() => {
  useSessionStore.setState(initialState, true);
  FakeWebSocket.instances = [];
  vi.stubGlobal('WebSocket', FakeWebSocket);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useSessionSocket', () => {
  it('opens a socket to the thread URL and updates connectionStatus on open', () => {
    renderHook(() => useSessionSocket('thread-1', 'local'));

    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(FakeWebSocket.instances[0].url).toContain('/ws/thread-1?backend=local');

    act(() => {
      FakeWebSocket.instances[0].onopen?.();
    });

    expect(useSessionStore.getState().connectionStatus).toBe('open');
  });

  it('sendChat appends a user message and sends a chat frame', () => {
    const { result } = renderHook(() => useSessionSocket('thread-1', 'local'));

    act(() => {
      result.current.sendChat('bearing is grinding');
    });

    expect(useSessionStore.getState().messages[0]).toMatchObject({
      kind: 'user',
      content: 'bearing is grinding',
    });
    const sentFrame = JSON.parse(FakeWebSocket.instances[0].sent[0]);
    expect(sentFrame).toEqual({ type: 'chat', content: 'bearing is grinding', pdf_text: undefined });
  });

  it('sendApproval resolves the pending approval and sends an approval frame', () => {
    const { result } = renderHook(() => useSessionSocket('thread-1', 'local'));
    useSessionStore.getState().handleServerEvent({
      type: 'approval_request',
      payload: { required_parts: [], inventory_status: [] },
    });

    act(() => {
      result.current.sendApproval('approve');
    });

    expect(useSessionStore.getState().pendingApproval).toBeNull();
    const sentFrame = JSON.parse(FakeWebSocket.instances[0].sent[0]);
    expect(sentFrame).toEqual({ type: 'approval', decision: 'approve' });
  });

  it('routes incoming node_update frames into the store', () => {
    renderHook(() => useSessionSocket('thread-1', 'local'));
    useSessionStore.getState().addUserMessage('bearing is grinding');

    act(() => {
      FakeWebSocket.instances[0].onmessage?.({
        data: JSON.stringify({ type: 'node_update', node: 'extract', data: {} }),
      });
    });

    expect(useSessionStore.getState().nodeStatus.extract).toBe('done');
  });

  it('sets connectionStatus to closed when the socket closes', () => {
    renderHook(() => useSessionSocket('thread-1', 'local'));

    act(() => {
      FakeWebSocket.instances[0].onclose?.();
    });

    expect(useSessionStore.getState().connectionStatus).toBe('closed');
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test`
Expected: FAIL with "Cannot find module '../src/hooks/useSessionSocket'".

- [ ] **Step 3: Implement the hook**

Create `frontend/src/hooks/useSessionSocket.ts`:

```ts
import { useEffect, useRef } from 'react';
import { useSessionStore, type ServerEvent } from '../store/sessionStore';

export interface UseSessionSocketResult {
  sendChat: (content: string, pdfText?: string) => void;
  sendApproval: (decision: 'approve' | 'reject') => void;
}

export function useSessionSocket(
  threadId: string,
  backend: 'local' | 'cloud'
): UseSessionSocketResult {
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/ws/${threadId}?backend=${backend}`;
    const socket = new WebSocket(url);
    socketRef.current = socket;

    socket.onopen = () => useSessionStore.getState().setConnectionStatus('open');
    socket.onclose = () => useSessionStore.getState().setConnectionStatus('closed');
    socket.onerror = () => useSessionStore.getState().setConnectionStatus('error');
    socket.onmessage = (event) => {
      let parsed: ServerEvent;
      try {
        parsed = JSON.parse(event.data);
      } catch {
        return;
      }
      if (
        parsed.type !== 'node_update' &&
        parsed.type !== 'approval_request' &&
        parsed.type !== 'error'
      ) {
        return;
      }
      useSessionStore.getState().handleServerEvent(parsed);
    };

    return () => socket.close();
  }, [threadId, backend]);

  const sendChat = (content: string, pdfText?: string) => {
    useSessionStore.getState().addUserMessage(content);
    socketRef.current?.send(JSON.stringify({ type: 'chat', content, pdf_text: pdfText }));
  };

  const sendApproval = (decision: 'approve' | 'reject') => {
    useSessionStore.getState().setApprovalDecision(decision);
    socketRef.current?.send(JSON.stringify({ type: 'approval', decision }));
  };

  return { sendChat, sendApproval };
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm test`
Expected: PASS — all `useSessionSocket` tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useSessionSocket.ts frontend/tests/useSessionSocket.test.tsx
git commit -m "feat(frontend): add useSessionSocket WebSocket hook"
```

---

## Task 4: Graph panel (`NodeBox`, `ToolCallLog`, `GraphPanel`)

**Files:**
- Create: `frontend/src/components/GraphPanel/NodeBox.tsx`
- Create: `frontend/src/components/GraphPanel/ToolCallLog.tsx`
- Create: `frontend/src/components/GraphPanel/GraphPanel.tsx`
- Test: `frontend/tests/NodeBox.test.tsx`
- Test: `frontend/tests/ToolCallLog.test.tsx`
- Test: `frontend/tests/GraphPanel.test.tsx`

**Interfaces:**
- Consumes: `NodeName`, `NodeState`, `NODE_ORDER`, `ToolCallEntry`, `useSessionStore` from Task 2.
- Produces: `NodeBox({ node, state }: { node: NodeName; state: NodeState })`, `ToolCallLog({ entries }: { entries: ToolCallEntry[] })`, `GraphPanel()` (no props, reads the store directly) — `GraphPanel` consumed by `App` in Task 7.

- [ ] **Step 1: Write the failing `NodeBox` test**

Create `frontend/tests/NodeBox.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { NodeBox } from '../src/components/GraphPanel/NodeBox';

describe('NodeBox', () => {
  it('renders the node label', () => {
    render(<NodeBox node="rag_lookup" state="idle" />);
    expect(screen.getByText('RAG Lookup')).toBeInTheDocument();
  });

  it('applies the active state styling', () => {
    render(<NodeBox node="extract" state="active" />);
    expect(screen.getByTestId('node-extract')).toHaveClass('bg-blue-100');
  });

  it('applies the error state styling', () => {
    render(<NodeBox node="finalize" state="error" />);
    expect(screen.getByTestId('node-finalize')).toHaveClass('bg-red-100');
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL with "Cannot find module '../src/components/GraphPanel/NodeBox'".

- [ ] **Step 3: Implement `NodeBox`**

Create `frontend/src/components/GraphPanel/NodeBox.tsx`:

```tsx
import type { NodeName, NodeState } from '../../store/sessionStore';

const LABELS: Record<NodeName, string> = {
  extract: 'Extract',
  rag_lookup: 'RAG Lookup',
  inventory_check: 'Inventory Check',
  hitl_gate: 'HITL Gate',
  finalize: 'Finalize',
};

const STATE_CLASSES: Record<NodeState, string> = {
  idle: 'bg-gray-100 text-gray-500 border-gray-300',
  active: 'bg-blue-100 text-blue-700 border-blue-500 animate-pulse',
  done: 'bg-green-100 text-green-700 border-green-500',
  error: 'bg-red-100 text-red-700 border-red-500',
};

export interface NodeBoxProps {
  node: NodeName;
  state: NodeState;
}

export function NodeBox({ node, state }: NodeBoxProps) {
  return (
    <div
      data-testid={`node-${node}`}
      className={`rounded border px-3 py-2 text-sm font-medium ${STATE_CLASSES[state]}`}
    >
      {LABELS[node]}
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS — `NodeBox` tests pass.

- [ ] **Step 5: Write the failing `ToolCallLog` test**

Create `frontend/tests/ToolCallLog.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ToolCallLog } from '../src/components/GraphPanel/ToolCallLog';

describe('ToolCallLog', () => {
  it('renders entries in order', () => {
    render(
      <ToolCallLog
        entries={[
          { id: '1', text: 'MCP: check_stock(part=A) → in_stock' },
          { id: '2', text: 'MCP: check_stock(part=B) → low_stock' },
        ]}
      />
    );

    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent('MCP: check_stock(part=A) → in_stock');
    expect(items[1]).toHaveTextContent('MCP: check_stock(part=B) → low_stock');
  });
});
```

- [ ] **Step 6: Run the test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL with "Cannot find module '../src/components/GraphPanel/ToolCallLog'".

- [ ] **Step 7: Implement `ToolCallLog`**

Create `frontend/src/components/GraphPanel/ToolCallLog.tsx`:

```tsx
import type { ToolCallEntry } from '../../store/sessionStore';

export interface ToolCallLogProps {
  entries: ToolCallEntry[];
}

export function ToolCallLog({ entries }: ToolCallLogProps) {
  return (
    <ul data-testid="tool-call-log" className="mt-4 space-y-1 overflow-y-auto text-xs text-gray-600">
      {entries.map((entry) => (
        <li key={entry.id}>{entry.text}</li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 8: Run the test to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS — `ToolCallLog` tests pass.

- [ ] **Step 9: Write the failing `GraphPanel` test**

Create `frontend/tests/GraphPanel.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { useSessionStore } from '../src/store/sessionStore';
import { GraphPanel } from '../src/components/GraphPanel/GraphPanel';

const initialState = useSessionStore.getState();

beforeEach(() => {
  useSessionStore.setState(initialState, true);
});

describe('GraphPanel', () => {
  it('renders all 5 nodes and the tool call log from the store', () => {
    useSessionStore.setState({
      nodeStatus: {
        extract: 'done',
        rag_lookup: 'done',
        inventory_check: 'active',
        hitl_gate: 'idle',
        finalize: 'idle',
      },
      toolCallLog: [{ id: '1', text: 'MCP: check_stock(part=A) → in_stock' }],
    });

    render(<GraphPanel />);

    expect(screen.getByTestId('node-extract')).toHaveClass('bg-green-100');
    expect(screen.getByTestId('node-inventory_check')).toHaveClass('bg-blue-100');
    expect(screen.getByText('MCP: check_stock(part=A) → in_stock')).toBeInTheDocument();
  });
});
```

- [ ] **Step 10: Run the test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL with "Cannot find module '../src/components/GraphPanel/GraphPanel'".

- [ ] **Step 11: Implement `GraphPanel`**

Create `frontend/src/components/GraphPanel/GraphPanel.tsx`:

```tsx
import { NODE_ORDER, useSessionStore } from '../../store/sessionStore';
import { NodeBox } from './NodeBox';
import { ToolCallLog } from './ToolCallLog';

export function GraphPanel() {
  const nodeStatus = useSessionStore((s) => s.nodeStatus);
  const toolCallLog = useSessionStore((s) => s.toolCallLog);

  return (
    <div className="flex h-full flex-col overflow-y-auto p-4">
      <div className="flex flex-col gap-2">
        {NODE_ORDER.map((node) => (
          <NodeBox key={node} node={node} state={nodeStatus[node]} />
        ))}
      </div>
      <ToolCallLog entries={toolCallLog} />
    </div>
  );
}
```

- [ ] **Step 12: Run the test to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS — all `GraphPanel` tests pass.

- [ ] **Step 13: Commit**

```bash
git add frontend/src/components/GraphPanel frontend/tests/NodeBox.test.tsx frontend/tests/ToolCallLog.test.tsx frontend/tests/GraphPanel.test.tsx
git commit -m "feat(frontend): add GraphPanel with NodeBox and ToolCallLog"
```

---

## Task 5: Chat message list and approval card

**Files:**
- Create: `frontend/src/components/ChatPanel/ApprovalCard.tsx`
- Create: `frontend/src/components/ChatPanel/MessageList.tsx`
- Test: `frontend/tests/ApprovalCard.test.tsx`
- Test: `frontend/tests/MessageList.test.tsx`

**Interfaces:**
- Consumes: `ApprovalRequestPayload`, `ChatMessage` from Task 2.
- Produces: `ApprovalCard({ payload, decision, onDecide }: { payload: ApprovalRequestPayload; decision?: 'approve' | 'reject'; onDecide: (decision: 'approve' | 'reject') => void })`, `MessageList({ messages, onDecide }: { messages: ChatMessage[]; onDecide: (decision: 'approve' | 'reject') => void })` — both consumed by `ChatPanel` in Task 7.

- [ ] **Step 1: Write the failing `ApprovalCard` test**

Create `frontend/tests/ApprovalCard.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ApprovalCard } from '../src/components/ChatPanel/ApprovalCard';

const payload = {
  required_parts: [{ part_id: 'BEARING-X4', quantity: 2 }],
  inventory_status: [{ part_id: 'BEARING-X4', status: 'low_stock' }],
};

describe('ApprovalCard', () => {
  it('renders inventory status and calls onDecide on Approve', async () => {
    const onDecide = vi.fn();
    render(<ApprovalCard payload={payload} onDecide={onDecide} />);

    expect(screen.getByText(/BEARING-X4: low_stock/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Approve' }));
    expect(onDecide).toHaveBeenCalledWith('approve');
  });

  it('disables both buttons once a decision has been made', () => {
    render(<ApprovalCard payload={payload} decision="approve" onDecide={vi.fn()} />);

    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Reject' })).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL with "Cannot find module '../src/components/ChatPanel/ApprovalCard'".

- [ ] **Step 3: Implement `ApprovalCard`**

Create `frontend/src/components/ChatPanel/ApprovalCard.tsx`:

```tsx
import type { ApprovalRequestPayload } from '../../store/sessionStore';

export interface ApprovalCardProps {
  payload: ApprovalRequestPayload;
  decision?: 'approve' | 'reject';
  onDecide: (decision: 'approve' | 'reject') => void;
}

export function ApprovalCard({ payload, decision, onDecide }: ApprovalCardProps) {
  const resolved = decision !== undefined;

  return (
    <div className="rounded border border-amber-400 bg-amber-50 p-3 text-sm">
      <p className="font-semibold text-amber-800">Parts order needs approval</p>
      <ul className="mt-2 space-y-1">
        {payload.inventory_status.map((item) => (
          <li key={item.part_id}>
            {item.part_id}: {item.status}
          </li>
        ))}
      </ul>
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          disabled={resolved}
          onClick={() => onDecide('approve')}
          className="rounded bg-green-600 px-3 py-1 text-white disabled:opacity-50"
        >
          Approve
        </button>
        <button
          type="button"
          disabled={resolved}
          onClick={() => onDecide('reject')}
          className="rounded bg-red-600 px-3 py-1 text-white disabled:opacity-50"
        >
          Reject
        </button>
      </div>
      {resolved && <p className="mt-2 text-xs text-gray-500">Decision: {decision}</p>}
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS — `ApprovalCard` tests pass.

- [ ] **Step 5: Write the failing `MessageList` test**

Create `frontend/tests/MessageList.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { MessageList } from '../src/components/ChatPanel/MessageList';
import type { ChatMessage } from '../src/store/sessionStore';

describe('MessageList', () => {
  it('renders chat messages and an inline approval card in order', async () => {
    const onDecide = vi.fn();
    const messages: ChatMessage[] = [
      { id: '1', kind: 'user', content: 'bearing is grinding' },
      {
        id: '2',
        kind: 'approval',
        approval: { required_parts: [], inventory_status: [{ part_id: 'BEARING-X4', status: 'low_stock' }] },
      },
    ];

    render(<MessageList messages={messages} onDecide={onDecide} />);

    expect(screen.getByTestId('message-user')).toHaveTextContent('bearing is grinding');
    expect(screen.getByText('Parts order needs approval')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Reject' }));
    expect(onDecide).toHaveBeenCalledWith('reject');
  });
});
```

- [ ] **Step 6: Run the test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL with "Cannot find module '../src/components/ChatPanel/MessageList'".

- [ ] **Step 7: Implement `MessageList`**

Create `frontend/src/components/ChatPanel/MessageList.tsx`:

```tsx
import type { ChatMessage } from '../../store/sessionStore';
import { ApprovalCard } from './ApprovalCard';

export interface MessageListProps {
  messages: ChatMessage[];
  onDecide: (decision: 'approve' | 'reject') => void;
}

export function MessageList({ messages, onDecide }: MessageListProps) {
  return (
    <div className="flex-1 space-y-2 overflow-y-auto p-4">
      {messages.map((message) => {
        if (message.kind === 'approval' && message.approval) {
          return (
            <ApprovalCard
              key={message.id}
              payload={message.approval}
              decision={message.decision}
              onDecide={onDecide}
            />
          );
        }
        return (
          <div
            key={message.id}
            data-testid={`message-${message.kind}`}
            className={message.kind === 'user' ? 'text-right' : 'text-left text-gray-700'}
          >
            {message.content}
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 8: Run the test to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS — all `MessageList` tests pass.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/ChatPanel/ApprovalCard.tsx frontend/src/components/ChatPanel/MessageList.tsx frontend/tests/ApprovalCard.test.tsx frontend/tests/MessageList.test.tsx
git commit -m "feat(frontend): add MessageList and inline ApprovalCard"
```

---

## Task 6: Chat input and PDF upload

**Files:**
- Create: `frontend/src/components/ChatPanel/ChatInput.tsx`
- Create: `frontend/src/components/ChatPanel/PdfUpload.tsx`
- Test: `frontend/tests/ChatInput.test.tsx`
- Test: `frontend/tests/PdfUpload.test.tsx`

**Interfaces:**
- Consumes: nothing from earlier tasks (plain presentational components).
- Produces: `ChatInput({ disabled, pendingPdfText, onSend, onClearPdfText }: { disabled: boolean; pendingPdfText: string | null; onSend: (content: string, pdfText?: string) => void; onClearPdfText: () => void })`, `PdfUpload({ disabled, onExtracted, onError }: { disabled: boolean; onExtracted: (text: string) => void; onError: (message: string) => void })` — both consumed by `ChatPanel` in Task 7.

- [ ] **Step 1: Write the failing `ChatInput` test**

Create `frontend/tests/ChatInput.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ChatInput } from '../src/components/ChatPanel/ChatInput';

describe('ChatInput', () => {
  it('sends trimmed content and the pending PDF text, then clears both', async () => {
    const onSend = vi.fn();
    const onClearPdfText = vi.fn();
    render(
      <ChatInput
        disabled={false}
        pendingPdfText="extracted pdf text"
        onSend={onSend}
        onClearPdfText={onClearPdfText}
      />
    );

    await userEvent.type(screen.getByPlaceholderText('Describe the error...'), '  bearing is grinding  ');
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));

    expect(onSend).toHaveBeenCalledWith('bearing is grinding', 'extracted pdf text');
    expect(onClearPdfText).toHaveBeenCalled();
  });

  it('does not send when disabled', async () => {
    const onSend = vi.fn();
    render(<ChatInput disabled pendingPdfText={null} onSend={onSend} onClearPdfText={vi.fn()} />);

    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
    expect(onSend).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL with "Cannot find module '../src/components/ChatPanel/ChatInput'".

- [ ] **Step 3: Implement `ChatInput`**

Create `frontend/src/components/ChatPanel/ChatInput.tsx`:

```tsx
import { useState } from 'react';

export interface ChatInputProps {
  disabled: boolean;
  pendingPdfText: string | null;
  onSend: (content: string, pdfText?: string) => void;
  onClearPdfText: () => void;
}

export function ChatInput({ disabled, pendingPdfText, onSend, onClearPdfText }: ChatInputProps) {
  const [value, setValue] = useState('');

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed, pendingPdfText ?? undefined);
    setValue('');
    if (pendingPdfText) onClearPdfText();
  };

  return (
    <div className="flex flex-1 gap-2 p-3">
      <input
        type="text"
        value={value}
        disabled={disabled}
        placeholder="Describe the error..."
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') submit();
        }}
        className="flex-1 rounded border px-3 py-2 text-sm disabled:opacity-50"
      />
      <button
        type="button"
        disabled={disabled}
        onClick={submit}
        className="rounded bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-50"
      >
        Send
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS — `ChatInput` tests pass.

- [ ] **Step 5: Write the failing `PdfUpload` tests**

Create `frontend/tests/PdfUpload.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PdfUpload } from '../src/components/ChatPanel/PdfUpload';

function makePdfFile() {
  return new File(['%PDF-1.4 fake'], 'error-log.pdf', { type: 'application/pdf' });
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('PdfUpload', () => {
  it('calls onExtracted with the extracted text on success', async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({ extracted_text: 'error code E42 on machine M1' }),
    });
    const onExtracted = vi.fn();
    render(<PdfUpload disabled={false} onExtracted={onExtracted} onError={vi.fn()} />);

    await userEvent.upload(screen.getByLabelText('Attach PDF'), makePdfFile());

    expect(onExtracted).toHaveBeenCalledWith('error code E42 on machine M1');
  });

  it('calls onError with the backend detail message on a 400 response', async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      json: async () => ({ detail: 'This PDF has no extractable text' }),
    });
    const onError = vi.fn();
    render(<PdfUpload disabled={false} onExtracted={vi.fn()} onError={onError} />);

    await userEvent.upload(screen.getByLabelText('Attach PDF'), makePdfFile());

    expect(onError).toHaveBeenCalledWith('This PDF has no extractable text');
  });

  it('calls onError when the request itself fails', async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('network down'));
    const onError = vi.fn();
    render(<PdfUpload disabled={false} onExtracted={vi.fn()} onError={onError} />);

    await userEvent.upload(screen.getByLabelText('Attach PDF'), makePdfFile());

    expect(onError).toHaveBeenCalledWith('Could not reach the server to upload this PDF.');
  });
});
```

- [ ] **Step 6: Run the tests to verify they fail**

Run: `cd frontend && npm test`
Expected: FAIL with "Cannot find module '../src/components/ChatPanel/PdfUpload'".

- [ ] **Step 7: Implement `PdfUpload`**

Create `frontend/src/components/ChatPanel/PdfUpload.tsx`:

```tsx
import { useRef, useState, type ChangeEvent } from 'react';

export interface PdfUploadProps {
  disabled: boolean;
  onExtracted: (text: string) => void;
  onError: (message: string) => void;
}

export function PdfUpload({ disabled, onExtracted, onError }: PdfUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  const handleChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const response = await fetch('/upload', { method: 'POST', body: formData });
      const body = await response.json();
      if (!response.ok) {
        onError(body.detail ?? 'Could not process this PDF.');
      } else {
        onExtracted(body.extracted_text as string);
      }
    } catch {
      onError('Could not reach the server to upload this PDF.');
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  return (
    <label className="flex cursor-pointer items-center gap-2 px-3 text-xs text-gray-500">
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        aria-label="Attach PDF"
        disabled={disabled || uploading}
        onChange={handleChange}
        className="hidden"
      />
      {uploading ? 'Uploading…' : 'Attach PDF'}
    </label>
  );
}
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `cd frontend && npm test`
Expected: PASS — all `PdfUpload` tests pass.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/ChatPanel/ChatInput.tsx frontend/src/components/ChatPanel/PdfUpload.tsx frontend/tests/ChatInput.test.tsx frontend/tests/PdfUpload.test.tsx
git commit -m "feat(frontend): add ChatInput and PdfUpload"
```

---

## Task 7: `ChatPanel`, `SettingsBar`, and full `App` wiring

**Files:**
- Create: `frontend/src/components/ChatPanel/ChatPanel.tsx`
- Create: `frontend/src/components/SettingsBar.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/tests/App.test.tsx`

**Interfaces:**
- Consumes: `useSessionStore` (Task 2), `useSessionSocket` (Task 3), `GraphPanel` (Task 4), `MessageList`/`ApprovalCard` (Task 5), `ChatInput`/`PdfUpload` (Task 6).
- Produces: `ChatPanel({ onSend, onDecide }: { onSend: (content: string, pdfText?: string) => void; onDecide: (decision: 'approve' | 'reject') => void })`, `SettingsBar()`, and the final `App` default export — this is the last task, nothing downstream consumes its output.

- [ ] **Step 1: Write the failing `ChatPanel` behavior into the App test**

Replace the contents of `frontend/tests/App.test.tsx`:

```tsx
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { useSessionStore } from '../src/store/sessionStore';

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.onclose?.();
  }
}

const initialState = useSessionStore.getState();

beforeEach(() => {
  useSessionStore.setState(initialState, true);
  FakeWebSocket.instances = [];
  vi.stubGlobal('WebSocket', FakeWebSocket);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('App', () => {
  it('renders settings, chat, and all 5 graph nodes; disables chat until the socket opens', () => {
    render(<App />);

    expect(screen.getByText('LLM backend:')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
    expect(screen.getByTestId('node-extract')).toBeInTheDocument();
    expect(screen.getByTestId('node-finalize')).toBeInTheDocument();
  });

  it('enables chat once the socket opens and sends a chat frame on submit', async () => {
    render(<App />);

    act(() => {
      FakeWebSocket.instances[0].onopen?.();
    });

    const input = screen.getByPlaceholderText('Describe the error...');
    await userEvent.type(input, 'bearing is grinding');
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));

    expect(screen.getByTestId('message-user')).toHaveTextContent('bearing is grinding');
    const sentFrame = JSON.parse(FakeWebSocket.instances[0].sent[0]);
    expect(sentFrame).toMatchObject({ type: 'chat', content: 'bearing is grinding' });
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test`
Expected: FAIL — `App` still renders only the placeholder text; `LLM backend:` and node testids are not present.

- [ ] **Step 3: Implement `SettingsBar`**

Create `frontend/src/components/SettingsBar.tsx`:

```tsx
import { useSessionStore } from '../store/sessionStore';

export function SettingsBar() {
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
    </div>
  );
}
```

- [ ] **Step 4: Implement `ChatPanel`**

Create `frontend/src/components/ChatPanel/ChatPanel.tsx`:

```tsx
import { useState } from 'react';
import { useSessionStore } from '../../store/sessionStore';
import { MessageList } from './MessageList';
import { ChatInput } from './ChatInput';
import { PdfUpload } from './PdfUpload';

export interface ChatPanelProps {
  onSend: (content: string, pdfText?: string) => void;
  onDecide: (decision: 'approve' | 'reject') => void;
}

export function ChatPanel({ onSend, onDecide }: ChatPanelProps) {
  const messages = useSessionStore((s) => s.messages);
  const connectionStatus = useSessionStore((s) => s.connectionStatus);
  const handleServerEvent = useSessionStore((s) => s.handleServerEvent);
  const [pendingPdfText, setPendingPdfText] = useState<string | null>(null);
  const disabled = connectionStatus !== 'open';

  return (
    <div className="flex h-full flex-col overflow-hidden border-r">
      <MessageList messages={messages} onDecide={onDecide} />
      <div className="flex items-center border-t">
        <PdfUpload
          disabled={disabled}
          onExtracted={setPendingPdfText}
          onError={(message) => handleServerEvent({ type: 'error', message })}
        />
        <ChatInput
          disabled={disabled}
          pendingPdfText={pendingPdfText}
          onSend={onSend}
          onClearPdfText={() => setPendingPdfText(null)}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Implement the final `App`**

Replace `frontend/src/App.tsx`:

```tsx
import { useMemo } from 'react';
import { useSessionStore } from './store/sessionStore';
import { useSessionSocket } from './hooks/useSessionSocket';
import { SettingsBar } from './components/SettingsBar';
import { ChatPanel } from './components/ChatPanel/ChatPanel';
import { GraphPanel } from './components/GraphPanel/GraphPanel';

export default function App() {
  const llmBackend = useSessionStore((s) => s.llmBackend);
  const threadId = useMemo(() => crypto.randomUUID(), []);
  const { sendChat, sendApproval } = useSessionSocket(threadId, llmBackend);

  return (
    <div className="flex h-screen flex-col">
      <SettingsBar />
      <div className="grid flex-1 grid-cols-2 overflow-hidden">
        <ChatPanel onSend={sendChat} onDecide={sendApproval} />
        <GraphPanel />
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd frontend && npm test`
Expected: PASS — full suite passes, including the two `App` integration tests.

- [ ] **Step 7: Manually verify against the real backend (optional but recommended)**

```bash
# Terminal 1 — from the backend package
cd backend && .venv/bin/uvicorn backend.api.app:app --reload

# Terminal 2 — from the frontend package
cd frontend && npm run dev
```

Open the printed Vite URL, confirm the chat input is disabled until the socket opens, send a message, and confirm graph nodes progress and the tool-call log fills in as the backend responds.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/ChatPanel/ChatPanel.tsx frontend/src/components/SettingsBar.tsx frontend/src/App.tsx frontend/tests/App.test.tsx
git commit -m "feat(frontend): wire ChatPanel, SettingsBar, and GraphPanel into App"
```
