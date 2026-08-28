from trading_desk.models import DeskDecision
from trading_desk.agents.technical import technical_signal
from trading_desk.agents.regime import regime_signal
from trading_desk.agents.devils_advocate import veto_reason

def decide(symbol, row) -> DeskDecision:
    tech = technical_signal(symbol, row)
    regime = regime_signal(symbol, row)
    veto = veto_reason(row)

    combined = 0.65 * tech.score + 0.35 * regime.score
    confidence = 0.65 * tech.confidence + 0.35 * regime.confidence

    stop = max(0.01, row["close"] - 2.0 * row["atr14"])
    direction = "LONG" if combined >= 0.55 and tech.direction == "LONG" and regime.direction == "LONG" else "FLAT"

    return DeskDecision(
        symbol=symbol,
        timestamp=row.name.to_pydatetime(),
        direction="FLAT" if veto else direction,
        score=combined,
        confidence=confidence,
        stop_price=stop if direction == "LONG" else None,
        rationale=[tech.reason, regime.reason],
        vetoed=veto is not None,
        veto_reason=veto,
    )
