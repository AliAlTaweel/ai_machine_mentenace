import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { useSessionStore } from '../src/store/sessionStore';
import { GraphPanel } from '../src/components/GraphPanel/GraphPanel';

const initialState = useSessionStore.getState();

beforeEach(() => {
  useSessionStore.setState(initialState, true);
});

describe('GraphPanel', () => {
  it('renders all 5 nodes and the tool call log from the store', () => {
    useSessionStore.setState({
      nodeStatus: {
        extract: 'done',
        rag_lookup: 'done',
        inventory_check: 'active',
        hitl_gate: 'idle',
        finalize: 'idle',
      },
      toolCallLog: [{ id: '1', text: 'MCP: check_stock(part=A) → in_stock' }],
    });

    render(<GraphPanel />);

    expect(screen.getByTestId('node-extract')).toHaveClass('bg-green-100');
    expect(screen.getByTestId('node-inventory_check')).toHaveClass('bg-blue-100');
    expect(screen.getByText('MCP: check_stock(part=A) → in_stock')).toBeInTheDocument();
  });
});
