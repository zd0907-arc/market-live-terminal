#!/usr/bin/env python3
"""Build AI advanced packaging and materials long-term trend tracking assets.

The script is intentionally deterministic for the 2026-05-11 research snapshot:
it reads local fine-grained market-heat data when available, then writes the
CSV/Markdown assets used by the long-term trend research page.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from backend.app.core.config import RESEARCH_CURRENT_ROOT

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data/selection/long_term_trends/ai_advanced_packaging"
DOC_DIR = ROOT / "docs/selection/long_term_trends/ai_advanced_packaging"
HEAT_DB = Path(RESEARCH_CURRENT_ROOT) / "market_heat" / "fine_theme_heat_daily.db"
LOCAL_TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_RUN_DATE = "2026-05-11"
TOPIC_ID = "ai_advanced_packaging"
TOPIC_NAME = "AI先进封装与材料"

TSMC_Q4_2025_TRANSCRIPT = (
    "https://investor.tsmc.com/english/encrypt/files/encrypt_file/reports/2026-01/"
    "51d09df96cd89ac19d65af39032b038dc2896a24/TSMC%204Q25%20Transcript.pdf"
)
AMKOR_2025_RESULTS = "https://ir.amkor.com/static-files/1e199e2d-d9ab-45e4-9a12-aee8a68b901c"
SEMI_300MM_OUTLOOK = (
    "https://www.semi.org/en/semi-press-release/"
    "semi-projects-double-digit-growth-in-global-300mm-fab-equipment-spending-for-2026-and-2027"
)
INTEL_GLASS_SUBSTRATE = (
    "https://www.intc.com/news-events/press-releases/detail/1647/"
    "intel-unveils-industry-leading-glass-substrates-to-meet"
)
ASE_WUS_AI_PACKAGING = "https://ase.aseglobal.com/press-room/ase-and-wus-announce-strategic-expansion/"
SAMSUNG_HBM4 = (
    "https://news.samsung.com/global/"
    "samsung-ships-industry-first-commercial-hbm4-with-ultimate-performance-for-ai-computing"
)
MICRON_HBM4 = (
    "https://investors.micron.com/news-releases/news-release-details/"
    "micron-high-volume-production-hbm4-designed-nvidia-vera-rubin"
)
JCET_2026_BRIEFING = "https://www.stcn.com/article/detail/3901109.html"
TONGFU_2025_AR = "https://static.cninfo.com.cn/finalpage/2026-04-17/1225112762.PDF"
HUATIAN_2025_AR = "https://money.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=12045582&stockid=002185"
XINGSEN_2025_AR = "https://www.fxbaogao.com/detail/5376267"
SHENNAN_2025_AR = "https://money.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=11992828&stockid=002916"
HUAHAI_2025_AR = "https://cniis.aastocks.com/CNSESH_STOCK/2026/2026-3/2026-03-18/12000695.pdf"
NOVORAY_2025_SEMI_STANDARD = "https://novoray.com/index.php/news/content/id/13/artid/173.html"
ACM_2025_AR = (
    "https://big5.sse.com.cn/site/cht/www.sse.com.cn/disclosure/listedinfo/"
    "announcement/c/new/2026-02-27/688082_20260227_7FPP.pdf"
)
XINQI_2025_AR = "https://www.fxbaogao.com/detail/5299419"
VOGUE_Q1_2026 = "https://www.stcn.com/article/detail/3788771.html"
TRIUMPH_2025_AR = "https://www.fxbaogao.com/detail/5325654"
YAK_2026_Q1 = "https://finance.sina.com.cn/wm/2026-05-09/doc-inhxhcxm1639959.shtml"
WLCSP_2025_AR = (
    "https://big5.sse.com.cn/site/cht/www.sse.com.cn/disclosure/listedinfo/"
    "announcement/c/new/2026-02-28/603005_20260228_AYEI.pdf"
)

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

HEAT_RANK_SEED_20260511 = [
    ("集成电路封测", 1),
    ("先进封装", 2),
    ("半导体", 3),
    ("华为海思", 4),
    ("半导体材料", 5),
    ("存储芯片", 6),
    ("数字芯片设计", 7),
    ("玻璃基板", 8),
]


@dataclass
class HeatStat:
    theme_name: str
    rank: int
    hot_score: str = ""
    persistence_score: str = ""
    top15_days_63d: int = 0
    top30_days_63d: int = 0
    latest_return_5d: str = ""
    latest_return_20d: str = ""
    amount_yi: str = ""
    l2_main_net_yi: str = ""
    leader_name: str = ""
    source_basis: str = "user_rank_seed"


def now_text() -> str:
    return datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M Asia/Shanghai")


def pct(value: float, total: float) -> float:
    return round(value / total * 100, 1) if total else 0.0


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


def try_load_fine_dashboard_from_api(days: int = 63, pool_size: int = 50) -> dict[str, Any]:
    query = urllib.parse.urlencode({"days": days, "pool_size": pool_size})
    url = f"http://127.0.0.1:8001/api/market_heat/fine_dashboard?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "trend-research-builder/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return {}
    if isinstance(payload, dict) and payload.get("code") == 200:
        data = payload.get("data")
        return data if isinstance(data, dict) else {}
    return {}


def load_heat_stats_from_db(rank_seed: list[tuple[str, int]], days: int = 63) -> list[HeatStat]:
    stats = {name: HeatStat(theme_name=name, rank=rank) for name, rank in rank_seed}
    if not HEAT_DB.exists():
        return list(stats.values())

    with sqlite3.connect(str(HEAT_DB)) as conn:
        conn.row_factory = sqlite3.Row
        max_date_row = conn.execute("SELECT MAX(trade_date) AS d FROM fine_theme_heat_daily").fetchone()
        max_date = str(max_date_row["d"]) if max_date_row and max_date_row["d"] else ""
        for name, rank in rank_seed:
            summary = conn.execute(
                """
                SELECT
                    COUNT(*) AS days,
                    SUM(CASE WHEN hot_rank <= 15 THEN 1 ELSE 0 END) AS top15,
                    SUM(CASE WHEN hot_rank <= 30 THEN 1 ELSE 0 END) AS top30
                FROM fine_theme_heat_daily
                WHERE trade_date >= date(?, ?)
                  AND trade_date <= ?
                  AND sector_name = ?
                """,
                (max_date, f"-{days - 1} day", max_date, name),
            ).fetchone()
            latest = conn.execute(
                """
                SELECT hot_score, persistence_score, avg_return_5d, avg_return_20d,
                       amount_yi, l2_main_net_yi, leader_name
                FROM fine_theme_heat_daily
                WHERE sector_name = ?
                ORDER BY trade_date DESC
                LIMIT 1
                """,
                (name,),
            ).fetchone()
            item = stats[name]
            if summary:
                item.top15_days_63d = int(summary["top15"] or 0)
                item.top30_days_63d = int(summary["top30"] or 0)
            if latest:
                item.hot_score = fmt(latest["hot_score"])
                item.persistence_score = fmt(latest["persistence_score"])
                item.latest_return_5d = fmt(latest["avg_return_5d"])
                item.latest_return_20d = fmt(latest["avg_return_20d"])
                item.amount_yi = fmt(latest["amount_yi"])
                item.l2_main_net_yi = fmt(latest["l2_main_net_yi"])
                item.leader_name = latest["leader_name"] or ""
                item.source_basis = f"user_2026-05-11_rank_seed + local_db_until_{max_date}"
    return sorted(stats.values(), key=lambda row: row.rank)


def load_heat_stats(rank_seed: list[tuple[str, int]]) -> list[HeatStat]:
    api_data = try_load_fine_dashboard_from_api()
    if api_data:
        pool = []
        for group in (api_data.get("cards") or {}).values():
            if isinstance(group, list):
                pool.extend(group)
        pool.extend(api_data.get("pool") or [])
        by_name = {str(item.get("name") or ""): item for item in pool if isinstance(item, dict)}
        if any(name in by_name for name, _ in rank_seed):
            fallback = {row.theme_name: row for row in load_heat_stats_from_db(rank_seed)}
            out: list[HeatStat] = []
            for name, rank in rank_seed:
                item = by_name.get(name) or {}
                base = fallback.get(name, HeatStat(name, rank))
                out.append(
                    HeatStat(
                        theme_name=name,
                        rank=int(item.get("rank_today") or rank),
                        hot_score=fmt(item.get("hot_score")) or base.hot_score,
                        persistence_score=base.persistence_score,
                        top15_days_63d=int(item.get("hot_hits_20") or base.top15_days_63d),
                        top30_days_63d=int(item.get("watch_hits_20") or base.top30_days_63d),
                        latest_return_5d=base.latest_return_5d,
                        latest_return_20d=base.latest_return_20d,
                        amount_yi=base.amount_yi,
                        l2_main_net_yi=base.l2_main_net_yi,
                        leader_name=base.leader_name,
                        source_basis="api_fine_dashboard + user_rank_seed",
                    )
                )
            return sorted(out, key=lambda row: row.rank)
    return load_heat_stats_from_db(rank_seed)


def fmt(value: Any, digits: int = 1) -> str:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return ""
    if abs(num) >= 100:
        return f"{num:.0f}"
    return f"{num:.{digits}f}".rstrip("0").rstrip(".")


def heat_rows(heat_stats: list[HeatStat], updated_at: str) -> list[dict[str, Any]]:
    rows = []
    for item in heat_stats:
        if item.rank <= 5:
            state = "强确认"
        elif item.rank <= 10:
            state = "链条扩散"
        else:
            state = "观察"
        rows.append(
            {
                "updated_at": updated_at,
                "heat_date": "2026-05-11",
                "theme_name": item.theme_name,
                "rank": item.rank,
                "hot_score": item.hot_score,
                "persistence_score": item.persistence_score,
                "top15_days_63d": item.top15_days_63d,
                "top30_days_63d": item.top30_days_63d,
                "latest_return_5d": item.latest_return_5d,
                "latest_return_20d": item.latest_return_20d,
                "amount_yi": item.amount_yi,
                "l2_main_net_yi": item.l2_main_net_yi,
                "leader_name": item.leader_name,
                "signal_state": state,
                "meaning": "半导体链细颗粒热点集中在封测、先进封装、材料、玻璃基板，说明市场正在交易 AI 封装瓶颈而不是泛半导体。",
                "source_basis": item.source_basis,
            }
        )
    return rows


def build_factor_scorecard(heat_stats: list[HeatStat]) -> list[dict[str, Any]]:
    top10_count = sum(1 for item in heat_stats if item.rank <= 10)
    top30_sum = sum(item.top30_days_63d for item in heat_stats)
    heat_evidence = f"{top10_count}/8个相关主题进入前10；63日样本前30合计{top30_sum}次"
    factors = [
        {
            "factor": "热点持续性/市场确认",
            "current_points": 16,
            "max_points": 18,
            "weight_pct": 18,
            "status": "强确认但偏拥挤",
            "meaning": "市场是否真的开始围绕先进封装瓶颈定价，而不是只有单条新闻。",
            "logic": "集成电路封测、先进封装、半导体材料、玻璃基板同时靠前，说明资金把 AI 算力映射到封测、材料和载板链。",
            "score_rule": "相关细分主题进入前10且本地63日有多次前30记录，说明值得继续研究；若只剩单一题材或连续退出前30则降级。",
            "watch_focus": "每天看前30留存、封测/先进封装是否仍有容量核心承接、玻璃基板是否从题材扩散回产业链核心。",
            "evidence_1_label": "2026-05-11本地热点",
            "evidence_1_value": "封测#1、先进封装#2、半导体材料#5、玻璃基板#8",
            "evidence_1_meaning": "题材不是孤立点火，已沿半导体后道链条扩散。",
            "evidence_2_label": "63日持续性",
            "evidence_2_value": heat_evidence,
            "evidence_2_meaning": "短线热度有阶段性持续，但仍需防止过热后退潮。",
            "evidence_3_label": "代表票",
            "evidence_3_value": "通富微电、长电科技、沃格光电等",
            "evidence_3_meaning": "封测容量核心和玻璃基板弹性票同时被交易。",
            "source_name": "本地 fine_theme_heat_daily / fine_dashboard",
            "source_url": "/api/market_heat/fine_dashboard?days=63&pool_size=50",
        },
        {
            "factor": "AI算力需求传导",
            "current_points": 18,
            "max_points": 20,
            "weight_pct": 20,
            "status": "强",
            "meaning": "先进封装的需求根源是 AI GPU/ASIC/HBM 的算力堆叠，不是普通消费电子复苏。",
            "logic": "TSMC 预计 AI accelerator 收入 2024-2029 CAGR 接近 mid-to-high-fifties，AI/HPC 需要更大 die、HBM 和 chiplet 互连，直接拉动 CoWoS/2.5D/3D 封装。",
            "score_rule": "云厂商/晶圆厂/HBM 厂同时上修 AI 需求时保持跟踪；若 AI accelerator 或 HBM 指引下修则降级。",
            "watch_focus": "每季盯 TSMC、NVIDIA/AMD、HBM 厂对 AI accelerator、HBM4、CoWoS 需求的表述。",
            "evidence_1_label": "TSMC AI accelerator",
            "evidence_1_value": "2024-2029收入CAGR接近mid-to-high-fifties",
            "evidence_1_meaning": "AI 芯片增量足够大，先进封装需求有长期底座。",
            "evidence_2_label": "SEMI 300mm",
            "evidence_2_value": "2026设备支出+18%至1330亿美元",
            "evidence_2_meaning": "AI/HBM 带动上游资本开支继续扩张。",
            "evidence_3_label": "HBM4",
            "evidence_3_value": "Samsung/Micron均强调AI HBM4与先进封装能力",
            "evidence_3_meaning": "高带宽内存迭代继续绑定先进封装。",
            "source_name": "TSMC / SEMI / Samsung / Micron",
            "source_url": f"{TSMC_Q4_2025_TRANSCRIPT} | {SEMI_300MM_OUTLOOK} | {SAMSUNG_HBM4} | {MICRON_HBM4}",
        },
        {
            "factor": "先进封装产能与良率",
            "current_points": 13,
            "max_points": 18,
            "weight_pct": 18,
            "status": "扩产明确，良率仍要验证",
            "meaning": "行业能不能持续，关键是 CoWoS/2.5D/3D 封装产能和良率是否跟上 AI 芯片订单。",
            "logic": "TSMC 2026资本预算中先进封装/测试/掩模等占10%-20%，先进封装收入占比预计升至low-teens；Amkor 2026资本开支指引25-30亿美元。",
            "score_rule": "海外龙头明确扩产支撑行业判断；若扩产不转化为收入、良率或客户交付，则维持观察。",
            "watch_focus": "盯 TSMC advanced packaging 收入占比、CoWoS/SoIC 产能、Amkor capex、A股封测厂先进封装稼动率。",
            "evidence_1_label": "TSMC资本预算",
            "evidence_1_value": "先进封装/测试/掩模等10%-20%",
            "evidence_1_meaning": "龙头把后道作为资本开支重点之一。",
            "evidence_2_label": "TSMC收入占比",
            "evidence_2_value": "2026 advanced packaging low-teens%",
            "evidence_2_meaning": "先进封装已从配套能力变成收入增长变量。",
            "evidence_3_label": "Amkor capex",
            "evidence_3_value": "2026约25-30亿美元",
            "evidence_3_meaning": "OSAT 端也在加速投入，但回报要看客户装载。",
            "source_name": "TSMC transcript / Amkor 2025 results",
            "source_url": f"{TSMC_Q4_2025_TRANSCRIPT} | {AMKOR_2025_RESULTS}",
        },
        {
            "factor": "封测/材料国产替代",
            "current_points": 11,
            "max_points": 15,
            "weight_pct": 15,
            "status": "有映射，订单纯度待确认",
            "meaning": "A股可操作性取决于国产封测、IC载板、封装材料是否拿到真实 AI/HPC 增量。",
            "logic": "A股有封测、IC载板、封装材料和设备映射，但高端 ABF、CoWoS 产能、客户认证仍是约束，不能把所有半导体都当受益。",
            "score_rule": "出现客户订单、产线投产、毛利率提升时升级；只有概念扩散、无收入占比则移出观察池。",
            "watch_focus": "中报看先进封装收入、FC-BGA/IC载板产能、封装材料放量、毛利率和现金流。",
            "evidence_1_label": "封测核心",
            "evidence_1_value": "长电科技、通富微电、华天科技",
            "evidence_1_meaning": "最直接的 A股产业映射在 OSAT。",
            "evidence_2_label": "载板材料",
            "evidence_2_value": "兴森科技、深南电路、华海诚科、联瑞新材",
            "evidence_2_meaning": "材料/载板决定国产替代弹性，但需要订单验证。",
            "evidence_3_label": "本地热点",
            "evidence_3_value": "封测#1、半导体材料#5",
            "evidence_3_meaning": "市场已经在找国产替代映射。",
            "source_name": "公司公告/定期报告待持续补齐 + 本地热点",
            "source_url": "https://www.sse.com.cn/ | https://www.szse.cn/",
        },
        {
            "factor": "玻璃基板/载板等技术路线验证",
            "current_points": 8,
            "max_points": 14,
            "weight_pct": 14,
            "status": "早期验证，题材热度高于产业兑现",
            "meaning": "玻璃基板、面板级封装、先进载板可能改变中长期封装成本/性能，但当前更像技术路线观察项。",
            "logic": "Intel 已宣布玻璃基板用于下一代先进封装且计划在本十年后半段推向市场，A股玻璃基板热度很高，但商业订单和良率尚未外露。",
            "score_rule": "样品认证、小批量订单、良率数据出来才升级；仅有涨停和概念互动不进入观察池。",
            "watch_focus": "盯玻璃基板客户验证、小批量订单、TGV/翘曲/良率指标、沃格光电等是否披露真实进展。",
            "evidence_1_label": "Intel路线",
            "evidence_1_value": "玻璃基板计划本十年后半段进入市场",
            "evidence_1_meaning": "技术方向存在，但不是当季利润变量。",
            "evidence_2_label": "A股热度",
            "evidence_2_value": "玻璃基板#8",
            "evidence_2_meaning": "市场正在提前交易路线验证。",
            "evidence_3_label": "验证缺口",
            "evidence_3_value": "订单/良率/客户认证未结构化",
            "evidence_3_meaning": "当前只能给中低分，防止把题材当兑现。",
            "source_name": "Intel / 本地热点",
            "source_url": f"{INTEL_GLASS_SUBSTRATE} | /api/market_heat/fine_dashboard?days=63&pool_size=50",
        },
        {
            "factor": "海外龙头/订单财报验证",
            "current_points": 12,
            "max_points": 15,
            "weight_pct": 15,
            "status": "海外验证强，A股传导待确认",
            "meaning": "海外龙头财报和订单是产业真需求的硬验证，A股需要证明能分到这条链的收入。",
            "logic": "TSMC、Amkor、ASE、Samsung、Micron 均把 AI/HPC、HBM、先进封装作为增长变量；但 A股公司还缺少同强度的订单和利润验证。",
            "score_rule": "海外龙头继续上修且A股中报跟随时升级；海外利好不涨或订单放缓则降级。",
            "watch_focus": "每季跟踪 TSMC/Amkor/ASE/HBM 厂财报，国内看长电/通富/华天/兴森/华海诚科中报。",
            "evidence_1_label": "Amkor",
            "evidence_1_value": "2025 advanced packaging和computing收入创新高",
            "evidence_1_meaning": "OSAT 龙头已经出现收入验证。",
            "evidence_2_label": "ASE",
            "evidence_2_value": "AI推动CoWoS/FOCoS等先进封装需求",
            "evidence_2_meaning": "海外封测龙头继续扩 AI 包装能力。",
            "evidence_3_label": "A股缺口",
            "evidence_3_value": "订单/毛利率/现金流待中报验证",
            "evidence_3_meaning": "能跟但不能直接按海外龙头估值外推。",
            "source_name": "Amkor / ASE / TSMC",
            "source_url": f"{AMKOR_2025_RESULTS} | {ASE_WUS_AI_PACKAGING} | {TSMC_Q4_2025_TRANSCRIPT}",
        },
    ]
    for row in factors:
        row["score_pct"] = pct(float(row["current_points"]), float(row["max_points"]))
    return factors


def build_company_research() -> list[dict[str, Any]]:
    return [
        {
            "symbol": "sh600584",
            "name": "长电科技",
            "include_decision": "进入观察池",
            "pool_tier": "核心跟踪",
            "branch": "先进封装/封测",
            "business_summary": "全球主要封测厂，覆盖晶圆级、SiP、倒装、系统级封装和测试服务，是A股最直接的OSAT容量映射。",
            "trend_link": "AI GPU/ASIC和HBM带来的2.5D/3D、chiplet和高密度互连需求，首先传导到先进封装产能、良率和客户装载率。",
            "profit_driver": "利润来自封测加工费、产品结构升级和产线稼动率；趋势若兑现，应表现为先进封装收入占比、毛利率和现金流改善。",
            "growth_space": "主要来自订单和份额，次要来自产能利用率修复；不把玻璃基板等远期题材并入长电的当期利润判断。",
            "valuation_snapshot": "大市值封测龙头，估值通常跟随半导体周期和先进封装订单预期摆动；当前更适合等财报验证和回踩承接。",
            "latest_validation": "公司已反复强调先进封装能力建设；本地热点中封测排名靠前，正在验证市场是否把AI封装瓶颈映射到容量龙头。",
            "key_risk": "A股订单披露颗粒度不足，若先进封装未带来毛利率改善，龙头属性只能提供防守，缺少弹性。",
            "next_data_to_watch": "2026中报先进封装收入、客户订单、稼动率、毛利率、经营现金流。",
            "action": "纳入观察池核心跟踪；只在订单/财报验证或分歧后重新承接时升级动作。",
            "source_url": JCET_2026_BRIEFING,
        },
        {
            "symbol": "sz002156",
            "name": "通富微电",
            "include_decision": "进入观察池",
            "pool_tier": "高弹性观察",
            "branch": "先进封装/封测",
            "business_summary": "封测厂，产品覆盖集成电路封装测试，市场常把它与CPU/GPU、Chiplet和高性能计算封测弹性绑定。",
            "trend_link": "AI算力芯片从单芯片转向chiplet和高带宽存储协同后，封装测试复杂度上升，通富是A股弹性最高的封测映射之一。",
            "profit_driver": "利润来自高性能计算封测订单、先进封装产线稼动率和产品结构；趋势影响通过收入增速和毛利率弹性体现。",
            "growth_space": "主要来自订单和产能装载，另有海外大客户/CPU GPU链条带来的估值想象。",
            "valuation_snapshot": "弹性票属性更强，热度上来时估值容易提前反映订单；追高性价比低于等分歧后的验证。",
            "latest_validation": "2025年报披露公司继续推进先进封装和高性能计算相关业务；本地封测主题代表票显示市场正在交易它的容量弹性。",
            "key_risk": "如果高性能计算订单没有转化为利润，或者客户集中度带来收入波动，股价弹性会反向放大。",
            "next_data_to_watch": "HPC/先进封装收入口径、重要客户拉货节奏、毛利率、资本开支和在建产线投产。",
            "action": "纳入观察池高弹性位；热度过高时只跟踪，不把题材强度等同于买点。",
            "source_url": TONGFU_2025_AR,
        },
        {
            "symbol": "sz002185",
            "name": "华天科技",
            "include_decision": "旁路观察",
            "pool_tier": "间接受益",
            "branch": "先进封装/封测",
            "business_summary": "综合封测厂，覆盖多类型封装测试和传统半导体封测需求。",
            "trend_link": "封测主题扩散时会跟随受益，但与AI HPC先进封装的直接订单绑定弱于长电、通富。",
            "profit_driver": "利润更依赖整体封测景气、产能利用率和产品结构，而不是单一AI先进封装订单。",
            "growth_space": "成长空间主要来自传统封测周期修复和先进封装占比提升的可能性，当前证据不足以进入核心池。",
            "valuation_snapshot": "更像封测板块补涨和景气修复映射，估值弹性依赖市场风险偏好。",
            "latest_validation": "2025年报能看到封测业务和先进封装布局，但仍需公司披露AI/HPC相关收入或客户订单。",
            "key_risk": "用传统封测复苏替代AI先进封装验证，导致主题纯度错判。",
            "next_data_to_watch": "先进封装收入占比、客户结构、毛利率和产能利用率。",
            "action": "不进入观察池；保留旁路用于判断封测板块扩散宽度。",
            "source_url": HUATIAN_2025_AR,
        },
        {
            "symbol": "sz002436",
            "name": "兴森科技",
            "include_decision": "进入观察池",
            "pool_tier": "核心跟踪",
            "branch": "IC载板/ABF",
            "business_summary": "PCB样板、小批量板和封装基板平台，市场重点看FC-BGA、IC载板产线爬坡和客户认证。",
            "trend_link": "AI先进封装需要更高层数、更低翘曲和高可靠性的封装基板，FC-BGA/ABF是A股少数能承接国产替代叙事的分支。",
            "profit_driver": "利润来自封装基板订单放量、产线稼动率和良率爬坡；AI趋势会通过高端载板需求和国产客户导入影响利润。",
            "growth_space": "主要来自订单、产能爬坡和份额；如果FC-BGA验证顺利，估值想象会明显放大。",
            "valuation_snapshot": "载板成长逻辑清晰但业绩兑现慢，估值会在认证/投产/亏损收窄之间大幅波动。",
            "latest_validation": "2025年报继续把封装基板和FC-BGA作为关键方向；当前需要从产能建设转向客户订单验证。",
            "key_risk": "FC-BGA客户认证周期长、良率和稼动率爬坡慢，资本开支先于利润释放。",
            "next_data_to_watch": "FC-BGA客户认证、量产订单、广州/珠海产线利用率、封装基板毛利率。",
            "action": "纳入观察池核心跟踪；只在订单和稼动率证据强化后提高权重。",
            "source_url": XINGSEN_2025_AR,
        },
        {
            "symbol": "sz002916",
            "name": "深南电路",
            "include_decision": "旁路观察",
            "pool_tier": "间接受益",
            "branch": "IC载板/ABF",
            "business_summary": "PCB、封装基板和电子装联平台型公司，质量和客户能力强，但业务更分散。",
            "trend_link": "AI服务器PCB和高端封装基板都与算力链相关，但先进封装主题只是公司多条成长线之一。",
            "profit_driver": "利润来自PCB、封装基板和通信/数据中心需求组合；AI先进封装影响更多通过高端载板和服务器板订单体现。",
            "growth_space": "订单和份额是主驱动，弹性小于纯载板或封测弹性票。",
            "valuation_snapshot": "更偏质量公司，估值承压通常来自业绩增速而非单一题材；不适合用主题热度追高。",
            "latest_validation": "2025年报显示封装基板业务仍是重要分支，但需要确认AI服务器和载板订单对利润的边际贡献。",
            "key_risk": "公司质量高但主题弹性不够直接，容易被纳入过宽的AI先进封装池。",
            "next_data_to_watch": "封装基板收入、AI服务器PCB订单、毛利率、产能利用率。",
            "action": "不进入观察池；保留为质量旁路，验证载板链景气而非作为主攻标的。",
            "source_url": SHENNAN_2025_AR,
        },
        {
            "symbol": "sh688535",
            "name": "华海诚科",
            "include_decision": "进入观察池",
            "pool_tier": "高弹性观察",
            "branch": "封装材料",
            "business_summary": "半导体封装材料公司，核心产品包括环氧塑封料，市场关注GMC等先进封装材料导入。",
            "trend_link": "先进封装从传统EMC向颗粒状环氧塑封料、底填、低应力和高可靠材料升级，材料国产替代弹性集中。",
            "profit_driver": "利润来自高端封装材料客户导入、单价提升和毛利率改善；AI趋势影响通过先进封装材料放量体现。",
            "growth_space": "主要来自客户认证转订单和高端产品占比提升，产能不是唯一约束。",
            "valuation_snapshot": "小市值材料弹性强，估值对客户验证和订单披露高度敏感；证据不够时容易被题材透支。",
            "latest_validation": "2025年报披露公司推进GMC等先进封装材料；当前要看导入是否从送样认证进入收入贡献。",
            "key_risk": "材料验证周期长，若客户导入慢或价格竞争加剧，利润弹性会低于题材预期。",
            "next_data_to_watch": "GMC/先进封装材料订单、客户认证状态、产品单价、毛利率。",
            "action": "纳入观察池高弹性位；用客户导入和毛利率验证，不用概念热度加仓。",
            "source_url": HUAHAI_2025_AR,
        },
        {
            "symbol": "sh688300",
            "name": "联瑞新材",
            "include_decision": "进入观察池",
            "pool_tier": "间接受益",
            "branch": "封装材料",
            "business_summary": "功能性粉体材料公司，球形硅微粉等产品用于覆铜板、封装材料和电子材料体系。",
            "trend_link": "ABF/封装材料升级需要低膨胀、高填充、高可靠填料，联瑞是材料上游相对清晰的A股映射。",
            "profit_driver": "利润来自高端球形粉体放量、电子级材料占比提升和客户结构升级；趋势影响通过封装/载板材料需求拉动体现。",
            "growth_space": "成长来自产品结构、订单和份额，估值想象来自先进封装材料国产替代。",
            "valuation_snapshot": "材料质量票属性强，弹性不如华海诚科，但若高端产品占比提升，估值更容易获得稳定支撑。",
            "latest_validation": "公司参与或牵头半导体封装用球形硅微粉标准，侧面验证其在封装材料链条的产业位置。",
            "key_risk": "作为上游填料，收入传导链条较长，可能出现行业热但公司利润弹性有限。",
            "next_data_to_watch": "电子级球形粉体销量、封装/载板客户占比、毛利率、扩产进度。",
            "action": "纳入观察池的间接受益位；用于跟踪材料链兑现质量。",
            "source_url": NOVORAY_2025_SEMI_STANDARD,
        },
        {
            "symbol": "sh688082",
            "name": "盛美上海",
            "include_decision": "暂不进入",
            "pool_tier": "题材映射",
            "branch": "设备",
            "business_summary": "半导体清洗、电镀、先进封装湿法设备平台，客户覆盖晶圆制造和封装相关环节。",
            "trend_link": "先进封装扩产需要清洗、电镀、湿法工艺等设备，但公司收入也受晶圆厂资本开支和设备验收周期影响。",
            "profit_driver": "利润来自设备订单、交付验收和产品组合；AI先进封装只是订单结构中的一个方向。",
            "growth_space": "成长空间来自订单和份额，特别是先进封装设备能否形成持续订单。",
            "valuation_snapshot": "设备平台公司估值更多由整体半导体设备国产替代和订单能见度决定，不能只按AI封装主题重估。",
            "latest_validation": "2025年报披露先进封装相关设备布局；但需要拆出订单、验收和收入确认节奏。",
            "key_risk": "泛设备逻辑过宽，先进封装订单占比不清晰时不适合进入主题观察池。",
            "next_data_to_watch": "先进封装设备订单、交付验收、在手订单结构、客户扩产节奏。",
            "action": "暂不进入观察池；等先进封装设备订单占比或验收数据更清楚。",
            "source_url": ACM_2025_AR,
        },
        {
            "symbol": "sh688630",
            "name": "芯碁微装",
            "include_decision": "暂不进入",
            "pool_tier": "题材映射",
            "branch": "设备",
            "business_summary": "直写光刻设备公司，产品应用于PCB、泛半导体和封装载板等制造场景。",
            "trend_link": "IC载板和先进封装对图形化精度和效率要求提高，直写光刻设备具备产业映射。",
            "profit_driver": "利润来自设备销售、客户扩产和验收确认；主题影响要通过封装载板客户订单体现。",
            "growth_space": "成长主要来自订单和份额，若封装载板客户扩产加速会带来弹性。",
            "valuation_snapshot": "设备弹性票，估值对订单披露敏感；没有封装载板订单细节时不进入核心。",
            "latest_validation": "2025年报显示公司继续拓展泛半导体与PCB直写光刻设备；当前缺少AI先进封装订单的直接验证。",
            "key_risk": "PCB设备和先进封装设备边界容易混淆，主题映射可能大于实际利润贡献。",
            "next_data_to_watch": "IC载板/封装客户订单、验收节奏、收入确认、毛利率。",
            "action": "暂不进入观察池；作为设备分支样本保留在研究卡。",
            "source_url": XINQI_2025_AR,
        },
        {
            "symbol": "sh603773",
            "name": "沃格光电",
            "include_decision": "旁路观察",
            "pool_tier": "题材映射",
            "branch": "玻璃基板",
            "business_summary": "玻璃精加工和显示相关公司，市场把TGV玻璃基板、面板级封装等路线映射到公司。",
            "trend_link": "玻璃基板是下一代先进封装潜在路线，但距离大规模商业化仍需客户认证、良率和小批量订单证明。",
            "profit_driver": "利润当前不主要来自AI先进封装，趋势影响更多是路线验证带来的订单想象和估值弹性。",
            "growth_space": "主要来自估值想象和潜在订单，短期不是财报利润驱动。",
            "valuation_snapshot": "题材弹性很高，价格阶段风险通常高于基本面验证速度；适合旁路监控，不适合作为观察池核心。",
            "latest_validation": "本地先进封装主题代表票出现沃格光电，说明市场正在交易玻璃基板路线；同时公开信息仍缺少稳定量产和利润验证。",
            "key_risk": "只有路线和涨幅，没有客户认证、良率、小批量订单或收入贡献。",
            "next_data_to_watch": "TGV/玻璃基板客户认证、小批量订单、良率、产能和收入口径。",
            "action": "不进入观察池；作为玻璃基板路线旁路观察，防止题材带偏核心池。",
            "source_url": f"{VOGUE_Q1_2026} | {INTEL_GLASS_SUBSTRATE}",
        },
        {
            "symbol": "sz002409",
            "name": "雅克科技",
            "include_decision": "旁路观察",
            "pool_tier": "间接受益",
            "branch": "封装材料",
            "business_summary": "电子材料和半导体材料平台公司，业务覆盖前驱体、光刻胶配套、LNG保温等多条线。",
            "trend_link": "半导体材料平台会受益于国产替代和AI算力链扩产，但与先进封装材料的直接绑定弱于华海诚科、联瑞新材。",
            "profit_driver": "利润来自多类电子材料订单和产品结构，AI先进封装只是间接需求来源。",
            "growth_space": "成长来自平台化材料订单和份额，不是单一封装材料爆发。",
            "valuation_snapshot": "平台型材料估值相对稳，但主题纯度不足时不应放入先进封装观察池。",
            "latest_validation": "2026一季报仍显示材料平台属性，需等待先进封装材料或HBM相关订单的明确披露。",
            "key_risk": "把半导体材料平台泛化成先进封装核心，造成观察池过宽。",
            "next_data_to_watch": "先进封装相关材料订单、客户导入、收入占比。",
            "action": "不进入观察池；保留旁路作为材料平台估值参照。",
            "source_url": YAK_2026_Q1,
        },
        {
            "symbol": "sh603005",
            "name": "晶方科技",
            "include_decision": "剔除",
            "pool_tier": "剔除",
            "branch": "先进封装/封测",
            "business_summary": "以传感器、CIS等晶圆级封装为主的封测公司，消费电子和光学应用属性更强。",
            "trend_link": "公司有WLCSP和晶圆级封装能力，但与AI GPU/HBM/CoWoS式先进封装瓶颈不是同一条主线。",
            "profit_driver": "利润主要来自传感器封装、消费电子和相关应用景气，而非AI先进封装产能短缺。",
            "growth_space": "成长来自CIS、汽车电子或消费电子修复，不来自本主题的核心订单。",
            "valuation_snapshot": "可以跟随半导体封测情绪波动，但主题匹配度不足。",
            "latest_validation": "2025年报仍体现晶圆级封装和传感器应用主线，没有足够证据进入AI先进封装池。",
            "key_risk": "概念误配，导致把消费电子封测当作AI先进封装受益。",
            "next_data_to_watch": "除非披露AI/HPC先进封装客户和收入，否则不重新纳入。",
            "action": "剔除，不进入观察池；只在主题边界复盘时作为反例。",
            "source_url": WLCSP_2025_AR,
        },
        {
            "symbol": "sh600552",
            "name": "凯盛科技",
            "include_decision": "旁路观察",
            "pool_tier": "题材映射",
            "branch": "玻璃基板",
            "business_summary": "新型显示和玻璃材料平台公司，市场关注其在玻璃材料、TGV和封装基板相关方向的潜在映射。",
            "trend_link": "玻璃基板是先进封装远期技术路线，凯盛可作为玻璃材料链观察点，但离AI封装利润兑现较远。",
            "profit_driver": "利润来自显示材料、电子玻璃和其他材料业务；AI先进封装影响主要是潜在新产品和估值想象。",
            "growth_space": "成长更多来自技术路线验证和潜在订单，不是当前产能利润释放。",
            "valuation_snapshot": "玻璃基板题材强时容易被重估，但缺少量产订单前估值基础不稳。",
            "latest_validation": "2025年报显示公司围绕玻璃材料和新显示材料布局；需要客户认证和订单把题材转成收入。",
            "key_risk": "路线过早、收入口径不清，市场热度领先产业兑现太多。",
            "next_data_to_watch": "玻璃基板/TGV相关客户认证、样品、小批量订单、产线进度。",
            "action": "不进入观察池；作为玻璃基板分支旁路样本。",
            "source_url": TRIUMPH_2025_AR,
        },
    ]


def build_watchlist(company_research: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in company_research if row.get("include_decision") == "进入观察池"]


def build_chain_layers() -> list[dict[str, Any]]:
    return [
        {
            "external_variable": "AI GPU/ASIC/HBM需求",
            "chain_layer": "需求源",
            "mechanism": "模型训练/推理扩大算力集群，单芯片面积、HBM堆叠和chiplet互连复杂度上升。",
            "direct_beneficiaries": "TSMC、HBM厂、AI芯片设计商",
            "a_share_mapping": "封测和材料只是二阶映射，必须看订单传导。",
            "data_to_watch": "AI accelerator指引、HBM4出货、CoWoS/2.5D产能缺口",
            "evidence_grade": "S/A",
            "current_status": "海外龙头验证强",
            "action_use": "决定行业趋势分能否维持高位。",
        },
        {
            "external_variable": "CoWoS/2.5D/3D产能",
            "chain_layer": "封装产能",
            "mechanism": "先进制程芯片要和HBM高密度互连，封装产能成为交付瓶颈。",
            "direct_beneficiaries": "先进封装厂、封装设备、封装基板",
            "a_share_mapping": "长电科技、通富微电、华天科技、盛美上海、芯碁微装",
            "data_to_watch": "先进封装收入占比、capex、良率、客户装载率",
            "evidence_grade": "A",
            "current_status": "扩产明确，A股订单待验证",
            "action_use": "决定观察池是否升级到研究仓。",
        },
        {
            "external_variable": "FC-BGA/ABF/IC载板",
            "chain_layer": "载板",
            "mechanism": "大尺寸封装和高速互连需要更高层数、更低翘曲和更高可靠性的载板。",
            "direct_beneficiaries": "IC载板厂、上游树脂/填料材料",
            "a_share_mapping": "兴森科技、深南电路、联瑞新材、华海诚科",
            "data_to_watch": "客户认证、产线稼动、良率、单价和毛利率",
            "evidence_grade": "A/B",
            "current_status": "国产替代可跟，缺订单硬证据",
            "action_use": "筛选不是泛半导体，而是载板和材料纯度。",
        },
        {
            "external_variable": "玻璃基板/面板级封装",
            "chain_layer": "下一代路线",
            "mechanism": "玻璃基板有望改善尺寸稳定性、互连密度和翘曲问题，但产业化时间更靠后。",
            "direct_beneficiaries": "玻璃基板材料、TGV、设备与验证平台",
            "a_share_mapping": "沃格光电、凯盛科技等只做路线观察",
            "data_to_watch": "样品认证、小批量订单、良率、TGV和客户合作公告",
            "evidence_grade": "B/C",
            "current_status": "题材热度强，产业兑现早期",
            "action_use": "只作为加分项，不作为买入主因。",
        },
        {
            "external_variable": "国产替代与供应链安全",
            "chain_layer": "国内替代",
            "mechanism": "AI芯片国产化会倒逼封测、材料、载板、本土设备认证。",
            "direct_beneficiaries": "本土封测、封装材料、IC载板和设备公司",
            "a_share_mapping": "长电、通富、兴森、华海诚科、联瑞新材",
            "data_to_watch": "国产AI芯片客户、产线导入、收入占比、毛利率",
            "evidence_grade": "B",
            "current_status": "逻辑成立，财报验证不足",
            "action_use": "决定A股可操作分，不决定行业趋势分。",
        },
    ]


def build_industry_signal_log() -> list[dict[str, Any]]:
    return [
        {
            "date": "2026-05-11",
            "signal_type": "market_heat",
            "indicator": "本地细颗粒热点排名",
            "value": "封测#1、先进封装#2、半导体材料#5、玻璃基板#8",
            "direction": "up",
            "affected_layer": "A股映射/市场确认",
            "evidence_grade": "B",
            "status": "已接入",
            "why_it_matters": "市场已从泛半导体收敛到封测、材料、载板等后道瓶颈。",
            "next_check": "每日收盘",
            "source_name": "本地 fine_dashboard",
            "source_url": "/api/market_heat/fine_dashboard?days=63&pool_size=50",
        },
        {
            "date": "2026-01-15",
            "signal_type": "overseas_capex",
            "indicator": "TSMC 2026 capex",
            "value": "520-560亿美元；先进封装/测试/掩模等占10%-20%",
            "direction": "up",
            "affected_layer": "先进封装产能",
            "evidence_grade": "S",
            "status": "已接入",
            "why_it_matters": "龙头用资本开支证明先进封装已经是AI芯片交付瓶颈之一。",
            "next_check": "TSMC下一季法说会",
            "source_name": "TSMC Q4 2025 transcript",
            "source_url": TSMC_Q4_2025_TRANSCRIPT,
        },
        {
            "date": "2026-01-15",
            "signal_type": "overseas_revenue",
            "indicator": "TSMC advanced packaging收入占比",
            "value": "2025略高于10%，2026预计low-teens",
            "direction": "up",
            "affected_layer": "行业趋势验证",
            "evidence_grade": "S",
            "status": "已接入",
            "why_it_matters": "先进封装不是概念，已经进入龙头收入结构。",
            "next_check": "TSMC下一季法说会",
            "source_name": "TSMC Q4 2025 transcript",
            "source_url": TSMC_Q4_2025_TRANSCRIPT,
        },
        {
            "date": "2026-02-09",
            "signal_type": "osat_validation",
            "indicator": "Amkor 2025 results / 2026 capex",
            "value": "2025 advanced packaging和computing收入创新高；2026 capex约25-30亿美元",
            "direction": "up",
            "affected_layer": "海外OSAT/封测",
            "evidence_grade": "S",
            "status": "已接入",
            "why_it_matters": "OSAT 龙头的收入和资本开支验证先进封装需求。",
            "next_check": "Amkor下一季业绩",
            "source_name": "Amkor 2025 results",
            "source_url": AMKOR_2025_RESULTS,
        },
        {
            "date": "2026-04-01",
            "signal_type": "equipment_capex",
            "indicator": "SEMI 300mm fab equipment spending",
            "value": "2026预计+18%至1330亿美元，AI推动HBM需求",
            "direction": "up",
            "affected_layer": "AI算力/HBM/设备",
            "evidence_grade": "A",
            "status": "已接入",
            "why_it_matters": "AI/HBM不是单一公司指引，已扩散到设备资本开支。",
            "next_check": "SEMI下一次展望",
            "source_name": "SEMI",
            "source_url": SEMI_300MM_OUTLOOK,
        },
        {
            "date": "2023-09-18",
            "signal_type": "technology_route",
            "indicator": "Intel glass substrate",
            "value": "计划在本十年后半段推出玻璃基板解决方案",
            "direction": "watch",
            "affected_layer": "玻璃基板/下一代载板",
            "evidence_grade": "A",
            "status": "路线已确认，产业化待验证",
            "why_it_matters": "支撑玻璃基板长期方向，但时间维度不等于当季订单。",
            "next_check": "客户认证/小批量订单",
            "source_name": "Intel",
            "source_url": INTEL_GLASS_SUBSTRATE,
        },
    ]


def build_price_radar() -> list[dict[str, Any]]:
    return [
        {
            "variable": "细颗粒热点前30留存",
            "category": "市场热度",
            "current_value": "2026-05-11封测#1、先进封装#2、材料#5、玻璃基板#8",
            "signal_state": "强",
            "frequency": "日",
            "threshold_buy": "核心链条仍在前30，龙头回踩不破且缩量",
            "threshold_add": "封测/材料连续3日回到前10且有容量票承接",
            "threshold_downgrade": "相关主题连续5个交易日退出前30",
            "why_it_matters": "这是A股可操作性的第一道门槛。",
            "source_name": "本地 fine_dashboard",
            "source_url": "/api/market_heat/fine_dashboard?days=63&pool_size=50",
        },
        {
            "variable": "TSMC advanced packaging收入/CapEx",
            "category": "海外龙头",
            "current_value": "2026收入占比预计low-teens；capex中后道等占10%-20%",
            "signal_state": "强",
            "frequency": "季",
            "threshold_buy": "下一季继续上修或保持强口径",
            "threshold_add": "收入占比继续上行，CoWoS/SoIC产能仍供不应求",
            "threshold_downgrade": "先进封装指引下修或客户拉货放缓",
            "why_it_matters": "决定行业趋势是否仍值得跟。",
            "source_name": "TSMC",
            "source_url": TSMC_Q4_2025_TRANSCRIPT,
        },
        {
            "variable": "Amkor/ASE先进封装订单与CapEx",
            "category": "海外OSAT",
            "current_value": "Amkor 2026 capex约25-30亿美元；ASE扩AI封装合作",
            "signal_state": "偏强",
            "frequency": "季/月",
            "threshold_buy": "capex不下修且computing/advanced packaging收入继续强",
            "threshold_add": "海外OSAT订单与毛利率同时改善",
            "threshold_downgrade": "capex削减或先进封装收入不及预期",
            "why_it_matters": "海外OSAT是A股封测的对标验证。",
            "source_name": "Amkor / ASE",
            "source_url": f"{AMKOR_2025_RESULTS} | {ASE_WUS_AI_PACKAGING}",
        },
        {
            "variable": "A股中报先进封装收入",
            "category": "国内财报",
            "current_value": "待2026中报/业绩会验证",
            "signal_state": "待验证",
            "frequency": "季",
            "threshold_buy": "长电/通富/华天披露先进封装订单、收入或稼动率提升",
            "threshold_add": "毛利率、现金流、订单三项同时改善",
            "threshold_downgrade": "只涨概念，财报没有收入占比和毛利率改善",
            "why_it_matters": "决定A股能否从观察池升级到研究仓。",
            "source_name": "交易所公告",
            "source_url": "https://www.sse.com.cn/ | https://www.szse.cn/",
        },
        {
            "variable": "玻璃基板验证",
            "category": "技术路线",
            "current_value": "路线有海外背书，A股仍偏题材",
            "signal_state": "观察",
            "frequency": "周/月",
            "threshold_buy": "披露客户认证/小批量订单且热点不退潮",
            "threshold_add": "良率、TGV、翘曲指标进入量产验证",
            "threshold_downgrade": "只有涨停，没有订单/良率/客户认证",
            "why_it_matters": "防止把长期技术路线误当短期业绩。",
            "source_name": "Intel / 公司公告",
            "source_url": INTEL_GLASS_SUBSTRATE,
        },
        {
            "variable": "HBM4/AI存储封装进展",
            "category": "需求验证",
            "current_value": "Samsung HBM4商用出货；Micron HBM4高量产/样品",
            "signal_state": "强",
            "frequency": "月/季",
            "threshold_buy": "HBM4出货和AI GPU平台节奏继续匹配",
            "threshold_add": "HBM厂继续扩先进封装能力且订单覆盖2027",
            "threshold_downgrade": "HBM4良率或客户导入显著低于预期",
            "why_it_matters": "HBM堆叠是先进封装需求的硬牵引之一。",
            "source_name": "Samsung / Micron",
            "source_url": f"{SAMSUNG_HBM4} | {MICRON_HBM4}",
        },
    ]


def build_data_source_matrix() -> list[dict[str, Any]]:
    return [
        {
            "module": "市场热度",
            "indicator": "细颗粒主题排名、前30留存、代表票",
            "source": "本地 /api/market_heat/fine_dashboard；fallback fine_theme_heat_daily.db",
            "source_type": "local_market_data",
            "frequency": "日",
            "update_method": "脚本自动读取",
            "status": "已接入",
            "decision_use": "决定当前是否值得盯，以及A股是否过热。",
            "failure_mode": "API不可用时读SQLite；若SQLite滞后则保留用户当日rank seed。",
            "source_url": "/api/market_heat/fine_dashboard?days=63&pool_size=50",
        },
        {
            "module": "海外龙头",
            "indicator": "TSMC advanced packaging收入、capex、AI需求",
            "source": "TSMC quarterly transcript",
            "source_type": "company_official",
            "frequency": "季",
            "update_method": "人工更新URL与摘要",
            "status": "已接入",
            "decision_use": "行业趋势分核心证据。",
            "failure_mode": "若法说会下修需求，行业分直接降级。",
            "source_url": TSMC_Q4_2025_TRANSCRIPT,
        },
        {
            "module": "海外OSAT",
            "indicator": "Amkor/ASE先进封装收入、CapEx、客户扩产",
            "source": "Amkor IR / ASE press room",
            "source_type": "company_official",
            "frequency": "季/月",
            "update_method": "人工更新",
            "status": "已接入",
            "decision_use": "验证封测环节是否真实受益。",
            "failure_mode": "capex下修或毛利率不改善。",
            "source_url": f"{AMKOR_2025_RESULTS} | {ASE_WUS_AI_PACKAGING}",
        },
        {
            "module": "技术路线",
            "indicator": "玻璃基板/面板级封装验证",
            "source": "Intel / 公司公告 / 产业新闻",
            "source_type": "company_official",
            "frequency": "月",
            "update_method": "人工更新",
            "status": "半结构化",
            "decision_use": "只作为长期路线加分，不直接触发买入。",
            "failure_mode": "没有客户认证与良率数据时不升级。",
            "source_url": INTEL_GLASS_SUBSTRATE,
        },
        {
            "module": "A股财报",
            "indicator": "先进封装收入、毛利率、订单、现金流",
            "source": "上交所/深交所公告",
            "source_type": "company_filing",
            "frequency": "季",
            "update_method": "中报/季报后补录",
            "status": "待接入",
            "decision_use": "决定A股可操作分能否从观察升到研究仓。",
            "failure_mode": "只披露概念不披露订单或收入占比。",
            "source_url": "https://www.sse.com.cn/ | https://www.szse.cn/",
        },
    ]


def build_tracking_tasks() -> list[dict[str, Any]]:
    return [
        {
            "task": "细颗粒热点留存",
            "frequency": "每日",
            "priority": "S",
            "current_status": "已接入",
            "watch_variable": "封测/先进封装/半导体材料/玻璃基板是否仍在前30",
            "upgrade_trigger": "连续3日有2个以上相关主题前10",
            "add_position_trigger": "强热点回踩不破，代表票放量承接",
            "downgrade_trigger": "连续5日退出前30或只剩玻璃基板题材票",
            "owner_note": "这是外露动态变量，不放hover。",
            "source_url": "/api/market_heat/fine_dashboard?days=63&pool_size=50",
        },
        {
            "task": "TSMC先进封装验证",
            "frequency": "每季",
            "priority": "S",
            "current_status": "已接入",
            "watch_variable": "advanced packaging收入占比、capex、客户需求",
            "upgrade_trigger": "收入占比/产能继续上行",
            "add_position_trigger": "海外口径强且A股封测回踩确认",
            "downgrade_trigger": "TSMC下修AI或advanced packaging指引",
            "owner_note": "行业分的硬锚。",
            "source_url": TSMC_Q4_2025_TRANSCRIPT,
        },
        {
            "task": "A股中报订单验证",
            "frequency": "季报/中报",
            "priority": "S",
            "current_status": "待公告",
            "watch_variable": "先进封装收入、毛利率、订单、现金流",
            "upgrade_trigger": "长电/通富/华天至少两家披露真实增量",
            "add_position_trigger": "订单和毛利率同步改善，且估值消化",
            "downgrade_trigger": "财报没有收入占比、毛利率或现金流支撑",
            "owner_note": "没有财报验证不升研究仓。",
            "source_url": "https://www.sse.com.cn/ | https://www.szse.cn/",
        },
        {
            "task": "IC载板/封装材料导入",
            "frequency": "月/季",
            "priority": "A",
            "current_status": "观察",
            "watch_variable": "FC-BGA、ABF、GMC、球形硅微粉客户认证和放量",
            "upgrade_trigger": "客户认证转订单，产能利用率提升",
            "add_position_trigger": "材料公司毛利率随高端产品占比提升",
            "downgrade_trigger": "订单仍停留在送样/认证，收入不兑现",
            "owner_note": "用于筛掉泛材料票。",
            "source_url": "https://www.sse.com.cn/ | https://www.szse.cn/",
        },
        {
            "task": "玻璃基板路线验证",
            "frequency": "周/月",
            "priority": "A",
            "current_status": "早期",
            "watch_variable": "客户认证、小批量订单、TGV/翘曲/良率数据",
            "upgrade_trigger": "有客户或量产节点公告",
            "add_position_trigger": "从题材票扩散到设备/材料订单",
            "downgrade_trigger": "涨停退潮且没有订单/良率进展",
            "owner_note": "路线长期重要，但短期不当主因。",
            "source_url": INTEL_GLASS_SUBSTRATE,
        },
    ]


def build_decision_summary(updated_at: str, industry_score: float, operability_score: float) -> list[dict[str, Any]]:
    return [
        {
            "updated_at": updated_at,
            "topic_id": TOPIC_ID,
            "topic_name": TOPIC_NAME,
            "industry_trend_score": industry_score,
            "industry_trend_max": 100,
            "a_share_operability_score": operability_score,
            "a_share_operability_max": 100,
            "conclusion": "值得跟，但不是无脑追高买点",
            "industry_status": "行业趋势较强",
            "operability_state": "观察池 / 等订单和分歧",
            "current_view": "AI算力需求、海外先进封装capex和本地热点共振，趋势进入跟踪池；A股仍缺中报订单/良率验证，当前更适合监控盘跟踪。",
            "block_reason": "玻璃基板等分支题材热度高于产业兑现；A股封测和材料需要确认先进封装收入占比、毛利率、现金流。",
            "next_trigger": "封测/先进封装热点连续留在前30，同时TSMC/Amkor下一季维持强指引，A股中报披露订单或毛利率改善。",
            "stage": "预期扩散 / 订单验证前",
            "next_stage": "订单 / 财报验证期",
            "next_stage_conditions": "长电/通富/华天或载板/材料公司披露AI/HPC先进封装订单、收入占比提升、毛利率改善；玻璃基板出现客户认证或小批量订单。",
            "downgrade_conditions": "相关热点连续5日退出前30；海外龙头下修advanced packaging或AI/HBM指引；A股只炒概念但中报无订单、收入占比和毛利率验证。",
        }
    ]


def build_score_history(path: Path, run_date: str, industry_score: float, operability_score: float) -> list[dict[str, Any]]:
    rows = read_csv(path)
    rows = [row for row in rows if row.get("date") != run_date]
    rows.append(
        {
            "date": run_date,
            "topic_id": TOPIC_ID,
            "industry_trend_score": industry_score,
            "a_share_operability_score": operability_score,
            "stage": "预期扩散 / 订单验证前",
            "conclusion": "值得跟，但不是无脑追高买点",
            "change_note": "初始基线：行业证据强，A股等订单和分歧。",
        }
    )
    return sorted(rows, key=lambda row: row.get("date", ""))


def render_report(
    run_date: str,
    decision: dict[str, Any],
    factor_rows: list[dict[str, Any]],
    heat: list[dict[str, Any]],
    company_research: list[dict[str, Any]],
    watchlist: list[dict[str, Any]],
    price_radar: list[dict[str, Any]],
    score_history: list[dict[str, Any]],
) -> str:
    lines = [
        f"# AI先进封装与材料长期趋势跟踪日报（{run_date}）",
        "",
        "## 1. 当前判断",
        f"- 行业趋势分：{decision['industry_trend_score']}/100，{decision['industry_status']}。",
        f"- A股可操作分：{decision['a_share_operability_score']}/100，{decision['operability_state']}。",
        f"- 当前结论：{decision['conclusion']}。",
        f"- 卡住原因：{decision['block_reason']}",
        f"- 下一触发：{decision['next_trigger']}",
        "",
        "## 2. 六因子评分卡",
        "| 因子 | 得分 | 状态 | 为什么影响趋势 | 之后盯什么 |",
        "|---|---:|---|---|---|",
    ]
    for row in factor_rows:
        lines.append(
            f"| {row['factor']} | {row['current_points']}/{row['max_points']} | {row['status']} | "
            f"{row['meaning']} | {row['watch_focus']} |"
        )

    lines += [
        "",
        "## 3. 本地热点确认",
        "| 排名 | 主题 | 热度 | 持续 | 63日前30 | 5日 | 20日 | 代表票 |",
        "|---:|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in heat:
        lines.append(
            f"| {row['rank']} | {row['theme_name']} | {row['hot_score'] or '--'} | "
            f"{row['persistence_score'] or '--'} | {row['top30_days_63d']} | "
            f"{row['latest_return_5d'] or '--'}% | {row['latest_return_20d'] or '--'}% | "
            f"{row['leader_name'] or '--'} |"
        )

    lines += [
        "",
        "## 4. 动态变量",
        "| 变量 | 当前状态 | 买入观察条件 | 加仓条件 | 降级条件 |",
        "|---|---|---|---|---|",
    ]
    for row in price_radar:
        lines.append(
            f"| {row['variable']} | {row['current_value']} | {row['threshold_buy']} | "
            f"{row['threshold_add']} | {row['threshold_downgrade']} |"
        )

    lines += [
        "",
        "## 5. 产业分支与公司池逻辑",
        "- 先拆产业分支，再判断公司是否进入观察池；公司池按分层、动作和验证点管理。",
        "- 进入观察池只看三件事：利润传导是否直接、下一项验证是否清楚、当前动作是否可执行。",
        "- 未进入观察池的公司仍保留研究卡，用来校验分支宽度、题材扩散和证伪条件。",
        "",
        "| 分支 | 公司 | 当前处理 | 为什么这样放 | 下一步看什么 |",
        "|---|---|---|---|---|",
    ]
    branch_order = ["先进封装/封测", "IC载板/ABF", "封装材料", "玻璃基板", "设备"]
    for branch in branch_order:
        names = [row["name"] for row in company_research if row.get("branch") == branch]
        if not names:
            continue
        in_pool = [row["name"] for row in company_research if row.get("branch") == branch and row.get("include_decision") == "进入观察池"]
        kept = "、".join(in_pool) if in_pool else "无"
        lines.append(
            f"| {branch} | {'、'.join(names)} | 观察池：{kept} | "
            f"同一分支内先区分直接利润兑现、间接受益和题材映射，避免把整条链都放进池。 | "
            "订单、收入占比、毛利率、客户认证 |"
        )

    lines += [
        "",
        "## 6. 观察池",
        "| 股票 | 层级 | 分支 | 入池理由 | 当前动作 | 下一步数据 |",
        "|---|---|---|---|---|---|",
    ]
    for row in watchlist:
        lines.append(
            f"| {row['name']} `{row['symbol']}` | {row['pool_tier']} | {row['branch']} | "
            f"{row['trend_link']} {row['profit_driver']} | {row['action']} | {row['next_data_to_watch']} |"
        )

    lines += [
        "",
        "## 7. 未入池/旁路逻辑",
        "| 股票 | 处理 | 分支 | 不进入观察池的原因 | 后续触发 |",
        "|---|---|---|---|---|",
    ]
    for row in company_research:
        if row.get("include_decision") == "进入观察池":
            continue
        lines.append(
            f"| {row['name']} `{row['symbol']}` | {row['include_decision']} / {row['pool_tier']} | "
            f"{row['branch']} | {row['key_risk']} | {row['next_data_to_watch']} |"
        )

    lines += [
        "",
        "## 8. 买入/加仓/降级口径",
        f"- 阶段：{decision['stage']}，下一阶段：{decision['next_stage']}。",
        f"- 买入观察：{decision['next_stage_conditions']}",
        "- 加仓：海外先进封装指引继续强，A股订单/毛利率/现金流同时确认，并且核心票经过分歧后重新承接。",
        f"- 降级：{decision['downgrade_conditions']}",
        "",
        "## 9. 数据来源",
        "- 本地市场热度：`/api/market_heat/fine_dashboard?days=63&pool_size=50`，fallback `fine_theme_heat_daily.db`。",
        f"- TSMC：{TSMC_Q4_2025_TRANSCRIPT}",
        f"- Amkor：{AMKOR_2025_RESULTS}",
        f"- SEMI：{SEMI_300MM_OUTLOOK}",
        f"- Intel glass substrate：{INTEL_GLASS_SUBSTRATE}",
        f"- ASE：{ASE_WUS_AI_PACKAGING}",
        f"- Samsung HBM4：{SAMSUNG_HBM4}",
        f"- Micron HBM4：{MICRON_HBM4}",
        "",
        "## 10. 分数历史",
    ]
    for row in score_history[-5:]:
        lines.append(
            f"- {row['date']}：行业 {row['industry_trend_score']} / A股 {row['a_share_operability_score']} / {row['conclusion']}"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=DEFAULT_RUN_DATE, help="snapshot date, YYYY-MM-DD")
    args = parser.parse_args()

    run_date = args.date
    updated_at = now_text()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOC_DIR.mkdir(parents=True, exist_ok=True)

    heat_stats = load_heat_stats(HEAT_RANK_SEED_20260511)
    market_heat = heat_rows(heat_stats, updated_at)
    factor_rows = build_factor_scorecard(heat_stats)
    industry_score = round(sum(float(row["current_points"]) for row in factor_rows), 1)
    operability_score = 46.0
    decision_rows = build_decision_summary(updated_at, industry_score, operability_score)
    company_research = build_company_research()
    watchlist = build_watchlist(company_research)
    chain_layers = build_chain_layers()
    signal_log = build_industry_signal_log()
    price_radar = build_price_radar()
    data_sources = build_data_source_matrix()
    tracking_tasks = build_tracking_tasks()
    score_history_path = DATA_DIR / "ai_advanced_packaging_score_history.csv"
    score_history = build_score_history(score_history_path, run_date, industry_score, operability_score)

    decision_fields = [
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
    factor_fields = [
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
    heat_fields = [
        "updated_at",
        "heat_date",
        "theme_name",
        "rank",
        "hot_score",
        "persistence_score",
        "top15_days_63d",
        "top30_days_63d",
        "latest_return_5d",
        "latest_return_20d",
        "amount_yi",
        "l2_main_net_yi",
        "leader_name",
        "signal_state",
        "meaning",
        "source_basis",
    ]
    chain_fields = [
        "external_variable",
        "chain_layer",
        "mechanism",
        "direct_beneficiaries",
        "a_share_mapping",
        "data_to_watch",
        "evidence_grade",
        "current_status",
        "action_use",
    ]
    signal_fields = [
        "date",
        "signal_type",
        "indicator",
        "value",
        "direction",
        "affected_layer",
        "evidence_grade",
        "status",
        "why_it_matters",
        "next_check",
        "source_name",
        "source_url",
    ]
    price_fields = [
        "variable",
        "category",
        "current_value",
        "signal_state",
        "frequency",
        "threshold_buy",
        "threshold_add",
        "threshold_downgrade",
        "why_it_matters",
        "source_name",
        "source_url",
    ]
    data_source_fields = [
        "module",
        "indicator",
        "source",
        "source_type",
        "frequency",
        "update_method",
        "status",
        "decision_use",
        "failure_mode",
        "source_url",
    ]
    task_fields = [
        "task",
        "frequency",
        "priority",
        "current_status",
        "watch_variable",
        "upgrade_trigger",
        "add_position_trigger",
        "downgrade_trigger",
        "owner_note",
        "source_url",
    ]
    history_fields = [
        "date",
        "topic_id",
        "industry_trend_score",
        "a_share_operability_score",
        "stage",
        "conclusion",
        "change_note",
    ]

    write_csv(DATA_DIR / f"ai_advanced_packaging_decision_summary_{run_date}.csv", decision_rows, decision_fields)
    write_csv(DATA_DIR / f"ai_advanced_packaging_factor_scorecard_{run_date}.csv", factor_rows, factor_fields)
    write_csv(DATA_DIR / f"ai_advanced_packaging_market_heat_{run_date}.csv", market_heat, heat_fields)
    write_csv(DATA_DIR / f"ai_advanced_packaging_company_research_{run_date}.csv", company_research, COMPANY_RESEARCH_FIELDS)
    write_csv(DATA_DIR / "ai_advanced_packaging_watchlist.csv", watchlist, COMPANY_RESEARCH_FIELDS)
    write_csv(DATA_DIR / "ai_advanced_packaging_score_history.csv", score_history, history_fields)
    write_csv(DATA_DIR / "chain_layers.csv", chain_layers, chain_fields)
    write_csv(DATA_DIR / "industry_signal_log.csv", signal_log, signal_fields)
    write_csv(DATA_DIR / "price_radar.csv", price_radar, price_fields)
    write_csv(DATA_DIR / "a_share_mapping_score.csv", company_research, COMPANY_RESEARCH_FIELDS)
    write_csv(DATA_DIR / "data_source_matrix.csv", data_sources, data_source_fields)
    write_csv(DATA_DIR / "tracking_tasks.csv", tracking_tasks, task_fields)

    report = render_report(
        run_date=run_date,
        decision=decision_rows[0],
        factor_rows=factor_rows,
        heat=market_heat,
        company_research=company_research,
        watchlist=watchlist,
        price_radar=price_radar,
        score_history=score_history,
    )
    report_path = DOC_DIR / f"ai_advanced_packaging_tracking_report_{run_date}.md"
    report_path.write_text(report, encoding="utf-8")

    print(f"wrote {DATA_DIR}")
    print(f"wrote {report_path}")
    print(f"industry_score={industry_score} operability_score={operability_score}")


if __name__ == "__main__":
    main()
