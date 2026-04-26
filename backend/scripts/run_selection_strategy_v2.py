from __future__ import annotations

import argparse
import json
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.app.services.selection_strategy_v2 import (  # noqa: E402
    SelectionV2Params,
    backtest_range_v2,
    build_research_card_v2,
    replay_trade_date_v2,
    replay_symbol_v2,
    resolve_selection_v2_atomic_db_path,
    screen_candidates_v2,
)


def _build_params(args: argparse.Namespace) -> SelectionV2Params:
    return SelectionV2Params(
        min_amount=args.min_amount,
        amount_anomaly_launch=args.amount_anomaly_launch,
        amount_anomaly_event=args.amount_anomaly_event,
        breakout_threshold_pct=args.breakout_threshold_pct,
        l2_main_net_ratio_launch=args.l2_main_net_ratio_launch,
        l2_super_net_ratio_launch=args.l2_super_net_ratio_launch,
        active_buy_strength_launch=args.active_buy_strength_launch,
        positive_l2_bar_ratio_min=args.positive_l2_bar_ratio_min,
        accumulation_main_net_5d=args.accumulation_main_net_5d,
        support_pressure_spread_min=args.support_pressure_spread_min,
        shakeout_drop_pct=args.shakeout_drop_pct,
        shakeout_repair_coverage=args.shakeout_repair_coverage,
        second_wave_amount_anomaly=args.second_wave_amount_anomaly,
        high_return_20d_pct=args.high_return_20d_pct,
        accumulation_score_min=args.accumulation_score_min,
        attack_score_min=args.attack_score_min,
        repair_score_min=args.repair_score_min,
        distribution_score_warn=args.distribution_score_warn,
        panic_distribution_score_exit=args.panic_distribution_score_exit,
        entry_attack_cvd_floor=args.entry_attack_cvd_floor,
        entry_return_20d_cap=args.entry_return_20d_cap,
        distribution_main_net_ratio=args.distribution_main_net_ratio,
        distribution_support_spread=args.distribution_support_spread,
        distribution_confirm_days=args.distribution_confirm_days,
        limit_up_pct=args.limit_up_pct,
        limit_down_pct=args.limit_down_pct,
        buy_slippage_bp=args.buy_slippage_bp,
        sell_slippage_bp=args.sell_slippage_bp,
        round_trip_fee_bp=args.round_trip_fee_bp,
        max_open_positions=args.max_open_positions,
        max_new_positions_per_day=args.max_new_positions_per_day,
        stop_loss_pct=args.stop_loss_pct,
        max_holding_days=args.max_holding_days,
    )


def _add_param_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-amount", type=float, default=300_000_000.0)
    parser.add_argument("--amount-anomaly-launch", type=float, default=1.5)
    parser.add_argument("--amount-anomaly-event", type=float, default=1.8)
    parser.add_argument("--breakout-threshold-pct", type=float, default=1.0)
    parser.add_argument("--l2-main-net-ratio-launch", type=float, default=0.02)
    parser.add_argument("--l2-super-net-ratio-launch", type=float, default=0.01)
    parser.add_argument("--active-buy-strength-launch", type=float, default=2.0)
    parser.add_argument("--positive-l2-bar-ratio-min", type=float, default=0.55)
    parser.add_argument("--accumulation-main-net-5d", type=float, default=0.0)
    parser.add_argument("--support-pressure-spread-min", type=float, default=0.0)
    parser.add_argument("--shakeout-drop-pct", type=float, default=-5.0)
    parser.add_argument("--shakeout-repair-coverage", type=float, default=0.8)
    parser.add_argument("--second-wave-amount-anomaly", type=float, default=1.2)
    parser.add_argument("--high-return-20d-pct", type=float, default=25.0)
    parser.add_argument("--accumulation-score-min", type=float, default=55.0)
    parser.add_argument("--attack-score-min", type=float, default=60.0)
    parser.add_argument("--repair-score-min", type=float, default=55.0)
    parser.add_argument("--distribution-score-warn", type=float, default=60.0)
    parser.add_argument("--panic-distribution-score-exit", type=float, default=70.0)
    parser.add_argument("--entry-attack-cvd-floor", type=float, default=-0.08)
    parser.add_argument("--entry-return-20d-cap", type=float, default=80.0)
    parser.add_argument("--distribution-main-net-ratio", type=float, default=-0.01)
    parser.add_argument("--distribution-support-spread", type=float, default=-0.02)
    parser.add_argument("--distribution-confirm-days", type=int, default=2)
    parser.add_argument("--limit-up-pct", type=float, default=9.5)
    parser.add_argument("--limit-down-pct", type=float, default=-9.5)
    parser.add_argument("--buy-slippage-bp", type=float, default=15.0)
    parser.add_argument("--sell-slippage-bp", type=float, default=15.0)
    parser.add_argument("--round-trip-fee-bp", type=float, default=20.0)
    parser.add_argument("--max-open-positions", type=int, default=3)
    parser.add_argument("--max-new-positions-per-day", type=int, default=1)
    parser.add_argument("--stop-loss-pct", type=float, default=-8.0)
    parser.add_argument("--max-holding-days", type=int, default=40)


