import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ToolCallLog } from '../src/components/GraphPanel/ToolCallLog';

describe('ToolCallLog', () => {
  it('renders entries in order', () => {
    render(
      <ToolCallLog
        entries={[
          { id: '1', text: 'MCP: check_stock(part=A) → in_stock' },
          { id: '2', text: 'MCP: check_stock(part=B) → low_stock' },
        ]}
      />
    );

    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent('MCP: check_stock(part=A) → in_stock');
    expect(items[1]).toHaveTextContent('MCP: check_stock(part=B) → low_stock');
  });
});
