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
    max_closed_bar_age_minutes: float = _f("MAX_CLOSED_BAR_AGE_MINUTES", 20)
    max_orders_per_cycle: int = int(_f("MAX_ORDERS_PER_CYCLE", 4))

    symbols: tuple[str, ...] = ("BTC/USD", "ETH/USD")

    def __post_init__(self) -> None:
        if self.initial_equity <= 0:
            raise ValueError("INITIAL_EQUITY must be positive.")
        if not 0 < self.risk_per_trade <= 1:
            raise ValueError("RISK_PER_TRADE must be in (0, 1].")
        if not 0 < self.max_symbol_exposure <= self.max_total_exposure <= 1:
            raise ValueError(
                "Exposure limits must satisfy 0 < symbol <= total <= 1."
            )
        if not 0 < self.daily_loss_limit < self.max_drawdown < 1:
            raise ValueError(
                "Loss limits must satisfy 0 < daily loss < max drawdown < 1."
            )
        if self.assumed_fee_bps < 0 or self.assumed_slippage_bps < 0:
            raise ValueError("Modeled fees and slippage cannot be negative.")
        if not 0 < self.paper_max_order_equity_pct <= self.max_symbol_exposure:
            raise ValueError(
                "PAPER_MAX_ORDER_EQUITY_PCT must be positive and no greater than "
                "MAX_SYMBOL_EXPOSURE."
            )
        if self.max_closed_bar_age_minutes <= 0:
            raise ValueError("MAX_CLOSED_BAR_AGE_MINUTES must be positive.")
        if self.max_orders_per_cycle < 1:
            raise ValueError("MAX_ORDERS_PER_CYCLE must be at least 1.")
        if not self.symbols or len(set(self.symbols)) != len(self.symbols):
            raise ValueError("At least one unique trading symbol is required.")
