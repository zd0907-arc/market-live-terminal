from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.app.services.selection_research import (
    get_candidates,
    refresh_selection_research,
    run_selection_backtest,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="选股研究模块 runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    refresh_parser = subparsers.add_parser("refresh", help="生成/刷新特征与信号")
    refresh_parser.add_argument("--start-date", default=None)
    refresh_parser.add_argument("--end-date", default=None)

    candidates_parser = subparsers.add_parser("candidates", help="查看某日候选")
    candidates_parser.add_argument("--date", default=None)
    candidates_parser.add_argument("--strategy", default="breakout", choices=["stealth", "breakout", "distribution"])
    candidates_parser.add_argument("--limit", type=int, default=20)

    backtest_parser = subparsers.add_parser("backtest", help="执行固定持有期回测")
    backtest_parser.add_argument("--strategy", default="breakout", choices=["stealth", "breakout", "distribution"])
    backtest_parser.add_argument("--start-date", required=True)
    backtest_parser.add_argument("--end-date", required=True)
    backtest_parser.add_argument("--holding-days", default="5,10,20,40")
    backtest_parser.add_argument("--max-positions", type=int, default=10)
    backtest_parser.add_argument("--stop-loss-pct", type=float, default=None)
    backtest_parser.add_argument("--take-profit-pct", type=float, default=None)

    args = parser.parse_args()

    if args.command == "refresh":
        result = refresh_selection_research(start_date=args.start_date, end_date=args.end_date)
        print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
        return

    if args.command == "candidates":
        result = get_candidates(trade_date=args.date, strategy=args.strategy, limit=int(args.limit))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "backtest":
        holding_days = [int(item.strip()) for item in str(args.holding_days).split(",") if item.strip()]
        result = run_selection_backtest(
            strategy_name=args.strategy,
            start_date=args.start_date,
            end_date=args.end_date,
            holding_days_set=holding_days,
            max_positions_per_day=int(args.max_positions),
            stop_loss_pct=args.stop_loss_pct,
            take_profit_pct=args.take_profit_pct,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return


if __name__ == "__main__":
    main()
