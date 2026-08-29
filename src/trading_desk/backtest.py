from dataclasses import dataclass
import math
import pandas as pd

from trading_desk.config import Config
from trading_desk.indicators import prepare
from trading_desk.head_of_desk import decide
from trading_desk.risk import RiskEngine


@dataclass
class BacktestResult:
    symbol: str
    starting_equity: float
    ending_equity: float
    return_pct: float
    buy_hold_return_pct: float
    excess_return_pct: float
    max_drawdown_pct: float
    trades: int
    wins: int
    losses: int
    win_rate_pct: float
    profit_factor: float
    expectancy_dollars: float


def run_backtest(symbol: str, df: pd.DataFrame, cfg: Config) -> BacktestResult:
    """Replay the fixed desk through history without same-bar execution.

    A signal is calculated only from bar t after it has closed. Entry/exit caused
    by that signal occurs at bar t+1 open, with configured costs applied. Stops
    are then tested against the high/low of bar t+1. This is intentionally more
    conservative than filling at the same close that created the signal.
    """
    data = prepare(df).dropna().copy()
    if len(data) < 2:
        raise ValueError("Backtest requires at least two prepared bars.")

    cash = cfg.initial_equity
    qty = 0.0
    entry = stop = 0.0
    peak = cash
    day_start_equity = cash
    current_day = None
    gross_profit = gross_loss = 0.0
    realized_pnl = 0.0
    trades = wins = losses = 0
    max_dd = 0.0
    risk = RiskEngine(cfg)
    one_way_cost = (cfg.assumed_fee_bps + cfg.assumed_slippage_bps) / 10_000

    first_tradeable_open = float(data.iloc[1]["open"])
    final_mark = float(data.iloc[-1]["close"])
    buy_hold_return = (final_mark / first_tradeable_open - 1) * 100

    for i in range(1, len(data)):
        signal_row = data.iloc[i - 1]
        row = data.iloc[i]
        ts = data.index[i]
        open_price = float(row["open"])
        mark = float(row["close"])

        equity = cash + qty * mark
        if current_day != ts.date():
            current_day = ts.date()
            day_start_equity = equity
        peak = max(peak, equity)
        dd = (peak - equity) / peak if peak else 0
        max_dd = max(max_dd, dd)

        signal = decide(symbol, signal_row)

        if qty > 0:
            exit_price = None
            if signal.direction == "FLAT":
                exit_price = open_price * (1 - one_way_cost)
            elif float(row["low"]) <= stop:
                # If the next bar gaps below the stop, assume the worse open;
                # otherwise fill at the stop, then apply modeled costs.
                raw_stop_fill = min(stop, open_price) if open_price < stop else stop
                exit_price = raw_stop_fill * (1 - one_way_cost)

            if exit_price is not None:
                proceeds = qty * exit_price
                pnl = proceeds - qty * entry
                cash += proceeds
                realized_pnl += pnl
                gross_profit += max(0.0, pnl)
                gross_loss += max(0.0, -pnl)
                wins += int(pnl > 0)
                losses += int(pnl <= 0)
                trades += 1
                qty = entry = stop = 0.0
                continue

        if qty == 0 and signal.direction == "LONG" and signal.stop_price is not None:
            # The stop was derived only from the closed signal bar. If price gaps
            # through it before our next-bar entry, skip rather than inventing a fill.
            if open_price <= signal.stop_price:
                continue

            rd = risk.approve(
                equity=cash,
                peak_equity=max(peak, cash),
                day_start_equity=day_start_equity,
                current_total_notional=0,
                current_symbol_notional=0,
                price=open_price,
                stop_price=signal.stop_price,
            )
            if rd.approved:
                buy_price = open_price * (1 + one_way_cost)
                new_qty = min(rd.quantity, cash / buy_price)
                if new_qty > 0:
                    cash -= new_qty * buy_price
                    qty = new_qty
                    entry = buy_price
                    stop = float(signal.stop_price)

    ending = cash + qty * final_mark
    strategy_return = (ending / cfg.initial_equity - 1) * 100
    pf = gross_profit / gross_loss if gross_loss > 0 else (math.inf if gross_profit > 0 else 0.0)
    win_rate = (wins / trades * 100) if trades else 0.0
    expectancy = (realized_pnl / trades) if trades else 0.0

    return BacktestResult(
        symbol=symbol,
        starting_equity=cfg.initial_equity,
        ending_equity=ending,
        return_pct=strategy_return,
        buy_hold_return_pct=buy_hold_return,
        excess_return_pct=strategy_return - buy_hold_return,
        max_drawdown_pct=max_dd * 100,
        trades=trades,
        wins=wins,
        losses=losses,
        win_rate_pct=win_rate,
        profit_factor=pf,
        expectancy_dollars=expectancy,
    )
