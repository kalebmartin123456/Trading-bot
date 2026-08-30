from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


@dataclass
class ManagedPosition:
    symbol: str
    stop_price: float
    opened_at: str
    entry_signal_timestamp: str
    entry_client_order_id: str


@dataclass
class ExecutionState:
    trading_day: str
    day_start_equity: float
    peak_equity: float
    positions: dict[str, ManagedPosition]
    halt_kind: str | None = None
    halt_reason: str | None = None
    halted_at: str | None = None
    halt_day: str | None = None

    @property
    def halted(self) -> bool:
        return self.halt_kind is not None

    @property
    def manual_resume_required(self) -> bool:
        return self.halt_kind in {"portfolio_drawdown", "insolvent", "operator"}

    def set_halt(self, kind: str, reason: str, now: datetime) -> None:
        # Never downgrade a hard/manual halt to a daily halt.
        if self.manual_resume_required and kind == "daily_loss":
            return
        if self.halt_kind == kind and self.halt_reason == reason:
            return
        self.halt_kind = kind
        self.halt_reason = reason
        self.halted_at = now.astimezone(timezone.utc).isoformat()
        self.halt_day = now.astimezone(timezone.utc).date().isoformat()

    def clear_expired_daily_halt(self, now: datetime) -> bool:
        today = now.astimezone(timezone.utc).date().isoformat()
        if self.halt_kind != "daily_loss" or self.halt_day == today:
            return False
        self.halt_kind = None
        self.halt_reason = None
        self.halted_at = None
        self.halt_day = None
        return True


class ExecutionStateStore:
    def __init__(self, path: str = "data/paper_execution_state.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self, equity: float, now: datetime | None = None) -> ExecutionState:
        now = now or datetime.now(timezone.utc)
        today = now.astimezone(timezone.utc).date().isoformat()
        if not self.path.exists():
            return ExecutionState(today, equity, equity, {})

        raw = json.loads(self.path.read_text(encoding="utf-8"))
        positions = {k: ManagedPosition(**v) for k, v in raw.get("positions", {}).items()}
        state = ExecutionState(
            trading_day=raw.get("trading_day", today),
            day_start_equity=float(raw.get("day_start_equity", equity)),
            peak_equity=float(raw.get("peak_equity", equity)),
            positions=positions,
            halt_kind=raw.get("halt_kind"),
            halt_reason=raw.get("halt_reason"),
            halted_at=raw.get("halted_at"),
            halt_day=raw.get("halt_day"),
        )
        if state.trading_day != today:
            state.trading_day = today
            state.day_start_equity = equity
        state.peak_equity = max(state.peak_equity, equity)
        return state

    def save(self, state: ExecutionState) -> None:
        payload = {
            "trading_day": state.trading_day,
            "day_start_equity": state.day_start_equity,
            "peak_equity": state.peak_equity,
            "positions": {k: asdict(v) for k, v in state.positions.items()},
            "halt_kind": state.halt_kind,
            "halt_reason": state.halt_reason,
            "halted_at": state.halted_at,
            "halt_day": state.halt_day,
        }
        temporary = self.path.with_name(f".{self.path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(self.path)
        finally:
            if temporary.exists():
                temporary.unlink()


class ExecutionAuditLog:
    def __init__(self, path: str = "data/paper_execution_audit.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, payload: dict) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
