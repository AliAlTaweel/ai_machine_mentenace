import { beforeEach, describe, expect, it } from 'vitest';
import { NODE_ORDER, useSessionStore } from '../src/store/sessionStore';

const initialState = useSessionStore.getState();

beforeEach(() => {
  useSessionStore.setState(initialState, true);
});

describe('sessionStore', () => {
  it('addUserMessage appends a user message and activates extract', () => {
    useSessionStore.getState().addUserMessage('bearing is grinding');

    const state = useSessionStore.getState();
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0]).toMatchObject({ kind: 'user', content: 'bearing is grinding' });
    expect(state.nodeStatus.extract).toBe('active');
    expect(state.activeNode).toBe('extract');
  });

  it('node_update marks the node done and advances the next node to active', () => {
    useSessionStore.getState().addUserMessage('bearing is grinding');

    useSessionStore.getState().handleServerEvent({
      type: 'node_update',
      node: 'extract',
      data: {},
    });

    const state = useSessionStore.getState();
    expect(state.nodeStatus.extract).toBe('done');
    expect(state.nodeStatus.rag_lookup).toBe('active');
    expect(state.activeNode).toBe('rag_lookup');
  });

  it('node_update for inventory_check appends tool call log entries', () => {
    useSessionStore.getState().addUserMessage('bearing is grinding');

    useSessionStore.getState().handleServerEvent({
      type: 'node_update',
      node: 'inventory_check',
      data: {
        inventory_status: [{ part_id: 'BEARING-X4', status: 'low_stock' }],
      },
    });

    const state = useSessionStore.getState();
    expect(state.toolCallLog).toHaveLength(1);
    expect(state.toolCallLog[0].text).toBe(
      'MCP: check_stock(part=BEARING-X4) → low_stock'
    );
  });

  it('node_update for finalize leaves no active node', () => {
    useSessionStore.getState().addUserMessage('bearing is grinding');

    useSessionStore.getState().handleServerEvent({
      type: 'node_update',
      node: 'finalize',
      data: {},
    });

    const state = useSessionStore.getState();
    NODE_ORDER.forEach((node) => expect(state.nodeStatus[node]).toBe('done'));
    expect(state.activeNode).toBeNull();
  });

  it('approval_request sets hitl_gate active, pendingApproval, and an approval message', () => {
    const payload = {
      required_parts: [{ part_id: 'BEARING-X4', quantity: 2 }],
      inventory_status: [{ part_id: 'BEARING-X4', status: 'low_stock' }],
    };

    useSessionStore.getState().handleServerEvent({ type: 'approval_request', payload });

    const state = useSessionStore.getState();
    expect(state.pendingApproval).toEqual(payload);
    expect(state.nodeStatus.hitl_gate).toBe('active');
    expect(state.activeNode).toBe('hitl_gate');
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0]).toMatchObject({ kind: 'approval', approval: payload });
  });

  it('error marks the active node as error and adds a system message', () => {
    useSessionStore.getState().addUserMessage('bearing is grinding');

    useSessionStore.getState().handleServerEvent({ type: 'error', message: 'MCP unreachable' });

    const state = useSessionStore.getState();
    expect(state.nodeStatus.extract).toBe('error');
    expect(state.messages[1]).toMatchObject({ kind: 'system', content: 'MCP unreachable' });
  });

  it('setApprovalDecision resolves pendingApproval and records the decision on the message', () => {
    const payload = { required_parts: [], inventory_status: [] };
    useSessionStore.getState().handleServerEvent({ type: 'approval_request', payload });

    useSessionStore.getState().setApprovalDecision('approve');

    const state = useSessionStore.getState();
    expect(state.pendingApproval).toBeNull();
    expect(state.messages[0].decision).toBe('approve');
  });
});
