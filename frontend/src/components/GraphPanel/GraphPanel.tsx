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
