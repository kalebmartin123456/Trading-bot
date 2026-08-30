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
    period_start: str
    period_end: str
    bars: int
    starting_equity: float
    ending_equity: float
    return_pct: float
    buy_hold_ending_equity: float
    buy_hold_return_pct: float
    excess_return_pct: float
    max_drawdown_pct: float
    trades: int
    wins: int
    losses: int
    win_rate_pct: float
    average_winner_dollars: float
    average_loser_dollars: float
    profit_factor: float
    expectancy_dollars: float
    best_trade_dollars: float
    worst_trade_dollars: float
    best_trade_pct: float
    worst_trade_pct: float
    exposure_pct: float
    average_holding_hours: float
    stop_exits: int
    signal_exits: int
    modeled_costs_dollars: float
    open_position: bool
    unrealized_pnl_dollars: float


def run_backtest(
    symbol: str,
    df: pd.DataFrame,
    cfg: Config,
    trade_log: list[dict] | None = None,
) -> BacktestResult:
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
    entry_context: dict | None = None
    position_bars = 0
    peak = cash
    day_start_equity = cash
    current_day = None
    trade_pnls: list[float] = []
    trade_returns: list[float] = []
    holding_hours: list[float] = []
    exit_reasons: list[str] = []
    modeled_costs = 0.0
    exposed_bars = 0
    max_dd = 0.0
    risk = RiskEngine(cfg)
    one_way_cost = (cfg.assumed_fee_bps + cfg.assumed_slippage_bps) / 10_000

    first_tradeable_open = float(data.iloc[1]["open"])
    final_mark = float(data.iloc[-1]["close"])
    buy_hold_return = (final_mark / first_tradeable_open - 1) * 100

    def close_position(raw_exit_price: float, ts, reason: str) -> None:
        nonlocal cash, qty, entry, stop, entry_context, position_bars, modeled_costs
        exit_price = raw_exit_price * (1 - one_way_cost)
        modeled_costs += qty * raw_exit_price * one_way_cost
        proceeds = qty * exit_price
        pnl = proceeds - qty * entry
        return_pct = (exit_price / entry - 1) * 100
        cash += proceeds
        trade_pnls.append(pnl)
        trade_returns.append(return_pct)
        holding_hours.append(float(position_bars))
        exit_reasons.append(reason)
        if trade_log is not None:
            trade_log.append(
                {
                    **(entry_context or {}),
                    "exit_time": ts.isoformat(),
                    "raw_exit_price": raw_exit_price,
                    "exit_price": exit_price,
                    "pnl_dollars": pnl,
                    "return_pct": return_pct,
                    "holding_hours": float(position_bars),
                    "exit_reason": reason,
                }
            )
        qty = entry = stop = 0.0
        entry_context = None
        position_bars = 0

    for i in range(1, len(data)):
        signal_row = data.iloc[i - 1]
        row = data.iloc[i]
        ts = data.index[i]
        open_price = float(row["open"])
        mark = float(row["close"])

        # Decisions are made from the prior completed bar and acted on at this
        # bar's open. Risk state must therefore use information available at the
        # open, not this bar's future close.
        equity_at_open = cash + qty * open_price
        if current_day != ts.date():
            current_day = ts.date()
            day_start_equity = equity_at_open
        peak = max(peak, equity_at_open)
        dd = (peak - equity_at_open) / peak if peak else 0
        max_dd = max(max_dd, dd)

        signal = decide(symbol, signal_row)

        if qty > 0:
            if signal.direction == "FLAT":
                close_position(open_price, ts, "signal")
                end_equity = cash
                peak = max(peak, end_equity)
                max_dd = max(max_dd, (peak - end_equity) / peak if peak else 0.0)
                continue

            if open_price <= stop:
                close_position(open_price, ts, "stop")
                end_equity = cash
                peak = max(peak, end_equity)
                max_dd = max(max_dd, (peak - end_equity) / peak if peak else 0.0)
                continue

            exposed_bars += 1
            position_bars += 1
            if float(row["low"]) <= stop:
                close_position(stop, ts, "stop")
                end_equity = cash
                peak = max(peak, end_equity)
                max_dd = max(max_dd, (peak - end_equity) / peak if peak else 0.0)
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
                    modeled_costs += new_qty * open_price * one_way_cost
                    qty = new_qty
                    entry = buy_price
                    stop = float(signal.stop_price)
                    entry_context = {
                        "signal_time": signal_row.name.isoformat(),
                        "entry_time": ts.isoformat(),
                        "raw_entry_price": open_price,
                        "entry_price": buy_price,
                        "quantity": new_qty,
                        "notional_dollars": new_qty * buy_price,
                        "stop_price": stop,
                        "ema_spread_pct": (
                            (float(signal_row["ema20"]) - float(signal_row["ema50"]))
                            / float(signal_row["close"])
                            * 100
                        ),
                        "annualized_volatility_pct": float(signal_row["vol24"]) * 100,
                        "ret6_pct": float(signal_row["ret6"]) * 100,
                        "ret24_pct": float(signal_row["ret24"]) * 100,
                        "breakout": bool(
                            float(signal_row["close"]) > float(signal_row["high20_prev"])
                        ),
                    }
                    position_bars = 1
                    exposed_bars += 1

                    # The position exists from this bar's open, so its low can
                    # trigger the stop during the same bar. Omitting this check
                    # creates a favorable execution bias.
                    if float(row["low"]) <= stop:
                        close_position(stop, ts, "stop")

        end_equity = cash + qty * mark
        peak = max(peak, end_equity)
        dd = (peak - end_equity) / peak if peak else 0.0
        max_dd = max(max_dd, dd)

    ending = cash + qty * final_mark
    strategy_return = (ending / cfg.initial_equity - 1) * 100
    wins_list = [pnl for pnl in trade_pnls if pnl > 0]
    losses_list = [pnl for pnl in trade_pnls if pnl <= 0]
    gross_profit = sum(wins_list)
    gross_loss = -sum(losses_list)
    realized_pnl = sum(trade_pnls)
    trades = len(trade_pnls)
    wins = len(wins_list)
    losses = len(losses_list)
    pf = gross_profit / gross_loss if gross_loss > 0 else (math.inf if gross_profit > 0 else 0.0)
    win_rate = (wins / trades * 100) if trades else 0.0
    expectancy = (realized_pnl / trades) if trades else 0.0
    unrealized_pnl = qty * (final_mark - entry) if qty > 0 else 0.0

    return BacktestResult(
        symbol=symbol,
        period_start=data.index[1].isoformat(),
        period_end=data.index[-1].isoformat(),
        bars=len(data) - 1,
        starting_equity=cfg.initial_equity,
        ending_equity=ending,
        return_pct=strategy_return,
        buy_hold_ending_equity=cfg.initial_equity * (1 + buy_hold_return / 100),
        buy_hold_return_pct=buy_hold_return,
        excess_return_pct=strategy_return - buy_hold_return,
        max_drawdown_pct=max_dd * 100,
        trades=trades,
        wins=wins,
        losses=losses,
        win_rate_pct=win_rate,
        average_winner_dollars=(sum(wins_list) / wins) if wins else 0.0,
        average_loser_dollars=(sum(losses_list) / losses) if losses else 0.0,
        profit_factor=pf,
        expectancy_dollars=expectancy,
        best_trade_dollars=max(trade_pnls) if trade_pnls else 0.0,
        worst_trade_dollars=min(trade_pnls) if trade_pnls else 0.0,
        best_trade_pct=max(trade_returns) if trade_returns else 0.0,
        worst_trade_pct=min(trade_returns) if trade_returns else 0.0,
        exposure_pct=exposed_bars / (len(data) - 1) * 100,
        average_holding_hours=(sum(holding_hours) / trades) if trades else 0.0,
        stop_exits=exit_reasons.count("stop"),
        signal_exits=exit_reasons.count("signal"),
        modeled_costs_dollars=modeled_costs,
        open_position=qty > 0,
        unrealized_pnl_dollars=unrealized_pnl,
    )
