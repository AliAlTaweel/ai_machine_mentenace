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
