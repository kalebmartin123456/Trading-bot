from datetime import datetime, timezone

from trading_desk.json_ledger import JsonLedger, PredictionRecord


def test_json_ledger_dedup_and_resolve(tmp_path):
    path = tmp_path / "predictions.jsonl"
    ledger = JsonLedger(str(path))
    record = PredictionRecord(
        timestamp="2026-08-28T00:00:00+00:00",
        symbol="BTC/USD",
        agent="technical",
        direction="LONG",
        score=0.8,
        confidence=0.8,
        reference_price=100.0,
        horizon_hours=6,
        reason="test",
        metadata={},
    )
    assert ledger.add(record) is True
    assert ledger.add(record) is False
    assert len(ledger.read_all()) == 1
    assert ledger.resolve(record.key, 0.05, datetime(2026, 8, 28, 6, tzinfo=timezone.utc)) is True
    resolved = ledger.read_all()[0]
    assert resolved.outcome_return == 0.05
    assert resolved.resolved_at is not None
