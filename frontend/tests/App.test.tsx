import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { NODE_ORDER, useSessionStore } from '../src/store/sessionStore';

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
  it('keeps the LLM backend toggle usable and opens no socket before Start Session', () => {
    render(<App />);

    expect(screen.getByText('LLM backend:')).toBeInTheDocument();
    expect(FakeWebSocket.instances).toHaveLength(0);
    screen.getAllByRole('radio').forEach((radio) => expect(radio).toBeEnabled());
    expect(screen.queryByRole('button', { name: 'Send' })).not.toBeInTheDocument();
  });

  it('renders settings, chat, and all 5 graph nodes; disables chat until the socket opens', async () => {
    render(<App />);
    await userEvent.click(screen.getByRole('button', { name: 'Start Session' }));

    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
    NODE_ORDER.forEach((node) => {
      expect(screen.getByTestId(`node-${node}`)).toBeInTheDocument();
    });
  });

  it('enables chat once the socket opens and sends a chat frame on submit', async () => {
    render(<App />);
    await userEvent.click(screen.getByRole('button', { name: 'Start Session' }));

    act(() => {
      FakeWebSocket.instances[0].onopen?.();
    });

    const input = screen.getByPlaceholderText('Describe the error...');
    await userEvent.type(input, 'bearing is grinding');
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));

    expect(screen.getByText('bearing is grinding')).toBeInTheDocument();
    const sentFrame = JSON.parse(FakeWebSocket.instances[0].sent[0]);
    expect(sentFrame).toMatchObject({ type: 'chat', content: 'bearing is grinding' });
  });

  it('starts a fresh thread and clears prior messages when New Session is clicked', async () => {
    render(<App />);
    await userEvent.click(screen.getByRole('button', { name: 'Start Session' }));
    act(() => {
      FakeWebSocket.instances[0].onopen?.();
    });

    const input = screen.getByPlaceholderText('Describe the error...');
    await userEvent.type(input, 'weird noise, part might be broken');
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));
    expect(screen.getByText('weird noise, part might be broken')).toBeInTheDocument();

    const firstThreadUrl = FakeWebSocket.instances[0].url;

    await userEvent.click(screen.getByRole('button', { name: 'New Session' }));
    expect(screen.getByRole('button', { name: 'Start Session' })).toBeInTheDocument();
    expect(screen.queryByText('weird noise, part might be broken')).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Start Session' }));

    expect(FakeWebSocket.instances).toHaveLength(2);
    expect(FakeWebSocket.instances[1].url).not.toBe(firstThreadUrl);
    expect(screen.queryByText('weird noise, part might be broken')).not.toBeInTheDocument();
  });

  it('opens the manuals panel from Settings and closes it', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => [] }));
    render(<App />);

    expect(screen.queryByTestId('manuals-list')).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Manage Manuals' }));
    expect(await screen.findByTestId('manuals-list')).toBeInTheDocument();

    await userEvent.click(screen.getByLabelText('Close'));
    expect(screen.queryByTestId('manuals-list')).not.toBeInTheDocument();
  });
});
