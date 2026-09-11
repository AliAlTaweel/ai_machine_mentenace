import type { ChatMessage } from '../../store/sessionStore';
import { ApprovalCard } from './ApprovalCard';

export interface MessageListProps {
  messages: ChatMessage[];
  onDecide: (decision: 'approve' | 'reject') => void;
  disabled: boolean;
}

export function MessageList({ messages, onDecide, disabled }: MessageListProps) {
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
              disabled={disabled}
            />
          );
        }
        return (
          <div
            key={message.id}
            data-testid={`message-${message.id}`}
            className={message.kind === 'user' ? 'text-right' : 'text-left text-gray-700'}
          >
            {message.content}
          </div>
        );
      })}
    </div>
  );
}
