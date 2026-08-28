def veto_reason(row) -> str | None:
    if row["atr14"] <= 0:
        return "Invalid ATR."

    atr_pct = row["atr14"] / row["close"]
    distance_ema20 = (row["close"] - row["ema20"]) / row["atr14"]

    if atr_pct > 0.05:
        return f"Hourly ATR too large ({atr_pct:.1%} of price)."
    if distance_ema20 > 3.0:
        return f"Price is too extended ({distance_ema20:.1f} ATR above EMA20)."
    if row["ret6"] > 0.12:
        return f"Six-hour move is too extended ({row['ret6']:.1%})."
    return None
