import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd

from trading_desk.config import Config
from trading_desk.execution_state import ExecutionState, ExecutionStateStore, ManagedPosition
from trading_desk.models import DeskDecision
from trading_desk.paper_broker import BrokerAccount, BrokerPosition, canonical_crypto_symbol
from trading_desk.paper_executor import run_paper_execution


NOW = datetime(2026, 8, 30, 16, 7, tzinfo=timezone.utc)


def paper_config(**overrides) -> Config:
    values = {
        "alpaca_api_key": "paper-key",
        "alpaca_secret_key": "paper-secret",
        "paper_execution_enabled": True,
        "live_trading_enabled": False,
    }
    values.update(overrides)
    return Config(**values)


def managed(symbol: str) -> ManagedPosition:
    return ManagedPosition(
        symbol=symbol,
        stop_price=90.0,
        opened_at="2026-08-29T00:00:00+00:00",
        entry_signal_timestamp="2026-08-29T00:00:00+00:00",
        entry_client_order_id=f"entry-{symbol}",
    )


def position(symbol: str, qty: float = 1.0) -> BrokerPosition:
    return BrokerPosition(
        symbol=symbol,
        qty=qty,
        market_value=qty * 100.0,
        avg_entry_price=100.0,
        current_price=100.0,
    )


class FakeBroker:
    def __init__(self, *, equity=10_000.0, positions=None, orders=None):
        self._account = BrokerAccount(equity, equity, False, False)
        self._positions = list(positions or [])
        self._orders = list(orders or [])
        self.submissions: list[dict] = []
        self.cancelled: list[str] = []

    def account(self):
        return self._account

    def positions(self):
        return list(self._positions)

    def open_orders(self):
        return list(self._orders)

    def has_open_order(self, symbol):
        target = canonical_crypto_symbol(symbol)
        return any(canonical_crypto_symbol(order.symbol) == target for order in self._orders)

    def cancel_open_orders(self, symbols=None, preserve_client_id_prefixes=()):
        targets = {canonical_crypto_symbol(s) for s in symbols} if symbols else None
        remaining = []
        for order in self._orders:
            client_id = str(getattr(order, "client_order_id", "") or "")
            preserve = client_id.startswith(preserve_client_id_prefixes)
            if (targets is None or canonical_crypto_symbol(order.symbol) in targets) and not preserve:
                self.cancelled.append(str(order.id))
            else:
                remaining.append(order)
        self._orders = remaining
        return list(self.cancelled)

    def submit_market(self, *, symbol, qty, side, client_order_id):
        call = {
            "symbol": symbol,
            "qty": qty,
            "side": side,
            "client_order_id": client_order_id,
        }
        self.submissions.append(call)
        return SimpleNamespace(id=f"order-{len(self.submissions)}"), True


def save_state(path, *, equity, peak, positions=None, halt_kind=None, halt_reason=None, halt_day=None):
    state = ExecutionState(
        trading_day=NOW.date().isoformat(),
        day_start_equity=10_000.0,
        peak_equity=peak,
        positions=positions or {},
        halt_kind=halt_kind,
        halt_reason=halt_reason,
        halted_at=NOW.isoformat() if halt_kind else None,
        halt_day=halt_day or (NOW.date().isoformat() if halt_kind else None),
    )
    ExecutionStateStore(str(path)).save(state)


def market_frame(last_timestamp: datetime) -> pd.DataFrame:
    index = pd.date_range(end=last_timestamp, periods=80, freq="h", tz="UTC")
    close = pd.Series(range(100, 180), index=index, dtype=float)
    return pd.DataFrame(
        {
            "open": close - 0.2,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000.0,
            "trade_count": 100.0,
            "vwap": close,
        },
        index=index,
    )


