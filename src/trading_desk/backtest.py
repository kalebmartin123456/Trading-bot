from dataclasses import dataclass
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
    max_drawdown_pct: float
    trades: int
    wins: int
    losses: int
    profit_factor: float

def run_backtest(symbol: str, df: pd.DataFrame, cfg: Config) -> BacktestResult:
    data = prepare(df).dropna().copy()
    cash = cfg.initial_equity
    qty = 0.0
    entry = stop = 0.0
    peak = cash
    day_start_equity = cash
    current_day = None
    gross_profit = gross_loss = 0.0
    trades = wins = losses = 0
    max_dd = 0.0
    risk = RiskEngine(cfg)
    one_way_cost = (cfg.assumed_fee_bps + cfg.assumed_slippage_bps) / 10_000

    for ts, row in data.iterrows():
        mark = float(row["close"])
        equity = cash + qty * mark
        if current_day != ts.date():
            current_day = ts.date()
            day_start_equity = equity
        peak = max(peak, equity)
        dd = (peak - equity) / peak if peak else 0
        max_dd = max(max_dd, dd)

        if qty > 0:
            exit_price = None
            if row["low"] <= stop:
                exit_price = stop * (1 - one_way_cost)
            else:
                d = decide(symbol, row)
                if d.direction == "FLAT":
                    exit_price = mark * (1 - one_way_cost)
            if exit_price is not None:
                proceeds = qty * exit_price
                pnl = proceeds - qty * entry
                cash += proceeds
                gross_profit += max(0.0, pnl)
                gross_loss += max(0.0, -pnl)
                wins += pnl > 0
                losses += pnl <= 0
                trades += 1
                qty = entry = stop = 0.0
                continue

        if qty == 0:
            d = decide(symbol, row)
            if d.direction != "LONG" or d.stop_price is None:
                continue
            rd = risk.approve(equity=cash, peak_equity=max(peak, cash), day_start_equity=day_start_equity, current_total_notional=0, current_symbol_notional=0, price=mark, stop_price=d.stop_price)
            if rd.approved:
                buy_price = mark * (1 + one_way_cost)
                qty = min(rd.quantity, cash / buy_price)
                if qty > 0:
                    cash -= qty * buy_price
                    entry = buy_price
                    stop = d.stop_price

    final_mark = float(data.iloc[-1]["close"])
    ending = cash + qty * final_mark
    pf = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
    return BacktestResult(symbol, cfg.initial_equity, ending, (ending / cfg.initial_equity - 1) * 100, max_dd * 100, trades, wins, losses, pf)
