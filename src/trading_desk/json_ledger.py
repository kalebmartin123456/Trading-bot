from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


@dataclass
class PredictionRecord:
    timestamp: str
    symbol: str
    agent: str
    direction: str
    score: float
    confidence: float
    reference_price: float
    horizon_hours: int
    reason: str
    metadata: dict
    outcome_return: float | None = None
    resolved_at: str | None = None

    @property
    def key(self) -> str:
        return f"{self.timestamp}|{self.symbol}|{self.agent}|{self.horizon_hours}"


class JsonLedger:
    """Small append/rewrite JSONL ledger designed to survive GitHub Actions runs.

    The repository can commit this text file after each hourly run. Text storage is
    intentionally used instead of SQLite so the research history remains auditable
    and Git-friendly.
    """

    def __init__(self, path: str = "data/predictions.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def read_all(self) -> list[PredictionRecord]:
        records: list[PredictionRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(PredictionRecord(**json.loads(line)))
        return records

    def _write_all(self, records: Iterable[PredictionRecord]) -> None:
        payload = "\n".join(json.dumps(asdict(r), sort_keys=True) for r in records)
        self.path.write_text(payload + ("\n" if payload else ""), encoding="utf-8")

    def add(self, record: PredictionRecord) -> bool:
        records = self.read_all()
        if record.key in {r.key for r in records}:
            return False
        records.append(record)
        records.sort(key=lambda r: (r.timestamp, r.symbol, r.agent, r.horizon_hours))
        self._write_all(records)
        return True

    def add_many(self, new_records: Iterable[PredictionRecord]) -> int:
        records = self.read_all()
        existing = {r.key for r in records}
        added = 0
        for record in new_records:
            if record.key not in existing:
                records.append(record)
                existing.add(record.key)
                added += 1
        records.sort(key=lambda r: (r.timestamp, r.symbol, r.agent, r.horizon_hours))
        self._write_all(records)
        return added

    def unresolved(self) -> list[PredictionRecord]:
        return [r for r in self.read_all() if r.resolved_at is None]

    def resolve(self, key: str, outcome_return: float, resolved_at: datetime | None = None) -> bool:
        records = self.read_all()
        changed = False
        resolved_iso = (resolved_at or datetime.now(timezone.utc)).isoformat()
        for record in records:
            if record.key == key and record.resolved_at is None:
                record.outcome_return = float(outcome_return)
                record.resolved_at = resolved_iso
                changed = True
                break
        if changed:
            self._write_all(records)
        return changed
