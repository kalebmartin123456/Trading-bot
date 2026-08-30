from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN

from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import GetOrdersRequest, MarketOrderRequest

from trading_desk.config import Config


def canonical_crypto_symbol(symbol: str) -> str:
    value = symbol.upper().replace("-", "/")
    if "/" in value:
        return value
    if value.endswith("USD") and len(value) > 3:
        return f"{value[:-3]}/USD"
    return value


def normalize_quantity(qty: float, min_increment: str | float | None, min_order_size: str | float | None) -> float:
    if qty <= 0:
        return 0.0
    increment = Decimal(str(min_increment or "0.00000001"))
    minimum = Decimal(str(min_order_size or increment))
    raw = Decimal(str(qty))
    units = (raw / increment).to_integral_value(rounding=ROUND_DOWN)
    normalized = units * increment
    if normalized < minimum:
        return 0.0
    return float(normalized)


@dataclass(frozen=True)
class BrokerAccount:
    equity: float
    buying_power: float
    trading_blocked: bool
    account_blocked: bool


@dataclass(frozen=True)
class BrokerPosition:
    symbol: str
    qty: float
    market_value: float
    avg_entry_price: float
    current_price: float


class PaperAlpacaBroker:
    """Thin, paper-only wrapper around Alpaca's TradingClient.

    The constructor hard-codes paper=True. There is intentionally no live-mode
    switch in this class, so this execution path cannot silently migrate to a
    funded account.
    """

    def __init__(self, cfg: Config):
        if cfg.live_trading_enabled:
            raise RuntimeError("Paper broker refuses to initialize while live trading is enabled.")
        if not cfg.paper_trading:
            raise RuntimeError("Paper broker requires PAPER_TRADING=true.")
        if not cfg.alpaca_api_key or not cfg.alpaca_secret_key:
            raise RuntimeError("Alpaca paper API credentials are required for paper execution.")
        self.client = TradingClient(cfg.alpaca_api_key, cfg.alpaca_secret_key, paper=True)

    def account(self) -> BrokerAccount:
        account = self.client.get_account()
        return BrokerAccount(
            equity=float(account.equity),
            buying_power=float(account.buying_power),
            trading_blocked=bool(account.trading_blocked),
            account_blocked=bool(account.account_blocked),
        )

    def positions(self) -> list[BrokerPosition]:
        out: list[BrokerPosition] = []
        for position in self.client.get_all_positions():
            qty = float(position.qty)
            current_price = float(position.current_price or 0)
            market_value = float(position.market_value or (qty * current_price))
            out.append(BrokerPosition(
                symbol=canonical_crypto_symbol(position.symbol),
                qty=qty,
                market_value=market_value,
                avg_entry_price=float(position.avg_entry_price or 0),
                current_price=current_price,
            ))
        return out

    def open_orders(self):
        return self.client.get_orders(filter=GetOrdersRequest(status=QueryOrderStatus.OPEN))

    def has_open_order(self, symbol: str) -> bool:
        target = canonical_crypto_symbol(symbol)
        return any(canonical_crypto_symbol(order.symbol or "") == target for order in self.open_orders())

    def cancel_open_orders(
        self,
        symbols: set[str] | None = None,
        preserve_client_id_prefixes: tuple[str, ...] = (),
    ) -> list[str]:
        targets = {canonical_crypto_symbol(s) for s in symbols} if symbols else None
        cancelled: list[str] = []
        for order in self.open_orders():
            symbol = canonical_crypto_symbol(order.symbol or "")
            if targets is not None and symbol not in targets:
                continue
            client_id = str(getattr(order, "client_order_id", "") or "")
            if client_id.startswith(preserve_client_id_prefixes):
                continue
            self.client.cancel_order_by_id(order.id)
            cancelled.append(str(order.id))
        return cancelled

    def get_order_by_client_id(self, client_order_id: str):
        try:
            return self.client.get_order_by_client_id(client_order_id)
        except APIError as exc:
            if getattr(exc, "status_code", None) == 404:
                return None
            # Alpaca's not-found payload has changed shape across SDK versions.
            if "not found" in str(exc).lower():
                return None
            raise

    def _normalized_qty(self, symbol: str, qty: float) -> float:
        asset = self.client.get_asset(symbol)
        if not bool(asset.tradable):
            raise RuntimeError(f"{symbol} is not tradable in the connected Alpaca paper account.")
        return normalize_quantity(
            qty,
            getattr(asset, "min_trade_increment", None),
            getattr(asset, "min_order_size", None),
        )

    def submit_market(self, *, symbol: str, qty: float, side: str, client_order_id: str):
        existing = self.get_order_by_client_id(client_order_id)
        if existing is not None:
            return existing, False

        normalized_qty = self._normalized_qty(symbol, qty)
        if normalized_qty <= 0:
            raise RuntimeError(f"Calculated quantity for {symbol} is below Alpaca's minimum order size.")

        side_enum = OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL
        request = MarketOrderRequest(
            symbol=symbol,
            qty=normalized_qty,
            side=side_enum,
            time_in_force=TimeInForce.GTC,
            client_order_id=client_order_id,
        )
        return self.client.submit_order(order_data=request), True
