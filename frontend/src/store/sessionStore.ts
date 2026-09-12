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

/**
 * Maps a backend node's `node_update` payload to the assistant-facing chat text.
 * Field names are those emitted by backend/backend/graph/nodes/*.py.
 * Returns null for nodes that should not produce an assistant message.
 */
function assistantContentFor(node: NodeName, data: Record<string, unknown>): string | null {
  if (node === 'extract') {
    if (data.needs_clarification === true && typeof data.clarification_message === 'string') {
      return data.clarification_message;
    }
    return null;
  }

  if (node === 'rag_lookup') {
    const diagnosis = typeof data.diagnosis === 'string' ? data.diagnosis : null;
    if (data.no_procedure_found === true) return diagnosis;
    if (diagnosis === null) return null;
    const steps = Array.isArray(data.repair_steps)
      ? (data.repair_steps as unknown[]).filter((s): s is string => typeof s === 'string')
      : [];
    if (steps.length === 0) return diagnosis;
    return `${diagnosis}\n\nRepair steps:\n${steps.map((step) => `- ${step}`).join('\n')}`;
  }

  if (node === 'finalize') {
    const id = data.work_order_id;
    const status = data.work_order_status;
    if (typeof id !== 'string' || typeof status !== 'string') return null;
    return `Work order ${id} — status: ${status}.`;
  }

  // inventory_check / hitl_gate are represented by the tool-call log and the
  // approval card respectively — no extra assistant message.
  return null;
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
  addSystemMessage: (content: string) => void;
  handleServerEvent: (event: ServerEvent) => void;
  setApprovalDecision: (decision: 'approve' | 'reject') => void;
  resetSession: () => void;
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

  addSystemMessage: (content) => {
    set((state) => ({
      messages: [...state.messages, { id: newId(), kind: 'system', content }],
    }));
  },

  handleServerEvent: (event) => {
    if (event.type === 'node_update') {
      const node = event.node as NodeName;
      if (!NODE_ORDER.includes(node)) return;

      const assistantContent = assistantContentFor(node, event.data);
      // The backend's graph routes straight to END after `extract` asks for
      // clarification or `rag_lookup` finds no procedure (see build.py's
      // route_after_extract / route_after_rag_lookup), so no later node runs.
      const isTerminal =
        (node === 'extract' && event.data.needs_clarification === true) ||
        (node === 'rag_lookup' && event.data.no_procedure_found === true);

      set((state) => {
        const fromIndex = state.activeNode ? NODE_ORDER.indexOf(state.activeNode) : 0;
        const toIndex = NODE_ORDER.indexOf(node);
        // Ignore out-of-order/duplicate updates for a node behind the active one.
        if (toIndex < fromIndex) return state;

        const nodeStatus = { ...state.nodeStatus };
        for (let i = fromIndex; i <= toIndex; i += 1) {
          nodeStatus[NODE_ORDER[i]] = 'done';
        }
        const nextIndex = toIndex + 1;
        const nextNode =
          !isTerminal && nextIndex < NODE_ORDER.length ? NODE_ORDER[nextIndex] : null;
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

        const messages =
          assistantContent === null
            ? state.messages
            : [
                ...state.messages,
                { id: newId(), kind: 'assistant' as const, content: assistantContent },
              ];

        return { nodeStatus, activeNode: nextNode, toolCallLog, messages };
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
      pendingApproval: null,
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

  resetSession: () => {
    set({
      messages: [],
      nodeStatus: initialNodeStatus(),
      activeNode: null,
      pendingApproval: null,
      toolCallLog: [],
      connectionStatus: 'connecting',
    });
  },
}));
