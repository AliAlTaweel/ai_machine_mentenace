import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ApprovalCard } from '../src/components/ChatPanel/ApprovalCard';

const payload = {
  required_parts: [{ part_id: 'BEARING-X4', quantity: 2 }],
  inventory_status: [{ part_id: 'BEARING-X4', status: 'low_stock' }],
};

describe('ApprovalCard', () => {
  it('renders inventory status and calls onDecide on Approve', async () => {
    const onDecide = vi.fn();
    render(<ApprovalCard payload={payload} onDecide={onDecide} disabled={false} />);

    expect(screen.getByText(/BEARING-X4: low_stock/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Approve' }));
    expect(onDecide).toHaveBeenCalledWith('approve');
  });

  it('disables both buttons once a decision has been made', () => {
    render(<ApprovalCard payload={payload} decision="approve" onDecide={vi.fn()} disabled={false} />);

    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Reject' })).toBeDisabled();
  });

  it('disables both buttons when disabled is set even with no decision made', () => {
    render(<ApprovalCard payload={payload} onDecide={vi.fn()} disabled />);

    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Reject' })).toBeDisabled();
  });
});
