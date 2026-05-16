from __future__ import annotations

import argparse
import json
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.app.services.aggressive_10cm_strategy import (  # noqa: E402
    Aggressive10cmParams,
    backtest_range,
    build_trade_plan,
    write_outputs,
)


def _add_param_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--budget", type=float, default=1_000_000.0)
    parser.add_argument("--max-positions", type=int, default=4)
    parser.add_argument("--max-new-positions-per-day", type=int, default=3)
    parser.add_argument("--max-total-exposure-pct", type=float, default=0.80)
    parser.add_argument("--per-position-pct", type=float, default=0.24)
    parser.add_argument("--min-amount", type=float, default=220_000_000.0)
    parser.add_argument("--min-score", type=float, default=82.0)
    parser.add_argument("--max-open-gap-up-pct", type=float, default=6.8)
    parser.add_argument("--max-open-gap-down-pct", type=float, default=-4.5)
    parser.add_argument("--hard-stop-pct", type=float, default=-7.0)
    parser.add_argument("--first-take-profit-pct", type=float, default=10.0)
    parser.add_argument("--trailing-activate-pct", type=float, default=15.0)
    parser.add_argument("--trailing-drawdown-pct", type=float, default=-8.0)
    parser.add_argument("--max-holding-days", type=int, default=22)
    parser.add_argument("--buy-slippage-bp", type=float, default=20.0)
    parser.add_argument("--sell-slippage-bp", type=float, default=20.0)
    parser.add_argument("--round-trip-fee-bp", type=float, default=22.0)
    parser.add_argument("--atomic-db-path", default=None)
    parser.add_argument("--selection-db-path", default=None)
    parser.add_argument("--fine-heat-db-path", default=None)
    parser.add_argument("--out", default="data/selection/aggressive_10cm")


def _params(args: argparse.Namespace) -> Aggressive10cmParams:
    return Aggressive10cmParams(
        initial_budget=float(args.budget),
        max_positions=int(args.max_positions),
        max_new_positions_per_day=int(args.max_new_positions_per_day),
        max_total_exposure_pct=float(args.max_total_exposure_pct),
        per_position_pct=float(args.per_position_pct),
        min_amount=float(args.min_amount),
        min_score=float(args.min_score),
        max_open_gap_up_pct=float(args.max_open_gap_up_pct),
        max_open_gap_down_pct=float(args.max_open_gap_down_pct),
        hard_stop_pct=float(args.hard_stop_pct),
        first_take_profit_pct=float(args.first_take_profit_pct),
        trailing_activate_pct=float(args.trailing_activate_pct),
        trailing_drawdown_pct=float(args.trailing_drawdown_pct),
        max_holding_days=int(args.max_holding_days),
        buy_slippage_bp=float(args.buy_slippage_bp),
        sell_slippage_bp=float(args.sell_slippage_bp),
        round_trip_fee_bp=float(args.round_trip_fee_bp),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggressive 10cm mock trading strategy runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Build next-session mock trading plan from one signal date")
    plan_parser.add_argument("--signal-date", required=True)
    plan_parser.add_argument("--top-n", type=int, default=12)
    _add_param_args(plan_parser)

    backtest_parser = subparsers.add_parser("backtest", help="Run no-lookahead portfolio backtest")
    backtest_parser.add_argument("--start-date", required=True)
    backtest_parser.add_argument("--end-date", required=True)
    backtest_parser.add_argument("--replay-end-date", default=None)
    backtest_parser.add_argument("--top-n", type=int, default=12)
    _add_param_args(backtest_parser)

    args = parser.parse_args()
    params = _params(args)
    if args.command == "plan":
        payload = build_trade_plan(
            args.signal_date,
            budget=float(args.budget),
            params=params,
            top_n=int(args.top_n),
            db_path=args.atomic_db_path,
            selection_db_path=args.selection_db_path,
            fine_heat_db_path=args.fine_heat_db_path,
        )
        written = write_outputs(payload, args.out, prefix=f"plan_{payload['signal_date']}")
        print(json.dumps({"payload": payload, "written": written}, ensure_ascii=False, indent=2))
        return

    if args.command == "backtest":
        payload = backtest_range(
            args.start_date,
            args.end_date,
            replay_end_date=args.replay_end_date,
            budget=float(args.budget),
            params=params,
            top_n=int(args.top_n),
            db_path=args.atomic_db_path,
            selection_db_path=args.selection_db_path,
            fine_heat_db_path=args.fine_heat_db_path,
        )
        written = write_outputs(payload, args.out, prefix=f"backtest_{args.start_date}_{args.end_date}")
        print(json.dumps({"summary": payload["summary"], "written": written}, ensure_ascii=False, indent=2))
        return


if __name__ == "__main__":
    main()
