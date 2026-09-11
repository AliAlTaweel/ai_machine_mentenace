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
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/ws/${threadId}?backend=${backend}`;
    const socket = new WebSocket(url);
    socketRef.current = socket;

    socket.onopen = () => useSessionStore.getState().setConnectionStatus('open');
    socket.onclose = () => useSessionStore.getState().setConnectionStatus('closed');
    socket.onerror = () => useSessionStore.getState().setConnectionStatus('error');
    socket.onmessage = (event) => {
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

    return () => socket.close();
  }, [threadId, backend]);

  const sendChat = (content: string, pdfText?: string) => {
    useSessionStore.getState().addUserMessage(content);
    socketRef.current?.send(JSON.stringify({ type: 'chat', content, pdf_text: pdfText }));
  };

  const sendApproval = (decision: 'approve' | 'reject') => {
    useSessionStore.getState().setApprovalDecision(decision);
    socketRef.current?.send(JSON.stringify({ type: 'approval', decision }));
  };

  return { sendChat, sendApproval };
}
