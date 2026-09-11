# Example inputs

The demo's `manuals` and `inventory` collections are seeded with a small,
synthetic dataset (see `backend/backend/rag/manuals_seed.py` and
`mcp_server/mcp_server/seed_data.py`). The examples below are built directly
from that seed data, so they'll actually produce a diagnosis, an inventory
check, and — for the parts that are low/out of stock — a HITL approval card.

Paste these into the chat input after clicking **Start Session**.

## Straightforward — parts in stock, no approval needed

```
Machine CNC-Mill-200 is throwing error E101. Getting a loud grinding noise
and vibration above 2000 RPM.
```
Expected: diagnosis points to the main spindle bearing (`BEARING-X4`,
12 in stock, above its threshold of 5) → work order completes immediately,
no approval prompt.

```
The Conveyor-Belt-A7 drive motor just stalled, error code B20.
```
Expected: diagnosis points to `MOTOR-C2` (4 in stock, above threshold 1) →
completes immediately.

```
CNC-Mill-200 error E204 — motor seems to be overheating under load.
```
Expected: diagnosis points to `MOTOR-C2` — also in stock, completes
immediately.

## Low stock — triggers the approval card

```
Conveyor-Belt-A7 is showing error B12, belt looks frayed and slipping.
```
Expected: diagnosis points to `BELT-A7`, which is below its reorder
threshold (2 on hand, threshold 3) → an approval card appears asking you to
approve/reject ordering more before the work order finalizes.

## Out of stock — the most dramatic approval case

```
Hydraulic-Press-9 machine, error H33. Losing hydraulic pressure, some
fluid pooling near the valve.
```
Expected: diagnosis points to `VALVE-H9` (0 on hand — out of stock) and
possibly `SEAL-K1` (1 on hand, below threshold 2) → approval card with a
shortfall on at least one part.

## Missing info — triggers a clarification question instead of failing

```
It's making a weird noise and I think a part might be broken.
```
Expected: no machine ID or error code given, so the agent asks a
clarifying question (e.g. "I need the machine ID and error code to
continue — could you provide it?") instead of guessing.

## Unrecognized error — no fabricated diagnosis

```
Machine CNC-Mill-200, error code Z999, not sure what's wrong.
```
Expected: no manual matches an unseeded error code, so the agent should say
no relevant procedure was found rather than making something up.

## PDF upload

Any text-extractable PDF containing a description like the examples above
works — e.g. a one-page "incident report" mentioning a machine ID and error
code. Click **Attach PDF**, confirm the extracted text looks right, then
send it (optionally with an added note) via the chat input.

## Reference: seeded data

| Machine type | Error code | Root cause | Part | Qty on hand | Reorder threshold | Stock status |
|---|---|---|---|---|---|---|
| CNC-Mill-200 | E101 | Spindle bearing wear | BEARING-X4 | 12 | 5 | in stock |
| CNC-Mill-200 | E204 | Drive motor overcurrent | MOTOR-C2 | 4 | 1 | in stock |
| Conveyor-Belt-A7 | B12 | Belt slippage/tearing | BELT-A7 | 2 | 3 | low stock |
| Conveyor-Belt-A7 | B20 | Drive motor stall | MOTOR-C2 | 4 | 1 | in stock |
| Hydraulic-Press-9 | H33 | Hydraulic pressure loss | VALVE-H9 | 0 | 2 | out of stock |
| Hydraulic-Press-9 | H33 | Hydraulic pressure loss (alt. cause) | SEAL-K1 | 1 | 2 | low stock |
