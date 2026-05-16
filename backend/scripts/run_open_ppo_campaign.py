from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.intraday_evolution_lab import (  # noqa: E402
    DEFAULT_OUTPUT_DIR,
    RLPPOTrainerConfig,
    TrendPortfolioPPOTrainerConfig,
    eval_rl_ppo_policy,
    eval_trend_portfolio_ppo_policy,
    train_rl_ppo_policy,
    train_trend_portfolio_ppo_policy,
)


CAMPAIGN_DIR = DEFAULT_OUTPUT_DIR / "open_ppo_campaign"
DEFAULT_REPORT_PATH = DEFAULT_OUTPUT_DIR / "open_ppo_campaign_report.json"
CURRENT_PAGE_REPORT_PATH = DEFAULT_OUTPUT_DIR / "two_stage_joint_objective_report.json"


@dataclass(frozen=True)
class CampaignRun:
    run_id: str
    family: str
    seed: int
    total_timesteps: int
    learning_rate: float
    n_steps: int
    batch_size: int
    n_epochs: int
    gamma: float
    max_symbols_per_day: int
    max_observation_symbols: int
    train_start: str = "2026-03-02"
    train_end: str = "2026-04-15"
    primary_start: str = "2026-03-15"
    primary_end: str = "2026-04-15"
    forward_start: str = "2026-04-16"
    forward_end: str = "2026-05-13"
    feature_set: str = "full_l2_order_book"
    episode_min_days: int = 10
    episode_max_days: int = 30
    ent_coef: float = 0.02
    clip_range: float = 0.2


def _standard_plan() -> List[CampaignRun]:
    return [
        CampaignRun("target_5m_s311_30k", "target_5m", 311, 30_000, 0.00030, 256, 64, 8, 0.995, 90, 30),
        CampaignRun("target_5m_s312_50k", "target_5m", 312, 50_000, 0.00025, 512, 128, 8, 0.997, 120, 40),
        CampaignRun("target_5m_s313_80k", "target_5m", 313, 80_000, 0.00020, 512, 128, 10, 0.998, 120, 40),
        CampaignRun("trend_daily_s411_20k", "trend_daily", 411, 20_000, 0.00025, 256, 64, 6, 0.999, 80, 30),
        CampaignRun("trend_daily_s412_30k", "trend_daily", 412, 30_000, 0.00020, 512, 128, 8, 0.999, 100, 40),
        CampaignRun("trend_daily_s413_40k", "trend_daily", 413, 40_000, 0.00018, 512, 128, 8, 0.999, 120, 40),
    ]


def _quick_plan() -> List[CampaignRun]:
    return [
        CampaignRun("target_5m_s311_10k", "target_5m", 311, 10_000, 0.00030, 256, 64, 6, 0.995, 70, 24),
        CampaignRun("trend_daily_s411_8k", "trend_daily", 411, 8_000, 0.00025, 256, 64, 4, 0.999, 70, 24),
    ]


def _safe_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
    summary = dict(payload.get("summary") or {})
    return {
        "final_equity": summary.get("final_equity"),
        "total_return_pct": summary.get("total_return_pct"),
        "max_drawdown_pct": summary.get("max_drawdown_pct"),
        "trade_count": summary.get("trade_count"),
        "open_positions": summary.get("open_positions"),
        "cash": summary.get("cash"),
    }


def _exposure_stats(equity_curve: List[Dict[str, Any]]) -> Dict[str, Any]:
    values = []
    for row in equity_curve:
        equity = float(row.get("equity") or row.get("cash") or 0.0)
        cash = float(row.get("cash") or 0.0)
        if equity <= 0:
            values.append(0.0)
        else:
            values.append(max(0.0, min(100.0, (equity - cash) / equity * 100.0)))
    return {
        "avg_exposure_pct": round(sum(values) / len(values), 2) if values else 0.0,
        "max_exposure_pct": round(max(values), 2) if values else 0.0,
        "invested_steps": int(sum(1 for item in values if item >= 5.0)),
        "full_exposure_steps": int(sum(1 for item in values if item >= 95.0)),
        "total_steps": int(len(values)),
    }


