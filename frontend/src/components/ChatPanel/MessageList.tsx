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
