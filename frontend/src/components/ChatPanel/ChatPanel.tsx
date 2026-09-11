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
