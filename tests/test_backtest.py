from datetime import datetime, timezone

import pandas as pd

from trading_desk.backtest import run_backtest
from trading_desk.config import Config
from trading_desk.models import DeskDecision


def test_stop_is_checked_on_entry_bar(monkeypatch):
    index = pd.date_range("2026-01-01", periods=4, freq="h", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0, 100.0],
            "high": [101.0, 101.0, 101.0, 101.0],
            "low": [99.0, 90.0, 99.0, 99.0],
            "close": [100.0, 100.0, 100.0, 100.0],
            "ema20": [101.0, 101.0, 101.0, 101.0],
            "ema50": [100.0, 100.0, 100.0, 100.0],
            "vol24": [0.5, 0.5, 0.5, 0.5],
            "ret6": [0.01, 0.01, 0.01, 0.01],
            "ret24": [0.02, 0.02, 0.02, 0.02],
            "high20_prev": [99.0, 99.0, 99.0, 99.0],
        },
        index=index,
    )

    monkeypatch.setattr("trading_desk.backtest.prepare", lambda frame: frame)

    def fake_decide(symbol, row):
        is_first_signal = row.name == index[0]
        return DeskDecision(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            direction="LONG" if is_first_signal else "FLAT",
            score=1.0 if is_first_signal else 0.0,
            confidence=1.0,
            stop_price=95.0 if is_first_signal else None,
            rationale=[],
        )

    monkeypatch.setattr("trading_desk.backtest.decide", fake_decide)

    trade_log = []
    result = run_backtest("BTC/USD", df, Config(), trade_log=trade_log)

    assert result.trades == 1
    assert result.stop_exits == 1
    assert result.losses == 1
    assert result.ending_equity < result.starting_equity
    assert len(trade_log) == 1
    assert trade_log[0]["exit_reason"] == "stop"
