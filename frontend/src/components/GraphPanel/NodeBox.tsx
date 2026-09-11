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
