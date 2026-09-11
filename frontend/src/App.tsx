import { useMemo } from 'react';
import { useSessionStore } from './store/sessionStore';
import { useSessionSocket } from './hooks/useSessionSocket';
import { SettingsBar } from './components/SettingsBar';
import { ChatPanel } from './components/ChatPanel/ChatPanel';
import { GraphPanel } from './components/GraphPanel/GraphPanel';

export default function App() {
  const llmBackend = useSessionStore((s) => s.llmBackend);
  const threadId = useMemo(() => crypto.randomUUID(), []);
  const { sendChat, sendApproval } = useSessionSocket(threadId, llmBackend);

  return (
    <div className="flex h-screen flex-col">
      <SettingsBar />
      <div className="grid flex-1 grid-cols-2 overflow-hidden">
        <ChatPanel onSend={sendChat} onDecide={sendApproval} />
        <GraphPanel />
      </div>
    </div>
  );
}
