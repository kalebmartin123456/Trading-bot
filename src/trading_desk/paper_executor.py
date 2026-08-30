from __future__ import annotations

import hashlib
import math
from datetime import datetime, timedelta, timezone

from trading_desk.config import Config
from trading_desk.data import fetch_hourly
from trading_desk.execution_state import (
    ExecutionAuditLog,
    ExecutionState,
    ExecutionStateStore,
    ManagedPosition,
)
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


def _order_symbol(order) -> str:
    return canonical_crypto_symbol(getattr(order, "symbol", "") or "")


def _is_desk_order(order) -> bool:
    return str(getattr(order, "client_order_id", "") or "").startswith("desk-")


def _finalize(
    *,
    store: ExecutionStateStore,
    audit: ExecutionAuditLog,
    state: ExecutionState,
    now: datetime,
    result: dict,
) -> dict:
    store.save(state)
    audit.append({"timestamp": now.isoformat(), **result})
    return result


def _halt_result(
    *,
    broker,
    cfg: Config,
    state: ExecutionState,
    positions: dict,
    now: datetime,
) -> dict:
    """Cancel pending desk orders and flatten every managed paper position."""
    actions: list[dict] = []
    allowed = set(cfg.symbols)

    # Never cancel a desk-created reducing exit. An in-flight liquidation is
    # already moving risk in the safe direction; wait for broker reconciliation.
    cancelled = broker.cancel_open_orders(
        allowed,
        preserve_client_id_prefixes=("desk-exit-",),
    )
    for order_id in cancelled:
        actions.append({"action": "CANCEL", "order_id": order_id, "reason": state.halt_kind})

    remaining_orders = [order for order in broker.open_orders() if _order_symbol(order) in allowed]
    if remaining_orders:
        actions.append({
            "action": "WAIT",
            "reason": "halt cancellation is not yet confirmed",
            "open_order_ids": [str(order.id) for order in remaining_orders],
        })
        return {
            "status": "halted",
            "halt_kind": state.halt_kind,
            "halt_reason": state.halt_reason,
            "manual_resume_required": state.manual_resume_required,
            "positions": sorted(positions),
            "actions": actions,
        }

    # Reconcile again after cancellation in case an entry filled during the
    # cancel race. Only state-managed positions may be liquidated automatically.
    positions = _position_map(broker.positions())
    unmanaged = sorted(set(positions) - set(state.positions))
    if unmanaged:
        state.set_halt(
            "operator",
            f"Unmanaged positions appeared during halt: {unmanaged}.",
            now,
        )
        return {
            "status": "halted",
            "halt_kind": state.halt_kind,
            "halt_reason": state.halt_reason,
            "manual_resume_required": True,
            "positions": sorted(positions),
            "actions": actions,
        }

    submitted_count = 0
    for symbol in sorted(state.positions):
        position = positions.get(symbol)
        if position is None:
            continue
        if submitted_count >= cfg.max_orders_per_cycle:
            actions.append({"symbol": symbol, "action": "WAIT", "reason": "cycle order cap reached"})
            continue
        client_id = _client_order_id(
            f"exit-halt-{state.halt_kind}",
            symbol,
            now.replace(second=0, microsecond=0).isoformat(),
        )
        order, submitted = broker.submit_market(
            symbol=symbol,
            qty=position.qty,
            side="SELL",
            client_order_id=client_id,
        )
        submitted_count += int(submitted)
        actions.append({
            "symbol": symbol,
            "action": "SELL",
            "reason": state.halt_kind,
            "submitted": submitted,
            "client_order_id": client_id,
            "order_id": str(order.id),
        })

    return {
        "status": "halted",
        "halt_kind": state.halt_kind,
        "halt_reason": state.halt_reason,
        "manual_resume_required": state.manual_resume_required,
        "positions": sorted(positions),
        "actions": actions,
    }


def _market_data_problem(row, now: datetime, cfg: Config) -> str | None:
    ts = row.name.to_pydatetime()
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ts = ts.astimezone(timezone.utc)
    age_minutes = (now - (ts + timedelta(hours=1))).total_seconds() / 60
    if age_minutes < -1:
        return f"Future-dated closed bar: {ts.isoformat()}."
    if age_minutes > cfg.max_closed_bar_age_minutes:
        return (
            f"Stale closed bar: {ts.isoformat()} is {age_minutes:.1f} minutes "
            f"past its close; limit is {cfg.max_closed_bar_age_minutes:.1f}."
        )

    required = ("open", "high", "low", "close", "ema20", "ema50", "atr14", "vol24", "ret6", "ret24")
    for field in required:
        value = float(row[field])
        if not math.isfinite(value):
            return f"Invalid market value for {field}: {value}."
    if float(row["close"]) <= 0 or float(row["atr14"]) <= 0:
        return "Market close and ATR must both be positive."
    return None


