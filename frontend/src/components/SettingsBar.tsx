import { useSessionStore } from '../store/sessionStore';

export function SettingsBar() {
  const llmBackend = useSessionStore((s) => s.llmBackend);
  const setLlmBackend = useSessionStore((s) => s.setLlmBackend);
  const connectionStatus = useSessionStore((s) => s.connectionStatus);
  const locked = connectionStatus !== 'connecting';

  return (
    <div className="flex items-center gap-3 border-b p-3 text-sm">
      <span className="font-medium">LLM backend:</span>
      <label className="flex items-center gap-1">
        <input
          type="radio"
          name="llmBackend"
          checked={llmBackend === 'local'}
          disabled={locked}
          onChange={() => setLlmBackend('local')}
        />
        Local Gemma
      </label>
      <label className="flex items-center gap-1">
        <input
          type="radio"
          name="llmBackend"
          checked={llmBackend === 'cloud'}
          disabled={locked}
          onChange={() => setLlmBackend('cloud')}
        />
        Claude API
      </label>
    </div>
  );
}
