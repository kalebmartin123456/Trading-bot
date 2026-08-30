from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib

import pandas as pd

from trading_desk.agents.relative_strength import (
    build_relative_strength_context,
    make_relative_strength_entry_filter,
)
from trading_desk.backtest import run_backtest
from trading_desk.config import Config


DEFAULT_BREADTH_UNIVERSE = (
    "BTC/USD",
    "ETH/USD",
    "SOL/USD",
    "LTC/USD",
    "BCH/USD",
    "LINK/USD",
    "UNI/USD",
    "AAVE/USD",
    "DOGE/USD",
    "AVAX/USD",
)


def _utc(value: datetime | pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def _result_delta(baseline: dict, candidate: dict) -> dict:
    return {
        "return_pct": candidate["return_pct"] - baseline["return_pct"],
        "excess_return_pct": candidate["excess_return_pct"] - baseline["excess_return_pct"],
        "max_drawdown_pct": candidate["max_drawdown_pct"] - baseline["max_drawdown_pct"],
        "profit_factor": candidate["profit_factor"] - baseline["profit_factor"],
        "expectancy_dollars": candidate["expectancy_dollars"] - baseline["expectancy_dollars"],
        "trades": candidate["trades"] - baseline["trades"],
    }


def _holdout_fingerprint(
    frames: dict[str, pd.DataFrame],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> str:
    digest = hashlib.sha256()
    for symbol in sorted(frames):
        series = frames[symbol].loc[
            (frames[symbol].index >= start) & (frames[symbol].index < end),
            "close",
        ]
        digest.update(symbol.encode())
        digest.update(series.to_csv(header=False).encode())
    return digest.hexdigest()


def _validation_gate(comparisons: dict[str, dict]) -> dict:
    """Apply a fixed absolute-and-incremental gate without touching holdout."""
    requirements = {
        "positive_return": "candidate return > 0%",
        "positive_incremental_return": "candidate return > baseline return",
        "profit_factor": "candidate profit factor > 1.0",
        "positive_expectancy": "candidate expectancy/trade > $0",
        "adequate_sample": "candidate completed trades >= 30",
        "drawdown_noninferior": "candidate max drawdown <= baseline max drawdown",
    }
    failures: list[str] = []
    symbol_checks: dict[str, dict[str, bool]] = {}
    for symbol, comparison in comparisons.items():
        baseline = comparison["baseline"]
        candidate = comparison["candidate"]
        checks = {
            "positive_return": bool(candidate["return_pct"] > 0),
            "positive_incremental_return": bool(
                candidate["return_pct"] > baseline["return_pct"]
            ),
            "profit_factor": bool(candidate["profit_factor"] > 1.0),
            "positive_expectancy": bool(candidate["expectancy_dollars"] > 0),
            "adequate_sample": bool(candidate["trades"] >= 30),
            "drawdown_noninferior": bool(
                candidate["max_drawdown_pct"] <= baseline["max_drawdown_pct"]
            ),
        }
        symbol_checks[symbol] = checks
        failures.extend(f"{symbol}: {name}" for name, passed in checks.items() if not passed)
    return {
        "status": "advance" if not failures else "reject",
        "requirements": requirements,
        "symbol_checks": symbol_checks,
        "failures": failures,
        "holdout_scored": False,
    }


def run_sealed_validation(
    *,
    frames: dict[str, pd.DataFrame],
    cfg: Config,
    evaluation_start: datetime | pd.Timestamp,
    evaluation_end: datetime | pd.Timestamp,
) -> dict:
    """Compare the frozen baseline and candidate without scoring final holdout."""
    start = _utc(evaluation_start)
    end = _utc(evaluation_end)
    if end <= start:
        raise ValueError("evaluation_end must be after evaluation_start.")
    duration = end - start
    train_end = start + duration * 0.60
    validation_end = start + duration * 0.80
    train_end = train_end.floor("h")
    validation_end = validation_end.floor("h")

    missing = sorted(set(cfg.symbols) - set(frames))
    if missing:
        raise ValueError(f"Missing execution-symbol frames: {missing}")

    context = build_relative_strength_context(frames)
    candidate_filter = make_relative_strength_entry_filter(context)
    periods = {
        "development": (start, train_end),
        "validation": (train_end, validation_end),
    }
    comparisons: dict[str, dict] = {}
    for period_name, (period_start, period_end) in periods.items():
        comparisons[period_name] = {}
        for symbol in cfg.symbols:
            baseline = asdict(
                run_backtest(
                    symbol,
                    frames[symbol],
                    cfg,
                    trade_start=period_start,
                    trade_end=period_end,
                )
            )
            candidate = asdict(
                run_backtest(
                    symbol,
                    frames[symbol],
                    cfg,
                    entry_filter=candidate_filter,
                    trade_start=period_start,
                    trade_end=period_end,
                )
            )
            comparisons[period_name][symbol] = {
                "baseline": baseline,
                "candidate": candidate,
                "candidate_minus_baseline": _result_delta(baseline, candidate),
            }

    return {
        "candidate": "relative_strength_v1_entry_filter",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "breadth_universe": sorted(frames),
        "survivorship_bias_warning": (
            "The breadth universe is selected from currently available assets and is research-only."
        ),
        "splits": {
            "development": {"start": start.isoformat(), "end": train_end.isoformat()},
            "validation": {"start": train_end.isoformat(), "end": validation_end.isoformat()},
            "sealed_holdout": {
                "start": validation_end.isoformat(),
                "end": end.isoformat(),
                "scored": False,
                "fingerprint": _holdout_fingerprint(frames, validation_end, end),
            },
        },
        "comparisons": comparisons,
        "validation_gate": _validation_gate(comparisons["validation"]),
    }


def research_fetch_days(evaluation_days: int) -> int:
    # Thirty days of causal warm-up precede the evaluation interval.
    if evaluation_days <= 0:
        raise ValueError("evaluation_days must be positive.")
    return evaluation_days + 30


def evaluation_start(end: datetime, evaluation_days: int) -> datetime:
    return end - timedelta(days=evaluation_days)
