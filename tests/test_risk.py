from trading_desk.config import Config
from trading_desk.risk import RiskEngine


def test_invalid_risk_configuration_is_rejected():
    try:
        Config(max_total_exposure=0.10, max_symbol_exposure=0.20)
    except ValueError as error:
        assert "Exposure limits" in str(error)
    else:
        raise AssertionError("Unsafe exposure configuration was accepted.")

    try:
        Config(max_orders_per_cycle=0)
    except ValueError as error:
        assert "MAX_ORDERS_PER_CYCLE" in str(error)
    else:
        raise AssertionError("Zero order cap was accepted.")


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


def test_drawdown_halt_requires_manual_resume():
    halt = RiskEngine(Config()).halt_reason(
        equity=9_100,
        peak_equity=10_000,
        day_start_equity=9_500,
    )
    assert halt is not None
    assert halt.kind == "portfolio_drawdown"
    assert halt.manual_resume_required is True


def test_daily_halt_can_reset_next_day():
    halt = RiskEngine(Config()).halt_reason(
        equity=9_890,
        peak_equity=10_000,
        day_start_equity=10_000,
    )
    assert halt is not None
    assert halt.kind == "daily_loss"
    assert halt.manual_resume_required is False