def _score(primary: Dict[str, Any], forward: Optional[Dict[str, Any]]) -> float:
    summary = primary.get("summary") or {}
    primary_return = float(summary.get("total_return_pct") or 0.0)
    primary_drawdown = abs(float(summary.get("max_drawdown_pct") or 0.0))
    trade_count = int(summary.get("trade_count") or 0)
    score = primary_return - primary_drawdown * 0.15 - max(0, trade_count - 120) * 0.01
    if forward:
        forward_summary = forward.get("summary") or {}
        score += 0.35 * float(forward_summary.get("total_return_pct") or 0.0)
        score -= 0.08 * abs(float(forward_summary.get("max_drawdown_pct") or 0.0))
    return round(score, 6)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_one(spec: CampaignRun, out_dir: Path) -> Dict[str, Any]:
    run_dir = out_dir / spec.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    model_path = run_dir / "model.zip"
    train_path = run_dir / "train.json"
    primary_path = run_dir / "primary_eval.json"
    forward_path = run_dir / "forward_eval.json"

    print(f"[campaign] start {spec.run_id} {spec.family} timesteps={spec.total_timesteps} seed={spec.seed}", flush=True)
    started = time.time()
    if spec.family == "target_5m":
        train_payload = train_rl_ppo_policy(
            RLPPOTrainerConfig(
                start_date=spec.train_start,
                end_date=spec.train_end,
                budget=1_000_000.0,
                total_timesteps=spec.total_timesteps,
                learning_rate=spec.learning_rate,
                n_steps=spec.n_steps,
                batch_size=spec.batch_size,
                n_epochs=spec.n_epochs,
                gamma=spec.gamma,
                seed=spec.seed,
                max_symbols_per_day=spec.max_symbols_per_day,
                max_observation_symbols=spec.max_observation_symbols,
                target_return_pct=5.0,
                feature_set=spec.feature_set,
            ),
            model_out=model_path,
        )
        primary_payload = eval_rl_ppo_policy(
            model_path=model_path,
            start_date=spec.primary_start,
            end_date=spec.primary_end,
            budget=1_000_000.0,
            max_symbols_per_day=spec.max_symbols_per_day,
            max_observation_symbols=spec.max_observation_symbols,
            seed=spec.seed + 10_000,
            feature_set=spec.feature_set,
        )
        forward_payload = eval_rl_ppo_policy(
            model_path=model_path,
            start_date=spec.forward_start,
            end_date=spec.forward_end,
            budget=1_000_000.0,
            max_symbols_per_day=spec.max_symbols_per_day,
            max_observation_symbols=spec.max_observation_symbols,
            seed=spec.seed + 20_000,
            feature_set=spec.feature_set,
        )
    elif spec.family == "trend_daily":
        train_payload = train_trend_portfolio_ppo_policy(
            TrendPortfolioPPOTrainerConfig(
                start_date=spec.train_start,
                end_date=spec.train_end,
                budget=1_000_000.0,
                total_timesteps=spec.total_timesteps,
                learning_rate=spec.learning_rate,
                n_steps=spec.n_steps,
                batch_size=spec.batch_size,
                n_epochs=spec.n_epochs,
                gamma=spec.gamma,
                seed=spec.seed,
                max_symbols_per_day=spec.max_symbols_per_day,
                max_observation_symbols=spec.max_observation_symbols,
                episode_min_days=spec.episode_min_days,
                episode_max_days=spec.episode_max_days,
                target_return_pct=5.0,
                ent_coef=spec.ent_coef,
                clip_range=spec.clip_range,
            ),
            model_out=model_path,
        )
        primary_payload = eval_trend_portfolio_ppo_policy(
            model_path=model_path,
            start_date=spec.primary_start,
            end_date=spec.primary_end,
            budget=1_000_000.0,
            max_symbols_per_day=spec.max_symbols_per_day,
            max_observation_symbols=spec.max_observation_symbols,
            episode_min_days=spec.episode_min_days,
            episode_max_days=spec.episode_max_days,
            seed=spec.seed + 10_000,
        )
        forward_payload = eval_trend_portfolio_ppo_policy(
            model_path=model_path,
            start_date=spec.forward_start,
            end_date=spec.forward_end,
            budget=1_000_000.0,
            max_symbols_per_day=spec.max_symbols_per_day,
            max_observation_symbols=spec.max_observation_symbols,
            episode_min_days=spec.episode_min_days,
            episode_max_days=spec.episode_max_days,
            seed=spec.seed + 20_000,
        )
    else:
        raise ValueError(f"unknown family: {spec.family}")

    _write_json(train_path, train_payload)
    _write_json(primary_path, primary_payload)
    _write_json(forward_path, forward_payload)
    elapsed = round(time.time() - started, 2)
    row = {
        "run_id": spec.run_id,
        "family": spec.family,
        "spec": asdict(spec),
        "elapsed_seconds": elapsed,
        "model_path": str(model_path),
        "train_path": str(train_path),
        "primary_eval_path": str(primary_path),
        "forward_eval_path": str(forward_path),
        "train_summary": _safe_summary(train_payload),
        "primary_summary": _safe_summary(primary_payload),
        "forward_summary": _safe_summary(forward_payload),
        "primary_exposure": _exposure_stats(list(primary_payload.get("equity_curve") or [])),
        "forward_exposure": _exposure_stats(list(forward_payload.get("equity_curve") or [])),
        "score": _score(primary_payload, forward_payload),
    }
    print(
        "[campaign] done "
        f"{spec.run_id} score={row['score']} primary={row['primary_summary']} "
        f"forward={row['forward_summary']} elapsed={elapsed}s",
        flush=True,
    )
    return {"row": row, "train": train_payload, "primary": primary_payload, "forward": forward_payload}


