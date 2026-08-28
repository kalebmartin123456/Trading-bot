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

Every hour the desk:

1. Fetches recent BTC/USD and ETH/USD hourly bars.
2. Ignores the still-forming candle.
3. Produces Technical, Regime, and Head-of-Desk predictions.
4. Stores independent 1h, 6h, and 24h predictions in `data/predictions.jsonl`.
5. Grades predictions once their horizon has elapsed.
6. Commits the updated research history back to the repository.

The JSONL ledger is intentionally Git-friendly so every prediction and subsequent outcome is auditable.

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
- No leverage
- No shorts
- Live execution disabled

## Commands

```bash
trading-desk scan
trading-desk backtest --symbol BTC/USD --days 180
trading-desk run-hourly
trading-desk grade
trading-desk scorecard
```

## GitHub Actions

`CI` runs tests on pushes and pull requests.

`Hourly Forward Test` runs at minute 7 of every hour and can also be started manually. It expects repository secrets named `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`. Keep `LIVE_TRADING_ENABLED=false`.

## Promotion gate before any meaningful live capital

Do not promote the system because of a few profitable days. Minimum research gate:

- At least 100 forward-tested trades
- Positive net expectancy after realistic fees/slippage
- Profit factor >= 1.30
- Max drawdown < 8%
- No risk-engine violations
- No single trade responsible for the majority of profits
- Evidence across more than one market regime

The first live allocation, if the gate is eventually passed, should still be a small fraction of available capital.
