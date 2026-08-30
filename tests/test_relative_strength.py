import pandas as pd

from trading_desk.agents.relative_strength import (
    build_relative_strength_context,
    relative_strength_signal,
)


SYMBOLS = (
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


def _frames(slopes: dict[str, float] | None = None) -> dict[str, pd.DataFrame]:
    index = pd.date_range("2025-01-01", periods=400, freq="h", tz="UTC")
    slopes = slopes or {}
    frames = {}
    for offset, symbol in enumerate(SYMBOLS):
        slope = slopes.get(symbol, 0.001)
        closes = [100.0 + offset + slope * 100 * step for step in range(len(index))]
        frames[symbol] = pd.DataFrame({"close": closes}, index=index)
    return frames


def test_relative_strength_accepts_leader_in_broad_uptrend():
    frames = _frames({"BTC/USD": 0.003, "ETH/USD": 0.0025})
    context = build_relative_strength_context(frames)
    row = frames["ETH/USD"].iloc[-1]

    signal = relative_strength_signal("ETH/USD", row, context)

    assert signal.direction == "LONG"
    assert signal.metadata["breadth_above_ema168"] >= 0.60
    assert signal.metadata["relative_ret72"] > 0


def test_relative_strength_rejects_narrow_market():
    slopes = {symbol: -0.0005 for symbol in SYMBOLS}
    slopes.update({"BTC/USD": 0.003, "ETH/USD": 0.0025})
    frames = _frames(slopes)
    context = build_relative_strength_context(frames)
    row = frames["ETH/USD"].iloc[-1]

    signal = relative_strength_signal("ETH/USD", row, context)

    assert signal.direction == "FLAT"
    assert signal.metadata["breadth_above_ema168"] < 0.60


def test_relative_strength_features_do_not_look_into_future():
    frames = _frames({"BTC/USD": 0.003, "ETH/USD": 0.0025})
    cutoff = frames["BTC/USD"].index[250]
    original = build_relative_strength_context(frames).loc[cutoff]

    mutated = {symbol: frame.copy() for symbol, frame in frames.items()}
    for frame in mutated.values():
        frame.loc[frame.index > cutoff, "close"] *= 100
    changed = build_relative_strength_context(mutated).loc[cutoff]

    pd.testing.assert_series_equal(original, changed)
