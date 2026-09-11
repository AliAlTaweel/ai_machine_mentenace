import { useEffect, useState, type FormEvent } from 'react';

interface ManualEntry {
  filename: string;
  machine_type: string;
  error_codes: string[];
  chunk_count: number;
  uploaded_at: string;
}

export interface ManualsPanelProps {
  onClose: () => void;
}

export function ManualsPanel({ onClose }: ManualsPanelProps) {
  const [manuals, setManuals] = useState<ManualEntry[]>([]);
  const [machineType, setMachineType] = useState('');
  const [errorCodes, setErrorCodes] = useState('');
  const [status, setStatus] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const fetchManuals = async () => {
    const response = await fetch('/manuals');
    const data = await response.json();
    setManuals(data);
  };

  useEffect(() => {
    fetchManuals();
  }, []);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const fileInput = form.elements.namedItem('file') as HTMLInputElement;
    const file = fileInput.files?.[0];
    if (!file) return;

    setUploading(true);
    setStatus(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('machine_type', machineType);
      formData.append('error_codes', errorCodes);
      const response = await fetch('/manuals/upload', { method: 'POST', body: formData });
      const body = await response.json();
      if (!response.ok) {
        setStatus(body.detail ?? 'Could not process this manual.');
      } else if (body.status === 'duplicate') {
        setStatus(`Already in the knowledge base as ${body.filename}`);
      } else {
        setStatus(`Ingested ${body.chunks} chunk(s).`);
        await fetchManuals();
        form.reset();
        setMachineType('');
        setErrorCodes('');
      }
    } catch {
      setStatus('Could not reach the server to upload this manual.');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded bg-white p-4 shadow-lg">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Manage Manuals</h2>
          <button type="button" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        <ul
          data-testid="manuals-list"
          className="mt-3 max-h-40 space-y-1 overflow-y-auto text-sm"
        >
          {manuals.map((manual) => (
            <li key={manual.filename}>
              {manual.filename} — {manual.machine_type} ({manual.error_codes.join(', ')},{' '}
              {manual.chunk_count} chunks)
            </li>
          ))}
        </ul>

        <form onSubmit={handleSubmit} className="mt-4 space-y-2" noValidate>
          <input
            type="file"
            name="file"
            accept="application/pdf"
            aria-label="Manual PDF file"
            required
          />
          <input
            type="text"
            placeholder="Machine type"
            value={machineType}
            onChange={(event) => setMachineType(event.target.value)}
            required
            className="w-full rounded border px-2 py-1 text-sm"
          />
          <input
            type="text"
            placeholder="Error codes (comma-separated)"
            value={errorCodes}
            onChange={(event) => setErrorCodes(event.target.value)}
            required
            className="w-full rounded border px-2 py-1 text-sm"
          />
          <button
            type="submit"
            disabled={uploading}
            className="rounded bg-blue-600 px-3 py-1 text-sm text-white disabled:opacity-50"
          >
            {uploading ? 'Uploading…' : 'Upload manual'}
          </button>
        </form>

        {status && (
          <p data-testid="manuals-status" className="mt-2 text-xs text-gray-600">
            {status}
          </p>
        )}
      </div>
    </div>
  );
}
