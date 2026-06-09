#!/usr/bin/env python3
"""Build AI high-speed interconnect long-term trend tracking assets.

Outputs CSV + Markdown under:
- data/selection/long_term_trends/ai_interconnect
- docs/selection/long_term_trends/ai_interconnect

This is research tracking only. It does not modify application routing or UI.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from backend.app.core.config import RESEARCH_CURRENT_ROOT

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data/selection/long_term_trends/ai_interconnect"
DOC_DIR = ROOT / "docs/selection/long_term_trends/ai_interconnect"
MARKET_HEAT_ROOT = Path(RESEARCH_CURRENT_ROOT) / "market_heat"
FINE_HEAT_DB = MARKET_HEAT_ROOT / "fine_theme_heat_daily.db"
FINE_HEAT_CACHE_DIR = MARKET_HEAT_ROOT / "cache"
LOCAL_TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_RUN_DATE = "2026-05-11"

TOPIC_ID = "ai_interconnect"
TOPIC_NAME = "AI高速互联"

TREND_FORCE_800G_URL = "https://www.trendforce.com/presscenter/news/20260210-12919.html"
TREND_FORCE_CPO_URL = "https://www.trendforce.com/presscenter/news/20260304-12947.html"
TREND_FORCE_SERVER_URL = "https://www.trendforce.com/presscenter/news/20260415-13013.html"
TREND_FORCE_GLASS_URL = "https://insights.trendforce.com/p/glass-fiber-cloth-shortage"
NVIDIA_SILICON_PHOTONICS_URL = "https://www.nvidia.com/en-us/networking/products/silicon-photonics/"
NVIDIA_RUBIN_URL = "https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-Vera-Rubin-Opens-Agentic-AI-Frontier/default.aspx"
BROADCOM_Q1_URL = "https://investors.broadcom.com/node/63976/pdf"
DELLORO_SWITCH_URL = "https://www.prnewswire.com/news-releases/ai-back-end-switch-market-will-push-past-100-billion-by-2030-according-to-delloro-group-302678344.html"
CIGNAL_OFC_URL = "https://cignal.ai/2026/03/ofc-2026-show-report/"
AOI_16T_URL = "https://newsroom.ao-inc.com/news-releases/aoi-receives-first-volume-order-of-1-6t-data-center-transceivers-from-major-hyperscale-customer/"
MOLEX_224G_URL = "https://www.molex.com/en-us/news/molex-launches-impress-co-packaged-copper-solutions-scaling-near-asic-connectivity-innovations-to-meet-next-gen-data-rate-demands"

SOURCE_INNOLIGHT_Q1 = "https://finance.sina.com.cn/roll/2026-04-17/doc-inhuvkwu2095950.shtml"
SOURCE_EOPTOLINK_Q1 = "https://finance.sina.com.cn/jjxw/2026-04-23/doc-inhvpcuy3637737.shtml"
SOURCE_TFC_Q1 = "https://www.stcn.com/article/detail/3768057.html"
SOURCE_TFC_RISK = "https://www.nbd.com.cn/articles/2026-04-07/4328213.html"
SOURCE_ACCElINK_Q1 = "https://finance.sina.com.cn/stock/stockzmt/2026-05-08/doc-inhxfanc4113865.shtml"
SOURCE_YUANJIE_REPORT = "https://big5.sse.com.cn/site/cht/www.sse.com.cn/disclosure/listedinfo/announcement/c/new/2026-03-25/688498_20260325_ZGFR.pdf"
SOURCE_HUDIAN_Q1 = "https://www.stcn.com/article/detail/3781672.html"
SOURCE_VICTORY_Q1 = "https://www.stcn.com/article/detail/3851825.html"
SOURCE_SHENGYI_2025 = "https://finance.sina.com.cn/wm/2026-04-27/doc-inhvxhze9061304.shtml"
SOURCE_SHENGYI_CAPEX = "https://finance.sina.com.cn/stock/aigc/tzxm/2026-04-25/doc-inhvrtis4435835.shtml"
SOURCE_SHENNAN_Q1 = "https://finance.sina.com.cn/roll/2026-04-23/doc-inhvnxnu4907483.shtml"
SOURCE_SHENNAN_2025 = "https://www.nbd.com.cn/articles/2026-03-12/4290324.html"
SOURCE_WOER_2025 = "https://finance.sina.com.cn/roll/2026-03-31/doc-inhswxzu2341137.shtml"
SOURCE_WOER_INTERACTIVE = "https://www.nbd.com.cn/articles/2026-01-15/4222545.html"
SOURCE_DINGTONG_Q1 = "https://finance.sina.com.cn/stock/aiassist/yjbg/2026-04-15/doc-inhuqsku0732075.shtml"
SOURCE_DINGTONG_2025 = "https://stock.finance.sina.com.cn/stock/go.php/vReport_Show/kind/search/rptid/828381312700/index.phtml"
SOURCE_ZHAOLONG_PRODUCT = "https://www.zhaolong.com.cn/blog/article_2208"
SOURCE_ZHAOLONG_Q1 = "https://finance.sina.com.cn/stock/relnews/cn/2026-04-27/doc-inhvxxxa9057827.shtml"
SOURCE_LUXSHARE_2025 = "https://www.stcn.com/article/detail/3750930.html"
SOURCE_LUXSHARE_DC = "https://www.donews.com/news/detail/4/6533664.html"
SOURCE_FII_Q1 = "https://finance.sina.com.cn/jjxw/2026-04-28/doc-inhwaavz1621034.shtml"
SOURCE_UNIS_2025 = "https://static.cninfo.com.cn/finalpage/2026-04-15/1225101865.PDF"

HEAT_THEMES = [
    ("CPO概念", "光模块/CPO"),
    ("光通信模块", "光模块/CPO"),
    ("PCB", "PCB/高速板材/CCL"),
    ("印制电路板", "PCB/高速板材/CCL"),
    ("高带宽内存", "海外验证链"),
    ("通信线缆及配套", "铜缆/连接器"),
    ("铜缆高速连接", "铜缆/连接器"),
    ("通信网络设备及器件", "交换机/网络设备"),
    ("光纤概念", "光模块/CPO"),
]

DECISION_FIELDS = [
    "updated_at",
    "topic_id",
    "topic_name",
    "industry_trend_score",
    "industry_trend_max",
    "a_share_operability_score",
    "a_share_operability_max",
    "conclusion",
    "industry_status",
    "operability_state",
    "current_view",
    "block_reason",
    "next_trigger",
    "stage",
    "next_stage",
    "next_stage_conditions",
    "downgrade_conditions",
]

FACTOR_FIELDS = [
    "factor",
    "current_points",
    "max_points",
    "score_pct",
    "weight_pct",
    "status",
    "meaning",
    "logic",
    "score_rule",
    "watch_focus",
    "evidence_1_label",
    "evidence_1_value",
    "evidence_1_meaning",
    "evidence_2_label",
    "evidence_2_value",
    "evidence_2_meaning",
    "evidence_3_label",
    "evidence_3_value",
    "evidence_3_meaning",
    "source_name",
    "source_url",
]

COMPANY_RESEARCH_FIELDS = [
    "symbol",
    "name",
    "include_decision",
    "pool_tier",
    "branch",
    "business_summary",
    "trend_link",
    "profit_driver",
    "growth_space",
    "valuation_snapshot",
    "latest_validation",
    "key_risk",
    "next_data_to_watch",
    "action",
    "source_url",
]

BRANCH_CLUSTER_FIELDS = [
    "branch",
    "hotspot_cluster",
    "industry_logic",
    "candidate_companies",
    "entry_gate",
    "not_enter_gate",
    "current_view",
]

MARKET_HEAT_FIELDS = [
    "updated_at",
    "trade_date",
    "theme",
    "theme_group",
    "rank_today",
    "hot_score",
    "pct_change",
    "rank_prev",
    "rank_delta",
    "front_hits_5",
    "hot_hits_5",
    "watch_hits_5",
    "hot_hits_20",
    "watch_hits_20",
    "best_rank_20",
    "avg_hot_score_20",
    "lifecycle",
    "signal_state",
    "decision_use",
    "source",
]


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def fmt_score(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def pct(num: float, den: float) -> float:
    return round(num / den * 100, 1) if den else 0.0


def infer_heat_lifecycle(rank_today: int, hot_hits_20: int, watch_hits_20: int, rank_delta: int) -> str:
    if rank_today <= 20 and hot_hits_20 >= 4:
        return "长期主线/强回流"
    if rank_today <= 50 and hot_hits_20 >= 5:
        return "长期主线/热度回升"
    if rank_today <= 50 and rank_delta >= 80:
        return "退潮后回流"
    if rank_today > 100 and (hot_hits_20 >= 4 or watch_hits_20 >= 8):
        return "退潮警告"
    if rank_today <= 100 and watch_hits_20 >= 6:
        return "主线观察"
    return "旁路观察"


def infer_heat_signal(rank_today: int, hot_score: float, pct_change: float, hot_hits_20: int) -> str:
    if rank_today <= 20 and hot_score >= 85:
        return "强"
    if rank_today <= 50 and hot_score >= 78:
        return "回升"
    if rank_today > 100 and hot_hits_20 >= 4:
        return "退潮未坏"
    if pct_change >= 3:
        return "修复"
    return "观察"


def latest_heat_cache(run_date: str) -> Path | None:
    if not FINE_HEAT_CACHE_DIR.exists():
        return None
    exact = sorted(FINE_HEAT_CACHE_DIR.glob(f"fine_heat_snapshots_*_{run_date}_m5_80.json"))
    if exact:
        return exact[-1]
    candidates = sorted(FINE_HEAT_CACHE_DIR.glob("fine_heat_snapshots_*_m5_80.json"))
    usable: list[Path] = []
    for path in candidates:
        parts = path.stem.split("_")
        if len(parts) >= 6 and parts[4] <= run_date:
            usable.append(path)
    return usable[-1] if usable else (candidates[-1] if candidates else None)


def load_market_heat_from_cache(run_date: str, updated_at: str) -> tuple[list[dict[str, Any]], str]:
    cache_path = latest_heat_cache(run_date)
    if not cache_path:
        return [], ""
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    snapshots = payload.get("snapshots") or {}
    dates = sorted(date for date in snapshots if date <= run_date)
    if not dates:
        return [], str(cache_path)

    series_by_theme: dict[str, list[dict[str, Any]]] = {theme: [] for theme, _ in HEAT_THEMES}
    for trade_date in dates:
        items = snapshots.get(trade_date, {}).get("hot_top") or snapshots.get(trade_date, {}).get("sectors") or []
        for rank, item in enumerate(items, start=1):
            name = str(item.get("name") or item.get("sector_name") or "")
            if name not in series_by_theme:
                continue
            series_by_theme[name].append(
                {
                    "trade_date": trade_date,
                    "rank": rank,
                    "hot_score": float(item.get("hot_score") or 0),
                    "pct_change": float(item.get("pct_change") or 0),
                }
            )

    rows: list[dict[str, Any]] = []
    for theme, group in HEAT_THEMES:
        points = series_by_theme.get(theme) or []
        if not points:
            continue
        latest = points[-1]
        prev = points[-2] if len(points) >= 2 else {}
        recent5 = points[-5:]
        recent20 = points[-20:]
        rank_today = int(latest["rank"])
        rank_prev = int(prev.get("rank") or 0)
        rank_delta = rank_prev - rank_today if rank_prev else 0
        hot_hits_20 = sum(1 for row in recent20 if int(row["rank"]) <= 15)
        watch_hits_20 = sum(1 for row in recent20 if int(row["rank"]) <= 50)
        lifecycle = infer_heat_lifecycle(rank_today, hot_hits_20, watch_hits_20, rank_delta)
        signal_state = infer_heat_signal(rank_today, float(latest["hot_score"]), float(latest["pct_change"]), hot_hits_20)
        decision_use = {
            "光模块/CPO": "判断光模块/CPO主线是否从退潮转回流；只服务观察池动作，不替代公司研究。",
            "PCB/高速板材/CCL": "判断PCB/高速板材是否独立加强；重点看订单和毛利率能否继续兑现。",
            "铜缆/连接器": "判断短距铜缆、连接器是否从情绪映射转成订单兑现。",
            "交换机/网络设备": "判断AI交换机和以太网扩散是否传导到A股设备链。",
            "海外验证链": "作为AI服务器硬件强度共振指标，不单独等同于高速互联买点。",
        }.get(group, "观察主题热度变化。")
        rows.append(
            {
                "updated_at": updated_at,
                "trade_date": latest["trade_date"],
                "theme": theme,
                "theme_group": group,
                "rank_today": rank_today,
                "hot_score": round(float(latest["hot_score"]), 1),
                "pct_change": round(float(latest["pct_change"]), 2),
                "rank_prev": rank_prev or "",
                "rank_delta": rank_delta if rank_prev else "",
                "front_hits_5": sum(1 for row in recent5 if int(row["rank"]) <= 5),
                "hot_hits_5": sum(1 for row in recent5 if int(row["rank"]) <= 15),
                "watch_hits_5": sum(1 for row in recent5 if int(row["rank"]) <= 50),
                "hot_hits_20": hot_hits_20,
                "watch_hits_20": watch_hits_20,
                "best_rank_20": min(int(row["rank"]) for row in recent20),
                "avg_hot_score_20": round(sum(float(row["hot_score"]) for row in recent20) / len(recent20), 1),
                "lifecycle": lifecycle,
                "signal_state": signal_state,
                "decision_use": decision_use,
                "source": f"fine_heat_snapshots_cache; equivalent to /api/market_heat/fine_dashboard?days=63&pool_size=50; {cache_path}",
            }
        )
    rows.sort(key=lambda row: (int(row["rank_today"]), -float(row["hot_score"])))
    return rows, str(cache_path)


def load_market_heat_from_db(run_date: str, updated_at: str) -> tuple[list[dict[str, Any]], str]:
    if not FINE_HEAT_DB.exists():
        return [], ""
    theme_groups = dict(HEAT_THEMES)
    names = [theme for theme, _ in HEAT_THEMES]
    placeholders = ",".join("?" for _ in names)
    with sqlite3.connect(str(FINE_HEAT_DB), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        date_rows = conn.execute(
            "SELECT DISTINCT trade_date FROM fine_theme_heat_daily WHERE trade_date <= ? ORDER BY trade_date",
            (run_date,),
        ).fetchall()
        dates = [row["trade_date"] for row in date_rows][-63:]
        if not dates:
            return [], str(FINE_HEAT_DB)
        target_date = dates[-1]
        start_date = dates[0]
        rows_by_theme: dict[str, list[sqlite3.Row]] = {}
        for row in conn.execute(
            f"""
            SELECT trade_date, sector_name, hot_rank, hot_score, avg_return_1d
            FROM fine_theme_heat_daily
            WHERE trade_date BETWEEN ? AND ? AND sector_name IN ({placeholders})
            ORDER BY trade_date, hot_rank
            """,
            (start_date, target_date, *names),
        ):
            rows_by_theme.setdefault(str(row["sector_name"]), []).append(row)

    out: list[dict[str, Any]] = []
    for theme, points in rows_by_theme.items():
        if not points:
            continue
        latest = points[-1]
        prev = points[-2] if len(points) >= 2 else None
        recent5 = points[-5:]
        recent20 = points[-20:]
        rank_today = int(latest["hot_rank"])
        rank_prev = int(prev["hot_rank"]) if prev else 0
        rank_delta = rank_prev - rank_today if rank_prev else 0
        hot_hits_20 = sum(1 for row in recent20 if int(row["hot_rank"]) <= 15)
        watch_hits_20 = sum(1 for row in recent20 if int(row["hot_rank"]) <= 50)
        lifecycle = infer_heat_lifecycle(rank_today, hot_hits_20, watch_hits_20, rank_delta)
        signal_state = infer_heat_signal(rank_today, float(latest["hot_score"] or 0), float(latest["avg_return_1d"] or 0), hot_hits_20)
        out.append(
            {
                "updated_at": updated_at,
                "trade_date": latest["trade_date"],
                "theme": theme,
                "theme_group": theme_groups.get(theme, ""),
                "rank_today": rank_today,
                "hot_score": round(float(latest["hot_score"] or 0), 1),
                "pct_change": round(float(latest["avg_return_1d"] or 0), 2),
                "rank_prev": rank_prev or "",
                "rank_delta": rank_delta if rank_prev else "",
                "front_hits_5": sum(1 for row in recent5 if int(row["hot_rank"]) <= 5),
                "hot_hits_5": sum(1 for row in recent5 if int(row["hot_rank"]) <= 15),
                "watch_hits_5": sum(1 for row in recent5 if int(row["hot_rank"]) <= 50),
                "hot_hits_20": hot_hits_20,
                "watch_hits_20": watch_hits_20,
                "best_rank_20": min(int(row["hot_rank"]) for row in recent20),
                "avg_hot_score_20": round(sum(float(row["hot_score"] or 0) for row in recent20) / len(recent20), 1),
                "lifecycle": lifecycle,
                "signal_state": signal_state,
                "decision_use": "DB fallback; use for local heat confirmation when cache is unavailable.",
                "source": str(FINE_HEAT_DB),
            }
        )
    out.sort(key=lambda row: (int(row["rank_today"]), -float(row["hot_score"])))
    return out, str(FINE_HEAT_DB)


def build_market_heat(run_date: str, updated_at: str) -> list[dict[str, Any]]:
    rows, _source = load_market_heat_from_cache(run_date, updated_at)
    if rows:
        return rows
    rows, _source = load_market_heat_from_db(run_date, updated_at)
    return rows


def build_branch_clusters() -> list[dict[str, Any]]:
    return [
        {
            "branch": "光模块/CPO",
            "hotspot_cluster": "800G/1.6T光模块、硅光、LPO/CPO、光器件、光芯片",
            "industry_logic": "AI集群东西向流量上升，先拉动可插拔高速光模块，CPO是后续功耗和架构变量。",
            "candidate_companies": "中际旭创、新易盛、天孚通信、源杰科技、光迅科技",
            "entry_gate": "已有800G/1.6T批量交付、客户需求可见度强、毛利率没有被价格竞争破坏。",
            "not_enter_gate": "只停留在CPO概念或国产替代映射，缺少高端数通收入占比和订单兑现。",
            "current_view": "先放光模块龙头和关键器件，光芯片/国产链保留研究但不自动入池。",
        },
        {
            "branch": "PCB/高速板材/CCL",
            "hotspot_cluster": "AI服务器PCB、高速交换机板、高频高速覆铜板、低Dk玻纤布",
            "industry_logic": "速率升级提高层数、材料等级和信号完整性要求，订单和毛利率比题材标签更重要。",
            "candidate_companies": "沪电股份、胜宏科技、生益科技、深南电路",
            "entry_gate": "AI服务器/交换机板收入增长明确，材料涨价可转嫁，高端产能投放匹配订单。",
            "not_enter_gate": "业务质量好但高速互联增量被其他业务稀释，或估值已提前透支中报验证。",
            "current_view": "这是本轮除光模块外最强分支，保留沪电、胜宏、生益进入观察池。",
        },
        {
            "branch": "铜缆/连接器",
            "hotspot_cluster": "DAC/AEC、224G/448G连接器、高速通信线、背板/近ASIC连接",
            "industry_logic": "短距低功耗场景仍需要铜连接，关键是能否变成客户订单和收入，而不是泛连接器概念。",
            "candidate_companies": "沃尔核材、鼎通科技、兆龙互连、立讯精密",
            "entry_gate": "224G产品批量交付、448G进入客户验证，且高速通信线或连接器收入占比足够能影响利润。",
            "not_enter_gate": "收入体量小、客户未披露、或大公司中数据中心业务占比不足以驱动利润重估。",
            "current_view": "只让已出现高速通信线收入验证的沃尔核材进入高弹性观察，其余旁路。",
        },
        {
            "branch": "交换机/网络设备",
            "hotspot_cluster": "AI后端交换机、800G/1.6T交换机、网络设备、交换芯片",
            "industry_logic": "高速互联最终落在交换机端口速率和网络架构升级，但A股映射要区分设备订单和泛ICT估值。",
            "candidate_companies": "工业富联、紫光股份",
            "entry_gate": "800G以上交换机出货、CPO样机或AI网络订单能独立影响收入和利润。",
            "not_enter_gate": "只是企业网/运营商设备或AI服务器装配映射，利润率和订单持续性没有拆清。",
            "current_view": "该分支先做海外验证链和旁路观察，暂不放进核心观察池。",
        },
        {
            "branch": "海外验证链",
            "hotspot_cluster": "NVIDIA Rubin/Spectrum-X、Broadcom AI networking、Google TPU/OCS、海外1.6T订单",
            "industry_logic": "用海外客户架构和订单验证产业趋势，再回到A股公司确认谁有真实交付和利润弹性。",
            "candidate_companies": "工业富联、中际旭创、新易盛、天孚通信、沪电股份、胜宏科技",
            "entry_gate": "能从海外订单、客户指引、产品切换节奏直接验证A股公司的收入和毛利率。",
            "not_enter_gate": "只有海外概念映射，没有公司订单、客户认证或财报验证。",
            "current_view": "海外链不是独立买点，是筛选A股观察池的验证层。",
        },
    ]


def build_factor_scorecard() -> list[dict[str, Any]]:
    return [
        {
            "factor": "热点持续性/市场确认",
            "current_points": 13,
            "max_points": 16,
            "score_pct": pct(13, 16),
            "weight_pct": 16,
            "status": "热度回升但不追高",
            "meaning": "市场热度是资金是否愿意反复定价的确认项，不是产业逻辑本身。",
            "logic": "CPO、PCB、高带宽内存在近一个月反复进热区，说明市场承认AI高速互联主线；但热度只能决定观察动作，不能替代公司入池判断。",
            "score_rule": "近20日多个相关主题进入Top50且5月11日仍有主题回到Top50给高确认；若连续5日全部跌出Top100则降级。",
            "watch_focus": "CPO、PCB、印制电路板、光通信模块、高带宽内存的Top50命中数和退潮后回流速度。",
            "evidence_1_label": "本地热点",
            "evidence_1_value": "PCB#33、印制电路板#37、CPO#48",
            "evidence_1_meaning": "2026-05-11仍有热度回升，不是完全熄火",
            "evidence_2_label": "近20日持续",
            "evidence_2_value": "CPO/PCB/印制电路板多次Top50",
            "evidence_2_meaning": "主线反复出现，适合监控而非一次性研报",
            "evidence_3_label": "风险",
            "evidence_3_value": "光通信模块#139",
            "evidence_3_meaning": "部分光模块主题仍处退潮后修复阶段",
            "source_name": "local market heat cache",
            "source_url": "/api/market_heat/fine_dashboard?days=63&pool_size=50",
        },
        {
            "factor": "AI集群规模与带宽需求",
            "current_points": 18,
            "max_points": 20,
            "score_pct": pct(18, 20),
            "weight_pct": 20,
            "status": "强",
            "meaning": "高速互联需求来自GPU/ASIC集群规模扩大后的东西向流量，不是单个硬件缺货故事。",
            "logic": "Google TPU架构、NVIDIA Rubin/Spectrum-X以及AI服务器出货增长都指向更高带宽、更低延迟、更低功耗的互联需求。",
            "score_rule": "AI服务器增长、800G/1.6T升级和大客户架构同时确认则维持高确认；若CSP CapEx下修或AI服务器出货显著延迟则降级。",
            "watch_focus": "CSP CapEx、AI服务器出货、Rubin/GB300部署节奏、800G到1.6T切换速度。",
            "evidence_1_label": "AI服务器",
            "evidence_1_value": "2026年约+28% YoY",
            "evidence_1_meaning": "服务器需求底座仍在扩张",
            "evidence_2_label": "Google TPU",
            "evidence_2_value": "800G+光模块份额>60%",
            "evidence_2_meaning": "高速光互联正在成为AI数据中心标配",
            "evidence_3_label": "NVIDIA",
            "evidence_3_value": "Spectrum-X / Quantum-X800",
            "evidence_3_meaning": "网络与算力平台同步升级",
            "source_name": "TrendForce / NVIDIA",
            "source_url": f"{TREND_FORCE_800G_URL} | {TREND_FORCE_SERVER_URL} | {NVIDIA_RUBIN_URL}",
        },
        {
            "factor": "光模块/CPO订单与产品迭代",
            "current_points": 17,
            "max_points": 20,
            "score_pct": pct(17, 20),
            "weight_pct": 20,
            "status": "强但CPO仍需兑现",
            "meaning": "光模块是当前利润映射最直接环节，CPO是后续功耗和架构升级变量。",
            "logic": "800G及以上光模块进入大规模部署，1.6T开始出现订单和产品验证；CPO方向明确，但量产可靠性、成本和供应链切换还没完全证明。",
            "score_rule": "800G大规模出货、1.6T订单确认、CPO进入客户平台则维持强确认；若1.6T订单延后或CPO量产失败则降级。",
            "watch_focus": "800G/1.6T订单、硅光占比、CPO交换机出货时间、光模块厂毛利率是否被价格竞争压缩。",
            "evidence_1_label": "800G+份额",
            "evidence_1_value": "2026年>60%",
            "evidence_1_meaning": "高速光模块从增量变成主规格",
            "evidence_2_label": "1.6T订单",
            "evidence_2_value": "AOI获超2亿美元订单",
            "evidence_2_meaning": "1.6T从样品验证转向客户订单",
            "evidence_3_label": "CPO节奏",
            "evidence_3_value": "imminent but not fully proven",
            "evidence_3_meaning": "方向强，兑现仍需盯NVIDIA/TSMC供应推进",
            "source_name": "TrendForce / NVIDIA / AOI / Cignal AI",
            "source_url": f"{TREND_FORCE_800G_URL} | {NVIDIA_SILICON_PHOTONICS_URL} | {AOI_16T_URL} | {CIGNAL_OFC_URL}",
        },
        {
            "factor": "交换机/高速连接器/线缆传导",
            "current_points": 11,
            "max_points": 14,
            "score_pct": pct(11, 14),
            "weight_pct": 14,
            "status": "传导增强",
            "meaning": "AI高速互联不是只有光模块，还包括交换机、NIC、连接器、线缆和近ASIC互连。",
            "logic": "AI后端网络交换机从800G向1.6T升级，NVIDIA Spectrum-X和产业连接器方案证明传导链存在；但A股交换机映射要用订单和收入拆分验证。",
            "score_rule": "交换机端口速率升级、224G连接器产品、客户部署同时推进则维持强确认；若只有概念炒作没有订单或设计导入则降级。",
            "watch_focus": "AI后端交换机端口速率、224G/448G连接器量产、铜缆与光互联的边界变化。",
            "evidence_1_label": "交换机市场",
            "evidence_1_value": "AI后端交换机2030年>$100B",
            "evidence_1_meaning": "高速互联从模块扩展到网络设备",
            "evidence_2_label": "端口速率",
            "evidence_2_value": "800G -> 1600G -> 3200G",
            "evidence_2_meaning": "速率升级路径清晰",
            "evidence_3_label": "连接器",
            "evidence_3_value": "224Gbps PAM-4",
            "evidence_3_meaning": "近ASIC连接器/线缆仍有结构性需求",
            "source_name": "Dell'Oro / NVIDIA / Molex",
            "source_url": f"{DELLORO_SWITCH_URL} | {NVIDIA_RUBIN_URL} | {MOLEX_224G_URL}",
        },
        {
            "factor": "PCB/覆铜板/高速板材景气",
            "current_points": 14,
            "max_points": 16,
            "score_pct": pct(14, 16),
            "weight_pct": 16,
            "status": "强",
            "meaning": "高速板材决定高频高速信号完整性，是AI服务器、交换机和背板升级的实物约束。",
            "logic": "AI服务器和800G/1.6T交换机提升PCB层数、板材等级和低损耗材料要求；玻纤布、CCL等材料瓶颈强化了景气持续性。",
            "score_rule": "PCB交期、低Dk材料、AI服务器PCB订单和毛利率同步强则维持强确认；若原材料涨价不能转嫁或客户砍单则降级。",
            "watch_focus": "高阶PCB订单、M7/M8/M9材料切换、低Dk玻纤布供应、覆铜板涨价与毛利率传导。",
            "evidence_1_label": "PCB/CPU交期",
            "evidence_1_value": "近一年",
            "evidence_1_meaning": "核心零组件仍紧",
            "evidence_2_label": "玻纤布",
            "evidence_2_value": "产能缓解或到2027年中",
            "evidence_2_meaning": "上游材料短期难放量",
            "evidence_3_label": "技术升级",
            "evidence_3_value": "224G、M8/M9、24-40层",
            "evidence_3_meaning": "需求来自规格升级，不只是总量增长",
            "source_name": "TrendForce / company news",
            "source_url": f"{TREND_FORCE_SERVER_URL} | {TREND_FORCE_GLASS_URL} | {SOURCE_HUDIAN_Q1} | {SOURCE_VICTORY_Q1}",
        },
        {
            "factor": "海外龙头/客户资本开支验证",
            "current_points": 12,
            "max_points": 14,
            "score_pct": pct(12, 14),
            "weight_pct": 14,
            "status": "强",
            "meaning": "海外龙头与客户CapEx验证决定这是不是全球订单周期，而非A股局部题材。",
            "logic": "Broadcom AI收入、NVIDIA Rubin平台、Google OCS/TPU架构和海外1.6T订单共同验证高速互联投资仍在加速。",
            "score_rule": "客户CapEx、AI networking收入和大客户订单三项同时向上则维持强确认；若海外龙头财报转弱或客户延期则降级。",
            "watch_focus": "Broadcom AI networking指引、NVIDIA Rubin量产、Google/AWS/Microsoft网络架构订单、海外光模块厂订单。",
            "evidence_1_label": "Broadcom AI收入",
            "evidence_1_value": "Q1 FY26 $8.4B, +106% YoY",
            "evidence_1_meaning": "AI networking和定制加速器需求强",
            "evidence_2_label": "Q2指引",
            "evidence_2_value": "AI半导体$10.7B",
            "evidence_2_meaning": "海外龙头没有给出降温信号",
            "evidence_3_label": "客户架构",
            "evidence_3_value": "Google Apollo OCS / NVIDIA CPO",
            "evidence_3_meaning": "客户架构强化互联地位",
            "source_name": "Broadcom / NVIDIA / TrendForce",
            "source_url": f"{BROADCOM_Q1_URL} | {NVIDIA_RUBIN_URL} | {TREND_FORCE_800G_URL}",
        },
    ]


def build_chain_layers() -> list[dict[str, Any]]:
    return [
        {
            "order": 1,
            "segment": "需求源头",
            "layer": "CSP / AI工厂",
            "role": "决定集群规模和互联端口数",
            "key_indicator": "CSP CapEx、GPU/ASIC集群规模、AI服务器出货",
            "current_signal": "TrendForce预计2026年AI server出货约+28% YoY；NVIDIA Rubin面向AI工厂规模化部署。",
            "positive_signal": "CapEx继续上修，Rubin/GB300/ASIC服务器部署不延后。",
            "risk_signal": "CapEx下修、GPU/ASIC交付延迟、数据中心电力约束扩大。",
            "a_share_mapping": "全链条需求底座，用于验证而不是直接选股。",
            "status": "强",
        },
        {
            "order": 2,
            "segment": "网络架构",
            "layer": "Scale-up / Scale-out / Scale-across",
            "role": "把算力从单机扩成集群，拉动交换机、光模块、线缆",
            "key_indicator": "Spectrum-X、OCS、后端交换机端口速率",
            "current_signal": "800G端口已成为AI后端网络主流，Dell'Oro预计后续向1600G、3200G升级。",
            "positive_signal": "800G端口放量，1.6T交换机/光模块订单启动。",
            "risk_signal": "网络架构升级延后，客户继续消化400G/800G库存。",
            "a_share_mapping": "工业富联、紫光股份旁路观察；需要拆清AI网络订单和利润率。",
            "status": "传导增强",
        },
        {
            "order": 3,
            "segment": "光互联",
            "layer": "800G/1.6T光模块、硅光、CPO",
            "role": "最直接的带宽升级受益环节",
            "key_indicator": "800G+占比、1.6T订单、CPO量产节奏、硅光占比",
            "current_signal": "TrendForce预计800G及以上光模块2026年出货份额超过60%；NVIDIA CPO交换机计划2H26。",
            "positive_signal": "800G订单不掉速，1.6T开始批量，CPO可靠性和良率过关。",
            "risk_signal": "1.6T订单延后，CPO成本/可靠性不及预期，价格竞争压毛利。",
            "a_share_mapping": "中际旭创、新易盛、天孚通信进入观察池；源杰科技和光迅科技继续研究验证。",
            "status": "强",
        },
        {
            "order": 4,
            "segment": "电互联",
            "layer": "高速连接器、铜缆、近ASIC连接",
            "role": "短距、低功耗、近ASIC场景保留结构性需求",
            "key_indicator": "224G/448G连接器、DAC/AEC、背板/中板设计导入",
            "current_signal": "Molex推出224Gbps PAM-4近ASIC连接方案，铜缆高速连接本地热度仍有脉冲。",
            "positive_signal": "224G产品进入AI服务器/交换机量产设计。",
            "risk_signal": "铜缆只停留在主题交易，订单和毛利率不兑现。",
            "a_share_mapping": "沃尔核材进入高弹性观察；鼎通科技、兆龙互连、立讯精密先旁路。",
            "status": "观察偏强",
        },
        {
            "order": 5,
            "segment": "PCB/材料",
            "layer": "高速PCB、覆铜板、低Dk玻纤布",
            "role": "高频高速信号完整性和高层数板的材料瓶颈",
            "key_indicator": "PCB交期、AI服务器PCB收入、低Dk材料供应、毛利率",
            "current_signal": "TrendForce提示PCB/CPU交期拉长，低Dk玻纤布供给瓶颈可能延续至2027年中。",
            "positive_signal": "AI服务器/交换机PCB订单继续放量，材料涨价可转嫁。",
            "risk_signal": "上游材料涨价侵蚀利润，客户砍单或产能集中释放。",
            "a_share_mapping": "沪电股份、胜宏科技、生益科技进入观察池；深南电路保留质量观察。",
            "status": "强",
        },
        {
            "order": 6,
            "segment": "A股交易层",
            "layer": "观察池动作",
            "role": "决定当下是否值得跟踪，不决定行业成立",
            "key_indicator": "include_decision、pool_tier、订单/毛利率/客户验证、回撤承接",
            "current_signal": "本轮研究15家公司，7家进入观察池，其余保留在公司研究卡。",
            "positive_signal": "财报继续验证订单和毛利率，核心公司回撤不破并优于后排扩散。",
            "risk_signal": "后排扩散强于核心，利好不涨或放量长阴。",
            "a_share_mapping": "只统计include_decision为进入观察池的公司。",
            "status": "等待分歧确认",
        },
    ]


def build_industry_signal_log() -> list[dict[str, Any]]:
    return [
        {
            "date": "2026-02-10",
            "source": "TrendForce",
            "source_type": "industry_forecast",
            "indicator": "800G及以上光模块出货份额",
            "value": "2024年19.5% -> 2026年超过60%",
            "direction": "up",
            "affected_links": "光模块/硅光/CPO/高速PCB",
            "confidence": "high",
            "next_check": "2026-06-30",
            "source_url": TREND_FORCE_800G_URL,
            "notes": "确认高速光模块正从增量规格变成AI数据中心标准配置。",
        },
        {
            "date": "2026-02-10",
            "source": "TrendForce",
            "source_type": "customer_architecture",
            "indicator": "Google TPU / Apollo OCS架构",
            "value": "2026年Google 800G+光模块需求预计超过600万只",
            "direction": "up",
            "affected_links": "中际旭创/新易盛/OCS供应链",
            "confidence": "high",
            "next_check": "Google/供应链订单更新",
            "source_url": TREND_FORCE_800G_URL,
            "notes": "客户架构层面验证互联不是单纯题材。",
        },
        {
            "date": "2026-03-04",
            "source": "TrendForce",
            "source_type": "technology_iteration",
            "indicator": "Micro LED CPO功耗",
            "value": "1.6T光通信产品功耗可从约30W降至约1.6W",
            "direction": "up",
            "affected_links": "CPO/硅光/低功耗互联",
            "confidence": "medium",
            "next_check": "NVIDIA CPO平台量产节点",
            "source_url": TREND_FORCE_CPO_URL,
            "notes": "CPO的核心变量是功耗/成本/可靠性，不是简单替代光模块。",
        },
        {
            "date": "2026-03-04",
            "source": "Broadcom",
            "source_type": "earnings",
            "indicator": "Q1 FY26 AI revenue",
            "value": "$8.4B, +106% YoY; Q2 AI semiconductor revenue expected $10.7B",
            "direction": "up",
            "affected_links": "AI networking/交换机/高速SerDes",
            "confidence": "high",
            "next_check": "FY26 Q2 earnings",
            "source_url": BROADCOM_Q1_URL,
            "notes": "海外AI networking龙头财报验证需求仍强。",
        },
        {
            "date": "2026-03-09",
            "source": "Applied Optoelectronics",
            "source_type": "order",
            "indicator": "1.6T data center transceiver volume order",
            "value": "超过2亿美元，预计2026Q3开始发货、Q4完成",
            "direction": "up",
            "affected_links": "1.6T光模块/海外客户订单",
            "confidence": "medium",
            "next_check": "2026Q3 shipment",
            "source_url": AOI_16T_URL,
            "notes": "1.6T从样品/验证转向订单，但不是A股直接订单。",
        },
        {
            "date": "2026-03-16",
            "source": "NVIDIA",
            "source_type": "platform",
            "indicator": "Spectrum-X Ethernet Photonics / Rubin",
            "value": "CPO交换机、Spectrum-6、2H26伙伴可用",
            "direction": "up",
            "affected_links": "CPO/交换机/光模块/PCB",
            "confidence": "high",
            "next_check": "2026H2 platform availability",
            "source_url": NVIDIA_RUBIN_URL,
            "notes": "NVIDIA把网络、存储和算力一起定义为AI工厂平台。",
        },
        {
            "date": "2026-04-15",
            "source": "TrendForce",
            "source_type": "server_forecast",
            "indicator": "2026 AI server shipment growth",
            "value": "约+28% YoY",
            "direction": "up",
            "affected_links": "AI服务器/PCB/光模块/连接器",
            "confidence": "high",
            "next_check": "2026Q2 server forecast update",
            "source_url": TREND_FORCE_SERVER_URL,
            "notes": "下游需求底座强，但ASIC服务器验证和调试有延迟风险。",
        },
        {
            "date": "2026-04-30",
            "source": "TrendForce",
            "source_type": "material_shortage",
            "indicator": "低Dk玻纤布/高速CCL供给",
            "value": "关键产能缓解可能要到2027年中",
            "direction": "tight",
            "affected_links": "覆铜板/高速PCB/交换机板",
            "confidence": "medium",
            "next_check": "2026H2 material lead time",
            "source_url": TREND_FORCE_GLASS_URL,
            "notes": "PCB材料瓶颈给板材链景气提供持续性，但也要盯成本转嫁。",
        },
        {
            "date": "2026-05-11",
            "source": "local market heat",
            "source_type": "market_confirmation",
            "indicator": "本地细颗粒热点",
            "value": "高带宽内存#17、PCB#33、印制电路板#37、CPO#48",
            "direction": "rebound",
            "affected_links": "A股情绪/可操作窗口",
            "confidence": "medium",
            "next_check": "每日收盘",
            "source_url": "/api/market_heat/fine_dashboard?days=63&pool_size=50",
            "notes": "有热度回升，但不是追高买点；用于监控分歧后的承接。",
        },
    ]


def build_price_radar() -> list[dict[str, Any]]:
    return [
        {
            "category": "需求",
            "indicator": "AI server出货",
            "current_value": "2026年约+28% YoY",
            "direction": "up",
            "importance": "S",
            "signal_state": "强",
            "status": "已记录",
            "source": "TrendForce",
            "frequency": "季",
            "next_check": "2026Q2更新",
            "decision_use": "确认高速互联需求底座是否继续扩张",
            "source_url": TREND_FORCE_SERVER_URL,
        },
        {
            "category": "光模块",
            "indicator": "800G及以上光模块份额",
            "current_value": "2026年超过60%",
            "direction": "up",
            "importance": "S",
            "signal_state": "强",
            "status": "已记录",
            "source": "TrendForce",
            "frequency": "季/半年",
            "next_check": "2026-06-30",
            "decision_use": "验证800G是否仍是主规格，1.6T是否顺利接力",
            "source_url": TREND_FORCE_800G_URL,
        },
        {
            "category": "光模块",
            "indicator": "1.6T订单/发货",
            "current_value": "AOI获超2亿美元1.6T订单，预计2026Q3发货",
            "direction": "up",
            "importance": "A",
            "signal_state": "偏强",
            "status": "已记录",
            "source": "AOI",
            "frequency": "季",
            "next_check": "2026Q3",
            "decision_use": "判断1.6T是样品故事还是批量订单",
            "source_url": AOI_16T_URL,
        },
        {
            "category": "CPO",
            "indicator": "NVIDIA CPO交换机",
            "current_value": "Spectrum-X Ethernet Photonics计划2026H2可用",
            "direction": "up",
            "importance": "A",
            "signal_state": "方向强/兑现待跟",
            "status": "已记录",
            "source": "NVIDIA",
            "frequency": "季/发布会",
            "next_check": "2026H2",
            "decision_use": "CPO从概念升级到量产平台的关键确认",
            "source_url": NVIDIA_SILICON_PHOTONICS_URL,
        },
        {
            "category": "交换机",
            "indicator": "AI后端交换机端口速率",
            "current_value": "800G为主，2027年向1600G迁移",
            "direction": "up",
            "importance": "A",
            "signal_state": "偏强",
            "status": "已记录",
            "source": "Dell'Oro",
            "frequency": "半年/年",
            "next_check": "2026H2",
            "decision_use": "确认交换机/高速连接器/PCB传导强度",
            "source_url": DELLORO_SWITCH_URL,
        },
        {
            "category": "连接器",
            "indicator": "224G PAM-4近ASIC连接",
            "current_value": "Molex Impress已推出，面向AI和超大规模数据中心",
            "direction": "up",
            "importance": "B",
            "signal_state": "待订单验证",
            "status": "已记录",
            "source": "Molex",
            "frequency": "产品/订单",
            "next_check": "2026H2",
            "decision_use": "判断铜缆连接器是否有独立订单线索",
            "source_url": MOLEX_224G_URL,
        },
        {
            "category": "PCB/板材",
            "indicator": "PCB/CPU交期",
            "current_value": "部分核心零组件交期拉长至近一年",
            "direction": "tight",
            "importance": "S",
            "signal_state": "强",
            "status": "已记录",
            "source": "TrendForce",
            "frequency": "月/季",
            "next_check": "2026-06-30",
            "decision_use": "确认AI服务器和通用服务器对高端PCB的挤占",
            "source_url": TREND_FORCE_SERVER_URL,
        },
        {
            "category": "PCB/板材",
            "indicator": "低Dk玻纤布/高端CCL",
            "current_value": "瓶颈或延续至2027年中；NER/NEZ/Q-glass对应800G/1.6T",
            "direction": "tight",
            "importance": "S",
            "signal_state": "强",
            "status": "已记录",
            "source": "TrendForce",
            "frequency": "月/季",
            "next_check": "2026H2",
            "decision_use": "决定覆铜板涨价和高层板毛利率持续性",
            "source_url": TREND_FORCE_GLASS_URL,
        },
        {
            "category": "A股热度",
            "indicator": "CPO/PCB/光通信本地热区",
            "current_value": "2026-05-11：高带宽内存#17、PCB#33、印制电路板#37、CPO#48",
            "direction": "rebound",
            "importance": "A",
            "signal_state": "热度回升",
            "status": "已接入",
            "source": "local market heat",
            "frequency": "日",
            "next_check": "每日收盘",
            "decision_use": "只作为买点窗口和风险提示，不作为公司入池依据",
            "source_url": "/api/market_heat/fine_dashboard?days=63&pool_size=50",
        },
    ]


def build_company_research() -> list[dict[str, Any]]:
    return [
        {
            "symbol": "sz300308",
            "name": "中际旭创",
            "include_decision": "进入观察池",
            "pool_tier": "核心跟踪",
            "branch": "光模块/CPO",
            "business_summary": "全球高速数通光模块龙头，覆盖800G、1.6T、硅光和下一代光互连技术。",
            "trend_link": "AI集群带宽升级最直接映射在800G/1.6T光模块出货和硅光渗透。",
            "profit_driver": "高端光模块出货结构、硅光良率、海外大客户份额和毛利率稳定性共同驱动利润。",
            "growth_space": "主要来自订单可见度、产品迭代和客户份额；估值想象来自1.6T/3.2T与硅光平台延伸。",
            "valuation_snapshot": "龙头地位已被市场充分定价，适合跟踪订单和回撤承接，不适合把高景气直接等同于追高。",
            "latest_validation": "2026Q1营收和净利继续高增，市场报道指800G与1.6T需求同步提升、交付量快速增长。",
            "key_risk": "客户集中、价格竞争压毛利、CPO路线变化或1.6T订单节奏低于预期。",
            "next_data_to_watch": "1.6T排产、硅光占比、重点客户2026-2027需求指引、毛利率。",
            "action": "核心跟踪；只在订单/毛利继续验证且股价出现分歧承接时提高动作级别。",
            "source_url": SOURCE_INNOLIGHT_Q1,
        },
        {
            "symbol": "sz300502",
            "name": "新易盛",
            "include_decision": "进入观察池",
            "pool_tier": "核心跟踪",
            "branch": "光模块/CPO",
            "business_summary": "高速光模块供应商，具备800G以上规模量产和1.6T/LPO产品能力。",
            "trend_link": "光模块速率升级直接带来收入结构提升，是AI高速互联的核心映射之一。",
            "profit_driver": "800G/1.6T产品占比、规模交付效率、原材料保障和客户认证进度。",
            "growth_space": "来自订单放量、产品迭代、规模制造和海外客户份额提升。",
            "valuation_snapshot": "业绩高增已进入市场预期，估值对季度环比和库存变化敏感。",
            "latest_validation": "2025年营收和净利大幅增长，2026Q1销售收入同比提升，预付款大增显示备料和交付压力上升。",
            "key_risk": "存货可变现风险、汇兑/财务费用扰动、客户集中与产品降价。",
            "next_data_to_watch": "Q2收入环比、原材料预付款消化、1.6T出货占比、存货跌价准备。",
            "action": "核心跟踪；等待急涨后的缩量分歧或订单再确认。",
            "source_url": SOURCE_EOPTOLINK_Q1,
        },
        {
            "symbol": "sz300394",
            "name": "天孚通信",
            "include_decision": "进入观察池",
            "pool_tier": "高弹性观察",
            "branch": "光模块/CPO",
            "business_summary": "光无源器件和精密光器件平台，供应高速光模块所需关键组件。",
            "trend_link": "高速光模块升级会拉动透镜阵列、隔离器、光引擎相关器件和CPO配套需求。",
            "profit_driver": "高速器件订单、产能利用率、产品结构升级和战略客户需求响应速度。",
            "growth_space": "来自1.6T光引擎配套、CPO器件、海外产能和产品迭代。",
            "valuation_snapshot": "不是整机模块龙头，估值更依赖高端器件份额和毛利率验证。",
            "latest_validation": "2026Q1净利同比增长，市场报道提到AI驱动高速光器件需求旺盛和1.6T光引擎规模量产。",
            "key_risk": "前五大客户集中度高，光通信元器件毛利率已有下滑压力。",
            "next_data_to_watch": "高端器件毛利率、CPO配套订单、泰国产能爬坡、客户集中度变化。",
            "action": "进入高弹性观察；跟随光模块龙头验证，不单独按题材追涨。",
            "source_url": f"{SOURCE_TFC_Q1} | {SOURCE_TFC_RISK}",
        },
        {
            "symbol": "sh688498",
            "name": "源杰科技",
            "include_decision": "暂不进入",
            "pool_tier": "高弹性观察",
            "branch": "光模块/CPO",
            "business_summary": "高速光芯片和激光器供应商，向数据中心和光通信链条提供上游芯片。",
            "trend_link": "800G/1.6T升级提高对高速光芯片、CW光源和硅光配套的要求。",
            "profit_driver": "高毛利数据中心产品收入占比、客户认证、良率和规模出货。",
            "growth_space": "来自国产上游替代、硅光CW光源、产品迭代和客户导入。",
            "valuation_snapshot": "弹性强但验证链更长，容易被上游国产替代叙事提前定价。",
            "latest_validation": "公告材料显示数据中心业务收入提升，50G/100G/CW光源等产品线持续布局。",
            "key_risk": "客户导入慢、良率和量产能力未充分验证，收入体量仍小于光模块龙头。",
            "next_data_to_watch": "数据中心收入占比、重点客户认证、CW光源批量订单、毛利率。",
            "action": "保留研究卡；等数据中心订单和良率验证后再决定是否入池。",
            "source_url": SOURCE_YUANJIE_REPORT,
        },
        {
            "symbol": "sz002281",
            "name": "光迅科技",
            "include_decision": "旁路观察",
            "pool_tier": "间接受益",
            "branch": "光模块/CPO",
            "business_summary": "光模块、光器件和光芯片国产供应链平台型公司。",
            "trend_link": "受益于800G/1.6T光模块和CPO器件国产化，但与海外AI大客户链条的直接利润弹性需拆分。",
            "profit_driver": "高端数通产品占比、国产客户突破、光芯片自研和利润率修复。",
            "growth_space": "来自国产替代、CPO配套研发和高速光模块产品放量。",
            "valuation_snapshot": "更偏国产链映射，若高端AI交付节奏不及龙头，估值弹性会弱化。",
            "latest_validation": "2026Q1收入和净利增长，报道提到400G/800G批量出货和1.6T产品布局。",
            "key_risk": "高端AI数通放量节奏、盈利能力和海外客户份额不如第一梯队清晰。",
            "next_data_to_watch": "800G/1.6T收入占比、CPO器件订单、国产客户毛利率。",
            "action": "旁路观察；只在国产AI网络订单明确时升级。",
            "source_url": SOURCE_ACCElINK_Q1,
        },
        {
            "symbol": "sz002463",
            "name": "沪电股份",
            "include_decision": "进入观察池",
            "pool_tier": "核心跟踪",
            "branch": "PCB/高速板材/CCL",
            "business_summary": "高端PCB制造商，重点覆盖AI服务器、高速交换机和汽车电子等场景。",
            "trend_link": "AI服务器和高速交换机提升PCB层数、材料等级和订单价值。",
            "profit_driver": "高速运算服务器PCB订单、产品结构、产能利用率和汇率影响。",
            "growth_space": "来自订单放量、高阶产品占比、产能扩张和客户份额。",
            "valuation_snapshot": "市场已把AI PCB中军属性计入估值，下一阶段看订单和毛利率是否继续兑现。",
            "latest_validation": "2026Q1业绩大幅增长，公告口径指受益于高速运算服务器和AI新兴计算场景PCB需求。",
            "key_risk": "高端材料成本、汇兑损失、客户拉货节奏和产能释放不匹配。",
            "next_data_to_watch": "AI服务器/交换机PCB收入、毛利率、在建产能投产、汇兑扰动。",
            "action": "核心跟踪；PCB分支首选，等回踩或新增订单验证。",
            "source_url": SOURCE_HUDIAN_Q1,
        },
        {
            "symbol": "sz300476",
            "name": "胜宏科技",
            "include_decision": "进入观察池",
            "pool_tier": "高弹性观察",
            "branch": "PCB/高速板材/CCL",
            "business_summary": "PCB厂商，覆盖AI服务器、高多层板、HDI和全球化产能布局。",
            "trend_link": "AI服务器、高速互联和GPU模块提升高多层板与高端HDI需求。",
            "profit_driver": "AI/HPC PCB收入占比、高层板产品结构、产能扩张和交付效率。",
            "growth_space": "来自高多层板订单、产品迭代、海外募资后产能和份额提升。",
            "valuation_snapshot": "弹性大但波动也大，港股募资和高景气已经被充分交易，需要业绩继续跟上。",
            "latest_validation": "2026Q1营收和净利增长，市场报道强调AI PCB龙头属性及H股募资支持全球产能布局。",
            "key_risk": "扩产后利用率、客户集中、原材料成本和高位交易拥挤。",
            "next_data_to_watch": "AI/HPC收入占比、100层以上产品、募资用途落地、毛利率。",
            "action": "高弹性观察；只在业绩和订单继续验证时保留，避免把涨幅当逻辑。",
            "source_url": SOURCE_VICTORY_Q1,
        },
        {
            "symbol": "sh600183",
            "name": "生益科技",
            "include_decision": "进入观察池",
            "pool_tier": "核心跟踪",
            "branch": "PCB/高速板材/CCL",
            "business_summary": "覆铜板和电子材料龙头，覆盖高频高速覆铜板、封装基材和PCB产业链上游。",
            "trend_link": "高速交换机和AI服务器升级推高M7/M8/M9等高速材料需求，低Dk玻纤布瓶颈强化景气。",
            "profit_driver": "覆铜板销量、售价、产品结构升级和涨价传导能力。",
            "growth_space": "来自高性能覆铜板项目、AI服务器高频高速材料、价格和份额提升。",
            "valuation_snapshot": "材料链景气被持续重估，关键不是题材纯度而是涨价能否转成利润。",
            "latest_validation": "2025年营收和净利高增，并公告约52亿元高性能覆铜板项目，产品面向AI服务器等领域。",
            "key_risk": "原材料涨价不能完全转嫁、扩产周期长、下游砍单导致库存压力。",
            "next_data_to_watch": "M7/M8/M9材料认证、覆铜板毛利率、涨价落地、高性能项目节奏。",
            "action": "核心跟踪；作为PCB材料分支锚点保留。",
            "source_url": f"{SOURCE_SHENGYI_2025} | {SOURCE_SHENGYI_CAPEX}",
        },
        {
            "symbol": "sz002916",
            "name": "深南电路",
            "include_decision": "暂不进入",
            "pool_tier": "间接受益",
            "branch": "PCB/高速板材/CCL",
            "business_summary": "高端PCB、封装基板和电子装联平台型公司，业务质量较高。",
            "trend_link": "AI服务器、高速交换机和光模块带动高端PCB需求，公司有数据中心和通信PCB映射。",
            "profit_driver": "PCB业务收入、毛利率、产能瓶颈缓解和封装基板稼动率。",
            "growth_space": "来自数据中心PCB、通信板、封装基板和国产算力链条。",
            "valuation_snapshot": "质量中军属性强，但与本主题的边际弹性弱于沪电和胜宏，适合等更清晰的订单拆分。",
            "latest_validation": "2026Q1营收和净利增长，2025年PCB业务受益AI算力基础设施和高速交换机需求。",
            "key_risk": "产能瓶颈、外协费用、封装基板周期和多业务稀释高速互联弹性。",
            "next_data_to_watch": "数据中心PCB收入、通信PCB订单、封装基板稼动率、毛利率。",
            "action": "保留研究卡；当前不占观察池名额，等数据中心收入拆分更清晰。",
            "source_url": f"{SOURCE_SHENNAN_Q1} | {SOURCE_SHENNAN_2025}",
        },
        {
            "symbol": "sz002130",
            "name": "沃尔核材",
            "include_decision": "进入观察池",
            "pool_tier": "高弹性观察",
            "branch": "铜缆/连接器",
            "business_summary": "电子材料、通信线缆、电力和新能源业务并行，高速通信线是AI数据中心增量业务。",
            "trend_link": "短距高速互联仍需要DAC/AEC和224G/448G高速通信线，AI集群扩容带来铜缆需求。",
            "profit_driver": "高速通信线收入、224G批量交付、448G客户验证和设备产能。",
            "growth_space": "来自订单放量、产品迭代、客户渗透率和高速通信线收入占比提升。",
            "valuation_snapshot": "不是纯互联公司，但高速通信线已出现收入验证，可作为铜缆分支弹性观察。",
            "latest_validation": "2025年高速通信线产品持续交付，报道提到224G占比较高、448G样品交由重点客户验证。",
            "key_risk": "传统业务稀释、客户和订单透明度不足、铜缆热度退潮快。",
            "next_data_to_watch": "高速通信线收入占比、224G/448G订单、产能利用率、毛利率。",
            "action": "进入高弹性观察；只作为铜缆分支代表，不扩成泛材料池。",
            "source_url": f"{SOURCE_WOER_2025} | {SOURCE_WOER_INTERACTIVE}",
        },
        {
            "symbol": "sh688668",
            "name": "鼎通科技",
            "include_decision": "暂不进入",
            "pool_tier": "高弹性观察",
            "branch": "铜缆/连接器",
            "business_summary": "通信连接器精密组件和汽车连接器厂商，布局高速连接器与液冷I/O连接器。",
            "trend_link": "AI服务器和智算中心需要224G/448G高速连接器及散热配套。",
            "profit_driver": "224G规模量产、448G试样、液冷I/O连接器和核心客户导入。",
            "growth_space": "来自产品迭代、客户导入和高速连接器收入占比提升。",
            "valuation_snapshot": "弹性强，但公司体量和客户验证信息仍需要跟踪，暂不与已兑现收入的铜缆标的同列。",
            "latest_validation": "2026Q1营收和净利增长，研报与年报材料提到224G规模量产和448G研发试样。",
            "key_risk": "客户导入节奏、规模量产稳定性、单季费用扰动和订单透明度。",
            "next_data_to_watch": "224G/448G订单、液冷连接器客户、通信连接器毛利率、现金流。",
            "action": "保留研究卡；等高速连接器收入拆分和客户验证后再考虑入池。",
            "source_url": f"{SOURCE_DINGTONG_Q1} | {SOURCE_DINGTONG_2025}",
        },
        {
            "symbol": "sz300913",
            "name": "兆龙互连",
            "include_decision": "旁路观察",
            "pool_tier": "题材映射",
            "branch": "铜缆/连接器",
            "business_summary": "数据电缆、专用电缆、连接产品和光互联解决方案供应商。",
            "trend_link": "AI服务器高速DAC、400G/800G/1.6T连接方案和数据中心布线属于高速互联配套。",
            "profit_driver": "高速互连业务收入、数据中心客户突破、产品结构和毛利率。",
            "growth_space": "来自高速DAC、数据中心中高端光布线、海外市场和产品迭代。",
            "valuation_snapshot": "体量较小，主题弹性容易领先财报验证，当前更适合作为旁路样本。",
            "latest_validation": "公司官网披露AI服务器高速DAC方案，2026Q1净利同比增长。",
            "key_risk": "收入规模小、毛利率波动、客户和订单披露不足。",
            "next_data_to_watch": "高速互连业务收入占比、400G/800G/1.6T方案订单、毛利率。",
            "action": "旁路观察；不纳入观察池，等收入拆分。",
            "source_url": f"{SOURCE_ZHAOLONG_PRODUCT} | {SOURCE_ZHAOLONG_Q1}",
        },
        {
            "symbol": "sz002475",
            "name": "立讯精密",
            "include_decision": "旁路观察",
            "pool_tier": "间接受益",
            "branch": "铜缆/连接器",
            "business_summary": "消费电子、汽车、通信与数据中心综合制造平台，覆盖连接器、光模块、液冷、电源和整机。",
            "trend_link": "高速铜缆、光模块、液冷和数据中心业务都能映射AI高速互联，但公司收入结构更宽。",
            "profit_driver": "通信与数据中心收入、重点客户认证、铜光高速互联模组和液冷产品批量导入。",
            "growth_space": "来自数据中心业务扩张、产品矩阵和客户平台化合作。",
            "valuation_snapshot": "大市值综合平台，AI高速互联不是唯一利润主线，入池会稀释主题判断。",
            "latest_validation": "2025年通信与数据中心业务增长，报道提到800G硅光模块量产、1.6T验证和224G高速铜缆量产。",
            "key_risk": "消费电子周期、原材料和汇率扰动、数据中心业务占比不足以驱动整体利润重估。",
            "next_data_to_watch": "数据中心收入占比、铜光互联订单、液冷导入、毛利率。",
            "action": "旁路观察；作为产业宽度验证，不进入窄主题观察池。",
            "source_url": f"{SOURCE_LUXSHARE_2025} | {SOURCE_LUXSHARE_DC}",
        },
        {
            "symbol": "sh601138",
            "name": "工业富联",
            "include_decision": "旁路观察",
            "pool_tier": "间接受益",
            "branch": "交换机/网络设备",
            "business_summary": "AI服务器、云计算设备和通信网络设备制造平台，服务海外云厂商和品牌客户。",
            "trend_link": "AI服务器机柜、800G以上高速交换机和CPO样机是海外AI互联需求的重要验证。",
            "profit_driver": "AI GPU/ASIC服务器出货、800G以上交换机出货、自动化交付效率和利润率改善。",
            "growth_space": "来自海外AI服务器订单、交换机产品升级和CPO样机导入。",
            "valuation_snapshot": "验证强但利润率和主题纯度低于光模块/PCB，适合作海外验证链旁路。",
            "latest_validation": "2026Q1营收和净利增长，报道提到AI GPU机柜、AI ASIC服务器和800G以上交换机出货高增，CPO全光交换机样机开始出货。",
            "key_risk": "装配制造利润率低、客户采购模式变化、AI服务器收入高但互联利润弹性不易拆分。",
            "next_data_to_watch": "800G以上交换机收入、CPO样机量产、AI服务器毛利率、客户订单模式。",
            "action": "旁路观察；用于验证海外AI硬件链，不放入窄口径观察池。",
            "source_url": SOURCE_FII_Q1,
        },
        {
            "symbol": "sz000938",
            "name": "紫光股份",
            "include_decision": "暂不进入",
            "pool_tier": "间接受益",
            "branch": "交换机/网络设备",
            "business_summary": "新华三为核心的网络设备、服务器、存储、云与安全产品平台。",
            "trend_link": "数据中心交换机和AI服务器能映射AI网络建设，但更偏国内ICT设备平台。",
            "profit_driver": "新华三网络设备收入、数据中心交换机份额、AI服务器订单和利润率。",
            "growth_space": "来自国内AI算力建设、企业网升级和数据中心交换机份额。",
            "valuation_snapshot": "设备平台属性强，AI高速互联的利润弹性尚未拆清，不应和光模块/PCB同池比较。",
            "latest_validation": "2025年报摘要显示公司在企业网交换机、以太网交换机和数据中心交换机市场份额较高。",
            "key_risk": "政企/运营商周期、服务器利润率、AI网络订单披露不足。",
            "next_data_to_watch": "AI交换机订单、数据中心交换机收入、新华三利润率、国内算力采购节奏。",
            "action": "保留研究卡；等AI交换机订单独立验证后再评估。",
            "source_url": SOURCE_UNIS_2025,
        },
    ]


def build_data_source_matrix() -> list[dict[str, Any]]:
    return [
        {
            "module": "本地热点",
            "indicator": "细颗粒主题排名、Top50命中、退潮/回流",
            "source": "/api/market_heat/fine_dashboard?days=63&pool_size=50 + local cache",
            "frequency": "日",
            "method": "脚本读取fine_heat_snapshots_cache，缺失时回退SQLite",
            "status": "已接入",
            "next_step": "每日收盘刷新ai_interconnect_market_heat",
        },
        {
            "module": "产业分支",
            "indicator": "光模块/CPO、PCB/高速板材/CCL、铜缆/连接器、交换机/网络设备、海外验证链",
            "source": "行业资料 + 本地主题热度 + 公司公告",
            "frequency": "周/事件",
            "method": "先拆热点聚类，再把公司放入分支验证",
            "status": "已建立",
            "next_step": "每次主题扩散时先判断分支，而不是先给公司排序",
        },
        {
            "module": "光模块需求",
            "indicator": "800G+份额、Google TPU光模块需求、1.6T订单",
            "source": "TrendForce / AOI / 公司公告",
            "frequency": "月/季",
            "method": "半结构化记录",
            "status": "已记录",
            "next_step": "补800G/1.6T连续订单与价格口径",
        },
        {
            "module": "CPO进展",
            "indicator": "NVIDIA CPO交换机、Cignal AI OFC反馈、功耗/可靠性",
            "source": "NVIDIA / Cignal AI / TrendForce",
            "frequency": "发布会/季",
            "method": "人工更新关键节点",
            "status": "已记录",
            "next_step": "2026H2跟踪Spectrum-X Ethernet Photonics实际交付",
        },
        {
            "module": "交换机/连接器",
            "indicator": "AI后端交换机端口速率、224G/448G连接器、DAC/AEC",
            "source": "Dell'Oro / Molex / NVIDIA / 公司公告",
            "frequency": "季/半年",
            "method": "按订单、收入占比、客户验证拆分公司",
            "status": "已记录",
            "next_step": "补国内交换机/连接器订单映射，避免泛概念",
        },
        {
            "module": "PCB/高速板材",
            "indicator": "PCB交期、低Dk玻纤布、AI服务器PCB收入、覆铜板涨价",
            "source": "TrendForce / 公司年报与公告 / 主流财经新闻",
            "frequency": "月/季",
            "method": "按订单、毛利率、材料传导验证",
            "status": "已记录",
            "next_step": "中报后刷新沪电/胜宏/生益/深南的AI收入和毛利率",
        },
        {
            "module": "A股公司研究卡",
            "indicator": "include_decision、pool_tier、branch、利润驱动、验证点、下一步动作",
            "source": "公司公告/年报/一季报 + 主流财经新闻",
            "frequency": "周/财报",
            "method": "文字研究卡；只有include_decision为进入观察池才写入观察池",
            "status": "已重做",
            "next_step": "持续保留未入池公司，不把研究样本误当观察池",
        },
    ]


def build_tracking_tasks() -> list[dict[str, Any]]:
    return [
        {
            "task": "每日本地热度",
            "priority": "S",
            "status": "已接入",
            "next_check": "每日收盘",
            "target": "CPO、光通信模块、PCB、印制电路板、高带宽内存、铜缆高速连接",
            "upgrade_use": "核心主题退潮后重新进入Top50，且核心票缩量承接",
            "downgrade_use": "连续5日全部跌出Top100，或后排补涨强于核心",
        },
        {
            "task": "800G/1.6T订单",
            "priority": "S",
            "status": "半结构化接入",
            "next_check": "2026Q2/Q3订单更新",
            "target": "中际旭创、新易盛、天孚通信、海外光模块厂",
            "upgrade_use": "1.6T批量订单与出货时间明确，毛利率不下滑",
            "downgrade_use": "订单延后、客户砍单、价格竞争导致毛利率下修",
        },
        {
            "task": "CPO量产验证",
            "priority": "A",
            "status": "待2026H2",
            "next_check": "2026H2",
            "target": "NVIDIA Spectrum-X Ethernet Photonics、CPO供应链",
            "upgrade_use": "CPO交换机实际交付，可靠性/成本被客户接受",
            "downgrade_use": "CPO量产延迟或客户继续只采用可插拔光模块",
        },
        {
            "task": "PCB/高速板材订单和毛利率",
            "priority": "S",
            "status": "待中报",
            "next_check": "2026中报/业绩预告",
            "target": "沪电股份、胜宏科技、深南电路、生益科技",
            "upgrade_use": "AI服务器/交换机PCB收入占比提升，材料涨价可转嫁",
            "downgrade_use": "材料涨价侵蚀利润，扩产晚于订单或客户拉货放缓",
        },
        {
            "task": "铜缆/连接器传导",
            "priority": "A",
            "status": "待订单",
            "next_check": "2026Q2-Q3",
            "target": "沃尔核材、鼎通科技、兆龙互连、立讯精密",
            "upgrade_use": "224G/448G产品批量订单或明确客户导入，且收入占比足够影响利润",
            "downgrade_use": "只在主题热度里扩散，没有收入占比和订单支撑",
        },
        {
            "task": "交换机/海外验证链",
            "priority": "S",
            "status": "已记录",
            "next_check": "Broadcom/NVIDIA/工业富联/紫光股份下一次财报",
            "target": "Broadcom AI networking、NVIDIA networking、工业富联800G交换机、紫光新华三AI网络",
            "upgrade_use": "AI networking指引继续上修，800G/CPO交换机订单能拆到公司收入",
            "downgrade_use": "AI networking收入降速、客户部署延期或A股公司只剩泛设备映射",
        },
    ]


def build_decision_summary(
    run_date: str,
    updated_at: str,
    factor_rows: list[dict[str, Any]],
    watchlist_rows: list[dict[str, Any]],
    research_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    industry_score = float(sum(float(row["current_points"]) for row in factor_rows))
    industry_max = float(sum(float(row["max_points"]) for row in factor_rows))
    branch_count = len({row["branch"] for row in watchlist_rows})
    research_count = len(research_rows)
    watch_count = len(watchlist_rows)
    a_share_operability = 46.0 if watch_count >= 5 and branch_count >= 3 else 40.0
    return {
        "updated_at": updated_at,
        "topic_id": TOPIC_ID,
        "topic_name": TOPIC_NAME,
        "industry_trend_score": fmt_score(industry_score),
        "industry_trend_max": fmt_score(industry_max),
        "a_share_operability_score": fmt_score(a_share_operability),
        "a_share_operability_max": "100",
        "conclusion": "值得跟踪 / 先研究后入池",
        "industry_status": "行业趋势强",
        "operability_state": "观察池已收敛，等待分歧确认",
        "current_view": f"AI高速互联先拆成光模块/CPO、PCB/高速板材/CCL、铜缆/连接器、交换机/网络设备、海外验证链；本轮研究{research_count}家公司，只有{watch_count}家进入观察池。",
        "block_reason": "核心链条拥挤且估值已反映高景气，不能用统一分数制造精确感；必须继续用订单、毛利率、客户验证和回撤承接决定动作。",
        "next_trigger": "CPO/PCB/光模块核心主题连续2-3日回到Top50，且观察池公司出现订单、毛利率或客户份额的新增验证。",
        "stage": "价格热度回流 / 公司研究卡重建",
        "next_stage": "订单/财报验证期",
        "next_stage_conditions": "1.6T批量订单确认；NVIDIA CPO平台2026H2按期交付；沪电/胜宏/生益等AI服务器PCB和高速板材收入、毛利率继续上修；铜缆连接器出现收入占比验证。",
        "downgrade_conditions": "相关热点连续5日跌出Top100；海外AI networking指引下修；1.6T或CPO量产延期；PCB材料涨价不能转嫁；观察池公司财报验证低于叙事。",
    }


def build_score_history(run_date: str, updated_at: str, decision: dict[str, Any]) -> list[dict[str, Any]]:
    path = DATA_DIR / "ai_interconnect_score_history.csv"
    rows = [
        row
        for row in read_csv(path)
        if row.get("date", "") < run_date
    ]
    rows.append(
        {
            "date": run_date,
            "updated_at": updated_at,
            "topic_id": TOPIC_ID,
            "topic_name": TOPIC_NAME,
            "industry_trend_score": decision["industry_trend_score"],
            "industry_trend_max": decision["industry_trend_max"],
            "a_share_operability_score": decision["a_share_operability_score"],
            "a_share_operability_max": decision["a_share_operability_max"],
            "conclusion": decision["conclusion"],
            "industry_status": decision["industry_status"],
            "operability_state": decision["operability_state"],
            "stage": decision["stage"],
            "notes": "公司池改为研究卡：先拆产业分支，再决定include_decision；只有进入观察池的公司才计入watchlist。",
        }
    )
    rows.sort(key=lambda row: row.get("date", ""))
    return rows


def markdown_table(rows: list[dict[str, Any]], headers: list[tuple[str, str]], limit: int | None = None) -> list[str]:
    use_rows = rows[:limit] if limit else rows
    lines = [
        "| " + " | ".join(label for label, _key in headers) + " |",
        "| " + " | ".join("---" for _label, _key in headers) + " |",
    ]
    for row in use_rows:
        values = [str(row.get(key, "")).replace("|", "/") for _label, key in headers]
        lines.append("| " + " | ".join(values) + " |")
    return lines


def build_report(
    run_date: str,
    decision: dict[str, Any],
    branch_rows: list[dict[str, Any]],
    factor_rows: list[dict[str, Any]],
    market_heat_rows: list[dict[str, Any]],
    watchlist_rows: list[dict[str, Any]],
    research_rows: list[dict[str, Any]],
    price_radar_rows: list[dict[str, Any]],
    tracking_tasks: list[dict[str, Any]],
    score_history: list[dict[str, Any]],
) -> str:
    not_in_pool = [row for row in research_rows if row["include_decision"] != "进入观察池"]
    lines: list[str] = [
        f"# AI高速互联长期趋势跟踪日报（{run_date}）",
        "",
        "## 1. 当前判断",
        f"- 行业趋势分：{decision['industry_trend_score']}/{decision['industry_trend_max']}，{decision['industry_status']}。",
        f"- A股可操作状态：{decision['operability_state']}。",
        f"- 结论：{decision['conclusion']}。{decision['current_view']}",
        f"- 卡住原因：{decision['block_reason']}",
        f"- 下一触发：{decision['next_trigger']}",
        f"- 降级条件：{decision['downgrade_conditions']}",
        "",
        "## 2. 产业分支和入池门槛",
    ]
    lines += markdown_table(
        branch_rows,
        [
            ("分支", "branch"),
            ("热点聚类", "hotspot_cluster"),
            ("入池门槛", "entry_gate"),
            ("不入池条件", "not_enter_gate"),
            ("当前判断", "current_view"),
        ],
    )
    lines += [
        "",
        "## 3. 行业六因子确认",
    ]
    lines += markdown_table(
        factor_rows,
        [
            ("因子", "factor"),
            ("得分", "score_text"),
            ("状态", "status"),
            ("为什么影响趋势", "meaning"),
            ("之后盯什么", "watch_focus"),
            ("Source", "source_name"),
        ],
    )
    lines += [
        "",
        "## 4. 本地热度监控",
    ]
    lines += markdown_table(
        market_heat_rows,
        [
            ("主题", "theme"),
            ("分组", "theme_group"),
            ("今日排名", "rank_today"),
            ("热度", "hot_score"),
            ("当日涨幅", "pct_change"),
            ("20日Top50", "watch_hits_20"),
            ("状态", "lifecycle"),
            ("用途", "decision_use"),
        ],
    )
    lines += [
        "",
        "## 5. 动态变量和触发器",
    ]
    lines += markdown_table(
        price_radar_rows,
        [
            ("类别", "category"),
            ("指标", "indicator"),
            ("当前值", "current_value"),
            ("状态", "signal_state"),
            ("频率", "frequency"),
            ("用途", "decision_use"),
        ],
    )
    lines += [
        "",
        "## 6. 真正观察池",
        "只有include_decision为进入观察池的公司计入本表；其他公司保留在company_research表，不作为观察池。",
    ]
    lines += markdown_table(
        watchlist_rows,
        [
            ("股票", "stock_text"),
            ("分支", "branch"),
            ("层级", "pool_tier"),
            ("为什么进入", "trend_link"),
            ("利润驱动", "profit_driver"),
            ("当前动作", "action"),
        ],
    )
    lines += [
        "",
        "## 7. 未进入/旁路公司",
    ]
    lines += markdown_table(
        not_in_pool,
        [
            ("股票", "stock_text"),
            ("决定", "include_decision"),
            ("分支", "branch"),
            ("层级", "pool_tier"),
            ("主要原因", "key_risk"),
            ("下一步", "next_data_to_watch"),
        ],
    )
    lines += [
        "",
        "## 8. 跟踪任务",
    ]
    for row in tracking_tasks:
        lines.append(
            f"- [{row['priority']}] {row['task']}：{row['status']}；检查：{row['next_check']}；升级：{row['upgrade_use']}；降级：{row['downgrade_use']}。"
        )
    lines += [
        "",
        "## 9. 历史记录",
    ]
    for row in score_history:
        lines.append(
            f"- {row['date']}：行业 {row['industry_trend_score']} / A股 {row['a_share_operability_score']} / 结论 {row['conclusion']} / {row['notes']}"
        )
    lines += [
        "",
        "## 10. 核心来源",
        f"- TrendForce 800G+：{TREND_FORCE_800G_URL}",
        f"- NVIDIA Silicon Photonics：{NVIDIA_SILICON_PHOTONICS_URL}",
        f"- Broadcom FY26 Q1：{BROADCOM_Q1_URL}",
        f"- Dell'Oro AI后端交换机：{DELLORO_SWITCH_URL}",
        f"- TrendForce 玻纤布/CCL：{TREND_FORCE_GLASS_URL}",
        f"- 公司研究卡来源：见ai_interconnect_company_research_{run_date}.csv的source_url字段",
        f"- 本地热点：/api/market_heat/fine_dashboard?days=63&pool_size=50",
        "",
    ]
    return "\n".join(lines)


def enrich_display_rows(
    factor_rows: list[dict[str, Any]],
    watchlist_rows: list[dict[str, Any]],
    research_rows: list[dict[str, Any]],
) -> None:
    for row in factor_rows:
        row["score_text"] = f"{row['current_points']}/{row['max_points']}"
    for row in research_rows:
        row["stock_text"] = f"{row['name']} `{row['symbol']}`"
    for row in watchlist_rows:
        row["stock_text"] = f"{row['name']} `{row['symbol']}`"


def run(run_date: str | None = None) -> None:
    now = datetime.now(LOCAL_TZ)
    run_date = run_date or DEFAULT_RUN_DATE
    updated_at = f"{run_date} {now.strftime('%H:%M')} Asia/Shanghai"

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOC_DIR.mkdir(parents=True, exist_ok=True)

    branch_rows = build_branch_clusters()
    factor_rows = build_factor_scorecard()
    market_heat_rows = build_market_heat(run_date, updated_at)
    research_rows = build_company_research()
    watchlist_rows = [row for row in research_rows if row["include_decision"] == "进入观察池"]
    chain_layers = build_chain_layers()
    industry_signal_log = build_industry_signal_log()
    price_radar = build_price_radar()
    data_source_matrix = build_data_source_matrix()
    tracking_tasks = build_tracking_tasks()
    decision = build_decision_summary(run_date, updated_at, factor_rows, watchlist_rows, research_rows)
    score_history = build_score_history(run_date, updated_at, decision)

    enrich_display_rows(factor_rows, watchlist_rows, research_rows)

    write_csv(DATA_DIR / f"ai_interconnect_decision_summary_{run_date}.csv", [decision], DECISION_FIELDS)
    write_csv(DATA_DIR / f"ai_interconnect_factor_scorecard_{run_date}.csv", factor_rows, FACTOR_FIELDS)
    write_csv(DATA_DIR / f"ai_interconnect_market_heat_{run_date}.csv", market_heat_rows, MARKET_HEAT_FIELDS)
    write_csv(DATA_DIR / f"ai_interconnect_company_research_{run_date}.csv", research_rows, COMPANY_RESEARCH_FIELDS)
    write_csv(DATA_DIR / f"ai_interconnect_branch_clusters_{run_date}.csv", branch_rows, BRANCH_CLUSTER_FIELDS)
    write_csv(DATA_DIR / "ai_interconnect_watchlist.csv", watchlist_rows, COMPANY_RESEARCH_FIELDS)
    write_csv(DATA_DIR / "a_share_mapping_score.csv", watchlist_rows, COMPANY_RESEARCH_FIELDS)
    write_csv(
        DATA_DIR / "ai_interconnect_score_history.csv",
        score_history,
        [
            "date",
            "updated_at",
            "topic_id",
            "topic_name",
            "industry_trend_score",
            "industry_trend_max",
            "a_share_operability_score",
            "a_share_operability_max",
            "conclusion",
            "industry_status",
            "operability_state",
            "stage",
            "notes",
        ],
    )
    write_csv(
        DATA_DIR / "chain_layers.csv",
        chain_layers,
        [
            "order",
            "segment",
            "layer",
            "role",
            "key_indicator",
            "current_signal",
            "positive_signal",
            "risk_signal",
            "a_share_mapping",
            "status",
        ],
    )
    write_csv(
        DATA_DIR / "industry_signal_log.csv",
        industry_signal_log,
        [
            "date",
            "source",
            "source_type",
            "indicator",
            "value",
            "direction",
            "affected_links",
            "confidence",
            "next_check",
            "source_url",
            "notes",
        ],
    )
    write_csv(
        DATA_DIR / "price_radar.csv",
        price_radar,
        [
            "category",
            "indicator",
            "current_value",
            "direction",
            "importance",
            "signal_state",
            "status",
            "source",
            "frequency",
            "next_check",
            "decision_use",
            "source_url",
        ],
    )
    write_csv(
        DATA_DIR / "data_source_matrix.csv",
        data_source_matrix,
        ["module", "indicator", "source", "frequency", "method", "status", "next_step"],
    )
    write_csv(
        DATA_DIR / "tracking_tasks.csv",
        tracking_tasks,
        ["task", "priority", "status", "next_check", "target", "upgrade_use", "downgrade_use"],
    )

    report = build_report(
        run_date=run_date,
        decision=decision,
        branch_rows=branch_rows,
        factor_rows=factor_rows,
        market_heat_rows=market_heat_rows,
        watchlist_rows=watchlist_rows,
        research_rows=research_rows,
        price_radar_rows=price_radar,
        tracking_tasks=tracking_tasks,
        score_history=score_history,
    )
    (DOC_DIR / f"ai_interconnect_tracking_report_{run_date}.md").write_text(report, encoding="utf-8")

    print(f"Wrote AI interconnect tracking assets for {run_date}")
    print(f"researched_companies={len(research_rows)}")
    print(f"watchlist_companies={len(watchlist_rows)}")
    print(f"data_dir={DATA_DIR}")
    print(f"doc_dir={DOC_DIR}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build AI high-speed interconnect trend tracking assets.")
    parser.add_argument("--date", default=None, help=f"Run date in YYYY-MM-DD. Defaults to {DEFAULT_RUN_DATE}.")
    args = parser.parse_args()
    run(args.date)


if __name__ == "__main__":
    main()
