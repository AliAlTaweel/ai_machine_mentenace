import { useRef, useState, type ChangeEvent } from 'react';

export interface PdfUploadProps {
  disabled: boolean;
  onExtracted: (text: string) => void;
  onError: (message: string) => void;
}

export function PdfUpload({ disabled, onExtracted, onError }: PdfUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  const handleChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const response = await fetch('/upload', { method: 'POST', body: formData });
      const body = await response.json();
      if (!response.ok) {
        onError(body.detail ?? 'Could not process this PDF.');
      } else {
        onExtracted(body.extracted_text as string);
      }
    } catch {
      onError('Could not reach the server to upload this PDF.');
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  return (
    <label className="flex cursor-pointer items-center gap-2 px-3 text-xs text-gray-500">
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        aria-label="Attach PDF"
        disabled={disabled || uploading}
        onChange={handleChange}
        className="hidden"
      />
      {uploading ? 'Uploading…' : 'Attach PDF'}
    </label>
  );
}
