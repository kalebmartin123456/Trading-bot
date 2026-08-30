# AI Trading Desk

A deliberately constrained crypto research + paper-trading system.

## Current mandate

- Universe: BTC/USD and ETH/USD
- Timeframe: 1 hour
- Direction: long-only
- Leverage: none
- Live trading: disabled
- Objective: prove or disprove positive expectancy before exposing capital

## What runs automatically

Every hour the research desk:

1. Fetches recent BTC/USD and ETH/USD hourly bars.
2. Ignores the still-forming candle.
3. Produces Technical, Regime, and Head-of-Desk predictions.
4. Stores independent 1h, 6h, and 24h predictions in `data/predictions.jsonl`.
5. Grades predictions once their horizon has elapsed.
6. Commits the updated research history back to the repository.

The JSONL ledger is intentionally Git-friendly so every prediction and subsequent outcome is auditable.

## Paper brokerage execution

V1 now contains a real Alpaca paper brokerage execution path. It is opt-in and paper-only.

`trading-desk paper-execute` performs one reconciliation/execution cycle:

1. Connects to Alpaca with `TradingClient(..., paper=True)`.
2. Reads actual paper account equity, buying power, positions, and open orders.
3. Persists a hard operator halt if positions, orders, symbols, or account state do not reconcile.
4. Rejects stale, invalid, future-dated, or cross-symbol-unsynchronized market data.
5. Cancels desk orders and liquidates managed positions on daily-loss, drawdown, insolvency, data, or operator halts.
6. Evaluates the latest fully closed hourly candle.
7. Exits managed positions when the desk turns FLAT or the software stop is breached.
8. Sends every proposed entry through the deterministic Risk Engine.
9. Applies an additional 10% of equity per-order paper cap and four-order cycle cap.
10. Uses deterministic client order IDs so repeated cycles are broker-idempotent.
11. Atomically persists state and appends a flushed JSONL audit record.

This release has no live brokerage path. The paper broker hard-codes `paper=True`, and the CLI refuses to start when `LIVE_TRADING_ENABLED=true`.

Hard drawdown/insolvency/operator halts never auto-clear. A daily-loss halt may clear on the next UTC day only after all positions and orders are confirmed empty.

Important: V1 stops are software-managed and checked on the hourly execution cadence. They are not broker-native resting stop orders. A process/API outage or intrahour gap can therefore exceed the modeled stop. See [`docs/paper_operations.md`](docs/paper_operations.md) for activation, recovery, and known limitations.

## Agents

- Technical Agent: trend, momentum, breakout evidence.
- Regime Agent: identifies constructive trend vs hostile/high-volatility environments.
- Devil's Advocate: vetoes extended or fragile setups.
- Head of Desk: combines independent evidence into a final decision.
- Risk Engine: deterministic sizing and kill switches. AI cannot override it.

## Hard risk defaults

- Risk per trade: 0.35% of equity
- Max symbol notional: 20% of equity
- Max total exposure: 35% of equity
- Daily loss stop: 1%
- Portfolio drawdown kill switch: 8%
- Paper V1 max new order: 10% of equity
- No leverage
- No shorts
- Live execution disabled

## Commands

```bash
trading-desk scan
trading-desk backtest --symbol BTC/USD --days 180 --end 2026-08-30T16:00:00+00:00
trading-desk research-validate --days 730 --end 2026-08-30T16:00:00+00:00
trading-desk run-hourly
trading-desk grade
trading-desk scorecard
trading-desk paper-execute
```

## Turning paper execution on

Keep credentials out of the repository. Configure Alpaca paper credentials as environment/repository secrets, then set:

```text
PAPER_TRADING=true
PAPER_EXECUTION_ENABLED=true
LIVE_TRADING_ENABLED=false
```

Do not use live-account credentials for the paper experiment.

## GitHub Actions

`CI` runs tests on pushes and pull requests.

`Hourly Forward Test` runs at minute 7 of every hour and can also be started manually. It expects repository secrets named `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`. The research workflow does not currently place paper orders; execution remains a separate explicit command until credentials and the first reconciliation are verified.

`Historical Research` and `Sealed Research Validation` are manual, read-only workflows requiring a fixed cutoff. The sealed workflow scores only the first 80% of the chronological interval and uploads its JSON report without evaluating the final 20%.

## Promotion gate before any meaningful live capital

Do not promote the system because of a few profitable days. Minimum research gate:

- At least 100 forward-tested completed trades
- Positive net expectancy after realistic fees/slippage
- Profit factor >= 1.30
- Max drawdown < 8%
- No risk-engine violations
- No single trade responsible for the majority of profits
- Evidence across more than one market regime

The first live allocation, if the gate is eventually passed, should still be a small fraction of available capital.

## Baseline status

The fixed BTC/USD and ETH/USD desk did **not** demonstrate an edge in the
90/180/365/730-day baseline ending 2026-08-30. All eight net returns and trade
expectancies were negative after modeled costs. Live promotion remains blocked.

See [`research/baseline_2026-08-30.md`](research/baseline_2026-08-30.md) for the
full results, regime diagnostics, and audit findings.

The first breadth/relative-strength candidate also failed its profitability gate. It reduced validation losses and drawdown, especially in the falling regime, but both assets still had negative returns, negative expectancy, and profit factor below 1. It remains research-only; its final holdout was not scored. See [`research/relative_strength_v1_2026-08-30.md`](research/relative_strength_v1_2026-08-30.md).
