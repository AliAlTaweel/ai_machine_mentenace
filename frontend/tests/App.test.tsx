import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { useSessionStore } from '../src/store/sessionStore';

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.onclose?.();
  }
}

const initialState = useSessionStore.getState();

beforeEach(() => {
  useSessionStore.setState(initialState, true);
  FakeWebSocket.instances = [];
  vi.stubGlobal('WebSocket', FakeWebSocket);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('App', () => {
  it('renders settings, chat, and all 5 graph nodes; disables chat until the socket opens', () => {
    render(<App />);

    expect(screen.getByText('LLM backend:')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
    expect(screen.getByTestId('node-extract')).toBeInTheDocument();
    expect(screen.getByTestId('node-finalize')).toBeInTheDocument();
  });

  it('enables chat once the socket opens and sends a chat frame on submit', async () => {
    render(<App />);

    act(() => {
      FakeWebSocket.instances[0].onopen?.();
    });

    const input = screen.getByPlaceholderText('Describe the error...');
    await userEvent.type(input, 'bearing is grinding');
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));

    expect(screen.getByTestId('message-user')).toHaveTextContent('bearing is grinding');
    const sentFrame = JSON.parse(FakeWebSocket.instances[0].sent[0]);
    expect(sentFrame).toMatchObject({ type: 'chat', content: 'bearing is grinding' });
  });
});
