import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { MessageList } from '../src/components/ChatPanel/MessageList';
import type { ChatMessage } from '../src/store/sessionStore';

describe('MessageList', () => {
  it('renders chat messages and an inline approval card in order', async () => {
    const onDecide = vi.fn();
    const messages: ChatMessage[] = [
      { id: '1', kind: 'user', content: 'bearing is grinding' },
      {
        id: '2',
        kind: 'approval',
        approval: { required_parts: [], inventory_status: [{ part_id: 'BEARING-X4', status: 'low_stock' }] },
      },
    ];

    render(<MessageList messages={messages} onDecide={onDecide} disabled={false} />);

    expect(screen.getByText('bearing is grinding')).toBeInTheDocument();
    expect(screen.getByText('Parts order needs approval')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Reject' }));
    expect(onDecide).toHaveBeenCalledWith('reject');
  });

  it('gives each message a unique testid so duplicate kinds stay addressable', () => {
    const messages: ChatMessage[] = [
      { id: '1', kind: 'user', content: 'first' },
      { id: '2', kind: 'user', content: 'second' },
    ];

    render(<MessageList messages={messages} onDecide={vi.fn()} disabled={false} />);

    expect(screen.getByTestId('message-1')).toHaveTextContent('first');
    expect(screen.getByTestId('message-2')).toHaveTextContent('second');
  });

  it('disables approval buttons when disabled is passed even with no decision', () => {
    const messages: ChatMessage[] = [
      {
        id: '1',
        kind: 'approval',
        approval: { required_parts: [], inventory_status: [] },
      },
    ];

    render(<MessageList messages={messages} onDecide={vi.fn()} disabled />);

    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Reject' })).toBeDisabled();
  });
});
