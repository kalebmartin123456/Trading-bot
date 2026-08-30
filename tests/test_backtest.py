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


def test_entry_filter_can_reject_entries_without_changing_signal_logic(monkeypatch):
    index = pd.date_range("2026-01-01", periods=5, freq="h", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [100.0] * 5,
            "high": [101.0] * 5,
            "low": [99.0] * 5,
            "close": [100.0] * 5,
            "ema20": [101.0] * 5,
            "ema50": [100.0] * 5,
            "vol24": [0.5] * 5,
            "ret6": [0.01] * 5,
            "ret24": [0.02] * 5,
            "high20_prev": [99.0] * 5,
        },
        index=index,
    )
    monkeypatch.setattr("trading_desk.backtest.prepare", lambda frame: frame)
    monkeypatch.setattr(
        "trading_desk.backtest.decide",
        lambda symbol, row: DeskDecision(
            symbol=symbol,
            timestamp=row.name.to_pydatetime(),
            direction="LONG",
            score=1.0,
            confidence=1.0,
            stop_price=95.0,
            rationale=[],
        ),
    )

    result = run_backtest(
        "BTC/USD",
        df,
        Config(),
        entry_filter=lambda symbol, row: False,
    )

    assert result.trades == 0
    assert result.entry_filter_rejections == 4
    assert result.ending_equity == result.starting_equity


def test_trade_window_uses_prior_bar_but_does_not_trade_before_start(monkeypatch):
    index = pd.date_range("2026-01-01", periods=8, freq="h", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [100.0] * 8,
            "high": [101.0] * 8,
            "low": [99.0] * 8,
            "close": [100.0] * 8,
            "ema20": [101.0] * 8,
            "ema50": [100.0] * 8,
            "vol24": [0.5] * 8,
            "ret6": [0.01] * 8,
            "ret24": [0.02] * 8,
            "high20_prev": [99.0] * 8,
        },
        index=index,
    )
    monkeypatch.setattr("trading_desk.backtest.prepare", lambda frame: frame)
    observed_signal_times = []

    def fake_decide(symbol, row):
        observed_signal_times.append(row.name)
        return DeskDecision(
            symbol=symbol,
            timestamp=row.name.to_pydatetime(),
            direction="FLAT",
            score=0.0,
            confidence=1.0,
            stop_price=None,
            rationale=[],
        )

    monkeypatch.setattr("trading_desk.backtest.decide", fake_decide)
    result = run_backtest(
        "BTC/USD",
        df,
        Config(),
        trade_start=index[3],
        trade_end=index[6],
    )

    assert result.period_start == index[3].isoformat()
    assert result.period_end == index[5].isoformat()
    assert observed_signal_times[0] == index[2]
    assert all(timestamp < index[6] for timestamp in observed_signal_times)


def test_portfolio_drawdown_halt_liquidates_and_stays_halted(monkeypatch):
    index = pd.date_range("2026-01-01", periods=6, freq="h", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [100.0, 100.0, 50.0, 100.0, 100.0, 100.0],
            "high": [101.0, 101.0, 51.0, 101.0, 101.0, 101.0],
            "low": [99.0, 99.0, 49.0, 99.0, 99.0, 99.0],
            "close": [100.0, 100.0, 50.0, 100.0, 100.0, 100.0],
            "ema20": [101.0] * 6,
            "ema50": [100.0] * 6,
            "vol24": [0.5] * 6,
            "ret6": [0.01] * 6,
            "ret24": [0.02] * 6,
            "high20_prev": [99.0] * 6,
        },
        index=index,
    )
    monkeypatch.setattr("trading_desk.backtest.prepare", lambda frame: frame)
    monkeypatch.setattr(
        "trading_desk.backtest.decide",
        lambda symbol, row: DeskDecision(
            symbol=symbol,
            timestamp=row.name.to_pydatetime(),
            direction="LONG",
            score=1.0,
            confidence=1.0,
            stop_price=98.0,
            rationale=[],
        ),
    )

    result = run_backtest(
        "BTC/USD",
        df,
        Config(assumed_fee_bps=0, assumed_slippage_bps=0),
    )

    assert result.risk_halt_exits == 1
    assert result.trades == 1
    assert result.open_position is False
    assert result.ending_equity < result.starting_equity