def patch_market(monkeypatch, *, direction_by_symbol=None, last_timestamp=None):
    last_timestamp = last_timestamp or NOW.replace(minute=0) - timedelta(hours=1)
    frame = market_frame(last_timestamp)
    monkeypatch.setattr("trading_desk.paper_executor.fetch_hourly", lambda *args, **kwargs: frame)
    monkeypatch.setattr("trading_desk.paper_executor._latest_closed_row", lambda prepared: prepared.iloc[-1])
    directions = direction_by_symbol or {"BTC/USD": "FLAT", "ETH/USD": "FLAT"}

    def fake_decide(symbol, row):
        direction = directions[symbol]
        return DeskDecision(
            symbol=symbol,
            timestamp=row.name.to_pydatetime(),
            direction=direction,
            score=1.0 if direction == "LONG" else 0.0,
            confidence=1.0,
            stop_price=float(row.close - 5.0) if direction == "LONG" else None,
            rationale=[],
        )

    monkeypatch.setattr("trading_desk.paper_executor.decide", fake_decide)


def run_with_fake(monkeypatch, tmp_path, broker, cfg=None):
    monkeypatch.setattr("trading_desk.paper_executor.PaperAlpacaBroker", lambda _: broker)
    return run_paper_execution(
        cfg or paper_config(),
        state_path=str(tmp_path / "state.json"),
        audit_path=str(tmp_path / "audit.jsonl"),
        now=NOW,
    )


def test_drawdown_halt_is_persisted_and_liquidates(monkeypatch, tmp_path):
    broker = FakeBroker(equity=9_190.0, positions=[position("BTC/USD")])
    save_state(
        tmp_path / "state.json",
        equity=9_190.0,
        peak=10_000.0,
        positions={"BTC/USD": managed("BTC/USD")},
    )
    monkeypatch.setattr(
        "trading_desk.paper_executor.fetch_hourly",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("halt must precede data fetch")),
    )

    result = run_with_fake(monkeypatch, tmp_path, broker)

    assert result["status"] == "halted"
    assert result["halt_kind"] == "portfolio_drawdown"
    assert result["manual_resume_required"] is True
    assert [call["side"] for call in broker.submissions] == ["SELL"]
    stored = json.loads((tmp_path / "state.json").read_text())
    assert stored["halt_kind"] == "portfolio_drawdown"
    assert len((tmp_path / "audit.jsonl").read_text().splitlines()) == 1


def test_daily_halt_liquidates_but_does_not_require_manual_resume(monkeypatch, tmp_path):
    broker = FakeBroker(equity=9_890.0, positions=[position("ETH/USD")])
    save_state(
        tmp_path / "state.json",
        equity=9_890.0,
        peak=10_000.0,
        positions={"ETH/USD": managed("ETH/USD")},
    )

    result = run_with_fake(monkeypatch, tmp_path, broker)

    assert result["halt_kind"] == "daily_loss"
    assert result["manual_resume_required"] is False
    assert [call["side"] for call in broker.submissions] == ["SELL"]


def test_hard_halt_remains_when_equity_recovers(monkeypatch, tmp_path):
    broker = FakeBroker(equity=10_000.0)
    save_state(
        tmp_path / "state.json",
        equity=10_000.0,
        peak=10_000.0,
        halt_kind="portfolio_drawdown",
        halt_reason="previous drawdown",
    )
    monkeypatch.setattr(
        "trading_desk.paper_executor.fetch_hourly",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("hard halt must remain closed")),
    )

    result = run_with_fake(monkeypatch, tmp_path, broker)

    assert result["status"] == "halted"
    assert result["halt_reason"] == "previous drawdown"
    assert broker.submissions == []


def test_halt_preserves_inflight_liquidation_order(monkeypatch, tmp_path):
    order = SimpleNamespace(
        id="liquidation-1",
        symbol="BTC/USD",
        client_order_id="desk-exit-halt-portfolio_drawdown-existing",
    )
    broker = FakeBroker(
        equity=9_190.0,
        positions=[position("BTC/USD")],
        orders=[order],
    )
    save_state(
        tmp_path / "state.json",
        equity=9_190.0,
        peak=10_000.0,
        positions={"BTC/USD": managed("BTC/USD")},
        halt_kind="portfolio_drawdown",
        halt_reason="previous drawdown",
    )

    result = run_with_fake(monkeypatch, tmp_path, broker)

    assert result["status"] == "halted"
    assert result["actions"][-1]["action"] == "WAIT"
    assert broker.cancelled == []
    assert broker.submissions == []


