from trading_desk.config import Config


def test_live_disabled_by_default():
    assert Config().live_trading_enabled is False
