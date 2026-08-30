from __future__ import annotations

import pandas as pd

from trading_desk.models import AgentSignal


def build_relative_strength_context(
    frames: dict[str, pd.DataFrame],
    benchmark_symbol: str = "BTC/USD",
) -> pd.DataFrame:
    """Build causal trend, breadth, and relative-strength features."""
    if benchmark_symbol not in frames:
        raise ValueError(f"Benchmark {benchmark_symbol} is missing from the breadth universe.")
    closes = pd.concat(
        {symbol: frame["close"].astype(float) for symbol, frame in frames.items()},
        axis=1,
    ).sort_index()
    ema168 = closes.ewm(span=168, adjust=False, min_periods=168).mean()
    ret72 = closes.pct_change(72, fill_method=None)
    ret168 = closes.pct_change(168, fill_method=None)

    context = pd.DataFrame(index=closes.index)
    context["breadth_above_ema168"] = (closes > ema168).mean(axis=1)
    context["median_ret72"] = ret72.median(axis=1)
    context["benchmark_above_ema168"] = closes[benchmark_symbol] > ema168[benchmark_symbol]
    context["benchmark_ret168"] = ret168[benchmark_symbol]

    for symbol in frames:
        prefix = symbol.replace("/", "_")
        context[f"{prefix}_above_ema168"] = closes[symbol] > ema168[symbol]
        context[f"{prefix}_ret72"] = ret72[symbol]
        context[f"{prefix}_ret168"] = ret168[symbol]
        context[f"{prefix}_relative_ret72"] = ret72[symbol] - context["median_ret72"]
    return context


def relative_strength_signal(
    symbol: str,
    row: pd.Series,
    context: pd.DataFrame,
) -> AgentSignal:
    prefix = symbol.replace("/", "_")
    if row.name not in context.index:
        return AgentSignal(
            agent="relative_strength",
            symbol=symbol,
            timestamp=row.name.to_pydatetime(),
            score=-1.0,
            direction="FLAT",
            confidence=0.95,
            reason="No synchronized breadth context.",
        )

    snapshot = context.loc[row.name]
    required = [
        "breadth_above_ema168",
        "benchmark_above_ema168",
        "benchmark_ret168",
        f"{prefix}_above_ema168",
        f"{prefix}_ret72",
        f"{prefix}_relative_ret72",
    ]
    if snapshot[required].isna().any():
        return AgentSignal(
            agent="relative_strength",
            symbol=symbol,
            timestamp=row.name.to_pydatetime(),
            score=-1.0,
            direction="FLAT",
            confidence=0.95,
            reason="Relative-strength features are not fully warmed up.",
        )

    breadth = float(snapshot["breadth_above_ema168"])
    benchmark_up = bool(snapshot["benchmark_above_ema168"]) and float(snapshot["benchmark_ret168"]) > 0
    own_trend = bool(snapshot[f"{prefix}_above_ema168"])
    relative_leader = float(snapshot[f"{prefix}_relative_ret72"]) > 0
    own_momentum = float(snapshot[f"{prefix}_ret72"]) > 0

    score = (
        (0.30 if benchmark_up else -0.30)
        + (0.25 if breadth >= 0.60 else -0.25)
        + (0.20 if own_trend else -0.20)
        + (0.15 if relative_leader else -0.15)
        + (0.10 if own_momentum else -0.10)
    )
    direction = (
        "LONG"
        if benchmark_up and breadth >= 0.60 and own_trend and relative_leader and own_momentum
        else "FLAT"
    )
    return AgentSignal(
        agent="relative_strength",
        symbol=symbol,
        timestamp=row.name.to_pydatetime(),
        score=max(-1.0, min(1.0, score)),
        direction=direction,
        confidence=min(0.95, 0.55 + abs(score) * 0.35),
        reason=(
            f"benchmark_up={benchmark_up}, breadth={breadth:.0%}, own_trend={own_trend}, "
            f"relative_leader={relative_leader}, ret72={float(snapshot[f'{prefix}_ret72']):.2%}"
        ),
        metadata={
            "breadth_above_ema168": breadth,
            "benchmark_up": benchmark_up,
            "own_trend": own_trend,
            "relative_ret72": float(snapshot[f"{prefix}_relative_ret72"]),
        },
    )


def make_relative_strength_entry_filter(context: pd.DataFrame):
    """Return a research-only entry filter; it never changes position sizing."""

    def entry_filter(symbol: str, row: pd.Series) -> bool:
        return relative_strength_signal(symbol, row, context).direction == "LONG"

    return entry_filter
