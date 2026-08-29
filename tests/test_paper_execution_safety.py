from trading_desk.config import Config
from trading_desk.paper_executor import run_paper_execution


def test_paper_execution_disabled_by_default():
    result = run_paper_execution(Config())
    assert result["status"] == "disabled"


def test_live_trading_disabled_by_default():
    assert Config().live_trading_enabled is False
