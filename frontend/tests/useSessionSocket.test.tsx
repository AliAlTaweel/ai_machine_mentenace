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
    expect(sentFrame).toEqual({ type: 'approval', decision: 'approve' });
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

  it('sets connectionStatus to closed when the socket closes', () => {
    renderHook(() => useSessionSocket('thread-1', 'local'));

    act(() => {
      FakeWebSocket.instances[0].onclose?.();
    });

    expect(useSessionStore.getState().connectionStatus).toBe('closed');
  });
});
