import { useState } from 'react';
import { useSessionStore } from './store/sessionStore';
import { useSessionSocket } from './hooks/useSessionSocket';
import { SettingsBar } from './components/SettingsBar';
import { ChatPanel } from './components/ChatPanel/ChatPanel';
import { GraphPanel } from './components/GraphPanel/GraphPanel';
import { ManualsPanel } from './components/ManualsPanel/ManualsPanel';

function ActiveSession({
  threadId,
  llmBackend,
  onEndSession,
}: {
  threadId: string;
  llmBackend: 'local' | 'cloud';
  onEndSession: () => void;
}) {
  const { sendChat, sendApproval } = useSessionSocket(threadId, llmBackend);
  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="flex justify-end border-b px-4 py-2">
        <button
          type="button"
          onClick={onEndSession}
          className="rounded border px-3 py-1 text-sm text-gray-600 hover:bg-gray-100"
        >
          New Session
        </button>
      </div>
      <div className="grid flex-1 grid-cols-2 overflow-hidden">
        <ChatPanel onSend={sendChat} onDecide={sendApproval} />
        <GraphPanel />
      </div>
    </div>
  );
}

export default function App() {
  const llmBackend = useSessionStore((s) => s.llmBackend);
  const resetSession = useSessionStore((s) => s.resetSession);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [showManuals, setShowManuals] = useState(false);

  const startSession = () => {
    resetSession();
    setThreadId(crypto.randomUUID());
  };

  const endSession = () => {
    resetSession();
    setThreadId(null);
  };

  return (
    <div className="flex h-screen flex-col">
      <SettingsBar onManageManuals={() => setShowManuals(true)} />
      {threadId ? (
        <ActiveSession threadId={threadId} llmBackend={llmBackend} onEndSession={endSession} />
      ) : (
        <div className="flex flex-1 items-center justify-center">
          <button
            type="button"
            onClick={startSession}
            className="rounded bg-blue-600 px-6 py-3 text-white"
          >
            Start Session
          </button>
        </div>
      )}
      {showManuals && <ManualsPanel onClose={() => setShowManuals(false)} />}
    </div>
  );
}
