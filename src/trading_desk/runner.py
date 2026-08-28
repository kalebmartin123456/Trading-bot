from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from trading_desk.agents.regime import regime_signal
from trading_desk.agents.technical import technical_signal
from trading_desk.config import Config
from trading_desk.data import fetch_hourly
from trading_desk.head_of_desk import decide
from trading_desk.indicators import prepare
from trading_desk.json_ledger import JsonLedger, PredictionRecord

HORIZONS = (1, 6, 24)


def _latest_closed_row(df):
    """Return the latest fully closed hourly candle.

    Alpaca may include the currently forming hour. We drop it until at least the
    next UTC hour has begun so forward-test timestamps are not contaminated by
    partial information.
    """
    now = datetime.now(timezone.utc)
    latest = df.iloc[-1]
    ts = latest.name.to_pydatetime()
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    if ts.hour == now.hour and ts.date() == now.date():
        return df.iloc[-2]
    return latest


def _decision_record(symbol: str, row, horizon: int) -> PredictionRecord:
    d = decide(symbol, row)
    return PredictionRecord(
        timestamp=d.timestamp.isoformat(),
        symbol=symbol,
        agent="head_of_desk",
        direction=d.direction,
        score=float(d.score),
        confidence=float(d.confidence),
        reference_price=float(row["close"]),
        horizon_hours=horizon,
        reason=" | ".join(d.rationale) + (f" | VETO: {d.veto_reason}" if d.vetoed else ""),
        metadata={"stop_price": d.stop_price, "vetoed": d.vetoed, "veto_reason": d.veto_reason},
    )


def _signal_records(symbol: str, row, horizon: int) -> list[PredictionRecord]:
    signals = [technical_signal(symbol, row), regime_signal(symbol, row)]
    out: list[PredictionRecord] = []
    for s in signals:
        out.append(PredictionRecord(
            timestamp=s.timestamp.isoformat(),
            symbol=symbol,
            agent=s.agent,
            direction=s.direction,
            score=float(s.score),
            confidence=float(s.confidence),
            reference_price=float(row["close"]),
            horizon_hours=horizon,
            reason=s.reason,
            metadata=s.metadata,
        ))
    out.append(_decision_record(symbol, row, horizon))
    return out


def run_hourly(cfg: Config | None = None, ledger_path: str = "data/predictions.jsonl") -> dict:
    cfg = cfg or Config()
    if cfg.live_trading_enabled:
        raise RuntimeError("Forward-test runner refuses to operate with live trading enabled.")

    ledger = JsonLedger(ledger_path)
    generated: list[PredictionRecord] = []
    snapshots: dict[str, dict] = {}

    for symbol in cfg.symbols:
        prepared = prepare(fetch_hourly(symbol, 10, cfg)).dropna()
        row = _latest_closed_row(prepared)
        for horizon in HORIZONS:
            generated.extend(_signal_records(symbol, row, horizon))
        snapshots[symbol] = {
            "timestamp": row.name.isoformat(),
            "close": float(row["close"]),
            "ema20": float(row["ema20"]),
            "ema50": float(row["ema50"]),
            "atr14": float(row["atr14"]),
            "ret6": float(row["ret6"]),
            "ret24": float(row["ret24"]),
        }

    added = ledger.add_many(generated)
    return {
        "generated": len(generated),
        "added": added,
        "duplicates_skipped": len(generated) - added,
        "snapshots": snapshots,
    }
