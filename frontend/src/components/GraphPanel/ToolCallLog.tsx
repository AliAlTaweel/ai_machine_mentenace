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
