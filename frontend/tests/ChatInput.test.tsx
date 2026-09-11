import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ChatInput } from '../src/components/ChatPanel/ChatInput';

describe('ChatInput', () => {
  it('sends trimmed content and the pending PDF text, then clears both', async () => {
    const onSend = vi.fn();
    const onClearPdfText = vi.fn();
    render(
      <ChatInput
        disabled={false}
        pendingPdfText="extracted pdf text"
        onSend={onSend}
        onClearPdfText={onClearPdfText}
      />
    );

    await userEvent.type(screen.getByPlaceholderText('Describe the error...'), '  bearing is grinding  ');
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));

    expect(onSend).toHaveBeenCalledWith('bearing is grinding', 'extracted pdf text');
    expect(onClearPdfText).toHaveBeenCalled();
  });

  it('does not send when disabled', async () => {
    const onSend = vi.fn();
    render(<ChatInput disabled pendingPdfText={null} onSend={onSend} onClearPdfText={vi.fn()} />);

    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
    expect(onSend).not.toHaveBeenCalled();
  });
});
