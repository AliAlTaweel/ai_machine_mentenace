import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PdfUpload } from '../src/components/ChatPanel/PdfUpload';

function makePdfFile() {
  return new File(['%PDF-1.4 fake'], 'error-log.pdf', { type: 'application/pdf' });
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('PdfUpload', () => {
  it('calls onExtracted with the extracted text on success', async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({ extracted_text: 'error code E42 on machine M1' }),
    });
    const onExtracted = vi.fn();
    render(<PdfUpload disabled={false} onExtracted={onExtracted} onError={vi.fn()} />);

    await userEvent.upload(screen.getByLabelText('Attach PDF'), makePdfFile());

    expect(onExtracted).toHaveBeenCalledWith('error code E42 on machine M1');
  });

  it('calls onError with the backend detail message on a 400 response', async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      json: async () => ({ detail: 'This PDF has no extractable text' }),
    });
    const onError = vi.fn();
    render(<PdfUpload disabled={false} onExtracted={vi.fn()} onError={onError} />);

    await userEvent.upload(screen.getByLabelText('Attach PDF'), makePdfFile());

    expect(onError).toHaveBeenCalledWith('This PDF has no extractable text');
  });

  it('calls onError when the request itself fails', async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('network down'));
    const onError = vi.fn();
    render(<PdfUpload disabled={false} onExtracted={vi.fn()} onError={onError} />);

    await userEvent.upload(screen.getByLabelText('Attach PDF'), makePdfFile());

    expect(onError).toHaveBeenCalledWith('Could not reach the server to upload this PDF.');
  });
});