def run_paper_execution(
    cfg: Config | None = None,
    state_path: str = "data/paper_execution_state.json",
    audit_path: str = "data/paper_execution_audit.jsonl",
    now: datetime | None = None,
) -> dict:
    """Reconcile and execute one fail-closed Alpaca paper-trading cycle."""
    cfg = cfg or Config()
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if cfg.live_trading_enabled:
        raise RuntimeError("Paper executor refuses to run with live trading enabled.")
    if not cfg.paper_execution_enabled:
        return {"status": "disabled", "reason": "Set PAPER_EXECUTION_ENABLED=true after paper credentials are configured."}

    broker = PaperAlpacaBroker(cfg)
    account = broker.account()
    store = ExecutionStateStore(state_path)
    audit = ExecutionAuditLog(audit_path)
    state = store.load(account.equity, now=now)
    risk = RiskEngine(cfg)

    positions = _position_map(broker.positions())
    open_orders = broker.open_orders()
    allowed = set(cfg.symbols)

    if account.trading_blocked or account.account_blocked:
        state.set_halt("operator", "Connected Alpaca paper account is blocked from trading.", now)
        return _finalize(
            store=store,
            audit=audit,
            state=state,
            now=now,
            result={
                "status": "halted",
                "halt_kind": state.halt_kind,
                "halt_reason": state.halt_reason,
                "manual_resume_required": True,
                "positions": sorted(positions),
                "actions": [],
            },
        )

    unexpected_positions = sorted(set(positions) - allowed)
    unexpected_orders = sorted({_order_symbol(order) for order in open_orders} - allowed)
    foreign_order_ids = sorted(
        str(order.id) for order in open_orders if not _is_desk_order(order)
    )
    unmanaged = sorted(set(positions) - set(state.positions))
    if unexpected_positions or unexpected_orders or foreign_order_ids or unmanaged:
        reason = (
            f"Manual reconciliation required; unexpected_positions={unexpected_positions}, "
            f"unexpected_orders={unexpected_orders}, foreign_order_ids={foreign_order_ids}, "
            f"unmanaged_positions={unmanaged}."
        )
        state.set_halt("operator", reason, now)
        return _finalize(
            store=store,
            audit=audit,
            state=state,
            now=now,
            result={
                "status": "halted",
                "halt_kind": state.halt_kind,
                "halt_reason": state.halt_reason,
                "manual_resume_required": True,
                "positions": sorted(positions),
                "actions": [],
            },
        )

    # Remove stale state only when both the position and any pending order are gone.
    open_order_symbols = {_order_symbol(order) for order in open_orders}
    for symbol in list(state.positions):
        if symbol not in positions and symbol not in open_order_symbols:
            del state.positions[symbol]

    # A daily halt may clear on the next UTC day, but only after liquidation and
    # cancellation have both been confirmed. Hard/operator halts never auto-clear.
    if not positions and not open_orders:
        state.clear_expired_daily_halt(now)

    current_halt = risk.halt_reason(
        equity=account.equity,
        peak_equity=state.peak_equity,
        day_start_equity=state.day_start_equity,
    )
    if current_halt is not None:
        state.set_halt(current_halt.kind, current_halt.reason, now)

    if state.halted:
        result = _halt_result(
            broker=broker,
            cfg=cfg,
            state=state,
            positions=positions,
            now=now,
        )
        return _finalize(store=store, audit=audit, state=state, now=now, result=result)

    market_rows = {}
    decisions = {}
    row_timestamps = set()
    for symbol in cfg.symbols:
        prepared = prepare(fetch_hourly(symbol, 10, cfg)).dropna()
        if prepared.empty:
            state.set_halt("operator", f"No prepared closed market bars for {symbol}.", now)
            result = _halt_result(
                broker=broker,
                cfg=cfg,
                state=state,
                positions=positions,
                now=now,
            )
            return _finalize(store=store, audit=audit, state=state, now=now, result=result)
        row = _latest_closed_row(prepared)
        problem = _market_data_problem(row, now, cfg)
        if problem:
            state.set_halt("operator", f"Market-data safety halt for {symbol}: {problem}", now)
            result = _halt_result(
                broker=broker,
                cfg=cfg,
                state=state,
                positions=positions,
                now=now,
            )
            return _finalize(store=store, audit=audit, state=state, now=now, result=result)
        market_rows[symbol] = row
        row_timestamps.add(row.name.isoformat())

    if len(row_timestamps) != 1:
        state.set_halt(
            "operator",
            f"Symbols are not synchronized to one closed bar: {sorted(row_timestamps)}.",
            now,
        )
        result = _halt_result(
            broker=broker,
            cfg=cfg,
            state=state,
            positions=positions,
            now=now,
        )
        return _finalize(store=store, audit=audit, state=state, now=now, result=result)

    for symbol, row in market_rows.items():
        decisions[symbol] = decide(symbol, row)

    actions: list[dict] = []
    submitted_count = 0

    # Exit management happens before all entries. Any submitted exit ends the
    # cycle so fills and account balances can reconcile before new risk is added.
    for symbol, managed in list(state.positions.items()):
        position = positions.get(symbol)
        if position is None:
            continue
        mark = float(market_rows[symbol]["close"])
        decision = decisions[symbol]
        stop_hit = mark <= managed.stop_price
        signal_exit = decision.direction == "FLAT"
        if not (stop_hit or signal_exit):
            continue
        if submitted_count >= cfg.max_orders_per_cycle:
            actions.append({"symbol": symbol, "action": "WAIT", "reason": "cycle order cap reached"})
            continue
        if broker.has_open_order(symbol):
            actions.append({"symbol": symbol, "action": "WAIT", "reason": "open order already exists"})
            continue
        reason = "stop" if stop_hit else "signal"
        client_id = _client_order_id(f"exit-{reason}", symbol, market_rows[symbol].name.isoformat())
        order, submitted = broker.submit_market(
            symbol=symbol,
            qty=position.qty,
            side="SELL",
            client_order_id=client_id,
        )
        submitted_count += int(submitted)
        actions.append({
            "symbol": symbol,
            "action": "SELL",
            "reason": reason,
            "submitted": submitted,
            "client_order_id": client_id,
            "order_id": str(order.id),
        })

    if submitted_count:
        result = {
            "status": "paper",
            "equity": account.equity,
            "buying_power": account.buying_power,
            "peak_equity": state.peak_equity,
            "day_start_equity": state.day_start_equity,
            "halted": False,
            "positions": sorted(positions),
            "actions": actions,
        }
        return _finalize(store=store, audit=audit, state=state, now=now, result=result)

    positions = _position_map(broker.positions())
    total_notional = sum(abs(position.market_value) for position in positions.values())

    available_buying_power = account.buying_power
    for symbol in cfg.symbols:
        if submitted_count >= cfg.max_orders_per_cycle:
            actions.append({"symbol": symbol, "action": "WAIT", "reason": "cycle order cap reached"})
            continue
        if symbol in positions or broker.has_open_order(symbol):
            continue
        decision = decisions[symbol]
        row = market_rows[symbol]
        if decision.direction != "LONG" or decision.stop_price is None:
            continue

        price = float(row["close"])
        rd = risk.approve(
            equity=account.equity,
            peak_equity=state.peak_equity,
            day_start_equity=state.day_start_equity,
            current_total_notional=total_notional,
            current_symbol_notional=0.0,
            price=price,
            stop_price=float(decision.stop_price),
        )
        if not rd.approved:
            actions.append({"symbol": symbol, "action": "REJECT", "reason": rd.reason})
            continue

        paper_notional_cap = account.equity * cfg.paper_max_order_equity_pct
        capped_notional = min(rd.notional, paper_notional_cap, available_buying_power)
        qty = capped_notional / price if price > 0 else 0
        if qty <= 0:
            continue

        signal_ts = row.name.isoformat()
        client_id = _client_order_id("entry", symbol, signal_ts)
        order, submitted = broker.submit_market(
            symbol=symbol,
            qty=qty,
            side="BUY",
            client_order_id=client_id,
        )
        submitted_count += int(submitted)
        if submitted:
            state.positions[symbol] = ManagedPosition(
                symbol=symbol,
                stop_price=float(decision.stop_price),
                opened_at=now.isoformat(),
                entry_signal_timestamp=signal_ts,
                entry_client_order_id=client_id,
            )
            total_notional += capped_notional
            available_buying_power -= capped_notional
        actions.append({
            "symbol": symbol,
            "action": "BUY",
            "submitted": submitted,
            "notional_target": round(capped_notional, 2),
            "risk_dollars": round(rd.risk_dollars, 2),
            "stop_price": float(decision.stop_price),
            "client_order_id": client_id,
            "order_id": str(order.id),
        })

    result = {
        "status": "paper",
        "equity": account.equity,
        "buying_power": account.buying_power,
        "peak_equity": state.peak_equity,
        "day_start_equity": state.day_start_equity,
        "halted": False,
        "positions": sorted(positions),
        "actions": actions,
    }
    return _finalize(store=store, audit=audit, state=state, now=now, result=result)
