from trading_desk.models import RiskDecision
from trading_desk.config import Config

class RiskEngine:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def approve(self, *, equity: float, peak_equity: float, day_start_equity: float, current_total_notional: float, current_symbol_notional: float, price: float, stop_price: float) -> RiskDecision:
        if equity <= 0:
            return RiskDecision(False, reason="No equity.")
        drawdown = (peak_equity - equity) / peak_equity if peak_equity else 0
        if drawdown >= self.cfg.max_drawdown:
            return RiskDecision(False, reason=f"Portfolio kill switch: drawdown {drawdown:.2%}.")
        daily_loss = (day_start_equity - equity) / day_start_equity if day_start_equity else 0
        if daily_loss >= self.cfg.daily_loss_limit:
            return RiskDecision(False, reason=f"Daily loss stop reached: {daily_loss:.2%}.")
        stop_distance = price - stop_price
        if stop_distance <= 0:
            return RiskDecision(False, reason="Invalid stop distance.")
        risk_dollars = equity * self.cfg.risk_per_trade
        qty_by_risk = risk_dollars / stop_distance
        symbol_room = max(0, equity * self.cfg.max_symbol_exposure - current_symbol_notional)
        total_room = max(0, equity * self.cfg.max_total_exposure - current_total_notional)
        qty = max(0, min(qty_by_risk, symbol_room / price, total_room / price))
        notional = qty * price
        if notional < 10:
            return RiskDecision(False, reason="Position below minimum meaningful notional.")
        return RiskDecision(True, quantity=qty, notional=notional, risk_dollars=qty * stop_distance, reason="Approved by deterministic risk limits.")
