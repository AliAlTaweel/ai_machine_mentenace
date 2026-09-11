import { useMemo, useState } from 'react';
import { useSessionStore } from './store/sessionStore';
import { useSessionSocket } from './hooks/useSessionSocket';
import { SettingsBar } from './components/SettingsBar';
import { ChatPanel } from './components/ChatPanel/ChatPanel';
import { GraphPanel } from './components/GraphPanel/GraphPanel';

function ActiveSession({
  threadId,
  llmBackend,
}: {
  threadId: string;
  llmBackend: 'local' | 'cloud';
}) {
  const { sendChat, sendApproval } = useSessionSocket(threadId, llmBackend);
  return (
    <div className="grid flex-1 grid-cols-2 overflow-hidden">
      <ChatPanel onSend={sendChat} onDecide={sendApproval} />
      <GraphPanel />
    </div>
  );
}

export default function App() {
  const llmBackend = useSessionStore((s) => s.llmBackend);
  const threadId = useMemo(() => crypto.randomUUID(), []);
  const [started, setStarted] = useState(false);

  return (
    <div className="flex h-screen flex-col">
      <SettingsBar />
      {started ? (
        <ActiveSession threadId={threadId} llmBackend={llmBackend} />
      ) : (
        <div className="flex flex-1 items-center justify-center">
          <button
            type="button"
            onClick={() => setStarted(true)}
            className="rounded bg-blue-600 px-6 py-3 text-white"
          >
            Start Session
          </button>
        </div>
      )}
    </div>
  );
}
