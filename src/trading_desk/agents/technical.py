from trading_desk.models import AgentSignal

def technical_signal(symbol, row):
    trend = 1 if row["ema20"] > row["ema50"] else -1
    breakout = 1 if row["close"] > row["high20_prev"] else 0
    mom6 = 1 if row["ret6"] > 0 else -1
    mom24 = 1 if row["ret24"] > 0 else -1

    raw = 0.40 * trend + 0.25 * breakout + 0.15 * mom6 + 0.20 * mom24
    score = max(-1.0, min(1.0, raw))
    direction = "LONG" if score >= 0.45 else "FLAT"
    confidence = min(0.95, 0.50 + abs(score) * 0.45)

    return AgentSignal(
        agent="technical",
        symbol=symbol,
        timestamp=row.name.to_pydatetime(),
        score=score,
        direction=direction,
        confidence=confidence,
        reason=f"trend={trend}, breakout={breakout}, ret6={row['ret6']:.3%}, ret24={row['ret24']:.3%}",
    )
