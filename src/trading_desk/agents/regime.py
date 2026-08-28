from trading_desk.models import AgentSignal

def regime_signal(symbol, row):
    spread = (row["ema20"] - row["ema50"]) / row["close"]
    trending_up = spread > 0.003
    extreme_vol = row["vol24"] > 1.20

    if trending_up and not extreme_vol:
        score = 0.75
        direction = "LONG"
        reason = f"constructive trend; EMA spread={spread:.2%}, annualized vol={row['vol24']:.0%}"
    elif trending_up and extreme_vol:
        score = 0.25
        direction = "FLAT"
        reason = f"uptrend but volatility is extreme; vol={row['vol24']:.0%}"
    else:
        score = -0.40
        direction = "FLAT"
        reason = f"no constructive trend; EMA spread={spread:.2%}"

    return AgentSignal(
        agent="regime",
        symbol=symbol,
        timestamp=row.name.to_pydatetime(),
        score=score,
        direction=direction,
        confidence=0.75,
        reason=reason,
    )
