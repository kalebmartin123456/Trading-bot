import argparse
from dataclasses import asdict
import json

from trading_desk.config import Config
from trading_desk.data import fetch_hourly
from trading_desk.indicators import prepare
from trading_desk.head_of_desk import decide
from trading_desk.backtest import run_backtest


def main():
    parser = argparse.ArgumentParser(prog="trading-desk")
    sub = parser.add_subparsers(dest="command", required=True)

    bt = sub.add_parser("backtest")
    bt.add_argument("--symbol", default="BTC/USD")
    bt.add_argument("--days", type=int, default=180)

    sub.add_parser("scan")
    sub.add_parser("run-hourly")
    sub.add_parser("grade")
    sub.add_parser("scorecard")
    sub.add_parser("paper-execute")

    args = parser.parse_args()
    cfg = Config()

    if cfg.live_trading_enabled:
        raise SystemExit("This release refuses to run with LIVE_TRADING_ENABLED=true.")

    if args.command == "backtest":
        df = fetch_hourly(args.symbol, args.days, cfg)
        result = run_backtest(args.symbol, df, cfg)
        print(json.dumps(asdict(result), indent=2))
        return

    if args.command == "scan":
        for symbol in cfg.symbols:
            df = prepare(fetch_hourly(symbol, 10, cfg)).dropna()
            row = df.iloc[-1]
            decision = decide(symbol, row)
            print(json.dumps(asdict(decision), indent=2, default=str))
        return

    if args.command == "run-hourly":
        from trading_desk.runner import run_hourly
        print(json.dumps(run_hourly(cfg), indent=2, default=str))
        return

    if args.command == "grade":
        from trading_desk.grader import grade_due_predictions
        print(json.dumps(grade_due_predictions(cfg), indent=2, default=str))
        return

    if args.command == "scorecard":
        from trading_desk.scorecard import build_scorecard
        print(json.dumps(build_scorecard(), indent=2, default=str))
        return

    if args.command == "paper-execute":
        from trading_desk.paper_executor import run_paper_execution
        print(json.dumps(run_paper_execution(cfg), indent=2, default=str))
        return
