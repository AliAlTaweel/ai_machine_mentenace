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

    render(<MessageList messages={messages} onDecide={onDecide} />);

    expect(screen.getByTestId('message-user')).toHaveTextContent('bearing is grinding');
    expect(screen.getByText('Parts order needs approval')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Reject' }));
    expect(onDecide).toHaveBeenCalledWith('reject');
  });
});
