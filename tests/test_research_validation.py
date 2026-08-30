from dataclasses import replace
import json

import pandas as pd

from trading_desk.backtest import BacktestResult
from trading_desk.config import Config
from trading_desk.research_validation import (
    DEFAULT_BREADTH_UNIVERSE,
    run_sealed_validation,
)


def _result(symbol: str) -> BacktestResult:
    return BacktestResult(
        symbol=symbol,
        period_start="2025-01-01T00:00:00+00:00",
        period_end="2025-01-02T00:00:00+00:00",
        bars=24,
        starting_equity=10_000,
        ending_equity=10_000,
        return_pct=0,
        buy_hold_ending_equity=10_000,
        buy_hold_return_pct=0,
        excess_return_pct=0,
        max_drawdown_pct=0,
        trades=0,
        wins=0,
        losses=0,
        win_rate_pct=0,
        average_winner_dollars=0,
        average_loser_dollars=0,
        profit_factor=0,
        expectancy_dollars=0,
        best_trade_dollars=0,
        worst_trade_dollars=0,
        best_trade_pct=0,
        worst_trade_pct=0,
        exposure_pct=0,
        average_holding_hours=0,
        stop_exits=0,
        signal_exits=0,
        risk_halt_exits=0,
        modeled_costs_dollars=0,
        open_position=False,
        unrealized_pnl_dollars=0,
        entry_filter_rejections=0,
    )


def test_sealed_validation_never_scores_holdout(monkeypatch):
    index = pd.date_range("2025-01-01", periods=1_000, freq="h", tz="UTC")
    frames = {
        symbol: pd.DataFrame({"close": range(1, 1_001)}, index=index)
        for symbol in DEFAULT_BREADTH_UNIVERSE
    }
    calls = []

    def fake_backtest(symbol, df, cfg, **kwargs):
        calls.append(kwargs)
        result = _result(symbol)
        return replace(result, return_pct=1 if kwargs.get("entry_filter") else 0)

    monkeypatch.setattr("trading_desk.research_validation.run_backtest", fake_backtest)
    end = index[-1] + pd.Timedelta(hours=1)
    start = index[200]
    report = run_sealed_validation(
        frames=frames,
        cfg=Config(),
        evaluation_start=start,
        evaluation_end=end,
    )

    holdout = report["splits"]["sealed_holdout"]
    holdout_start = pd.Timestamp(holdout["start"])
    assert holdout["scored"] is False
    assert len(holdout["fingerprint"]) == 64
    assert len(calls) == 8
    assert all(pd.Timestamp(call["trade_end"]) <= holdout_start for call in calls)
    assert sum("entry_filter" in call for call in calls) == 4
    assert report["validation_gate"]["status"] == "reject"
    assert report["validation_gate"]["holdout_scored"] is False
    json.dumps(report)
