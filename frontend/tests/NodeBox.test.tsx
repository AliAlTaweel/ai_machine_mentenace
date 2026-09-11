import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { NodeBox } from '../src/components/GraphPanel/NodeBox';

describe('NodeBox', () => {
  it('renders the node label', () => {
    render(<NodeBox node="rag_lookup" state="idle" />);
    expect(screen.getByText('RAG Lookup')).toBeInTheDocument();
  });

  it('applies the active state styling', () => {
    render(<NodeBox node="extract" state="active" />);
    expect(screen.getByTestId('node-extract')).toHaveClass('bg-blue-100');
  });

  it('applies the error state styling', () => {
    render(<NodeBox node="finalize" state="error" />);
    expect(screen.getByTestId('node-finalize')).toHaveClass('bg-red-100');
  });
});
