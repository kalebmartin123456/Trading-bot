import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
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
    bt.add_argument(
        "--end",
        help="Optional ISO-8601 UTC cutoff; bars timestamped at/after it are excluded.",
    )

    sub.add_parser("scan")
    sub.add_parser("run-hourly")
    sub.add_parser("grade")
    sub.add_parser("scorecard")
    sub.add_parser("paper-execute")

    research = sub.add_parser("research-validate")
    research.add_argument("--days", type=int, default=730)
    research.add_argument(
        "--end",
        required=True,
        help="Required fixed ISO-8601 UTC cutoff. The final 20%% remains sealed.",
    )
    research.add_argument(
        "--breadth-universe",
        help="Optional comma-separated research universe; execution remains BTC/ETH.",
    )

    args = parser.parse_args()
    cfg = Config()

    if cfg.live_trading_enabled:
        raise SystemExit("This release refuses to run with LIVE_TRADING_ENABLED=true.")

    if args.command == "backtest":
        end = (
            datetime.fromisoformat(args.end.replace("Z", "+00:00"))
            if args.end
            else datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        )
        # Fetch causal warm-up before the requested evaluation boundary so a
        # 90-day test contains 90 days of tradeable bars, not 90 days minus the
        # indicator warm-up period.
        df = fetch_hourly(args.symbol, args.days + 30, cfg, end=end)
        result = run_backtest(
            args.symbol,
            df,
            cfg,
            trade_start=end - timedelta(days=args.days),
            trade_end=end,
        )
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

    if args.command == "research-validate":
        from trading_desk.data import fetch_hourly_many
        from trading_desk.research_validation import (
            DEFAULT_BREADTH_UNIVERSE,
            evaluation_start,
            research_fetch_days,
            run_sealed_validation,
        )

        end = datetime.fromisoformat(args.end.replace("Z", "+00:00"))
        universe = (
            tuple(value.strip() for value in args.breadth_universe.split(",") if value.strip())
            if args.breadth_universe
            else DEFAULT_BREADTH_UNIVERSE
        )
        frames = fetch_hourly_many(
            universe,
            research_fetch_days(args.days),
            cfg,
            end=end,
        )
        result = run_sealed_validation(
            frames=frames,
            cfg=cfg,
            evaluation_start=evaluation_start(end, args.days),
            evaluation_end=end,
        )
        print(json.dumps(result, indent=2, default=str))
        return
