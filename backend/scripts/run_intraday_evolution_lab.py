from __future__ import annotations

import argparse
import json
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.app.services.intraday_evolution_lab import (  # noqa: E402
    DEFAULT_OUTPUT_DIR,
    EvolutionConfig,
    MarketReplayEnv,
    catalog_intraday_data,
    load_intraday_panel,
    make_seed_strategy,
    run_rl_random_agent_smoke,
    run_evolution_arena,
    train_rl_policy_search,
    RLTrainerConfig,
    RLPPOTrainerConfig,
    TrendPortfolioPPOTrainerConfig,
    write_arena_outputs,
    write_catalog_output,
    train_rl_ppo_policy,
    eval_rl_ppo_policy,
    train_trend_portfolio_ppo_policy,
    eval_trend_portfolio_ppo_policy,
)


def _split_symbols(text: str | None) -> list[str] | None:
    if not text:
        return None
    symbols = [item.strip().lower() for item in text.split(",") if item.strip()]
    return symbols or None


def main() -> None:
    parser = argparse.ArgumentParser(description="5m pseudo-intraday evolution lab")
    subparsers = parser.add_subparsers(dest="command", required=True)

    catalog = subparsers.add_parser("catalog-data", help="Inspect processed intraday atomic coverage")
    catalog.add_argument("--atomic-db-path", default=None)
    catalog.add_argument("--out", default=str(DEFAULT_OUTPUT_DIR / "catalog.json"))

    seed = subparsers.add_parser("seed-backtest", help="Run one seed strategy on a date range")
    seed.add_argument("--start-date", required=True)
    seed.add_argument("--end-date", required=True)
    seed.add_argument("--budget", type=float, default=1_000_000.0)
    seed.add_argument("--data-tier", choices=["full_l2_order_book", "weak_trade_l2"], default="full_l2_order_book")
    seed.add_argument("--max-symbols-per-day", type=int, default=180)
    seed.add_argument("--symbols", default=None, help="Comma-separated symbols for a narrow smoke run")
    seed.add_argument("--atomic-db-path", default=None)
    seed.add_argument("--out", default=str(DEFAULT_OUTPUT_DIR / "seed_backtest"))

    arena = subparsers.add_parser("run-arena", help="Run Monte Carlo / genetic strategy arena")
    arena.add_argument("--start-date", required=True)
    arena.add_argument("--end-date", required=True)
    arena.add_argument("--budget", type=float, default=1_000_000.0)
    arena.add_argument("--population-size", type=int, default=200)
    arena.add_argument("--generations", type=int, default=2)
    arena.add_argument("--elite-size", type=int, default=12)
    arena.add_argument("--mutation-rate", type=float, default=0.35)
    arena.add_argument("--seed", type=int, default=7)
    arena.add_argument("--max-symbols-per-day", type=int, default=180)
    arena.add_argument("--data-tier", choices=["full_l2_order_book", "weak_trade_l2"], default="full_l2_order_book")
    arena.add_argument("--train-days", type=int, default=18)
    arena.add_argument("--validation-days", type=int, default=8)
    arena.add_argument("--test-days", type=int, default=8)
    arena.add_argument("--step-days", type=int, default=8)
    arena.add_argument("--symbols", default=None, help="Comma-separated symbols for a narrow smoke run")
    arena.add_argument("--atomic-db-path", default=None)
    arena.add_argument("--out", default=str(DEFAULT_OUTPUT_DIR / "arena"))

    rl_smoke = subparsers.add_parser("rl-random-smoke", help="Run a random agent through the RL market environment")
    rl_smoke.add_argument("--start-date", required=True)
    rl_smoke.add_argument("--end-date", required=True)
    rl_smoke.add_argument("--budget", type=float, default=1_000_000.0)
    rl_smoke.add_argument("--max-symbols-per-day", type=int, default=60)
    rl_smoke.add_argument("--seed", type=int, default=7)
    rl_smoke.add_argument("--symbols", default=None, help="Comma-separated symbols for a narrow smoke run")
    rl_smoke.add_argument("--atomic-db-path", default=None)
    rl_smoke.add_argument("--out", default=str(DEFAULT_OUTPUT_DIR / "rl_random_smoke.json"))

    rl_train = subparsers.add_parser("train-rl-policy", help="Train a lightweight RL policy-search agent")
    rl_train.add_argument("--start-date", required=True)
    rl_train.add_argument("--end-date", required=True)
    rl_train.add_argument("--budget", type=float, default=1_000_000.0)
    rl_train.add_argument("--population-size", type=int, default=48)
    rl_train.add_argument("--generations", type=int, default=4)
    rl_train.add_argument("--elite-fraction", type=float, default=0.20)
    rl_train.add_argument("--sigma", type=float, default=0.65)
    rl_train.add_argument("--sigma-decay", type=float, default=0.80)
    rl_train.add_argument("--seed", type=int, default=7)
    rl_train.add_argument("--max-symbols-per-day", type=int, default=60)
    rl_train.add_argument("--max-observation-symbols", type=int, default=60)
    rl_train.add_argument("--symbols", default=None, help="Comma-separated symbols for a narrow smoke run")
    rl_train.add_argument("--atomic-db-path", default=None)
    rl_train.add_argument("--out", default=str(DEFAULT_OUTPUT_DIR / "rl_policy_train.json"))

    ppo_train = subparsers.add_parser("train-ppo-policy", help="Train a PyTorch PPO target-weight policy")
    ppo_train.add_argument("--start-date", required=True)
    ppo_train.add_argument("--end-date", required=True)
    ppo_train.add_argument("--budget", type=float, default=1_000_000.0)
    ppo_train.add_argument("--total-timesteps", type=int, default=20_000)
    ppo_train.add_argument("--learning-rate", type=float, default=0.0003)
    ppo_train.add_argument("--n-steps", type=int, default=256)
    ppo_train.add_argument("--batch-size", type=int, default=64)
    ppo_train.add_argument("--n-epochs", type=int, default=8)
    ppo_train.add_argument("--gamma", type=float, default=0.995)
    ppo_train.add_argument("--seed", type=int, default=13)
    ppo_train.add_argument("--max-symbols-per-day", type=int, default=40)
    ppo_train.add_argument("--max-observation-symbols", type=int, default=20)
    ppo_train.add_argument("--target-return-pct", type=float, default=5.0)
    ppo_train.add_argument("--feature-set", choices=["weak_l2", "full_l2_order_book"], default="full_l2_order_book")
    ppo_train.add_argument("--symbols", default=None, help="Comma-separated symbols for a narrow smoke run")
    ppo_train.add_argument("--atomic-db-path", default=None)
    ppo_train.add_argument("--model-out", default=str(DEFAULT_OUTPUT_DIR / "ppo_policy_model.zip"))
    ppo_train.add_argument("--out", default=str(DEFAULT_OUTPUT_DIR / "ppo_policy_train.json"))

    ppo_eval = subparsers.add_parser("eval-ppo-policy", help="Evaluate a saved PPO policy without training")
    ppo_eval.add_argument("--model-path", required=True)
    ppo_eval.add_argument("--start-date", required=True)
    ppo_eval.add_argument("--end-date", required=True)
    ppo_eval.add_argument("--budget", type=float, default=1_000_000.0)
    ppo_eval.add_argument("--seed", type=int, default=101)
    ppo_eval.add_argument("--max-symbols-per-day", type=int, default=40)
    ppo_eval.add_argument("--max-observation-symbols", type=int, default=20)
    ppo_eval.add_argument("--feature-set", choices=["weak_l2", "full_l2_order_book"], default="full_l2_order_book")
    ppo_eval.add_argument("--symbols", default=None, help="Comma-separated symbols for a narrow smoke run")
    ppo_eval.add_argument("--atomic-db-path", default=None)
    ppo_eval.add_argument("--out", default=str(DEFAULT_OUTPUT_DIR / "ppo_policy_eval.json"))

    trend_train = subparsers.add_parser("train-trend-ppo-policy", help="Train a trend-holding portfolio PPO policy")
    trend_train.add_argument("--start-date", required=True)
    trend_train.add_argument("--end-date", required=True)
    trend_train.add_argument("--budget", type=float, default=1_000_000.0)
    trend_train.add_argument("--total-timesteps", type=int, default=60_000)
    trend_train.add_argument("--learning-rate", type=float, default=0.00025)
    trend_train.add_argument("--n-steps", type=int, default=512)
    trend_train.add_argument("--batch-size", type=int, default=128)
    trend_train.add_argument("--n-epochs", type=int, default=8)
    trend_train.add_argument("--gamma", type=float, default=0.999)
    trend_train.add_argument("--seed", type=int, default=29)
    trend_train.add_argument("--max-symbols-per-day", type=int, default=80)
    trend_train.add_argument("--max-observation-symbols", type=int, default=30)
    trend_train.add_argument("--episode-min-days", type=int, default=10)
    trend_train.add_argument("--episode-max-days", type=int, default=30)
    trend_train.add_argument("--target-return-pct", type=float, default=5.0)
    trend_train.add_argument("--symbols", default=None, help="Comma-separated symbols for a narrow smoke run")
    trend_train.add_argument("--atomic-db-path", default=None)
    trend_train.add_argument("--model-out", default=str(DEFAULT_OUTPUT_DIR / "trend_portfolio_ppo_model.zip"))
    trend_train.add_argument("--out", default=str(DEFAULT_OUTPUT_DIR / "trend_portfolio_ppo_train.json"))

    trend_eval = subparsers.add_parser("eval-trend-ppo-policy", help="Evaluate a saved trend portfolio PPO policy")
    trend_eval.add_argument("--model-path", required=True)
    trend_eval.add_argument("--start-date", required=True)
    trend_eval.add_argument("--end-date", required=True)
    trend_eval.add_argument("--budget", type=float, default=1_000_000.0)
    trend_eval.add_argument("--seed", type=int, default=101)
    trend_eval.add_argument("--max-symbols-per-day", type=int, default=80)
    trend_eval.add_argument("--max-observation-symbols", type=int, default=30)
    trend_eval.add_argument("--episode-min-days", type=int, default=10)
    trend_eval.add_argument("--episode-max-days", type=int, default=30)
    trend_eval.add_argument("--symbols", default=None, help="Comma-separated symbols for a narrow smoke run")
    trend_eval.add_argument("--atomic-db-path", default=None)
    trend_eval.add_argument("--out", default=str(DEFAULT_OUTPUT_DIR / "trend_portfolio_ppo_eval.json"))

    args = parser.parse_args()

    if args.command == "catalog-data":
        payload = catalog_intraday_data(db_path=args.atomic_db_path)
        written = write_catalog_output(payload, args.out)
        print(json.dumps({"payload": payload, "written": written}, ensure_ascii=False, indent=2))
        return

    if args.command == "seed-backtest":
        panel = load_intraday_panel(
            args.start_date,
            args.end_date,
            db_path=args.atomic_db_path,
            symbols=_split_symbols(args.symbols),
            max_symbols_per_day=int(args.max_symbols_per_day),
        )
        spec = make_seed_strategy(args.data_tier)
        payload = MarketReplayEnv(panel, budget=float(args.budget)).backtest(spec)
        payload["range"] = {"start_date": args.start_date, "end_date": args.end_date}
        aggregate = {
            "fold_count": 1,
            "mean_train_return_pct": payload["summary"]["total_return_pct"],
            "mean_validation_return_pct": payload["summary"]["total_return_pct"],
            "min_validation_return_pct": payload["summary"]["total_return_pct"],
            "mean_test_return_pct": payload["summary"]["total_return_pct"],
            "min_test_return_pct": payload["summary"]["total_return_pct"],
            "mean_validation_max_drawdown_pct": payload["summary"]["max_drawdown_pct"],
            "worst_validation_max_drawdown_pct": payload["summary"]["max_drawdown_pct"],
            "mean_max_drawdown_pct": payload["summary"]["max_drawdown_pct"],
            "worst_max_drawdown_pct": payload["summary"]["max_drawdown_pct"],
            "total_validation_trade_count": payload["summary"]["trade_count"],
            "total_trade_count": payload["summary"]["trade_count"],
            "mean_validation_win_rate_pct": payload["summary"]["win_rate_pct"],
            "mean_win_rate_pct": payload["summary"]["win_rate_pct"],
            "mean_validation_profit_factor": payload["summary"]["profit_factor"],
            "mean_profit_factor": payload["summary"]["profit_factor"],
            "mean_score": 0.0,
            "mean_test_score": 0.0,
            "short_range_overlap_folds": 0,
        }
        written = write_arena_outputs(
            {
                "lab_version": payload["lab_version"],
                "config": {
                    "start_date": args.start_date,
                    "end_date": args.end_date,
                    "data_tier": args.data_tier,
                    "budget": float(args.budget),
                    "population_size": 1,
                    "generations": 1,
                },
                "data": {
                    "atomic_db_path": args.atomic_db_path,
                    "symbols": int(panel["symbol"].nunique()) if not panel.empty else 0,
                    "rows": int(len(panel)),
                    "trade_dates": sorted(panel["trade_date"].unique().tolist()) if not panel.empty else [],
                    "folds": [],
                },
                "leaderboard": [
                    {
                        "generation": 1,
                        "strategy_name": spec.name,
                        **aggregate,
                        "strategy": payload["strategy"],
                    }
                ],
                "best": {
                    "strategy": payload["strategy"],
                    "aggregate": aggregate,
                    "folds": [],
                    "test_trades": payload["trades"],
                },
                "raw_extract_policy": "not used; this run reads processed atomic_*_5m tables only",
            },
            args.out,
        )
        print(json.dumps({"summary": payload["summary"], "written": written}, ensure_ascii=False, indent=2))
        return

    if args.command == "run-arena":
        config = EvolutionConfig(
            start_date=args.start_date,
            end_date=args.end_date,
            budget=float(args.budget),
            population_size=int(args.population_size),
            generations=int(args.generations),
            elite_size=int(args.elite_size),
            mutation_rate=float(args.mutation_rate),
            seed=int(args.seed),
            max_symbols_per_day=int(args.max_symbols_per_day),
            data_tier=args.data_tier,
            train_days=int(args.train_days),
            validation_days=int(args.validation_days),
            test_days=int(args.test_days),
            step_days=int(args.step_days),
        )
        payload = run_evolution_arena(config, db_path=args.atomic_db_path, symbols=_split_symbols(args.symbols))
        written = write_arena_outputs(payload, args.out)
        best = payload.get("best") or {}
        print(json.dumps({"best": best.get("aggregate"), "written": written}, ensure_ascii=False, indent=2))
        return

    if args.command == "rl-random-smoke":
        payload = run_rl_random_agent_smoke(
            args.start_date,
            args.end_date,
            db_path=args.atomic_db_path,
            symbols=_split_symbols(args.symbols),
            budget=float(args.budget),
            max_symbols_per_day=int(args.max_symbols_per_day),
            seed=int(args.seed),
        )
        out_path = args.out
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(json.dumps({"summary": payload["summary"], "total_reward": payload["total_reward"], "written": out_path}, ensure_ascii=False, indent=2))
        return

    if args.command == "train-rl-policy":
        payload = train_rl_policy_search(
            RLTrainerConfig(
                start_date=args.start_date,
                end_date=args.end_date,
                budget=float(args.budget),
                population_size=int(args.population_size),
                generations=int(args.generations),
                elite_fraction=float(args.elite_fraction),
                sigma=float(args.sigma),
                sigma_decay=float(args.sigma_decay),
                seed=int(args.seed),
                max_symbols_per_day=int(args.max_symbols_per_day),
                max_observation_symbols=int(args.max_observation_symbols),
            ),
            db_path=args.atomic_db_path,
            symbols=_split_symbols(args.symbols),
        )
        out_path = args.out
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        best = payload.get("best") or {}
        print(json.dumps({"best": best.get("summary"), "score": best.get("score"), "written": out_path}, ensure_ascii=False, indent=2))
        return

    if args.command == "train-ppo-policy":
        payload = train_rl_ppo_policy(
            RLPPOTrainerConfig(
                start_date=args.start_date,
                end_date=args.end_date,
                budget=float(args.budget),
                total_timesteps=int(args.total_timesteps),
                learning_rate=float(args.learning_rate),
                n_steps=int(args.n_steps),
                batch_size=int(args.batch_size),
                n_epochs=int(args.n_epochs),
                gamma=float(args.gamma),
                seed=int(args.seed),
                max_symbols_per_day=int(args.max_symbols_per_day),
                max_observation_symbols=int(args.max_observation_symbols),
                target_return_pct=float(args.target_return_pct),
                feature_set=args.feature_set,
            ),
            db_path=args.atomic_db_path,
            symbols=_split_symbols(args.symbols),
            model_out=args.model_out,
        )
        out_path = args.out
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(json.dumps({"summary": payload.get("summary"), "target_met": payload.get("target_met"), "written": out_path, "model": payload.get("model_path")}, ensure_ascii=False, indent=2))
        return

    if args.command == "eval-ppo-policy":
        payload = eval_rl_ppo_policy(
            model_path=args.model_path,
            start_date=args.start_date,
            end_date=args.end_date,
            db_path=args.atomic_db_path,
            symbols=_split_symbols(args.symbols),
            budget=float(args.budget),
            max_symbols_per_day=int(args.max_symbols_per_day),
            max_observation_symbols=int(args.max_observation_symbols),
            seed=int(args.seed),
            feature_set=args.feature_set,
        )
        out_path = args.out
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(json.dumps({"summary": payload.get("summary"), "written": out_path}, ensure_ascii=False, indent=2))
        return

    if args.command == "train-trend-ppo-policy":
        payload = train_trend_portfolio_ppo_policy(
            TrendPortfolioPPOTrainerConfig(
                start_date=args.start_date,
                end_date=args.end_date,
                budget=float(args.budget),
                total_timesteps=int(args.total_timesteps),
                learning_rate=float(args.learning_rate),
                n_steps=int(args.n_steps),
                batch_size=int(args.batch_size),
                n_epochs=int(args.n_epochs),
                gamma=float(args.gamma),
                seed=int(args.seed),
                max_symbols_per_day=int(args.max_symbols_per_day),
                max_observation_symbols=int(args.max_observation_symbols),
                episode_min_days=int(args.episode_min_days),
                episode_max_days=int(args.episode_max_days),
                target_return_pct=float(args.target_return_pct),
            ),
            db_path=args.atomic_db_path,
            symbols=_split_symbols(args.symbols),
            model_out=args.model_out,
        )
        out_path = args.out
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(json.dumps({"summary": payload.get("summary"), "target_met": payload.get("target_met"), "written": out_path, "model": payload.get("model_path")}, ensure_ascii=False, indent=2))
        return

    if args.command == "eval-trend-ppo-policy":
        payload = eval_trend_portfolio_ppo_policy(
            model_path=args.model_path,
            start_date=args.start_date,
            end_date=args.end_date,
            db_path=args.atomic_db_path,
            symbols=_split_symbols(args.symbols),
            budget=float(args.budget),
            max_symbols_per_day=int(args.max_symbols_per_day),
            max_observation_symbols=int(args.max_observation_symbols),
            episode_min_days=int(args.episode_min_days),
            episode_max_days=int(args.episode_max_days),
            seed=int(args.seed),
        )
        out_path = args.out
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(json.dumps({"summary": payload.get("summary"), "written": out_path}, ensure_ascii=False, indent=2))
        return


if __name__ == "__main__":
    main()
