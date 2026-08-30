# Paper execution operations

This runbook is for paper trading only. Live execution is deliberately unavailable.

## Activation checklist

Paper execution must remain disabled until all items are true:

1. Use a dedicated, empty Alpaca paper account with paper-only credentials.
2. Confirm no positions or open orders exist in that account.
3. Keep `PAPER_TRADING=true` and `LIVE_TRADING_ENABLED=false`.
4. Set `PAPER_EXECUTION_ENABLED=true` only for the execution environment.
5. Run one attended `trading-desk paper-execute` cycle and verify a `paper` status with the expected reconciliation.
6. Confirm `data/paper_execution_state.json` and `data/paper_execution_audit.jsonl` are on persistent storage. They are intentionally excluded from Git.
7. Do not schedule execution until alerting observes process failures and every `halted` result.
8. Guarantee only one execution cycle can run at a time; concurrent invocations are not supported.

## Fail-closed behavior

Every cycle reconciles the broker before reading signals. The executor persists an operator halt when it sees an account block, unmanaged or unexpected positions, unexpected symbols, or an order without the desk's deterministic `desk-` client ID.

A daily-loss, drawdown, insolvency, operator, stale-data, invalid-data, or cross-symbol timestamp halt blocks entries. It cancels desk orders first, confirms cancellation, then submits liquidation orders for state-managed positions. If cancellation is not yet confirmed, the cycle waits and retries on the next invocation rather than adding another order.

- Daily-loss halt: may clear on the next UTC day, only after positions and orders are confirmed empty.
- Drawdown, insolvency, or operator halt: never auto-clears. Human investigation and an explicit reviewed state recovery are required.
- Unmanaged positions and foreign orders are never automatically altered; this prevents the desk from taking control of activity it did not create.

## State and audit invariants

- State updates are atomic and flushed to disk.
- Every completed normal or halted cycle appends a flushed JSONL audit record.
- Deterministic client order IDs make repeated submission attempts idempotent at the broker.
- Exit submission ends the cycle; new entries wait for the next reconciliation.
- Buying power is decremented across proposed entries in the same cycle.
- At most four new orders are submitted per cycle by default.
- Configuration bounds are validated at startup.

## Known paper-only limitations

- Stops are software-managed on the hourly cadence, not broker-native resting stops. A crash, API outage, or sharp intrahour move can exceed the modeled stop.
- Hourly OHLC research assumptions do not reproduce real queue position, spread changes, partial fills, or market impact.
- The current strategy has no demonstrated historical edge and is not approved for autonomous paper execution yet.
- No live-account recovery procedure exists because live trading is intentionally disabled.

These limitations must be resolved or explicitly accepted in a written promotion review before any live-capital implementation is designed.
