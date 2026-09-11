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
  const addSystemMessage = useSessionStore((s) => s.addSystemMessage);
  const [pendingPdfText, setPendingPdfText] = useState<string | null>(null);
  const disabled = connectionStatus !== 'open';

  return (
    <div className="flex h-full flex-col overflow-hidden border-r">
      <MessageList messages={messages} onDecide={onDecide} disabled={disabled} />
      {pendingPdfText && (
        <div className="flex items-center gap-2 border-t bg-amber-50 px-3 py-1 text-xs text-amber-800">
          <span>PDF attached — will be sent with your next message</span>
          <button
            type="button"
            onClick={() => setPendingPdfText(null)}
            className="font-bold"
            aria-label="Remove attached PDF"
          >
            ×
          </button>
        </div>
      )}
      <div className="flex items-center border-t">
        <PdfUpload disabled={disabled} onExtracted={setPendingPdfText} onError={addSystemMessage} />
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
