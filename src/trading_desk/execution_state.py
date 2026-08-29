from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


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


class ExecutionStateStore:
    def __init__(self, path: str = "data/paper_execution_state.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self, equity: float) -> ExecutionState:
        today = datetime.now(timezone.utc).date().isoformat()
        if not self.path.exists():
            return ExecutionState(today, equity, equity, {})

        raw = json.loads(self.path.read_text(encoding="utf-8"))
        positions = {k: ManagedPosition(**v) for k, v in raw.get("positions", {}).items()}
        state = ExecutionState(
            trading_day=raw.get("trading_day", today),
            day_start_equity=float(raw.get("day_start_equity", equity)),
            peak_equity=float(raw.get("peak_equity", equity)),
            positions=positions,
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
        }
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
