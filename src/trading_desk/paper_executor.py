from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from trading_desk.config import Config
from trading_desk.data import fetch_hourly
from trading_desk.execution_state import ExecutionStateStore, ManagedPosition
from trading_desk.head_of_desk import decide
from trading_desk.indicators import prepare
from trading_desk.paper_broker import PaperAlpacaBroker, canonical_crypto_symbol
from trading_desk.risk import RiskEngine
from trading_desk.runner import _latest_closed_row


def _client_order_id(action: str, symbol: str, timestamp: str) -> str:
    digest = hashlib.sha256(f"{action}|{symbol}|{timestamp}".encode()).hexdigest()[:20]
    return f"desk-{action.lower()}-{digest}"


def _position_map(positions):
    return {canonical_crypto_symbol(p.symbol): p for p in positions}


def run_paper_execution(
    cfg: Config | None = None,
    state_path: str = "data/paper_execution_state.json",
) -> dict:
    """Reconcile and execute one paper-trading cycle.

    This function is intentionally incapable of live execution. It first
    reconciles the broker's actual paper positions, then manages exits, then
    considers new entries through the deterministic RiskEngine.
    """
    cfg = cfg or Config()
    if cfg.live_trading_enabled:
        raise RuntimeError("Paper executor refuses to run with live trading enabled.")
    if not cfg.paper_execution_enabled:
        return {"status": "disabled", "reason": "Set PAPER_EXECUTION_ENABLED=true after paper credentials are configured."}

    broker = PaperAlpacaBroker(cfg)
    account = broker.account()
    if account.trading_blocked or account.account_blocked:
        raise RuntimeError("Connected Alpaca paper account is blocked from trading.")

    store = ExecutionStateStore(state_path)
    state = store.load(account.equity)
    state.peak_equity = max(state.peak_equity, account.equity)

    positions = _position_map(broker.positions())
    allowed = set(cfg.symbols)
    unexpected = sorted(set(positions) - allowed)
    if unexpected:
        raise RuntimeError(f"Unexpected broker positions present: {unexpected}. Refusing to trade until reconciled manually.")

    # If the broker has a position that our state file does not know about, do
    # not guess a stop or provenance. Freeze new trading until it is reconciled.
    unmanaged = sorted(set(positions) - set(state.positions))
    if unmanaged:
        raise RuntimeError(f"Unmanaged paper positions present: {unmanaged}. Refusing to guess risk state.")

    # Remove stale state only when the broker confirms the position is gone.
    for symbol in list(state.positions):
        if symbol not in positions:
            del state.positions[symbol]

    market_rows = {}
    decisions = {}
    for symbol in cfg.symbols:
        prepared = prepare(fetch_hourly(symbol, 10, cfg)).dropna()
        row = _latest_closed_row(prepared)
        market_rows[symbol] = row
        decisions[symbol] = decide(symbol, row)

    actions: list[dict] = []

    # Exits first. We use the latest market price as the trigger and submit a
    # market sell to Alpaca paper. This is a software-managed stop, not a
    # broker-native resting stop; the hourly cadence is therefore part of the
    # experiment and must be measured honestly.
    for symbol, managed in list(state.positions.items()):
        position = positions.get(symbol)
        if position is None:
            continue
        mark = float(market_rows[symbol]["close"])
        d = decisions[symbol]
        stop_hit = mark <= managed.stop_price
        signal_exit = d.direction == "FLAT"
        if not (stop_hit or signal_exit):
            continue
        if broker.has_open_order(symbol):
            actions.append({"symbol": symbol, "action": "WAIT", "reason": "open order already exists"})
            continue
        reason = "stop" if stop_hit else "signal"
        client_id = _client_order_id(f"exit-{reason}", symbol, market_rows[symbol].name.isoformat())
        order, submitted = broker.submit_market(symbol=symbol, qty=position.qty, side="SELL", client_order_id=client_id)
        actions.append({
            "symbol": symbol,
            "action": "SELL",
            "reason": reason,
            "submitted": submitted,
            "client_order_id": client_id,
            "order_id": str(order.id),
        })

    # Re-read broker state after exits were submitted. Do not enter a symbol
    # while an exit or any other order is pending.
    positions = _position_map(broker.positions())
    total_notional = sum(abs(p.market_value) for p in positions.values())
    risk = RiskEngine(cfg)

    for symbol in cfg.symbols:
        if symbol in positions or broker.has_open_order(symbol):
            continue
        d = decisions[symbol]
        row = market_rows[symbol]
        if d.direction != "LONG" or d.stop_price is None:
            continue

        price = float(row["close"])
        rd = risk.approve(
            equity=account.equity,
            peak_equity=state.peak_equity,
            day_start_equity=state.day_start_equity,
            current_total_notional=total_notional,
            current_symbol_notional=0.0,
            price=price,
            stop_price=float(d.stop_price),
        )
        if not rd.approved:
            actions.append({"symbol": symbol, "action": "REJECT", "reason": rd.reason})
            continue

        paper_notional_cap = account.equity * cfg.paper_max_order_equity_pct
        capped_notional = min(rd.notional, paper_notional_cap, account.buying_power)
        qty = capped_notional / price if price > 0 else 0
        if qty <= 0:
            continue

        signal_ts = row.name.isoformat()
        client_id = _client_order_id("entry", symbol, signal_ts)
        order, submitted = broker.submit_market(symbol=symbol, qty=qty, side="BUY", client_order_id=client_id)
        if submitted:
            state.positions[symbol] = ManagedPosition(
                symbol=symbol,
                stop_price=float(d.stop_price),
                opened_at=datetime.now(timezone.utc).isoformat(),
                entry_signal_timestamp=signal_ts,
                entry_client_order_id=client_id,
            )
            total_notional += capped_notional
        actions.append({
            "symbol": symbol,
            "action": "BUY",
            "submitted": submitted,
            "notional_target": round(capped_notional, 2),
            "risk_dollars": round(rd.risk_dollars, 2),
            "stop_price": float(d.stop_price),
            "client_order_id": client_id,
            "order_id": str(order.id),
        })

    store.save(state)
    return {
        "status": "paper",
        "equity": account.equity,
        "buying_power": account.buying_power,
        "peak_equity": state.peak_equity,
        "day_start_equity": state.day_start_equity,
        "positions": sorted(positions),
        "actions": actions,
    }
