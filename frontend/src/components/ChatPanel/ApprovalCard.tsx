import type { ApprovalRequestPayload } from '../../store/sessionStore';

export interface ApprovalCardProps {
  payload: ApprovalRequestPayload;
  decision?: 'approve' | 'reject';
  onDecide: (decision: 'approve' | 'reject') => void;
  disabled: boolean;
}

export function ApprovalCard({ payload, decision, onDecide, disabled }: ApprovalCardProps) {
  const resolved = decision !== undefined;
  const buttonsDisabled = resolved || disabled;

  return (
    <div className="rounded border border-amber-400 bg-amber-50 p-3 text-sm">
      <p className="font-semibold text-amber-800">Parts order needs approval</p>
      <ul className="mt-2 space-y-1">
        {payload.inventory_status.map((item) => (
          <li key={item.part_id}>
            {item.part_id}: {item.status}
          </li>
        ))}
      </ul>
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          disabled={buttonsDisabled}
          onClick={() => onDecide('approve')}
          className="rounded bg-green-600 px-3 py-1 text-white disabled:opacity-50"
        >
          Approve
        </button>
        <button
          type="button"
          disabled={buttonsDisabled}
          onClick={() => onDecide('reject')}
          className="rounded bg-red-600 px-3 py-1 text-white disabled:opacity-50"
        >
          Reject
        </button>
      </div>
      {resolved && <p className="mt-2 text-xs text-gray-500">Decision: {decision}</p>}
    </div>
  );
}
