from __future__ import annotations

from collections import defaultdict

from trading_desk.json_ledger import JsonLedger


def build_scorecard(ledger_path: str = "data/predictions.jsonl") -> list[dict]:
    rows = [r for r in JsonLedger(ledger_path).read_all() if r.outcome_return is not None]
    buckets: dict[tuple, list] = defaultdict(list)
    for r in rows:
        confidence_bucket = f"{int(r.confidence * 10) * 10:02d}-{min(100, int(r.confidence * 10) * 10 + 9):02d}%"
        buckets[(r.agent, r.symbol, r.horizon_hours, confidence_bucket)].append(r)

    out = []
    for (agent, symbol, horizon, conf_bucket), records in sorted(buckets.items()):
        signed_returns = []
        correct = 0
        for r in records:
            directional = r.outcome_return if r.direction == "LONG" else -r.outcome_return
            signed_returns.append(directional)
            correct += directional > 0
        wins = [x for x in signed_returns if x > 0]
        losses = [-x for x in signed_returns if x < 0]
        gross_win = sum(wins)
        gross_loss = sum(losses)
        profit_factor = gross_win / gross_loss if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)
        out.append({
            "agent": agent,
            "symbol": symbol,
            "horizon_hours": horizon,
            "confidence_bucket": conf_bucket,
            "n": len(records),
            "accuracy": correct / len(records),
            "expectancy": sum(signed_returns) / len(records),
            "profit_factor": profit_factor,
            "avg_confidence": sum(r.confidence for r in records) / len(records),
        })
    return out
