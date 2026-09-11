import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ManualsPanel } from '../src/components/ManualsPanel/ManualsPanel';

function makePdfFile() {
  return new File(['%PDF-1.4 fake'], 'press-manual.pdf', { type: 'application/pdf' });
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ManualsPanel', () => {
  it('fetches and renders the list of already-uploaded manuals on mount', async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => [
        {
          filename: 'press-manual.pdf',
          machine_type: 'Hydraulic-Press-9',
          error_codes: ['H33'],
          chunk_count: 3,
          uploaded_at: '2026-09-11T00:00:00Z',
        },
      ],
    });

    render(<ManualsPanel onClose={vi.fn()} />);

    expect(await screen.findByText(/press-manual\.pdf/)).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith('/manuals');
  });

  it('submits the upload form with the correct multipart fields and refreshes the list', async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock
      .mockResolvedValueOnce({ ok: true, json: async () => [] })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ status: 'ingested', chunks: 2 }) })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [
          {
            filename: 'press-manual.pdf',
            machine_type: 'Hydraulic-Press-9',
            error_codes: ['H33'],
            chunk_count: 2,
            uploaded_at: '2026-09-11T00:00:00Z',
          },
        ],
      });

    render(<ManualsPanel onClose={vi.fn()} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    await userEvent.upload(screen.getByLabelText('Manual PDF file'), makePdfFile());
    await userEvent.type(screen.getByPlaceholderText('Machine type'), 'Hydraulic-Press-9');
    await userEvent.type(screen.getByPlaceholderText('Error codes (comma-separated)'), 'H33');
    await userEvent.click(screen.getByRole('button', { name: 'Upload manual' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const uploadCall = fetchMock.mock.calls[1];
    expect(uploadCall[0]).toBe('/manuals/upload');
    const sentFormData = uploadCall[1].body as FormData;
    expect(sentFormData.get('machine_type')).toBe('Hydraulic-Press-9');
    expect(sentFormData.get('error_codes')).toBe('H33');
    expect(sentFormData.get('file')).toBeInstanceOf(File);

    expect(await screen.findByText(/Ingested 2 chunk/)).toBeInTheDocument();
  });

  it('shows the duplicate message without treating it as an error', async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock
      .mockResolvedValueOnce({ ok: true, json: async () => [] })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'duplicate', filename: 'press-manual.pdf' }),
      });

    render(<ManualsPanel onClose={vi.fn()} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    await userEvent.upload(screen.getByLabelText('Manual PDF file'), makePdfFile());
    await userEvent.type(screen.getByPlaceholderText('Machine type'), 'Hydraulic-Press-9');
    await userEvent.type(screen.getByPlaceholderText('Error codes (comma-separated)'), 'H33');
    await userEvent.click(screen.getByRole('button', { name: 'Upload manual' }));

    expect(
      await screen.findByText('Already in the knowledge base as press-manual.pdf')
    ).toBeInTheDocument();
  });

  it('shows the backend detail message on a 400 response', async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock
      .mockResolvedValueOnce({ ok: true, json: async () => [] })
      .mockResolvedValueOnce({
        ok: false,
        json: async () => ({ detail: 'This PDF has no extractable text' }),
      });

    render(<ManualsPanel onClose={vi.fn()} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    await userEvent.upload(screen.getByLabelText('Manual PDF file'), makePdfFile());
    await userEvent.type(screen.getByPlaceholderText('Machine type'), 'Hydraulic-Press-9');
    await userEvent.type(screen.getByPlaceholderText('Error codes (comma-separated)'), 'H33');
    await userEvent.click(screen.getByRole('button', { name: 'Upload manual' }));

    expect(await screen.findByText('This PDF has no extractable text')).toBeInTheDocument();
  });

  it('calls onClose when the close button is clicked', async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue({ ok: true, json: async () => [] });
    const onClose = vi.fn();

    render(<ManualsPanel onClose={onClose} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    await userEvent.click(screen.getByLabelText('Close'));
    expect(onClose).toHaveBeenCalled();
  });
});
