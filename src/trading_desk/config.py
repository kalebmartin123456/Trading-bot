from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()


def _f(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _b(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    alpaca_api_key: str = os.getenv("ALPACA_API_KEY", "")
    alpaca_secret_key: str = os.getenv("ALPACA_SECRET_KEY", "")
    paper_trading: bool = _b("PAPER_TRADING", True)
    paper_execution_enabled: bool = _b("PAPER_EXECUTION_ENABLED", False)
    live_trading_enabled: bool = _b("LIVE_TRADING_ENABLED", False)

    initial_equity: float = _f("INITIAL_EQUITY", 10_000)
    risk_per_trade: float = _f("RISK_PER_TRADE", 0.0035)
    max_symbol_exposure: float = _f("MAX_SYMBOL_EXPOSURE", 0.20)
    max_total_exposure: float = _f("MAX_TOTAL_EXPOSURE", 0.35)
    daily_loss_limit: float = _f("DAILY_LOSS_LIMIT", 0.01)
    max_drawdown: float = _f("MAX_DRAWDOWN", 0.08)

    assumed_fee_bps: float = _f("ASSUMED_FEE_BPS", 10)
    assumed_slippage_bps: float = _f("ASSUMED_SLIPPAGE_BPS", 5)

    # Paper execution adds a second, deliberately conservative cap. Even if the
    # research risk engine calculates a larger position, V1 paper orders cannot
    # exceed this fraction of account equity per symbol.
    paper_max_order_equity_pct: float = _f("PAPER_MAX_ORDER_EQUITY_PCT", 0.10)

    symbols: tuple[str, ...] = ("BTC/USD", "ETH/USD")
