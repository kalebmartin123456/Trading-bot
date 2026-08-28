import sqlite3
import json
from pathlib import Path

SCHEMA = '''
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    agent TEXT NOT NULL,
    direction TEXT NOT NULL,
    score REAL NOT NULL,
    confidence REAL NOT NULL,
    reference_price REAL NOT NULL,
    horizon_hours INTEGER NOT NULL,
    reason TEXT,
    metadata_json TEXT,
    outcome_return REAL,
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_predictions_symbol_time ON predictions(symbol, timestamp);
'''

class Ledger:
    def __init__(self, path: str = "trading_desk.sqlite3"):
        self.path = Path(path)
        with sqlite3.connect(self.path) as conn:
            conn.executescript(SCHEMA)

    def log_prediction(self, *, signal, reference_price: float, horizon_hours: int = 6):
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                '''INSERT INTO predictions
                   (timestamp,symbol,agent,direction,score,confidence,reference_price,horizon_hours,reason,metadata_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?)''',
                (signal.timestamp.isoformat(), signal.symbol, signal.agent, signal.direction, signal.score,
                 signal.confidence, reference_price, horizon_hours, signal.reason, json.dumps(signal.metadata)),
            )

    def unresolved(self):
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute("SELECT * FROM predictions WHERE resolved_at IS NULL ORDER BY timestamp")]

    def resolve(self, prediction_id: int, outcome_return: float, resolved_at: str):
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE predictions SET outcome_return=?, resolved_at=? WHERE id=?", (outcome_return, resolved_at, prediction_id))