def test_expired_daily_halt_clears_only_when_flat(monkeypatch, tmp_path):
    broker = FakeBroker(equity=10_000.0)
    yesterday = (NOW.date() - timedelta(days=1)).isoformat()
    save_state(
        tmp_path / "state.json",
        equity=10_000.0,
        peak=10_000.0,
        halt_kind="daily_loss",
        halt_reason="prior day",
        halt_day=yesterday,
    )
    patch_market(monkeypatch)

    result = run_with_fake(monkeypatch, tmp_path, broker)

    assert result["status"] == "paper"
    assert result["halted"] is False
    stored = json.loads((tmp_path / "state.json").read_text())
    assert stored["halt_kind"] is None


def test_stale_market_data_blocks_all_orders(monkeypatch, tmp_path):
    broker = FakeBroker(equity=10_000.0, positions=[position("BTC/USD")])
    save_state(
        tmp_path / "state.json",
        equity=10_000.0,
        peak=10_000.0,
        positions={"BTC/USD": managed("BTC/USD")},
    )
    patch_market(
        monkeypatch,
        direction_by_symbol={"BTC/USD": "LONG", "ETH/USD": "LONG"},
        last_timestamp=NOW.replace(minute=0) - timedelta(hours=3),
    )

    result = run_with_fake(monkeypatch, tmp_path, broker)

    assert result["status"] == "halted"
    assert result["halt_kind"] == "operator"
    assert "Stale closed bar" in result["halt_reason"]
    assert [call["side"] for call in broker.submissions] == ["SELL"]


def test_unmanaged_position_persists_operator_halt(monkeypatch, tmp_path):
    broker = FakeBroker(equity=10_000.0, positions=[position("BTC/USD")])

    result = run_with_fake(monkeypatch, tmp_path, broker)

    assert result["halt_kind"] == "operator"
    assert result["manual_resume_required"] is True
    assert broker.submissions == []


def test_foreign_open_order_persists_operator_halt(monkeypatch, tmp_path):
    order = SimpleNamespace(id="manual-1", symbol="BTC/USD", client_order_id="manual-order")
    broker = FakeBroker(equity=10_000.0, orders=[order])

    result = run_with_fake(monkeypatch, tmp_path, broker)

    assert result["halt_kind"] == "operator"
    assert "foreign_order_ids=['manual-1']" in result["halt_reason"]
    assert broker.cancelled == []
    assert broker.submissions == []


def test_exit_submission_prevents_new_entry_same_cycle(monkeypatch, tmp_path):
    broker = FakeBroker(equity=10_000.0, positions=[position("BTC/USD")])
    save_state(
        tmp_path / "state.json",
        equity=10_000.0,
        peak=10_000.0,
        positions={"BTC/USD": managed("BTC/USD")},
    )
    patch_market(
        monkeypatch,
        direction_by_symbol={"BTC/USD": "FLAT", "ETH/USD": "LONG"},
    )

    result = run_with_fake(monkeypatch, tmp_path, broker)

    assert result["status"] == "paper"
    assert [call["side"] for call in broker.submissions] == ["SELL"]


def test_cycle_order_cap_limits_new_entries(monkeypatch, tmp_path):
    broker = FakeBroker(equity=10_000.0)
    patch_market(
        monkeypatch,
        direction_by_symbol={"BTC/USD": "LONG", "ETH/USD": "LONG"},
    )

    result = run_with_fake(
        monkeypatch,
        tmp_path,
        broker,
        cfg=paper_config(max_orders_per_cycle=1),
    )

    assert result["status"] == "paper"
    assert [call["side"] for call in broker.submissions] == ["BUY"]
    assert any(action.get("reason") == "cycle order cap reached" for action in result["actions"])
