from trading_desk.config import Config
from trading_desk.risk import RiskEngine


def test_position_risk_is_capped():
    cfg = Config()
    r = RiskEngine(cfg)
    out = r.approve(equity=10_000, peak_equity=10_000, day_start_equity=10_000,
                    current_total_notional=0, current_symbol_notional=0, price=100, stop_price=95)
    assert out.approved
    assert out.risk_dollars <= 10_000 * cfg.risk_per_trade + 1e-9
    assert out.notional <= 10_000 * cfg.max_symbol_exposure + 1e-9
    assert out.notional <= 10_000 * cfg.max_total_exposure + 1e-9


def test_drawdown_kill_switch():
    cfg = Config()
    r = RiskEngine(cfg)
    out = r.approve(equity=9_100, peak_equity=10_000, day_start_equity=9_100,
                    current_total_notional=0, current_symbol_notional=0, price=100, stop_price=95)
    assert not out.approved
    assert "kill switch" in out.reason.lower()


def test_daily_loss_stop():
    cfg = Config()
    r = RiskEngine(cfg)
    out = r.approve(equity=9_880, peak_equity=10_000, day_start_equity=10_000,
                    current_total_notional=0, current_symbol_notional=0, price=100, stop_price=95)
    assert not out.approved
    assert "daily loss" in out.reason.lower()
