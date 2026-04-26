from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_DIR = Path("docs/strategy-rework/strategies/S01-capital-trend-reversal/experiments/EXP-20260426-S01-M05-conservative-combined-risk")
ROBUST_FEATURES = Path("docs/strategy-rework/strategies/S04-capital-exit-risk/experiments/EXP-20260426-combined-risk-stack-robustness/combined_risk_robustness_features.csv")


def summarize(df: pd.DataFrame, ret_col: str = "net_return_pct") -> Dict[str, Any]:
    if df.empty:
        return {
            "trade_count": 0,
            "win_rate_pct": 0.0,
            "avg_net_return_pct": 0.0,
            "median_net_return_pct": 0.0,
            "max_net_return_pct": 0.0,
            "min_net_return_pct": 0.0,
            "sum_net_return_pct": 0.0,
            "big_winner_gt_15_count": 0,
            "big_loss_le_-8_count": 0,
        }
    s = pd.to_numeric(df[ret_col], errors="coerce").dropna()
    if s.empty:
        return summarize(pd.DataFrame())
    return {
        "trade_count": int(len(s)),
        "win_rate_pct": round(float((s > 0).mean() * 100), 2),
        "avg_net_return_pct": round(float(s.mean()), 2),
        "median_net_return_pct": round(float(s.median()), 2),
        "max_net_return_pct": round(float(s.max()), 2),
        "min_net_return_pct": round(float(s.min()), 2),
        "sum_net_return_pct": round(float(s.sum()), 2),
        "big_winner_gt_15_count": int((s > 15).sum()),
        "big_loss_le_-8_count": int((s <= -8).sum()),
    }


def prefixed(prefix: str, d: Dict[str, Any]) -> Dict[str, Any]:
    return {f"{prefix}_{k}": v for k, v in d.items()}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    feats = pd.read_csv(ROBUST_FEATURES)

    # 用 full 口径做一次策略定义，再按 is_mature_trade 分成熟交易；避免 mature/full 重复样本。
    base_full = feats[feats["sample_name"] == "modes:v1.4-balanced:full"].copy()
    base_full["strategy_method"] = "S01-M04B-balanced-weak-launch-filter"
    base_full["combined_risk_filter"] = pd.to_numeric(base_full["risk_count_R1_R5"], errors="coerce").fillna(0) >= 2

    m05_full = base_full[~base_full["combined_risk_filter"]].copy()
    m05_full["strategy_method"] = "S01-M05-conservative-combined-risk"
    filtered_full = base_full[base_full["combined_risk_filter"]].copy()

    base_mature = base_full[base_full["is_mature_trade"].astype(bool)].copy()
    m05_mature = m05_full[m05_full["is_mature_trade"].astype(bool)].copy()
    filtered_mature = filtered_full[filtered_full["is_mature_trade"].astype(bool)].copy()

    comparison_rows = []
    for label, full_df, mature_df in [
        ("S01-M04B", base_full, base_mature),
        ("S01-M05", m05_full, m05_mature),
        ("S04-filtered-out", filtered_full, filtered_mature),
    ]:
        row = {"strategy_method": label}
        row.update(prefixed("full", summarize(full_df)))
        row.update(prefixed("mature", summarize(mature_df)))
        comparison_rows.append(row)

    comparison = pd.DataFrame(comparison_rows)
    comparison.to_csv(OUT_DIR / "s01_m05_comparison.csv", index=False)
    m05_full.to_csv(OUT_DIR / "s01_m05_trades.csv", index=False)
    filtered_full.to_csv(OUT_DIR / "s04_combined_risk_filtered_trades.csv", index=False)
    base_full.to_csv(OUT_DIR / "s01_m04b_base_trades_with_risk.csv", index=False)

    summary = {
        "experiment": "EXP-20260426-S01-M05-conservative-combined-risk",
        "definition": "S01-M05 = S01-M04B + filter risk_count_R1_R5 >= 2 before entry",
        "base_method": "S01-M04B-balanced-weak-launch-filter",
        "risk_module": "S04-M01-observe-combined-risk-stack",
        "risk_rule": "risk_count_R1_R5 >= 2",
        "comparison": comparison_rows,
        "mature_delta": {
            "trade_count_delta": int(len(m05_mature) - len(base_mature)),
            "win_rate_delta_pct": round(summarize(m05_mature)["win_rate_pct"] - summarize(base_mature)["win_rate_pct"], 2),
            "avg_net_return_delta_pct": round(summarize(m05_mature)["avg_net_return_pct"] - summarize(base_mature)["avg_net_return_pct"], 2),
            "median_net_return_delta_pct": round(summarize(m05_mature)["median_net_return_pct"] - summarize(base_mature)["median_net_return_pct"], 2),
            "big_loss_le_-8_delta": summarize(m05_mature)["big_loss_le_-8_count"] - summarize(base_mature)["big_loss_le_-8_count"],
            "big_winner_gt_15_delta": summarize(m05_mature)["big_winner_gt_15_count"] - summarize(base_mature)["big_winner_gt_15_count"],
        },
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    readme = f"""# EXP-20260426-S01-M05-conservative-combined-risk

## 问题

把 S04 组合风险规则作为一个明确的 S01 实验方法版本，验证：

```text
S01-M05 = S01-M04B + 组合风险 >=2 时不进场
```

## 策略定义

基础策略：`S01-M04B-balanced-weak-launch-filter`。

新增过滤：

```text
risk_count_R1_R5 >= 2
```

也就是以下 5 个风险信号中同时出现至少 2 个：

- R1：启动期撤买/新增买接近异常防线。
- R2：启动期 OIB/CVD 背离。
- R3：确认日出货分偏高。
- R4：确认日超大单和主力同时为负。
- R5：弱启动 + 回调承接差。

## 结果

{comparison.to_markdown(index=False)}

## 解释

- `avg_net_return_pct`：平均净收益率，不是金额。
- `median_net_return_pct`：中位净收益率，更能避免被单只大牛扭曲。
- `S04-filtered-out`：被 M05 排除的交易。如果这组整体为负，说明过滤有价值。

## 阶段结论

按当前 2026-03~04 的 L2 挂单样本，M05 明显优于 M04B：胜率、平均净收益率、中位净收益率均提升，且没有过滤掉成熟样本里的 >15% 大赢家。

但 full 口径仍有未来数据不足的交易，且挂单数据只有两个月，所以建议先作为实验策略/稳健模式，不直接覆盖主策略。

## 输出文件

- `s01_m05_comparison.csv`
- `s01_m05_trades.csv`
- `s04_combined_risk_filtered_trades.csv`
- `s01_m04b_base_trades_with_risk.csv`
- `summary.json`
"""
    (OUT_DIR / "README.md").write_text(readme, encoding="utf-8")
    print(comparison.to_string(index=False))


if __name__ == "__main__":
    main()
