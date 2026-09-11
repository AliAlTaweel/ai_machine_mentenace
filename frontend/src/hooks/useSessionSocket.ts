import { useEffect, useRef } from 'react';
import { useSessionStore, type ServerEvent } from '../store/sessionStore';

export interface UseSessionSocketResult {
  sendChat: (content: string, pdfText?: string) => void;
  sendApproval: (decision: 'approve' | 'reject') => void;
}

export function useSessionSocket(
  threadId: string,
  backend: 'local' | 'cloud'
): UseSessionSocketResult {
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    useSessionStore.getState().setConnectionStatus('connecting');

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/ws/${threadId}?backend=${backend}`;
    const socket = new WebSocket(url);
    socketRef.current = socket;

    // Guards against a stale socket (StrictMode double-mount, or a
    // threadId/backend change) clobbering the current socket's status.
    const isCurrent = () => socketRef.current === socket;

    socket.onopen = () => {
      if (isCurrent()) useSessionStore.getState().setConnectionStatus('open');
    };
    socket.onclose = () => {
      if (!isCurrent()) return;
      useSessionStore.getState().setConnectionStatus('closed');
      useSessionStore
        .getState()
        .addSystemMessage('Connection closed — reload the page to start a new session.');
    };
    socket.onerror = () => {
      if (!isCurrent()) return;
      useSessionStore.getState().setConnectionStatus('error');
      useSessionStore.getState().addSystemMessage('Connection error.');
    };
    socket.onmessage = (event) => {
      if (!isCurrent()) return;
      let parsed: ServerEvent;
      try {
        parsed = JSON.parse(event.data);
      } catch {
        return;
      }
      if (
        parsed.type !== 'node_update' &&
        parsed.type !== 'approval_request' &&
        parsed.type !== 'error'
      ) {
        return;
      }
      useSessionStore.getState().handleServerEvent(parsed);
    };

    return () => {
      socket.onopen = null;
      socket.onclose = null;
      socket.onerror = null;
      socket.onmessage = null;
      socket.close();
    };
  }, [threadId, backend]);

  const sendChat = (content: string, pdfText?: string) => {
    useSessionStore.getState().addUserMessage(content);
    socketRef.current?.send(JSON.stringify({ type: 'chat', content, pdf_text: pdfText }));
  };

  const sendApproval = (decision: 'approve' | 'reject') => {
    useSessionStore.getState().setApprovalDecision(decision);
    // The backend compares against the exact strings 'approved'/'rejected'
    // (backend/backend/graph/nodes/finalize.py) — translate at the wire boundary.
    const wireDecision = decision === 'approve' ? 'approved' : 'rejected';
    socketRef.current?.send(JSON.stringify({ type: 'approval', decision: wireDecision }));
  };

  return { sendChat, sendApproval };
}
