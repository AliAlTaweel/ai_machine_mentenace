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

  it('node_update for extract with needs_clarification adds an assistant message and stops the run', () => {
    useSessionStore.getState().addUserMessage('it is broken');

    useSessionStore.getState().handleServerEvent({
      type: 'node_update',
      node: 'extract',
      data: {
        needs_clarification: true,
        clarification_message: 'Which machine and what error code?',
      },
    });

    const state = useSessionStore.getState();
    expect(state.messages[1]).toMatchObject({
      kind: 'assistant',
      content: 'Which machine and what error code?',
    });
    expect(state.nodeStatus.extract).toBe('done');
    expect(state.nodeStatus.rag_lookup).toBe('idle');
    expect(state.activeNode).toBeNull();
  });

  it('node_update for rag_lookup with no_procedure_found adds the diagnosis and stops the run', () => {
    useSessionStore.getState().addUserMessage('bearing is grinding');
    useSessionStore.getState().handleServerEvent({
      type: 'node_update',
      node: 'extract',
      data: { needs_clarification: false },
    });

    useSessionStore.getState().handleServerEvent({
      type: 'node_update',
      node: 'rag_lookup',
      data: {
        no_procedure_found: true,
        diagnosis: 'No relevant repair procedure was found in the technical manuals.',
        repair_steps: [],
      },
    });

    const state = useSessionStore.getState();
    expect(state.messages[1]).toMatchObject({
      kind: 'assistant',
      content: 'No relevant repair procedure was found in the technical manuals.',
    });
    expect(state.nodeStatus.rag_lookup).toBe('done');
    expect(state.nodeStatus.inventory_check).toBe('idle');
    expect(state.activeNode).toBeNull();
  });

  it('node_update for rag_lookup combines diagnosis and repair steps into an assistant message', () => {
    useSessionStore.getState().addUserMessage('bearing is grinding');

    useSessionStore.getState().handleServerEvent({
      type: 'node_update',
      node: 'rag_lookup',
      data: {
        no_procedure_found: false,
        diagnosis: 'Worn spindle bearing.',
        repair_steps: ['Power down the machine', 'Replace bearing BEARING-X4'],
      },
    });

    const state = useSessionStore.getState();
    expect(state.messages[1]).toMatchObject({
      kind: 'assistant',
      content:
        'Worn spindle bearing.\n\nRepair steps:\n- Power down the machine\n- Replace bearing BEARING-X4',
    });
    expect(state.activeNode).toBe('inventory_check');
  });

  it('node_update for finalize adds an assistant summary message', () => {
    useSessionStore.getState().addUserMessage('bearing is grinding');

    useSessionStore.getState().handleServerEvent({
      type: 'node_update',
      node: 'finalize',
      data: { work_order_id: 'wo-123', work_order_status: 'completed' },
    });

    const state = useSessionStore.getState();
    expect(state.messages[1]).toMatchObject({
      kind: 'assistant',
      content: 'Work order wo-123 — status: completed.',
    });
  });

  it('node_update for inventory_check and hitl_gate adds no assistant message', () => {
    useSessionStore.getState().addUserMessage('bearing is grinding');

    useSessionStore.getState().handleServerEvent({
      type: 'node_update',
      node: 'inventory_check',
      data: { inventory_status: [{ part_id: 'BEARING-X4', status: 'low_stock' }] },
    });
    useSessionStore.getState().handleServerEvent({
      type: 'node_update',
      node: 'hitl_gate',
      data: {},
    });

    const state = useSessionStore.getState();
    expect(state.messages.filter((m) => m.kind === 'assistant')).toHaveLength(0);
  });

  it('node_update for a node behind the active node is ignored', () => {
    useSessionStore.getState().addUserMessage('bearing is grinding');
    useSessionStore.getState().handleServerEvent({
      type: 'node_update',
      node: 'inventory_check',
      data: {},
    });
    const before = useSessionStore.getState();

    useSessionStore.getState().handleServerEvent({
      type: 'node_update',
      node: 'extract',
      data: {},
    });

    const after = useSessionStore.getState();
    expect(after.activeNode).toBe('hitl_gate');
    expect(after.nodeStatus).toEqual(before.nodeStatus);
    expect(after.messages).toHaveLength(before.messages.length);
  });

  it('addSystemMessage appends a system message without touching node state', () => {
    useSessionStore.getState().addUserMessage('bearing is grinding');

    useSessionStore.getState().addSystemMessage('Connection closed.');

    const state = useSessionStore.getState();
    expect(state.messages[1]).toMatchObject({ kind: 'system', content: 'Connection closed.' });
    expect(state.nodeStatus.extract).toBe('active');
    expect(state.activeNode).toBe('extract');
  });

  it('error clears any pending approval', () => {
    useSessionStore.getState().handleServerEvent({
      type: 'approval_request',
      payload: { required_parts: [], inventory_status: [] },
    });

    useSessionStore.getState().handleServerEvent({ type: 'error', message: 'MCP unreachable' });

    expect(useSessionStore.getState().pendingApproval).toBeNull();
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
