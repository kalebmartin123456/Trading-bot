# Build Roadmap

## V0 — now
Deterministic BTC/ETH hourly desk, backtest, risk engine, prediction ledger.

Baseline status (2026-08-30): failed the edge test. All eight 90/180/365/730-day
BTC/ETH replays had negative net expectancy. Keep live capital at $0 and preserve
the frozen results in `research/baseline_2026-08-30.md` as the control.

## V1 — forward-test
Run every hour and store every agent prediction:
- technical
- regime
- adversarial veto
- final desk decision
- reference price
- 1h / 6h / 24h realized outcome

Do not optimize parameters during the forward-test.

## V2 — information agents
Add independent inputs:
- crypto news/catalyst
- macro calendar
- market-wide breadth
- order-book / spread quality
- funding / futures basis if reliable source is added
- on-chain data if reliable source is added

LLMs must return structured JSON. They may propose or veto trades; they may not size positions.

## V3 — learning layer
Calibrate each agent by:
- asset
- regime
- confidence bucket
- horizon

Weight agents by out-of-sample performance only.

## V4 — paper execution API
Connect real Alpaca paper-trading endpoints.
Require:
- idempotent order IDs
- stop protection
- position reconciliation
- stale-data guard
- max order count
- kill switch
- audit log

## V5 — tiny live capital
Only after written promotion gate is passed.
Start with a small fraction of the available $10k.
