from trading_desk.json_ledger import JsonLedger, PredictionRecord
from trading_desk.scorecard import build_scorecard


def test_scorecard_groups_and_scores(tmp_path):
    path = tmp_path / "predictions.jsonl"
    ledger = JsonLedger(str(path))
    rows = [
        PredictionRecord("2026-08-28T00:00:00+00:00","BTC/USD","technical","LONG",0.8,0.82,100,1,"a",{},0.05,"2026-08-28T01:00:00+00:00"),
        PredictionRecord("2026-08-28T01:00:00+00:00","BTC/USD","technical","LONG",0.7,0.84,100,1,"b",{},-0.02,"2026-08-28T02:00:00+00:00"),
    ]
    ledger.add_many(rows)
    card = build_scorecard(str(path))
    assert len(card) == 1
    assert card[0]["n"] == 2
    assert card[0]["accuracy"] == 0.5
    assert abs(card[0]["expectancy"] - 0.015) < 1e-9