def main() -> None:
    parser = argparse.ArgumentParser(description="Selection strategy v2 lifecycle runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    db_parser = subparsers.add_parser("db-path", help="Show resolved atomic database path")

    candidates_parser = subparsers.add_parser("candidates", help="Screen daily v2 candidates")
    candidates_parser.add_argument("--date", required=True)
    candidates_parser.add_argument("--limit", type=int, default=10)
    candidates_parser.add_argument("--symbol", action="append", default=[])
    _add_param_args(candidates_parser)

    replay_parser = subparsers.add_parser("symbol-replay", help="Replay one symbol through v2 state machine")
    replay_parser.add_argument("--symbol", required=True)
    replay_parser.add_argument("--start-date", required=True)
    replay_parser.add_argument("--end-date", required=True)
    _add_param_args(replay_parser)

    day_parser = subparsers.add_parser("day-replay", help="Replay one historical trade date across candidates")
    day_parser.add_argument("--date", required=True)
    day_parser.add_argument("--limit", type=int, default=10)
    day_parser.add_argument("--symbol", action="append", default=[])
    day_parser.add_argument("--replay-end-date", default=None)
    _add_param_args(day_parser)

    research_parser = subparsers.add_parser("research-card", help="Build Layer 2 research card for one symbol/date")
    research_parser.add_argument("--date", required=True)
    research_parser.add_argument("--symbol", required=True)
    _add_param_args(research_parser)

    range_parser = subparsers.add_parser("range-backtest", help="Run a range backtest over historical trade dates")
    range_parser.add_argument("--start-date", required=True)
    range_parser.add_argument("--end-date", required=True)
    range_parser.add_argument("--limit", type=int, default=10)
    range_parser.add_argument("--symbol", action="append", default=[])
    range_parser.add_argument("--replay-end-date", default=None)
    _add_param_args(range_parser)

    args = parser.parse_args()
    if args.command == "db-path":
        print(resolve_selection_v2_atomic_db_path())
        return

    params = _build_params(args)
    if args.command == "candidates":
        payload = screen_candidates_v2(
            trade_date=args.date,
            limit=int(args.limit),
            params=params,
            symbols=args.symbol or None,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.command == "symbol-replay":
        payload = replay_symbol_v2(
            symbol=args.symbol,
            start_date=args.start_date,
            end_date=args.end_date,
            params=params,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.command == "day-replay":
        payload = replay_trade_date_v2(
            trade_date=args.date,
            limit=int(args.limit),
            params=params,
            symbols=args.symbol or None,
            replay_end_date=args.replay_end_date,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.command == "research-card":
        candidates = screen_candidates_v2(
            trade_date=args.date,
            limit=20,
            params=params,
            symbols=[args.symbol],
        )
        candidate = next(
            (item for item in candidates["items"] if str(item["symbol"]).lower() == str(args.symbol).lower()),
            {
                "symbol": args.symbol.lower(),
                "trade_date": args.date,
                "candidate_types": [],
                "top_reasons": [],
                "warnings": [],
            },
        )
        payload = build_research_card_v2(
            symbol=args.symbol,
            trade_date=args.date,
            candidate=candidate,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.command == "range-backtest":
        payload = backtest_range_v2(
            start_date=args.start_date,
            end_date=args.end_date,
            limit=int(args.limit),
            params=params,
            symbols=args.symbol or None,
            replay_end_date=args.replay_end_date,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return


if __name__ == "__main__":
    main()
