from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.selection_strategy_v2 import SelectionV2Params, _compute_intent_profile, compute_v2_metrics, load_atomic_daily_window
from backend.scripts.run_strategy_v1_4_modes import filter_reason as m04_filter_reason
from backend.scripts.run_strategy_v1_3_orderbook_filter import launch_cancel_buy_vs_hist
from backend.scripts.run_strategy_v1_trend_reversal import add_ma, candidate_ok, find_launch, find_pullback_confirm, setup_score
from backend.scripts.research_trend_sample_factors import pct, slice_stats

DEFAULT_OUT = Path("docs/strategy-rework/strategies/S01-capital-trend-reversal/experiments/EXP-20260426-market-extreme-reverse-audit")
LEGACY_V14_OUT = Path("docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-v1-4-modes")
LOOKBACK = "2026-01-01"


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default


def max_runup(g: pd.DataFrame) -> Dict[str, Any]:
    best = {"runup_pct": -999.0, "start_i": 0, "end_i": 0}
    min_low = None
    min_i = None
    for i, r in g.iterrows():
        low = float(r.low)
        high = float(r.high)
        if min_low is None or low < min_low:
            min_low = low
            min_i = i
        if min_low and min_low > 0:
            ru = pct(min_low, high)
            if ru > best["runup_pct"]:
                best = {"runup_pct": ru, "start_i": int(min_i), "end_i": int(i)}
    return best


def max_drawdown(g: pd.DataFrame) -> Dict[str, Any]:
    worst = {"drawdown_pct": 999.0, "start_i": 0, "end_i": 0}
    max_high = None
    max_i = None
    for i, r in g.iterrows():
        high = float(r.high)
        low = float(r.low)
        if max_high is None or high > max_high:
            max_high = high
            max_i = i
        if max_high and max_high > 0:
            dd = pct(max_high, low)
            if dd < worst["drawdown_pct"]:
                worst = {"drawdown_pct": dd, "start_i": int(max_i), "end_i": int(i)}
    return worst


