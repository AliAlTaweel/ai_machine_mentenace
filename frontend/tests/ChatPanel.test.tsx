import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatPanel } from '../src/components/ChatPanel/ChatPanel';
import { useSessionStore } from '../src/store/sessionStore';

const CHIP_TEXT = 'PDF attached — will be sent with your next message';
const initialState = useSessionStore.getState();

function makePdfFile() {
  return new File(['%PDF-1.4 fake'], 'error-log.pdf', { type: 'application/pdf' });
}

async function attachPdf() {
  (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
    ok: true,
    json: async () => ({ extracted_text: 'error code E42' }),
  });
  await userEvent.upload(screen.getByLabelText('Attach PDF'), makePdfFile());
}

beforeEach(() => {
  useSessionStore.setState(initialState, true);
  useSessionStore.getState().setConnectionStatus('open');
  vi.stubGlobal('fetch', vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ChatPanel', () => {
  it('shows an attachment chip once a PDF is extracted and clears it on ×', async () => {
    render(<ChatPanel onSend={vi.fn()} onDecide={vi.fn()} />);

    expect(screen.queryByText(CHIP_TEXT)).not.toBeInTheDocument();

    await attachPdf();
    expect(screen.getByText(CHIP_TEXT)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Remove attached PDF' }));
    expect(screen.queryByText(CHIP_TEXT)).not.toBeInTheDocument();
  });

  it('clears the attachment chip after the message is sent', async () => {
    const onSend = vi.fn();
    render(<ChatPanel onSend={onSend} onDecide={vi.fn()} />);

    await attachPdf();
    await userEvent.type(screen.getByPlaceholderText('Describe the error...'), 'bearing grinding');
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));

    expect(onSend).toHaveBeenCalledWith('bearing grinding', 'error code E42');
    expect(screen.queryByText(CHIP_TEXT)).not.toBeInTheDocument();
  });

  it('reports a failed PDF upload as a system message without marking a node errored', async () => {
    useSessionStore.getState().addUserMessage('bearing grinding');
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      json: async () => ({ detail: 'This PDF has no extractable text' }),
    });
    render(<ChatPanel onSend={vi.fn()} onDecide={vi.fn()} />);

    await userEvent.upload(screen.getByLabelText('Attach PDF'), makePdfFile());

    const state = useSessionStore.getState();
    expect(state.messages[state.messages.length - 1]).toMatchObject({
      kind: 'system',
      content: 'This PDF has no extractable text',
    });
    expect(state.nodeStatus.extract).toBe('active');
  });

  it('disables the approval card buttons when the socket is not open', () => {
    useSessionStore.getState().handleServerEvent({
      type: 'approval_request',
      payload: { required_parts: [], inventory_status: [] },
    });
    useSessionStore.getState().setConnectionStatus('closed');

    render(<ChatPanel onSend={vi.fn()} onDecide={vi.fn()} />);

    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Reject' })).toBeDisabled();
  });
});