def _load_baseline() -> Optional[Dict[str, Any]]:
    if not CURRENT_PAGE_REPORT_PATH.exists():
        return None
    try:
        payload = json.loads(CURRENT_PAGE_REPORT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    return {
        "run_id": "current_two_stage_baseline",
        "family": "fixed_selector_holding_search",
        "score": None,
        "primary_summary": _safe_summary(payload),
        "primary_exposure": _exposure_stats(list(payload.get("equity_curve") or [])),
        "report_path": str(CURRENT_PAGE_REPORT_PATH),
    }


def _make_report(best_result: Dict[str, Any], leaderboard: List[Dict[str, Any]], profile: str) -> Dict[str, Any]:
    row = best_result["row"]
    primary = dict(best_result["primary"])
    report = {
        **primary,
        "lab_version": "open_ppo_campaign_v0_1",
        "mode": f"open_ppo_campaign_{row['family']}",
        "range": primary.get("range") or {"start_date": row["spec"]["primary_start"], "end_date": row["spec"]["primary_end"]},
        "training": {
            "assessment": "completed_open_ppo_campaign",
            "profile": profile,
            "run_id": row["run_id"],
            "family": row["family"],
            "score": row["score"],
            "elapsed_seconds": row["elapsed_seconds"],
            "total_timesteps": row["spec"]["total_timesteps"],
            "seed": row["spec"]["seed"],
            "primary_exposure": row["primary_exposure"],
            "forward_summary": row["forward_summary"],
            "forward_exposure": row["forward_exposure"],
            "leaderboard": leaderboard,
        },
        "policy_note": (
            "Open PPO campaign. The model outputs target portfolio weights; the environment enforces cash, "
            "position, T+1, limit-up/down, fees and slippage. No hand-written stop-loss/holding-day policy is used."
        ),
    }
    return report


def run_campaign(profile: str, *, publish_if_beats: bool) -> Dict[str, Any]:
    out_dir = CAMPAIGN_DIR / time.strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    plan = _quick_plan() if profile == "quick" else _standard_plan()
    rows: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []
    baseline = _load_baseline()
    if baseline:
        rows.append(baseline)

    for spec in plan:
        result = _run_one(spec, out_dir)
        results.append(result)
        rows.append(result["row"])
        leaderboard = sorted(
            rows,
            key=lambda item: (
                float(item.get("score") if item.get("score") is not None else -9999.0),
                float((item.get("primary_summary") or {}).get("total_return_pct") or 0.0),
            ),
            reverse=True,
        )
        _write_json(out_dir / "leaderboard.json", {"profile": profile, "leaderboard": leaderboard})

    open_results = [item for item in results if item.get("row")]
    open_results.sort(key=lambda item: float(item["row"]["score"]), reverse=True)
    best_open = open_results[0] if open_results else None
    leaderboard = sorted(
        rows,
        key=lambda item: (
            float(item.get("score") if item.get("score") is not None else -9999.0),
            float((item.get("primary_summary") or {}).get("total_return_pct") or 0.0),
        ),
        reverse=True,
    )
    payload = {
        "profile": profile,
        "started_output_dir": str(out_dir),
        "completed_runs": len(open_results),
        "planned_runs": len(plan),
        "leaderboard": leaderboard,
    }
    if best_open:
        report = _make_report(best_open, leaderboard, profile)
        _write_json(DEFAULT_REPORT_PATH, report)
        payload["best_open_report_path"] = str(DEFAULT_REPORT_PATH)
        payload["best_open"] = best_open["row"]
        current_return = float((baseline or {}).get("primary_summary", {}).get("total_return_pct") or -9999.0)
        best_return = float(best_open["row"]["primary_summary"].get("total_return_pct") or -9999.0)
        if publish_if_beats and best_return > current_return:
            shutil.copyfile(DEFAULT_REPORT_PATH, CURRENT_PAGE_REPORT_PATH)
            payload["published_to_page_report"] = str(CURRENT_PAGE_REPORT_PATH)
    _write_json(out_dir / "campaign_summary.json", payload)
    print("[campaign] complete", json.dumps(payload, ensure_ascii=False), flush=True)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=["quick", "standard"], default="standard")
    parser.add_argument("--publish-if-beats", action="store_true")
    args = parser.parse_args()
    run_campaign(args.profile, publish_if_beats=bool(args.publish_if_beats))


if __name__ == "__main__":
    main()