def fetch_names(symbols: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for i in range(0, len(symbols), 80):
        batch = ",".join(symbols[i : i + 80])
        url = "https://hq.sinajs.cn/list=" + batch
        try:
            req = urllib.request.Request(url, headers={"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"})
            text = urllib.request.urlopen(req, timeout=20).read().decode("gbk", "ignore")
            for sym, body in re.findall(r"var hq_str_(\w+)=\"([^\"]*)\";", text):
                name = body.split(",")[0].strip()
                if name:
                    out[sym] = name
        except Exception:
            pass
    return out


def build_extremes(metrics: pd.DataFrame, start: str, end: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    scoped = metrics[(metrics.trade_date >= start) & (metrics.trade_date <= end)].copy()
    for sym, g0 in scoped.groupby("symbol", sort=False):
        g = g0.sort_values("trade_date").reset_index(drop=True)
        if len(g) < 10:
            continue
        ru = max_runup(g)
        dd = max_drawdown(g)
        rows.append({
            "symbol": sym,
            "runup_pct": round(float(ru["runup_pct"]), 2),
            "runup_start_date": str(g.loc[ru["start_i"], "trade_date"]),
            "runup_end_date": str(g.loc[ru["end_i"], "trade_date"]),
            "runup_start_price": round(float(g.loc[ru["start_i"], "low"]), 3),
            "runup_end_price": round(float(g.loc[ru["end_i"], "high"]), 3),
            "drawdown_pct": round(float(dd["drawdown_pct"]), 2),
            "drawdown_start_date": str(g.loc[dd["start_i"], "trade_date"]),
            "drawdown_end_date": str(g.loc[dd["end_i"], "trade_date"]),
            "drawdown_start_price": round(float(g.loc[dd["start_i"], "high"]), 3),
            "drawdown_end_price": round(float(g.loc[dd["end_i"], "low"]), 3),
            "period_return_pct": round(pct(float(g.close.iloc[0]), float(g.close.iloc[-1])), 2),
            "amount_avg": round(float(g.total_amount.mean()), 2),
        })
    df = pd.DataFrame(rows)
    top = df.sort_values(["runup_pct", "amount_avg"], ascending=[False, False]).head(30).copy()
    bottom = df.sort_values(["drawdown_pct", "amount_avg"], ascending=[True, False]).head(30).copy()
    names = fetch_names(sorted(set(top.symbol.tolist() + bottom.symbol.tolist())))
    top.insert(1, "name", top.symbol.map(names).fillna(""))
    bottom.insert(1, "name", bottom.symbol.map(names).fillna(""))
    return top, bottom


def stage_analysis(sym: str, anchor_date: str, by_symbol: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    g = by_symbol.get(sym)
    if g is None or g.empty:
        return {"stage_status": "no_data"}
    idxs = g.index[g.trade_date <= anchor_date].tolist()
    if not idxs:
        return {"stage_status": "no_prior_data"}
    i = int(idxs[-1])
    if i < 8:
        return {"stage_status": "insufficient_lookback", "nearest_date": str(g.loc[i, "trade_date"])}

    pre20 = slice_stats(g, i - 20, i - 1, "pre20")
    pre5 = slice_stats(g, i - 5, i - 1, "pre5")
    current = g.loc[i]
    sc = setup_score(pre20, pre5, current)
    ok = candidate_ok(pre20, pre5, current, sc)
    launch_start, launch_end, launch_meta = find_launch(g, str(g.loc[i, "trade_date"]))
    pull_date = None
    pull_reason = "no_launch"
    pull_meta: Dict[str, Any] = {}
    ladder: Dict[str, Any] = {}
    if launch_end:
        pull_date, pull_reason, pull_meta = find_pullback_confirm(g, launch_start, launch_end)
        ladder = launch_cancel_buy_vs_hist(g, str(launch_start), str(launch_end))

    intent = _compute_intent_profile(current, SelectionV2Params())
    reasons = []
    if safe_float(current.get("total_amount")) < 250_000_000:
        reasons.append("成交额<2.5亿")
    if sc < 50:
        reasons.append("setup_score<50")
    if safe_float(pre20.get("pre20_return_pct")) > 12:
        reasons.append("前20日涨幅>12")
    if safe_float(pre5.get("pre5_return_pct")) > 8:
        reasons.append("前5日涨幅>8")
    if max(safe_float(pre20.get("pre20_super_price_divergence")), safe_float(pre20.get("pre20_main_price_divergence")), safe_float(pre5.get("pre5_super_price_divergence"))) <= 0.015:
        reasons.append("资金价格背离不足")

    if not ok:
        stage_status = "setup_rejected"
        primary = ";".join(reasons) or "setup_rejected"
    elif not launch_start:
        stage_status = "setup_ok_no_launch"
        primary = "候选通过但未找到启动3日"
    elif not pull_date:
        stage_status = "launch_ok_no_pullback"
        primary = "启动通过但未等到回调承接"
    else:
        stage_status = "anchor_chain_passed"
        primary = "锚点附近链路可通过"

    out = {
        "nearest_date": str(g.loc[i, "trade_date"]),
        "stage_status": stage_status,
        "setup_score_at_anchor": sc,
        "candidate_ok_at_anchor": bool(ok),
        "primary_anchor_reason": primary,
        "anchor_total_amount": round(safe_float(current.get("total_amount")), 2),
        "anchor_distribution_score": round(safe_float(intent.get("distribution_score")), 2),
        "anchor_pre20_return_pct": pre20.get("pre20_return_pct"),
        "anchor_pre20_super_price_divergence": pre20.get("pre20_super_price_divergence"),
        "anchor_pre20_main_price_divergence": pre20.get("pre20_main_price_divergence"),
        "anchor_pre5_return_pct": pre5.get("pre5_return_pct"),
        "anchor_pre5_super_price_divergence": pre5.get("pre5_super_price_divergence"),
        "anchor_launch_start": launch_start,
        "anchor_launch_end": launch_end,
        "anchor_pullback_confirm_date": pull_date,
        "anchor_pullback_reason": pull_reason,
        **{f"anchor_{k}": v for k, v in launch_meta.items() if k in ["launch3_return_pct", "launch3_super_net_ratio", "launch3_main_net_ratio", "launch3_max_drawdown_pct", "launch3_add_buy_ratio"]},
        **{f"anchor_{k}": v for k, v in pull_meta.items() if k in ["pullback_super_net_ratio", "pullback_main_net_ratio", "pullback_support_spread_avg", "confirm_distribution_score"]},
        **{f"anchor_{k}": v for k, v in ladder.items() if k in ["launch_cancel_buy_to_add_buy_vs_hist", "launch_cancel_buy_to_add_buy"]},
    }
    return out


def mode_filter_counts(cands: pd.DataFrame) -> Dict[str, int]:
    c = Counter()
    for _, r in cands.iterrows():
        reason = m04_filter_reason(r.to_dict(), "v1.4-balanced")
        if reason:
            c[reason] += 1
    return dict(c)


def classify_top(row: Dict[str, Any]) -> Tuple[str, str]:
    if int(row.get("m04b_trade_count") or 0) > 0:
        return "已交易", "S01已覆盖"
    if int(row.get("candidate_count") or 0) > 0:
        if row.get("candidate_only_filter_reasons"):
            if "v1_3_ladder_pull_filter" in str(row.get("candidate_only_filter_reasons")):
                return "被挂单诱多过滤", "S04复核，避免误杀真强票"
            return "被M04B弱启动过滤", "S01复核过滤强度"
        if not bool(row.get("has_pullback_confirm_candidate")):
            return "有发现但无回调确认", "S02/等待中继，不强塞S01"
        return "有发现但未形成交易", "S01工程链路复核"

    reason = str(row.get("primary_anchor_reason") or "")
    pre20 = safe_float(row.get("anchor_pre20_return_pct"))
    pre5 = safe_float(row.get("anchor_pre5_return_pct"))
    if "成交额<2.5亿" in reason:
        return "发现层成交额硬门槛", "S01优先优化：绝对成交额改相对流动性/换手"
    if pre20 > 12 or pre5 > 8:
        return "起点前已涨过/过热", "S02趋势中继"
    if "资金价格背离不足" in reason:
        return "资金背离不足", "非S01或需S03消息面解释"
    if "setup_score<50" in reason:
        return "低位资金结构不达标", "S01可优化打分，但不宜放松过多"
    if "候选通过但未找到启动3日" in reason:
        return "启动确认缺失", "S01启动识别可优化"
    if "启动通过但未等到回调承接" in reason:
        return "无回调承接", "S02趋势中继/追踪，不归S01买点"
    if "锚点附近链路可通过" in reason:
        return "链路可过但未进每日Top10", "S01排序/容量问题"
    return "其他", "人工复盘"


def bottom_risk_flags(trades: pd.DataFrame) -> List[str]:
    flags = []
    if trades.empty:
        return flags
    # 一只票可能多次交易；按最早 M04B 交易归因。
    r = trades.sort_values("entry_date").iloc[0]
    if safe_float(r.get("launch_cancel_buy_to_add_buy_vs_hist")) >= 1.0:
        flags.append("启动期撤买/新增买相对历史偏高但未过1.5")
    if safe_float(r.get("confirm_distribution_score")) >= 45:
        flags.append("确认日出货分偏高")
    if safe_float(r.get("launch3_return_pct")) < 6:
        flags.append("启动3日涨幅偏弱")
    if safe_float(r.get("pullback_support_spread_avg")) < 0:
        flags.append("回调承接为负")
    if safe_float(r.get("final_super_peak_drawdown_pct")) >= 20:
        flags.append("买入后累计超大单从峰值明显回撤")
    if str(r.get("exit_reason")) in {"violent_super_outflow"} or "cum_super_peak_dd" in str(r.get("exit_reason")):
        flags.append("退出由资金撤退触发")
    if "hard_stop" in str(r.get("exit_reason")):
        flags.append("硬止损退出")
    if safe_float(r.get("pre20_return_pct")) > 12 or safe_float(r.get("pre5_return_pct")) > 8:
        flags.append("入场前价格已过热")
    if not flags:
        flags.append("M04B常规通过，需S04专门识别下跌风险")
    return flags


def diagnose(extreme: pd.DataFrame, kind: str, candidates: pd.DataFrame, trades: pd.DataFrame, by_symbol: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for _, er in extreme.iterrows():
        sym = str(er.symbol)
        anchor_date = str(er.runup_start_date if kind == "top" else er.drawdown_start_date)
        c = candidates[candidates.symbol == sym].copy()
        t_all = trades[trades.symbol == sym].copy()
        t_m04 = t_all[t_all.strategy_mode == "v1.4-balanced"].copy() if "strategy_mode" in t_all.columns else pd.DataFrame()
        c_filter_counts = mode_filter_counts(c) if not c.empty else {}
        analysis = stage_analysis(sym, anchor_date, by_symbol)
        row = {
            **er.to_dict(),
            "anchor_date_for_audit": anchor_date,
            "candidate_count": int(len(c)),
            "candidate_dates": ",".join(c.discovery_date.astype(str).head(10).tolist()) if not c.empty else "",
            "has_pullback_confirm_candidate": bool((c.pullback_confirm_date.notna()).any()) if not c.empty else False,
            "candidate_only_filter_reasons": ";".join(f"{k}:{v}" for k, v in c_filter_counts.items()),
            "m04b_trade_count": int(len(t_m04)),
            "m04b_entry_dates": ",".join(t_m04.entry_date.astype(str).head(5).tolist()) if not t_m04.empty else "",
            "m04b_best_return_pct": round(float(t_m04.net_return_pct.max()), 2) if not t_m04.empty else None,
            "m04b_worst_return_pct": round(float(t_m04.net_return_pct.min()), 2) if not t_m04.empty else None,
            "m04b_exit_reasons": ";".join(t_m04.exit_reason.astype(str).value_counts().head(5).index.tolist()) if not t_m04.empty else "",
            **analysis,
        }
        if kind == "top":
            bucket, owner = classify_top(row)
            row["miss_or_hit_status"] = "hit" if row["m04b_trade_count"] > 0 else "missed"
            row["primary_reason_bucket"] = bucket
            row["recommended_owner"] = owner
        else:
            flags = bottom_risk_flags(t_m04)
            row["miss_or_hit_status"] = "mis_entry" if row["m04b_trade_count"] > 0 else "not_traded"
            row["primary_reason_bucket"] = ";".join(flags)
            row["recommended_owner"] = "S04风险退出/诱多识别优先" if row["m04b_trade_count"] > 0 else "S01未交易，无需处理"
        rows.append(row)
    return pd.DataFrame(rows)


def reason_summary(df: pd.DataFrame, status: str | None = None, explode_flags: bool = False) -> pd.DataFrame:
    d = df if status is None else df[df.miss_or_hit_status == status]
    rows = []
    if explode_flags:
        items = []
        for _, r in d.iterrows():
            for flag in str(r.get("primary_reason_bucket") or "").split(";"):
                flag = flag.strip()
                if flag:
                    items.append({**r.to_dict(), "_reason": flag})
        d = pd.DataFrame(items)
        group_col = "_reason"
    else:
        group_col = "primary_reason_bucket"
    if d.empty:
        return pd.DataFrame(columns=["reason", "count", "avg_runup_pct", "avg_drawdown_pct", "symbols", "recommended_owner_top"])
    for bucket, g in d.groupby(group_col, dropna=False):
        rows.append({
            "reason": bucket,
            "count": int(len(g)),
            "avg_runup_pct": round(float(g.runup_pct.mean()), 2) if "runup_pct" in g else None,
            "avg_drawdown_pct": round(float(g.drawdown_pct.mean()), 2) if "drawdown_pct" in g else None,
            "symbols": ",".join(g.symbol.astype(str).head(8).tolist()),
            "recommended_owner_top": g.recommended_owner.mode().iloc[0] if not g.empty else "",
        })
    return pd.DataFrame(rows).sort_values("count", ascending=False)


def write_readme(out: Path, summary: Dict[str, Any], top_diag: pd.DataFrame, bottom_diag: pd.DataFrame, top_reason: pd.DataFrame, bottom_reason: pd.DataFrame) -> None:
    overview = pd.DataFrame([
        {
            "sample": "最强30",
            "count": summary["top30"]["count"],
            "discovered_count": summary["top30"]["discovered_count"],
            "m04b_trade_count": summary["top30"]["m04b_trade_hit_count"],
            "miss_or_mis_entry_count": summary["top30"]["missed_count"],
            "main_read": "只交易1只，主要漏在成交额硬门槛",
        },
        {
            "sample": "最弱30",
            "count": summary["bottom30"]["count"],
            "discovered_count": summary["bottom30"]["discovered_count"],
            "m04b_trade_count": summary["bottom30"]["m04b_mis_entry_count"],
            "miss_or_mis_entry_count": summary["bottom30"]["m04b_mis_entry_count"],
            "main_read": "误入3只，均有出货分/撤买/超大单回撤风险",
        },
    ])
    top_table = top_diag[["symbol", "name", "runup_pct", "runup_start_date", "runup_end_date", "candidate_count", "m04b_trade_count", "primary_reason_bucket", "recommended_owner"]]
    bottom_hit = bottom_diag[bottom_diag.miss_or_hit_status == "mis_entry"][["symbol", "name", "drawdown_pct", "drawdown_start_date", "drawdown_end_date", "m04b_trade_count", "m04b_worst_return_pct", "primary_reason_bucket"]]
    lines = [
        "# EXP-20260426-market-extreme-reverse-audit",
        "",
        "## 1. 问题",
        "",
        "从 2026-03-02 ~ 2026-04-24 市场最强/最弱 30 反推当前 S01-M04B 的发现层、入场过滤和风险识别问题。",
        "",
        "## 2. 假设",
        "",
        "- 最强 30 未覆盖，不一定都是 S01 失效；已涨过/无回调的样本应拆给 S02。",
        "- 最弱 30 被交易，更多是 S04 风险退出/诱多识别问题，而不是简单放宽或收紧 S01。",
        "",
        "## 3. 数据范围",
        "",
        f"- 市场极端样本：{summary['range']['start']} ~ {summary['range']['end']} 全市场。",
        "- 策略对比：S01-M04B-balanced-weak-launch-filter（旧 v1.4-balanced）既有全市场 Top10/日候选与交易。",
        "",
        "## 4. 样本口径",
        "",
        "- 最强30：区间内任意低点到后续高点最大波段涨幅 Top30。",
        "- 最弱30：区间内任意高点到后续低点最大回撤 Top30。",
        "- 发现：进入 S01 原始候选；实际交易：通过 M04B 过滤且形成回调确认后的交易。",
        "",
        "## 5. 规则/参数",
        "",
        "- 复用 S01-M04B：v1.3 挂单撤梯子过滤 + balanced 弱启动组合过滤。",
        "- 原因归因按锚点附近 setup、启动、回调，以及候选/交易记录综合判断。",
        "",
        "## 6. 核心结果",
        "",
        overview.to_markdown(index=False),
        "",
        "### 最强30 错过原因",
        "",
        top_reason.to_markdown(index=False),
        "",
        "### 最弱30 误入特征",
        "",
        bottom_reason.to_markdown(index=False),
        "",
        "### 最强30 明细",
        "",
        top_table.to_markdown(index=False),
        "",
        "### 最弱30 中被 M04B 交易的样本",
        "",
        bottom_hit.to_markdown(index=False) if not bottom_hit.empty else "无。",
        "",
        "## 7. 结论：继续观察，分拆优化",
        "",
        "- S01 优先改发现层：用相对成交额/换手/个股历史分位替代 2.5 亿硬门槛。",
        "- 已经涨过、无回调但继续上行的样本，不应强行放进 S01，拆给 S02 趋势中继。",
        "- 最弱30误入主要交给 S04：累计超大单回撤、撤买单相对放大、确认日出货分等做风险层。",
        "",
        "## 8. 输出文件",
        "",
        "- market_top30_runup.csv",
        "- market_bottom30_drawdown.csv",
        "- top30_strategy_diagnosis.csv",
        "- bottom30_strategy_diagnosis.csv",
        "- missed_top30_reason_summary.csv",
        "- hit_bottom30_reason_summary.csv",
        "- summary.json",
        "",
    ]
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2026-03-02")
    parser.add_argument("--end", default="2026-04-24")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--strategy-out", default=str(LEGACY_V14_OUT))
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    raw = load_atomic_daily_window(LOOKBACK, args.end)
    metrics = add_ma(compute_v2_metrics(raw))
    by_symbol = {s: g.sort_values("trade_date").reset_index(drop=True) for s, g in metrics.groupby("symbol", sort=False)}

    top, bottom = build_extremes(metrics, args.start, args.end)
    top.to_csv(out / "market_top30_runup.csv", index=False)
    bottom.to_csv(out / "market_bottom30_drawdown.csv", index=False)

    strategy_out = Path(args.strategy_out)
    candidates = pd.read_csv(strategy_out / "enriched_candidates.csv")
    trades = pd.read_csv(strategy_out / "all_mode_trades.csv")

    top_diag = diagnose(top, "top", candidates, trades, by_symbol)
    bottom_diag = diagnose(bottom, "bottom", candidates, trades, by_symbol)
    top_reason = reason_summary(top_diag, "missed")
    bottom_reason = reason_summary(bottom_diag, "mis_entry", explode_flags=True)

    top_diag.to_csv(out / "top30_strategy_diagnosis.csv", index=False)
    bottom_diag.to_csv(out / "bottom30_strategy_diagnosis.csv", index=False)
    top_reason.to_csv(out / "missed_top30_reason_summary.csv", index=False)
    bottom_reason.to_csv(out / "hit_bottom30_reason_summary.csv", index=False)

    summary = {
        "range": {"start": args.start, "end": args.end, "lookback": LOOKBACK},
        "stock_count": int(metrics.symbol.nunique()),
        "top30": {
            "count": int(len(top_diag)),
            "discovered_count": int((top_diag.candidate_count > 0).sum()),
            "m04b_trade_hit_count": int((top_diag.m04b_trade_count > 0).sum()),
            "missed_count": int((top_diag.m04b_trade_count == 0).sum()),
            "anchor_chain_passed_count": int((top_diag.stage_status == "anchor_chain_passed").sum()),
            "missed_reason_counts": top_reason.set_index("reason")["count"].to_dict(),
        },
        "bottom30": {
            "count": int(len(bottom_diag)),
            "discovered_count": int((bottom_diag.candidate_count > 0).sum()),
            "m04b_mis_entry_count": int((bottom_diag.m04b_trade_count > 0).sum()),
            "not_traded_count": int((bottom_diag.m04b_trade_count == 0).sum()),
            "hit_reason_counts": bottom_reason.set_index("reason")["count"].to_dict(),
        },
        "outputs": [
            "market_top30_runup.csv",
            "market_bottom30_drawdown.csv",
            "top30_strategy_diagnosis.csv",
            "bottom30_strategy_diagnosis.csv",
            "missed_top30_reason_summary.csv",
            "hit_bottom30_reason_summary.csv",
            "summary.json",
        ],
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_readme(out, summary, top_diag, bottom_diag, top_reason, bottom_reason)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
