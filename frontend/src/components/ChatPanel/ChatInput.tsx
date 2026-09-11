import { useState } from 'react';

export interface ChatInputProps {
  disabled: boolean;
  pendingPdfText: string | null;
  onSend: (content: string, pdfText?: string) => void;
  onClearPdfText: () => void;
}

export function ChatInput({ disabled, pendingPdfText, onSend, onClearPdfText }: ChatInputProps) {
  const [value, setValue] = useState('');

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed, pendingPdfText ?? undefined);
    setValue('');
    if (pendingPdfText) onClearPdfText();
  };

  return (
    <div className="flex flex-1 gap-2 p-3">
      <input
        type="text"
        value={value}
        disabled={disabled}
        placeholder="Describe the error..."
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') submit();
        }}
        className="flex-1 rounded border px-3 py-2 text-sm disabled:opacity-50"
      />
      <button
        type="button"
        disabled={disabled}
        onClick={submit}
        className="rounded bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-50"
      >
        Send
      </button>
    </div>
  );
}
