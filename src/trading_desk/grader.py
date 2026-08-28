from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trading_desk.config import Config
from trading_desk.data import fetch_hourly
from trading_desk.json_ledger import JsonLedger


def _parse_iso(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def grade_due_predictions(cfg: Config | None = None, ledger_path: str = "data/predictions.jsonl") -> dict:
    cfg = cfg or Config()
    ledger = JsonLedger(ledger_path)
    unresolved = ledger.unresolved()
    if not unresolved:
        return {"checked": 0, "resolved": 0}

    now = datetime.now(timezone.utc)
    by_symbol: dict[str, list] = {}
    for record in unresolved:
        due = _parse_iso(record.timestamp) + timedelta(hours=record.horizon_hours)
        if due <= now:
            by_symbol.setdefault(record.symbol, []).append(record)

    resolved = 0
    for symbol, records in by_symbol.items():
        oldest = min(_parse_iso(r.timestamp) for r in records)
        days = max(3, (now - oldest).days + 2)
        bars = fetch_hourly(symbol, days, cfg)
        for record in records:
            target = _parse_iso(record.timestamp) + timedelta(hours=record.horizon_hours)
            eligible = bars[bars.index >= target]
            if eligible.empty:
                continue
            outcome_price = float(eligible.iloc[0]["close"])
            outcome_return = outcome_price / record.reference_price - 1.0
            if ledger.resolve(record.key, outcome_return, resolved_at=now):
                resolved += 1

    return {"checked": sum(len(v) for v in by_symbol.values()), "resolved": resolved}
