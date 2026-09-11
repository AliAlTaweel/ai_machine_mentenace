import { StrictMode } from 'react';
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useSessionStore } from '../src/store/sessionStore';
import { useSessionSocket } from '../src/hooks/useSessionSocket';

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

function lastMessage() {
  const { messages } = useSessionStore.getState();
  return messages[messages.length - 1];
}

beforeEach(() => {
  useSessionStore.setState(initialState, true);
  FakeWebSocket.instances = [];
  vi.stubGlobal('WebSocket', FakeWebSocket);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useSessionSocket', () => {
  it('opens a socket to the thread URL and updates connectionStatus on open', () => {
    renderHook(() => useSessionSocket('thread-1', 'local'));

    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(FakeWebSocket.instances[0].url).toContain('/ws/thread-1?backend=local');

    act(() => {
      FakeWebSocket.instances[0].onopen?.();
    });

    expect(useSessionStore.getState().connectionStatus).toBe('open');
  });

  it('sendChat appends a user message and sends a chat frame', () => {
    const { result } = renderHook(() => useSessionSocket('thread-1', 'local'));

    act(() => {
      result.current.sendChat('bearing is grinding');
    });

    expect(useSessionStore.getState().messages[0]).toMatchObject({
      kind: 'user',
      content: 'bearing is grinding',
    });
    const sentFrame = JSON.parse(FakeWebSocket.instances[0].sent[0]);
    expect(sentFrame).toEqual({ type: 'chat', content: 'bearing is grinding', pdf_text: undefined });
  });

  it('sendApproval resolves the pending approval and sends an approval frame', () => {
    const { result } = renderHook(() => useSessionSocket('thread-1', 'local'));
    useSessionStore.getState().handleServerEvent({
      type: 'approval_request',
      payload: { required_parts: [], inventory_status: [] },
    });

    act(() => {
      result.current.sendApproval('approve');
    });

    expect(useSessionStore.getState().pendingApproval).toBeNull();
    const sentFrame = JSON.parse(FakeWebSocket.instances[0].sent[0]);
    expect(sentFrame).toEqual({ type: 'approval', decision: 'approved' });
  });

  it('sendApproval translates a reject decision to the backend wire value', () => {
    const { result } = renderHook(() => useSessionSocket('thread-1', 'local'));
    useSessionStore.getState().handleServerEvent({
      type: 'approval_request',
      payload: { required_parts: [], inventory_status: [] },
    });

    act(() => {
      result.current.sendApproval('reject');
    });

    const sentFrame = JSON.parse(FakeWebSocket.instances[0].sent[0]);
    expect(sentFrame).toEqual({ type: 'approval', decision: 'rejected' });
  });

  it('routes incoming node_update frames into the store', () => {
    renderHook(() => useSessionSocket('thread-1', 'local'));
    useSessionStore.getState().addUserMessage('bearing is grinding');

    act(() => {
      FakeWebSocket.instances[0].onmessage?.({
        data: JSON.stringify({ type: 'node_update', node: 'extract', data: {} }),
      });
    });

    expect(useSessionStore.getState().nodeStatus.extract).toBe('done');
  });

  it('sets connectionStatus to closed and adds a system message when the socket closes', () => {
    renderHook(() => useSessionSocket('thread-1', 'local'));

    act(() => {
      FakeWebSocket.instances[0].onclose?.();
    });

    expect(useSessionStore.getState().connectionStatus).toBe('closed');
    expect(lastMessage()).toMatchObject({
      kind: 'system',
      content: 'Connection closed — reload the page to start a new session.',
    });
  });

  it('sets connectionStatus to error and adds a system message on socket error', () => {
    renderHook(() => useSessionSocket('thread-1', 'local'));

    act(() => {
      FakeWebSocket.instances[0].onerror?.();
    });

    expect(useSessionStore.getState().connectionStatus).toBe('error');
    expect(lastMessage()).toMatchObject({
      kind: 'system',
      content: 'Connection error.',
    });
  });

  it('ignores a stale socket callback after a newer socket has replaced it', () => {
    const { rerender } = renderHook(({ id }) => useSessionSocket(id, 'local'), {
      initialProps: { id: 'thread-1' },
    });

    // Capture the first socket's handler while it is still attached; after the
    // effect re-runs, cleanup detaches it from the socket object itself.
    const staleOnClose = FakeWebSocket.instances[0].onclose!;
    expect(staleOnClose).toBeTypeOf('function');

    rerender({ id: 'thread-2' });
    expect(FakeWebSocket.instances).toHaveLength(2);
    expect(FakeWebSocket.instances[0].onclose).toBeNull();

    act(() => {
      FakeWebSocket.instances[1].onopen?.();
    });
    expect(useSessionStore.getState().connectionStatus).toBe('open');

    // The stale socket's callback must not clobber the current socket's status.
    act(() => {
      staleOnClose();
    });
    expect(useSessionStore.getState().connectionStatus).toBe('open');
  });

  it('survives a StrictMode double-mount with connectionStatus tracking the live socket', () => {
    renderHook(() => useSessionSocket('thread-1', 'local'), { wrapper: StrictMode });

    expect(FakeWebSocket.instances.length).toBeGreaterThanOrEqual(2);
    const live = FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
    const stale = FakeWebSocket.instances[0];
    expect(stale.onclose).toBeNull();

    act(() => {
      live.onopen?.();
    });

    expect(useSessionStore.getState().connectionStatus).toBe('open');
  });
});
