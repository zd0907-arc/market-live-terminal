#!/usr/bin/env python3
"""Build robot actuator / reducer long-term trend tracking assets.

Outputs CSV + Markdown under:
- data/selection/long_term_trends/robot_actuator
- docs/selection/long_term_trends/robot_actuator

This is research tracking only. It does not change app routing or services.
"""
from __future__ import annotations

import csv
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from backend.app.core.config import RESEARCH_CURRENT_ROOT

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data/selection/long_term_trends/robot_actuator"
DOC_DIR = ROOT / "docs/selection/long_term_trends/robot_actuator"
HEAT_DB = Path(RESEARCH_CURRENT_ROOT) / "market_heat" / "fine_theme_heat_daily.db"
LITONG_CSV = ROOT / "data/selection/litong_similarity/litong_similarity_all_20260331_20260430.csv"
LOCAL_TZ = ZoneInfo("Asia/Shanghai")
RUN_DATE = os.getenv("TREND_RUN_DATE", "2026-05-11")
UPDATED_AT = f"{RUN_DATE} {datetime.now(LOCAL_TZ).strftime('%H:%M')} Asia/Shanghai"

TESLA_Q1_PDF_URL = "https://electrek.co/wp-content/uploads/sites/3/2026/04/TSLA-Q1-2026-Update.pdf"
TESLA_CALL_URL = "https://electrek.co/2026/04/22/tesla-optimus-production-fremont-model-sx-line/"
MIIT_HUMANOID_URL = "https://www.miit.gov.cn/jgsj/kjs/wjfb/art/2023/art_50316f76a9b1454b898c7bb2a5846b79.html"
IFR_WR2025_URL = "https://ifr.org/ifr-press-releases/news/global-robot-demand-in-factories-doubles-over-10-years%20%20%20"
SANHUA_IR_URL = "https://static.cninfo.com.cn/finalpage/2025-03-27/1222929865.PDF"
SHUANGHUAN_IR_URL = "https://static.cninfo.com.cn/finalpage/2025-05-06/1223478836.PDF"
LEADERDRIVE_SSE_URL = "https://star.sse.com.cn/star/en/marketdata/snapshot/c/5545073.shtml"
BEITE_DISCLOSURE_URL = "https://www.sse.com.cn/assortment/stock/list/info/company/index.shtml?COMPANY_CODE=603009"
WUZHOU_DISCLOSURE_URL = "https://www.sse.com.cn/assortment/stock/list/info/company/index.shtml?COMPANY_CODE=603667"
BEST_DISCLOSURE_URL = "https://www.cninfo.com.cn/new/disclosure/stock?stockCode=300580"
TUOPU_SUSTAINABILITY_URL = "https://www.tuopu.com/wp-content/uploads/2026/04/%E6%8B%93%E6%99%AE%E9%9B%86%E5%9B%A22025%E5%B9%B4%E5%BA%A6%E5%8F%AF%E6%8C%81%E7%BB%AD%E5%8F%91%E5%B1%95%E6%8A%A5%E5%91%8A.pdf"
MINGZHI_DISCLOSURE_URL = "https://www.sse.com.cn/disclosure/listedinfo/regular/"
LEADSHINE_DISCLOSURE_URL = "https://www.cninfo.com.cn/new/disclosure/stock?stockCode=002979"
ZHONGDA_IR_URL = "https://money.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=12274854&stockid=002896"
HAOZHI_DISCLOSURE_URL = "https://www.cninfo.com.cn/new/disclosure/stock?stockCode=300503"
INOVANCE_DISCLOSURE_URL = "https://www.cninfo.com.cn/new/disclosure/stock?stockCode=300124"
ESTUN_DISCLOSURE_URL = "https://www.cninfo.com.cn/new/disclosure/stock?stockCode=002747"

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


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def fmt(value: Any, digits: int = 1) -> str:
    try:
        num = float(value)
    except Exception:
        return ""
    return f"{num:.{digits}f}".rstrip("0").rstrip(".")


def load_litong_snapshot() -> dict[str, dict[str, str]]:
    rows = read_csv(LITONG_CSV)
    return {row.get("symbol", ""): row for row in rows if row.get("symbol")}


def build_market_heat() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    fields = [
        "updated_at",
        "window_start",
        "window_end",
        "sector_name",
        "days_seen",
        "top30_days",
        "best_rank",
        "avg_rank",
        "avg_hot_score",
        "avg_persistence_score",
        "avg_return_5d",
        "avg_amount_ratio",
        "avg_l2_main_net_yi",
        "avg_l2_positive_ratio",
        "last_seen",
        "signal_meaning",
    ]
    if not HEAT_DB.exists():
        return [], {
            "fields": fields,
            "summary": "本地热度库缺失，热点持续性按保守分处理。",
            "hits": 0,
            "active_days": 0,
            "top30_hits": 0,
            "best_rank": "",
            "avg_hot": 0.0,
            "avg_persist": 0.0,
            "last_seen": "",
            "window_start": "",
            "window_end": "",
        }

    conn = sqlite3.connect(f"file:{HEAT_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    latest_dates = [
        row["trade_date"]
        for row in conn.execute(
            "select distinct trade_date from fine_theme_heat_daily order by trade_date desc limit 63"
        )
    ]
    latest_dates = sorted(latest_dates)
    if not latest_dates:
        conn.close()
        return [], {
            "fields": fields,
            "summary": "本地热度库无交易日，热点持续性按保守分处理。",
            "hits": 0,
            "active_days": 0,
            "top30_hits": 0,
            "best_rank": "",
            "avg_hot": 0.0,
            "avg_persist": 0.0,
            "last_seen": "",
            "window_start": "",
            "window_end": "",
        }

    params = latest_dates
    placeholders = ",".join("?" for _ in params)
    keyword_filter = """
        hot_rank <= 50
        and (
            sector_name like '%机器人%'
            or sector_name like '%减速器%'
            or sector_name like '%执行器%'
            or sector_name like '%丝杠%'
            or sector_name like '%自动化设备%'
        )
    """
    sector_rows = conn.execute(
        f"""
        select
            sector_name,
            count(*) as days_seen,
            sum(case when hot_rank <= 30 then 1 else 0 end) as top30_days,
            min(hot_rank) as best_rank,
            avg(hot_rank) as avg_rank,
            avg(hot_score) as avg_hot_score,
            avg(persistence_score) as avg_persistence_score,
            avg(avg_return_5d) as avg_return_5d,
            avg(amount_ratio) as avg_amount_ratio,
            avg(l2_main_net_yi) as avg_l2_main_net_yi,
            avg(l2_positive_ratio) as avg_l2_positive_ratio,
            max(trade_date) as last_seen
        from fine_theme_heat_daily
        where trade_date in ({placeholders}) and {keyword_filter}
        group by sector_name
        order by days_seen desc, best_rank asc
        """,
        params,
    ).fetchall()
    summary_row = conn.execute(
        f"""
        select
            count(*) as hits,
            count(distinct trade_date) as active_days,
            sum(case when hot_rank <= 30 then 1 else 0 end) as top30_hits,
            min(hot_rank) as best_rank,
            avg(hot_rank) as avg_rank,
            avg(hot_score) as avg_hot,
            avg(persistence_score) as avg_persist,
            avg(avg_return_5d) as avg_5d,
            avg(l2_main_net_yi) as avg_l2,
            avg(l2_positive_ratio) as avg_l2_pos,
            max(trade_date) as last_seen
        from fine_theme_heat_daily
        where trade_date in ({placeholders}) and {keyword_filter}
        """,
        params,
    ).fetchone()
    conn.close()

    rows: list[dict[str, Any]] = []
    for row in sector_rows:
        rows.append(
            {
                "updated_at": UPDATED_AT,
                "window_start": latest_dates[0],
                "window_end": latest_dates[-1],
                "sector_name": row["sector_name"],
                "days_seen": row["days_seen"],
                "top30_days": row["top30_days"],
                "best_rank": row["best_rank"],
                "avg_rank": fmt(row["avg_rank"]),
                "avg_hot_score": fmt(row["avg_hot_score"]),
                "avg_persistence_score": fmt(row["avg_persistence_score"]),
                "avg_return_5d": fmt(row["avg_return_5d"], 2),
                "avg_amount_ratio": fmt(row["avg_amount_ratio"], 2),
                "avg_l2_main_net_yi": fmt(row["avg_l2_main_net_yi"], 2),
                "avg_l2_positive_ratio": fmt(row["avg_l2_positive_ratio"]),
                "last_seen": row["last_seen"],
                "signal_meaning": heat_signal_meaning(row["sector_name"], row["last_seen"], row["top30_days"]),
            }
        )

    summary = {
        "fields": fields,
        "hits": int(summary_row["hits"] or 0),
        "active_days": int(summary_row["active_days"] or 0),
        "top30_hits": int(summary_row["top30_hits"] or 0),
        "best_rank": summary_row["best_rank"] or "",
        "avg_rank": round(float(summary_row["avg_rank"] or 0), 1),
        "avg_hot": round(float(summary_row["avg_hot"] or 0), 1),
        "avg_persist": round(float(summary_row["avg_persist"] or 0), 1),
        "avg_5d": round(float(summary_row["avg_5d"] or 0), 2),
        "avg_l2": round(float(summary_row["avg_l2"] or 0), 2),
        "avg_l2_pos": round(float(summary_row["avg_l2_pos"] or 0), 1),
        "last_seen": summary_row["last_seen"] or "",
        "window_start": latest_dates[0],
        "window_end": latest_dates[-1],
    }
    summary["summary"] = (
        f"近63个交易日窗口（{summary['window_start']}至{summary['window_end']}）内，机器人/执行器/减速器相关细分主题"
        f"进入Top50共{summary['hits']}次、覆盖{summary['active_days']}个交易日、Top30共{summary['top30_hits']}次，"
        f"最佳排名第{summary['best_rank']}，平均热度{summary['avg_hot']}。"
    )
    return rows, summary


def heat_signal_meaning(sector_name: str, last_seen: str, top30_days: int) -> str:
    if "机器人执行器" in sector_name:
        return "最贴近本主题，4月多次Top30，说明市场已经开始交易执行器线索。"
    if "减速器" in sector_name:
        return "减速器出现次数少但方向直接，后续要看是否从单日脉冲变成连续热点。"
    if sector_name == "机器人":
        return "宽主题重新出现，能给执行器/减速器带来扩散，但需要过滤纯概念股。"
    if "虚拟机器人" in sector_name:
        return "热度强但与硬件链不完全等同，只作为情绪外溢信号。"
    if "自动化设备" in sector_name:
        return "制造业自动化底座偏强，但不能直接等同于人形机器人执行器订单。"
    return f"最后出现于{last_seen}，作为旁路热度观察。"


def build_company_research() -> list[dict[str, Any]]:
    return [
        {
            "symbol": "sh688017",
            "name": "绿的谐波",
            "include_decision": "进入观察池",
            "pool_tier": "核心跟踪",
            "branch": "谐波/精密减速器",
            "business_summary": "国内谐波减速器龙头，收入和利润对精密传动景气更敏感。",
            "trend_link": "人形机器人关节传动需要高精度减速器，是执行器BOM里最直接的A股映射之一。",
            "profit_driver": "利润主要来自谐波减速器出货、产能利用率和毛利率；机器人订单如果批量化，会直接影响收入弹性。",
            "growth_space": "成长空间来自国产替代、机器人客户批量订单和规模降本，不来自单纯概念扩散。",
            "valuation_snapshot": "市场已按核心零部件稀缺性定价，估值容错不高，适合跟踪验证而不是追高。",
            "latest_validation": "公司持续被市场作为谐波减速器核心标的跟踪；下一步要用订单、产能利用率和毛利率验证。",
            "key_risk": "若人形机器人订单落地慢，或减速器价格战压缩毛利，纯度反而会放大股价波动。",
            "next_data_to_watch": "机器人客户订单、出货量、产能利用率、谐波减速器毛利率、中报机器人相关描述。",
            "action": "核心跟踪，不追高；只在订单或分歧后承接信号出现时升级动作。",
            "source_url": LEADERDRIVE_SSE_URL,
        },
        {
            "symbol": "sz002472",
            "name": "双环传动",
            "include_decision": "进入观察池",
            "pool_tier": "核心跟踪",
            "branch": "谐波/精密减速器",
            "business_summary": "精密齿轮和传动件公司，汽车齿轮是基本盘，智能执行机构提供机器人链映射。",
            "trend_link": "精密传动能力可迁移到机器人减速器和执行机构，是减速器分支里比纯概念更有产业基础的标的。",
            "profit_driver": "利润来自汽车齿轮基本盘和智能执行机构增量；趋势影响利润的关键是新业务收入占比和毛利率能否上来。",
            "growth_space": "成长空间来自智能执行机构收入增长、客户拓展和份额提升。",
            "valuation_snapshot": "基本盘较厚，估值压力比纯小票可控，但机器人弹性需要收入拆分验证。",
            "latest_validation": "投资者关系材料提到智能执行机构收入高增，是比样机故事更强的验证，但仍需拆机器人贡献。",
            "key_risk": "智能执行机构高增若主要来自非人形机器人或汽车链，主题弹性会被高估。",
            "next_data_to_watch": "智能执行机构收入、机器人客户、毛利率、公告后价格承接。",
            "action": "进入核心观察池，等回踩承接和收入拆分验证。",
            "source_url": SHUANGHUAN_IR_URL,
        },
        {
            "symbol": "sh603009",
            "name": "北特科技",
            "include_decision": "进入观察池",
            "pool_tier": "高弹性观察",
            "branch": "丝杠/轴承",
            "business_summary": "汽车零部件公司，市场主要跟踪其滚柱丝杠和精密部件的人形机器人映射。",
            "trend_link": "滚柱丝杠是线性执行器关键部件之一，若客户验证走向批量，会成为丝杠分支高弹性标的。",
            "profit_driver": "当前利润仍靠原有汽车零部件，机器人丝杠要等客户认证、良率和量产订单才能影响利润。",
            "growth_space": "成长空间来自样件验证转批量订单、产线投放和份额想象。",
            "valuation_snapshot": "交易的是订单预期和小基数弹性，估值对延迟验证很敏感。",
            "latest_validation": "市场关注滚柱丝杠样件和客户验证进度，但可确认的收入占比仍不足。",
            "key_risk": "样件不等于定点，定点不等于批量收入；若中报仍无订单证据，需要降级。",
            "next_data_to_watch": "客户认证、批量订单、丝杠产线资本开支、收入占比。",
            "action": "保留高弹性观察，只看订单验证，不按概念加权。",
            "source_url": BEITE_DISCLOSURE_URL,
        },
        {
            "symbol": "sh603667",
            "name": "五洲新春",
            "include_decision": "进入观察池",
            "pool_tier": "高弹性观察",
            "branch": "丝杠/轴承",
            "business_summary": "轴承、精密零部件公司，机器人方向主要看丝杠、轴承和精密加工能力。",
            "trend_link": "丝杠和轴承处在线性执行与关节传动的基础件位置，受益于机器人执行器放量。",
            "profit_driver": "利润来源仍是轴承和精密件基本盘；机器人业务影响利润要靠订单规模和良率。",
            "growth_space": "成长空间来自丝杠/轴承客户验证、量产良率、产品结构升级。",
            "valuation_snapshot": "题材弹性较强，市场容易提前交易量产想象，估值需要订单兑现托底。",
            "latest_validation": "机器人零部件和丝杠方向被反复关注，但缺少连续订单和财务拆分。",
            "key_risk": "若只有产业链布局没有可披露订单，股价弹性会先于利润透支。",
            "next_data_to_watch": "丝杠订单、机器人客户、轴承/丝杠收入拆分、毛利率变化。",
            "action": "进入观察池，但定位高弹性，不作为核心确定性仓位。",
            "source_url": WUZHOU_DISCLOSURE_URL,
        },
        {
            "symbol": "sz002050",
            "name": "三花智控",
            "include_decision": "进入观察池",
            "pool_tier": "核心跟踪",
            "branch": "执行器总成",
            "business_summary": "热管理龙头，机器人方向重点在机电执行器和总成能力。",
            "trend_link": "执行器总成直接连接电机、传动、控制和结构件，是人形机器人硬件链的中军型映射。",
            "profit_driver": "利润主要由热管理主业贡献；机器人执行器若量产，会通过新客户和总成出货形成增量。",
            "growth_space": "成长空间来自客户研发试制转量产、平台化总成能力和份额提升。",
            "valuation_snapshot": "大市值中军，估值已包含部分机器人预期，短期弹性不如小票但验证价值更高。",
            "latest_validation": "投资者关系记录明确聚焦机电执行器，并配合客户研发、试制、迭代至量产落地。",
            "key_risk": "机器人收入占比可能长期较低，主业估值和机器人叙事容易互相拉扯。",
            "next_data_to_watch": "客户量产节点、执行器收入披露、资本开支、毛利率和订单节奏。",
            "action": "作为执行器总成中军进入观察池，只在量产证据增强时加权。",
            "source_url": SANHUA_IR_URL,
        },
        {
            "symbol": "sz300580",
            "name": "贝斯特",
            "include_decision": "暂不进入",
            "pool_tier": "间接受益",
            "branch": "丝杠/轴承",
            "business_summary": "精密零部件和智能装备公司，市场关注滚柱丝杠、精密加工和产能布局。",
            "trend_link": "公司处在线性执行器精密加工链，能受益于丝杠国产化和机器人零部件放量。",
            "profit_driver": "利润主要来自原有精密零部件；机器人链贡献取决于新产能爬坡和客户订单。",
            "growth_space": "成长空间来自产能建设、客户定点和订单从验证转收入。",
            "valuation_snapshot": "有产业位置，但机器人收入证明不足，估值不能直接按纯丝杠标的处理。",
            "latest_validation": "投资者关系和公告侧重精密部件、丝杠能力与产能建设，财务端仍待验证。",
            "key_risk": "产能先行而订单滞后，或机器人收入占比太低。",
            "next_data_to_watch": "丝杠产能、客户定点、机器人相关收入、设备利用率。",
            "action": "暂不进入观察池，作为丝杠链间接受益保留研究卡。",
            "source_url": BEST_DISCLOSURE_URL,
        },
        {
            "symbol": "sh601689",
            "name": "拓普集团",
            "include_decision": "旁路观察",
            "pool_tier": "间接受益",
            "branch": "执行器总成",
            "business_summary": "汽车零部件平台型公司，机器人方向看客户协同、执行器和制造能力迁移。",
            "trend_link": "具备大客户配套和制造体系，可能参与机器人执行器或结构件，但与减速器/丝杠纯度不高。",
            "profit_driver": "利润主要来自汽车零部件；机器人业务短期更像估值想象而非财务主驱动。",
            "growth_space": "成长空间来自客户项目、产线落地和平台制造能力外溢。",
            "valuation_snapshot": "大票估值受汽车业务和机器人预期共同影响，执行器逻辑难单独定价。",
            "latest_validation": "公司公开材料强调平台化制造和可持续发展，机器人具体收入验证不足。",
            "key_risk": "机器人线索无法独立影响利润，容易被汽车主业周期覆盖。",
            "next_data_to_watch": "机器人客户、执行器产线、项目定点、收入披露。",
            "action": "旁路观察，只在客户/产线明确后再考虑进入观察池。",
            "source_url": TUOPU_SUSTAINABILITY_URL,
        },
        {
            "symbol": "sh603728",
            "name": "鸣志电器",
            "include_decision": "暂不进入",
            "pool_tier": "间接受益",
            "branch": "电机/控制",
            "business_summary": "控制电机及驱动系统公司，产品覆盖步进、电机、驱动和控制。",
            "trend_link": "执行器需要电机和驱动控制，鸣志处在电机分支，但不是减速器或丝杠核心环节。",
            "profit_driver": "利润来自电机和驱动产品；机器人订单若进入批量，会改善产品结构和需求弹性。",
            "growth_space": "成长空间来自空心杯/控制电机进入机器人客户、海外与工业自动化需求恢复。",
            "valuation_snapshot": "估值取决于电机景气和机器人订单，当前更适合等客户批量证据。",
            "latest_validation": "市场持续关注其机器人电机映射，但收入端需要和自动化需求区分。",
            "key_risk": "电机订单如果主要来自传统自动化，机器人弹性会被高估。",
            "next_data_to_watch": "机器人客户订单、电机新品、收入结构、毛利率。",
            "action": "暂不进入观察池，等电机订单验证。",
            "source_url": MINGZHI_DISCLOSURE_URL,
        },
        {
            "symbol": "sz002979",
            "name": "雷赛智能",
            "include_decision": "暂不进入",
            "pool_tier": "间接受益",
            "branch": "电机/控制",
            "business_summary": "运动控制、伺服驱动和控制系统公司，服务自动化设备客户。",
            "trend_link": "机器人执行器需要运动控制和驱动，但公司更偏自动化底座，和人形机器人执行器订单距离较远。",
            "profit_driver": "利润来自伺服、步进和控制产品；趋势影响利润需要机器人客户放量而非泛自动化复苏。",
            "growth_space": "成长空间来自伺服产品升级、机器人客户拓展和自动化需求恢复。",
            "valuation_snapshot": "估值更像自动化周期票，机器人题材只能作为附加项。",
            "latest_validation": "控制/伺服业务具备底座属性，但暂无足够证据证明人形机器人收入弹性。",
            "key_risk": "把自动化景气误判为机器人订单，会造成主题错配。",
            "next_data_to_watch": "机器人客户收入、伺服订单、下游自动化景气、价格趋势。",
            "action": "暂不进入观察池，保留为电机控制分支样本。",
            "source_url": LEADSHINE_DISCLOSURE_URL,
        },
        {
            "symbol": "sz002896",
            "name": "中大力德",
            "include_decision": "旁路观察",
            "pool_tier": "题材映射",
            "branch": "谐波/精密减速器",
            "business_summary": "小型减速器、电机和传动产品公司，具备机器人执行单元题材映射。",
            "trend_link": "产品接近减速器和执行单元，但公司规模和利润承接能力需要谨慎验证。",
            "profit_driver": "利润来自减速器、电机及机电一体化产品；机器人趋势只有在订单放量时才会改善利润质量。",
            "growth_space": "成长空间来自机器人减速器和执行单元订单，也来自市场对小型传动件的弹性想象。",
            "valuation_snapshot": "题材弹性强，基本面证明不足时估值容易大幅波动。",
            "latest_validation": "投资者关系材料多次提及机器人相关产品，但财务端仍需订单和利润验证。",
            "key_risk": "利润绝对额和业务规模承接不了高弹性预期。",
            "next_data_to_watch": "机器人产品收入、订单、毛利率、公告后股价反应。",
            "action": "旁路观察，只用于观察题材弹性，不纳入核心观察池。",
            "source_url": ZHONGDA_IR_URL,
        },
        {
            "symbol": "sz300503",
            "name": "昊志机电",
            "include_decision": "旁路观察",
            "pool_tier": "题材映射",
            "branch": "执行器总成",
            "business_summary": "高端装备核心功能部件公司，市场关注关节模组、减速器、主轴等高端部件。",
            "trend_link": "与机器人关节模组和高端部件存在映射，但不是当前减速器/丝杠最清晰的主线标的。",
            "profit_driver": "利润来自装备功能部件，机器人趋势需要订单和产品结构改善才能传导。",
            "growth_space": "成长空间来自关节模组、机器人部件订单和高端装备国产替代。",
            "valuation_snapshot": "题材属性较强，估值更依赖订单质量和利润修复。",
            "latest_validation": "机器人部件方向有市场关注，但缺少与本主题强绑定的连续财务验证。",
            "key_risk": "题材先涨、利润后验失败，导致估值回落。",
            "next_data_to_watch": "机器人部件订单、关节模组进展、利润率、应收与现金流。",
            "action": "旁路观察，不进入当前观察池。",
            "source_url": HAOZHI_DISCLOSURE_URL,
        },
        {
            "symbol": "sz300124",
            "name": "汇川技术",
            "include_decision": "旁路观察",
            "pool_tier": "间接受益",
            "branch": "机器人成套/自动化底座",
            "business_summary": "工控和自动化龙头，覆盖伺服、控制、工业机器人等自动化底座。",
            "trend_link": "处在电机控制和自动化底座分支，可验证行业景气，但对执行器/减速器主题不够纯。",
            "profit_driver": "利润由工控、新能源车和自动化业务驱动；机器人执行器对整体利润弹性有限。",
            "growth_space": "成长空间来自自动化周期、伺服份额、工业机器人和平台化能力。",
            "valuation_snapshot": "高质量大票，机器人执行器主题只是一部分估值叙事。",
            "latest_validation": "自动化底座强，但不是本页要找的减速器/丝杠/执行器纯标的。",
            "key_risk": "主题贡献被主业体量稀释，难作为本方向高弹性观察池成员。",
            "next_data_to_watch": "伺服订单、工业机器人收入、自动化景气、人形机器人客户线索。",
            "action": "旁路观察，作为行业底座，不进入观察池。",
            "source_url": INOVANCE_DISCLOSURE_URL,
        },
        {
            "symbol": "sz002747",
            "name": "埃斯顿",
            "include_decision": "暂不进入",
            "pool_tier": "间接受益",
            "branch": "机器人成套/自动化底座",
            "business_summary": "工业机器人和自动化公司，主营机器人本体、控制和系统集成。",
            "trend_link": "成套机器人和自动化底座能反映产业景气，但与执行器/减速器零部件利润弹性隔了一层。",
            "profit_driver": "利润主要来自工业机器人本体和系统集成，受工业自动化需求影响更大。",
            "growth_space": "成长空间来自国产工业机器人份额、控制系统和下游自动化复苏。",
            "valuation_snapshot": "更适合机器人整机/自动化主题，不适合放进执行器/减速器观察池。",
            "latest_validation": "公开披露重点仍在工业机器人和智能制造，不是本页核心部件验证对象。",
            "key_risk": "整机竞争、集成毛利率和自动化周期会稀释执行器主题。",
            "next_data_to_watch": "工业机器人订单、毛利率、控制系统收入、人形机器人实质合作。",
            "action": "暂不进入观察池，保留为机器人成套分支对照样本。",
            "source_url": ESTUN_DISCLOSURE_URL,
        },
    ]


def build_watchlist(company_research: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in company_research if row["include_decision"] == "进入观察池"]


def build_factor_scorecard(
    heat_summary: dict[str, Any],
    company_research: list[dict[str, Any]],
    watchlist: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    research_count = len(company_research)
    watchlist_count = len(watchlist)
    core_watch_count = sum(1 for row in watchlist if row["pool_tier"] == "核心跟踪")
    watch_branches = "、".join(dict.fromkeys(row["branch"] for row in watchlist))
    heat_text = (
        f"Top50出现{heat_summary.get('hits', 0)}次，覆盖{heat_summary.get('active_days', 0)}个交易日，"
        f"Top30出现{heat_summary.get('top30_hits', 0)}次，最佳第{heat_summary.get('best_rank', '')}名。"
    )
    factor_rows = [
        {
            "factor": "热点持续性/市场确认",
            "current_points": 13,
            "max_points": 18,
            "score_pct": 72,
            "weight_pct": 18,
            "status": "预热反复出现",
            "meaning": "决定这条线是不是从概念噪音变成可持续跟踪对象。",
            "logic": "长期趋势页先看市场是否反复给票。执行器、机器人、减速器多次入榜，说明不是单日热搜，但还没形成日级主线。",
            "score_rule": "近63交易日Top30反复出现且有硬件细分给高分；只有宽泛机器人或虚拟机器人给中分；连续两周消失降分。",
            "watch_focus": "每日看机器人执行器/减速器/丝杠是否Top30，是否从宽主题扩散到硬件细分。",
            "evidence_1_label": "本地热度窗口",
            "evidence_1_value": heat_text,
            "evidence_1_meaning": "4月以来有多次提前热身，不是当天最强榜首。",
            "evidence_2_label": "最近出现",
            "evidence_2_value": str(heat_summary.get("last_seen", "")),
            "evidence_2_meaning": "截至本地热度库最新日仍有机器人相关主题。",
            "evidence_3_label": "平均热度/持续性",
            "evidence_3_value": f"{heat_summary.get('avg_hot', 0)}/{heat_summary.get('avg_persist', 0)}",
            "evidence_3_meaning": "热度不低，但主线地位仍需连续性确认。",
            "source_name": "本地市场热点 fine_theme_heat_daily.db",
            "source_url": "/api/market_heat/fine_dashboard?days=63&pool_size=50",
        },
        {
            "factor": "特斯拉/海外人形机器人量产节奏",
            "current_points": 12,
            "max_points": 18,
            "score_pct": 67,
            "weight_pct": 18,
            "status": "量产窗口临近但未兑现",
            "meaning": "海外头部厂量产节奏决定供应链订单从样机走向批量的概率。",
            "logic": "Tesla Q1资料显示California Optimus处于建设状态；财报电话会口径指向Fremont在7月底或8月启动，但初期爬坡慢，不能按满产预期估值。",
            "score_rule": "产线建设+明确启动窗口给中高分；若实际投产、供应商订单披露和出货节奏同步确认再升分；若延期或初期产量极慢则降分。",
            "watch_focus": "Optimus V3披露、Fremont是否按7月底/8月启动、产量爬坡、Texas二代线进展。",
            "evidence_1_label": "Tesla Q1更新",
            "evidence_1_value": "California Optimus: Construction",
            "evidence_1_meaning": "官方产能表已把Optimus列入机器人制造建设项。",
            "evidence_2_label": "财报电话会口径",
            "evidence_2_value": "late July or August",
            "evidence_2_meaning": "量产观察窗口明确，但仍是预期阶段。",
            "evidence_3_label": "爬坡风险",
            "evidence_3_value": "initial output slow",
            "evidence_3_meaning": "短期不适合按百万台满产直接外推。",
            "source_name": "Tesla Q1 2026 Update / Electrek earnings call coverage",
            "source_url": f"{TESLA_Q1_PDF_URL} | {TESLA_CALL_URL}",
        },
        {
            "factor": "执行器 BOM 价值量与降本路径",
            "current_points": 11,
            "max_points": 16,
            "score_pct": 69,
            "weight_pct": 16,
            "status": "价值量高，价格曲线缺失",
            "meaning": "执行器是人形机器人肢体的核心成本池，价值量决定利润弹性，降本路径决定量产可行性。",
            "logic": "执行器由电机、减速器/丝杠、传感器、控制器、结构件构成，是硬件链最直接的利润映射。但现在缺少连续报价和单机价值量的可验证数据，只能给中高分。",
            "score_rule": "有明确BOM拆分、降本目标、核心部件价格曲线给高分；只有方向性表述给中分；若整机方案绕开高价值部件或降本失败则降分。",
            "watch_focus": "单机执行器数量、谐波/行星/丝杠方案选择、无框力矩电机和空心杯电机价格、供应商降本目标。",
            "evidence_1_label": "政策关键技术",
            "evidence_1_value": "高功率密度执行器",
            "evidence_1_meaning": "工信部把肢体执行相关技术放在关键攻关方向。",
            "evidence_2_label": "执行器总成",
            "evidence_2_value": "三花聚焦机电执行器",
            "evidence_2_meaning": "A股已有总成厂配合客户研发试制迭代。",
            "evidence_3_label": "缺口",
            "evidence_3_value": "无连续BOM报价",
            "evidence_3_meaning": "还不能像存储价格一样用周/月报价验证。",
            "source_name": "工信部 / 三花智控投资者关系",
            "source_url": f"{MIIT_HUMANOID_URL} | {SANHUA_IR_URL}",
        },
        {
            "factor": "减速器/丝杠/电机供给验证",
            "current_points": 10,
            "max_points": 16,
            "score_pct": 63,
            "weight_pct": 16,
            "status": "供给链有雏形，批量订单未充分验证",
            "meaning": "这决定A股映射是不是能从主题扩散到真实收入。",
            "logic": "谐波减速器、精密齿轮、滚柱丝杠、电机控制都有A股公司映射，但不少公司仍停留在样件、客户验证或机器人占比未披露阶段。",
            "score_rule": "核心部件厂披露定点、产能、订单和毛利率则上调；只有样件/技术储备保持观察；若订单迟迟不落地则降级。",
            "watch_focus": "绿的谐波减速器、北特/五洲/贝斯特丝杠、鸣志电器电机、雷赛/汇川控制的订单和毛利率。",
            "evidence_1_label": "核心纯度",
            "evidence_1_value": f"观察池覆盖{watch_branches}",
            "evidence_1_meaning": "先按分支研究，再决定进入观察池。",
            "evidence_2_label": "本地财务风险",
            "evidence_2_value": "多只纯标的利润绝对额偏小",
            "evidence_2_meaning": "主题弹性大，但业绩承接还弱。",
            "evidence_3_label": "公司研究范围",
            "evidence_3_value": f"研究{research_count}家，观察池{watchlist_count}家",
            "evidence_3_meaning": "只让有直接利润验证路径的公司进入观察池。",
            "source_name": "上交所/巨潮公告 + 本地财务快照",
            "source_url": f"{LEADERDRIVE_SSE_URL} | {SHUANGHUAN_IR_URL}",
        },
        {
            "factor": "国内订单/样机/客户验证",
            "current_points": 8,
            "max_points": 14,
            "score_pct": 57,
            "weight_pct": 14,
            "status": "样机和客户配合多，收入兑现少",
            "meaning": "没有订单和收入，长期趋势只停留在主题，不能升级研究仓。",
            "logic": "三花披露配合客户研发、试制、迭代并最终实现量产落地；双环披露智能执行机构高增。它们能说明链条在推进，但不是整个人形机器人部件行业的订单兑现。",
            "score_rule": "定点/批量订单/机器人收入占比披露给高分；样机和客户验证给中分；只讲布局不给订单降分。",
            "watch_focus": "中报机器人相关收入、在手订单、定点公告、产线资本开支、客户集中度。",
            "evidence_1_label": "三花智控",
            "evidence_1_value": "研发/试制/迭代/量产落地",
            "evidence_1_meaning": "总成链条有客户协同信号。",
            "evidence_2_label": "双环传动",
            "evidence_2_value": "智能执行机构2024收入+69%以上",
            "evidence_2_meaning": "执行机构业务已高增，但需拆分机器人贡献。",
            "evidence_3_label": "缺口",
            "evidence_3_value": "机器人收入占比未充分披露",
            "evidence_3_meaning": "不能把所有汽车零部件收入都当机器人订单。",
            "source_name": "三花智控/双环传动投资者关系",
            "source_url": f"{SANHUA_IR_URL} | {SHUANGHUAN_IR_URL}",
        },
        {
            "factor": "A股核心标的价格阶段与拥挤度",
            "current_points": 9,
            "max_points": 18,
            "score_pct": 50,
            "weight_pct": 18,
            "status": "有热度但观察池要收窄",
            "meaning": "这不是行业因子，但决定现在能不能动手。",
            "logic": "部分硬件标的处于高估值或利润小基数阶段，本地快照显示若干纯标的有L2转负、利润绝对额偏小等风险。当前更适合用研究卡筛选，不适合把整条链都放进观察池。",
            "score_rule": "核心票分歧后守位、量价重新转强且业绩验证则升级动作；高位拥挤或利好不涨则降级。",
            "watch_focus": "绿的谐波、双环、北特、五洲、三花的回撤承接、成交额、L2净流入、公告后股价反应。",
            "evidence_1_label": "核心标的池",
            "evidence_1_value": f"{watchlist_count}只进入观察池",
            "evidence_1_meaning": "只覆盖减速器、丝杠、执行器总成三类最直接利润链。",
            "evidence_2_label": "未进入公司",
            "evidence_2_value": f"{research_count - watchlist_count}只保留研究卡",
            "evidence_2_meaning": "间接受益、题材映射、整机底座不混入观察池。",
            "evidence_3_label": "风险",
            "evidence_3_value": "纯标的业绩小、价格弹性大",
            "evidence_3_meaning": "容易出现主题强但标的难买。",
            "source_name": "本地litong_similarity快照 / A股公告",
            "source_url": str(LITONG_CSV),
        },
    ]
    industry_score = sum(int(row["current_points"]) for row in factor_rows)
    factor_summary = {
        "industry_score": industry_score,
        "industry_max": 100,
        "industry_status": "观察加强 / 未到强趋势",
        "research_count": research_count,
        "watchlist_count": watchlist_count,
        "core_watch_count": core_watch_count,
    }
    return factor_rows, factor_summary


def build_decision_summary(factor_summary: dict[str, Any], watchlist: list[dict[str, Any]]) -> dict[str, Any]:
    direct_branches = {row["branch"] for row in watchlist}
    operability = min(48.0, 28.0 + len(watchlist) * 2.2 + len(direct_branches) * 2.0)
    return {
        "updated_at": UPDATED_AT,
        "topic_id": "robot_actuator",
        "topic_name": "机器人执行器/减速器",
        "industry_trend_score": factor_summary["industry_score"],
        "industry_trend_max": factor_summary["industry_max"],
        "a_share_operability_score": operability,
        "a_share_operability_max": 100,
        "conclusion": "值得跟踪，不值得直接追买",
        "industry_status": factor_summary["industry_status"],
        "operability_state": f"研究{factor_summary['research_count']}家，只让{factor_summary['watchlist_count']}家进入观察池",
        "current_view": "4月以来本地热点反复出现，Tesla量产窗口临近，执行器/减速器是硬件链核心。但本页先拆分支和公司利润路径，只把验证路径直接的公司放进观察池。",
        "block_reason": "最大卡点不是方向，而是从样机到批量订单的验证不足；A股纯标的利润基数小、估值和价格弹性都偏高。",
        "next_trigger": "机器人执行器/减速器连续进入Top30，Tesla Fremont按7月底/8月启动，三花/双环/绿的/丝杠链披露订单或中报收入验证。",
        "stage": "概率上升 / 预警期",
        "next_stage": "订单 / 量产验证期",
        "next_stage_conditions": "海外量产实际启动 + 国内核心部件订单披露 + 核心A股分歧后守位转强 + 中报机器人相关收入或毛利率改善。",
        "downgrade_conditions": "Tesla量产延期或产量极慢、热点连续两周退出Top50、公司公告仍停留在样机验证、核心标的利好不涨并跌破关键位。",
    }


def build_chain_layers() -> list[dict[str, Any]]:
    return [
        {
            "layer": "外部变量",
            "node": "Tesla/海外人形机器人量产",
            "direct_signal": "Fremont Optimus产线建设，7月底/8月启动预期",
            "transmission": "量产排产提高执行器、减速器、丝杠、电机的供应链验证概率",
            "a_share_mapping": "三花智控、拓普集团、绿的谐波、北特科技、五洲新春、贝斯特、鸣志电器",
            "validation_data": "产线状态、产量爬坡、供应商订单、机器人收入占比",
            "risk": "初期产量慢、供应商未进入量产、技术路线变化",
        },
        {
            "layer": "硬件价值量",
            "node": "执行器总成",
            "direct_signal": "机电执行器从研发试制进入量产落地",
            "transmission": "总成厂可承接电机、传动、控制和结构件集成利润",
            "a_share_mapping": "三花智控、拓普集团",
            "validation_data": "客户进度、定点、收入披露、毛利率",
            "risk": "整车/整机客户压价，收入占比低",
        },
        {
            "layer": "核心传动",
            "node": "谐波/行星/精密齿轮减速器",
            "direct_signal": "机器人关节需要高精度传动",
            "transmission": "国产替代和量产降本带来收入弹性",
            "a_share_mapping": "绿的谐波、双环传动、中大力德、昊志机电",
            "validation_data": "出货量、产能利用率、ASP、毛利率",
            "risk": "价格战、路线替代、纯题材估值过高",
        },
        {
            "layer": "线性执行",
            "node": "滚柱丝杠/轴承/精密加工",
            "direct_signal": "线性关节和灵巧部件需要丝杠与精密加工能力",
            "transmission": "样品验证后订单弹性大，但财务基数小",
            "a_share_mapping": "北特科技、五洲新春、贝斯特",
            "validation_data": "样品进度、客户认证、产线资本开支、批量订单",
            "risk": "样机不等于订单，量产良率和成本不达标",
        },
        {
            "layer": "运动控制",
            "node": "电机/伺服/驱动/控制器",
            "direct_signal": "执行器控制精度和响应速度要求提升",
            "transmission": "从工业自动化能力外溢到机器人链",
            "a_share_mapping": "鸣志电器、雷赛智能、汇川技术",
            "validation_data": "机器人客户收入、伺服/电机订单、控制算法和驱动方案",
            "risk": "自动化景气不等于人形机器人订单",
        },
        {
            "layer": "市场交易",
            "node": "A股主题热度与拥挤度",
            "direct_signal": "机器人执行器/机器人/减速器多次进入热点",
            "transmission": "热点确认提高关注度，但价格拥挤会降低可操作性",
            "a_share_mapping": "全观察池",
            "validation_data": "Top30持续性、L2净流入、核心票回撤承接",
            "risk": "概念扩散过快，后排无业绩支撑",
        },
    ]


def build_industry_signal_log(heat_summary: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "date": heat_summary.get("last_seen", ""),
            "signal_type": "market_heat",
            "indicator": "机器人/执行器/减速器相关Top50命中",
            "current_value": f"{heat_summary.get('hits', 0)}次 / {heat_summary.get('active_days', 0)}个交易日 / Top30 {heat_summary.get('top30_hits', 0)}次",
            "direction": "up",
            "evidence_level": "B",
            "meaning": "市场已经反复预热，但还不是每天都在榜首的强主线。",
            "next_check": "每日收盘",
            "source_name": "本地市场热点DB",
            "source_url": "/api/market_heat/fine_dashboard?days=63&pool_size=50",
        },
        {
            "date": "2026-04-22",
            "signal_type": "overseas_mass_production",
            "indicator": "Tesla Optimus Fremont生产窗口",
            "current_value": "late July or August；California Optimus construction",
            "direction": "up",
            "evidence_level": "A/B",
            "meaning": "海外龙头量产窗口明确，是未来一个月继续跟踪的核心外部变量。",
            "next_check": "2026-07-31",
            "source_name": "Tesla Q1 Update / Electrek",
            "source_url": f"{TESLA_Q1_PDF_URL} | {TESLA_CALL_URL}",
        },
        {
            "date": "2023-11-02",
            "signal_type": "policy",
            "indicator": "人形机器人创新发展指导意见",
            "current_value": "2025批量生产目标；2027形成安全可靠产业链供应链体系",
            "direction": "up",
            "evidence_level": "S",
            "meaning": "国内产业政策支持长期方向，但不能替代订单验证。",
            "next_check": "政策/标准更新",
            "source_name": "工业和信息化部",
            "source_url": MIIT_HUMANOID_URL,
        },
        {
            "date": "2025-09-25",
            "signal_type": "industrial_robot_base",
            "indicator": "中国工业机器人安装量",
            "current_value": "2024年29.5万台，全球部署占比54%，国产份额57%",
            "direction": "up",
            "evidence_level": "A",
            "meaning": "中国制造业机器人底座强，利于执行器供应链成熟，但工业机器人不等于人形机器人。",
            "next_check": "World Robotics 2026",
            "source_name": "International Federation of Robotics",
            "source_url": IFR_WR2025_URL,
        },
        {
            "date": "2025-03-27",
            "signal_type": "domestic_customer_validation",
            "indicator": "三花智控仿生机器人业务",
            "current_value": "聚焦机电执行器，配合客户研发、试制、迭代并最终实现量产落地",
            "direction": "up",
            "evidence_level": "A",
            "meaning": "执行器总成已经有客户协同，但还要等收入和订单披露。",
            "next_check": "2026中报/投资者关系活动",
            "source_name": "三花智控投资者关系活动记录",
            "source_url": SANHUA_IR_URL,
        },
        {
            "date": "2025-05-06",
            "signal_type": "domestic_revenue_validation",
            "indicator": "双环传动智能执行机构",
            "current_value": "2024收入同比+69%以上，2025Q1保持相似增速",
            "direction": "up",
            "evidence_level": "A",
            "meaning": "执行机构高增是正信号，但需拆分机器人和汽车链贡献。",
            "next_check": "2026中报/投资者关系活动",
            "source_name": "双环传动投资者关系活动记录",
            "source_url": SHUANGHUAN_IR_URL,
        },
        {
            "date": RUN_DATE,
            "signal_type": "a_share_risk",
            "indicator": "纯标的利润和资金风险",
            "current_value": "绿的谐波/五洲/中大力德等存在利润基数小或L2转负风险",
            "direction": "watch",
            "evidence_level": "B",
            "meaning": "这条线适合监控盘，不适合只按概念买入。",
            "next_check": "每日价格 + 中报",
            "source_name": "本地litong_similarity快照",
            "source_url": str(LITONG_CSV),
        },
    ]


def build_price_radar(heat_summary: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "category": "热度",
            "indicator": "机器人执行器/减速器Top30天数",
            "current_value": f"{heat_summary.get('top30_hits', 0)}次Top30，最佳第{heat_summary.get('best_rank', '')}名",
            "direction": "watch_up",
            "importance": "S",
            "signal_state": "预热",
            "status": "已接入",
            "source": "本地市场热点DB",
            "frequency": "日",
            "next_check": "每日收盘",
            "decision_use": "连续Top30才升级；连续两周不出现则降级。",
            "source_url": "/api/market_heat/fine_dashboard?days=63&pool_size=50",
        },
        {
            "category": "海外量产",
            "indicator": "Tesla Optimus Fremont",
            "current_value": "Q1资料显示Construction；电话会指向7月底/8月启动",
            "direction": "up",
            "importance": "S",
            "signal_state": "待兑现",
            "status": "半结构化",
            "source": "Tesla Q1 Update / Electrek",
            "frequency": "周/月",
            "next_check": "2026-07-31",
            "decision_use": "实际启动并有爬坡数据则升级；延期则降级。",
            "source_url": f"{TESLA_Q1_PDF_URL} | {TESLA_CALL_URL}",
        },
        {
            "category": "订单",
            "indicator": "国内执行器/减速器/丝杠订单",
            "current_value": "样机验证多，批量订单披露不足",
            "direction": "watch",
            "importance": "S",
            "signal_state": "未充分确认",
            "status": "待公告",
            "source": "交易所公告/投资者关系",
            "frequency": "周/季",
            "next_check": "2026中报",
            "decision_use": "订单和收入占比披露是从观察到研究仓的关键。",
            "source_url": f"{SANHUA_IR_URL} | {SHUANGHUAN_IR_URL}",
        },
        {
            "category": "价格",
            "indicator": "谐波减速器/滚柱丝杠/电机报价",
            "current_value": "未接入连续价格曲线",
            "direction": "watch",
            "importance": "A",
            "signal_state": "数据缺口",
            "status": "待接入",
            "source": "产业链报价/公司口径",
            "frequency": "周/月",
            "next_check": "2026-05-31",
            "decision_use": "有连续价格和降本曲线后，BOM价值量因子才能升分。",
            "source_url": "",
        },
        {
            "category": "公司",
            "indicator": "中报机器人相关收入/毛利率",
            "current_value": "待2026中报披露",
            "direction": "watch",
            "importance": "S",
            "signal_state": "待验证",
            "status": "待公告",
            "source": "上市公司定期报告",
            "frequency": "季",
            "next_check": "2026中报",
            "decision_use": "收入和毛利率兑现才允许升级到订单/财报验证期。",
            "source_url": "https://www.cninfo.com.cn/new/disclosure",
        },
        {
            "category": "A股价格",
            "indicator": "核心标的回撤承接/L2净流入",
            "current_value": "部分纯标的利润小、资金风险偏高",
            "direction": "watch_down",
            "importance": "A",
            "signal_state": "不追高",
            "status": "本地快照",
            "source": "litong_similarity",
            "frequency": "日",
            "next_check": "每日收盘",
            "decision_use": "分歧后守位且资金转正才考虑加仓；利好不涨先降级。",
            "source_url": str(LITONG_CSV),
        },
    ]


def build_data_source_matrix() -> list[dict[str, Any]]:
    return [
        {
            "module": "市场热度",
            "indicator": "机器人/执行器/减速器Top50、Top30、热度分、L2",
            "source": "fine_theme_heat_daily.db / fine_dashboard API",
            "frequency": "日",
            "method": "脚本直接读本地SQLite",
            "status": "已接入",
            "next_step": "每日收盘刷新",
        },
        {
            "module": "海外量产",
            "indicator": "Optimus产线、量产时间、爬坡节奏",
            "source": "Tesla Q1 Update / 财报电话会",
            "frequency": "周/月",
            "method": "人工结构化",
            "status": "半结构化",
            "next_step": "补Tesla官方生产更新",
        },
        {
            "module": "订单验证",
            "indicator": "定点、批量订单、客户验证、收入占比",
            "source": "交易所公告/投资者关系活动",
            "frequency": "周/季",
            "method": "人工结构化",
            "status": "部分接入",
            "next_step": "中报后更新订单和收入字段",
        },
        {
            "module": "BOM价格",
            "indicator": "谐波减速器、滚柱丝杠、电机、传感器报价",
            "source": "产业链报价/行业机构",
            "frequency": "周/月",
            "method": "待接入",
            "status": "缺口",
            "next_step": "找到可重复报价源",
        },
        {
            "module": "A股可操作",
            "indicator": "公司研究卡、观察池准入、估值状态、资金和价格阶段",
            "source": "本地litong_similarity + 公告",
            "frequency": "日/季",
            "method": "本地快照 + 人工研究卡",
            "status": "已接入基础版",
            "next_step": "补实时日线和公告后反应",
        },
    ]


def build_tracking_tasks() -> list[dict[str, Any]]:
    return [
        {
            "task": "每日热点持续性",
            "priority": "S",
            "status": "已接入",
            "next_check": "每日收盘",
            "target": "机器人执行器、减速器、丝杠、机器人",
            "upgrade_use": "连续Top30且硬件细分强于宽主题",
            "downgrade_use": "连续两周退出Top50或只剩虚拟机器人情绪",
        },
        {
            "task": "Tesla Optimus产线节点",
            "priority": "S",
            "status": "半结构化",
            "next_check": "2026-07-31",
            "target": "Fremont Optimus / V3 / Texas二代线",
            "upgrade_use": "按期启动并披露爬坡或供应链订单",
            "downgrade_use": "量产延期、初期产量极低且无供应链订单",
        },
        {
            "task": "国内订单和客户验证",
            "priority": "S",
            "status": "待公告",
            "next_check": "2026中报",
            "target": "三花、双环、绿的、北特、五洲、贝斯特",
            "upgrade_use": "定点/批量订单/机器人收入占比披露",
            "downgrade_use": "仍停留在样机或客户验证，无收入兑现",
        },
        {
            "task": "BOM与降本曲线",
            "priority": "A",
            "status": "待接入",
            "next_check": "2026-05-31",
            "target": "谐波减速器、滚柱丝杠、无框力矩电机、空心杯电机",
            "upgrade_use": "关键部件有连续报价，降本可验证",
            "downgrade_use": "核心部件价格战压缩毛利，或技术路线替代",
        },
        {
            "task": "核心票价格阶段",
            "priority": "A",
            "status": "基础快照",
            "next_check": "每日收盘",
            "target": "绿的、双环、北特、五洲、三花、拓普、鸣志",
            "upgrade_use": "分歧后守位，L2转正，公告后放量承接",
            "downgrade_use": "利好不涨、跌破平台、后排无量扩散",
        },
    ]


def upsert_score_history(summary: dict[str, Any], factor_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    path = DATA_DIR / "robot_actuator_score_history.csv"
    history = read_csv(path)
    factor_map = {row["factor"]: row for row in factor_rows}
    new_row = {
        "date": RUN_DATE,
        "industry_trend_score": summary["industry_trend_score"],
        "a_share_operability_score": summary["a_share_operability_score"],
        "hotspot_confirmation": factor_map["热点持续性/市场确认"]["current_points"],
        "tesla_overseas_ramp": factor_map["特斯拉/海外人形机器人量产节奏"]["current_points"],
        "bom_value_costdown": factor_map["执行器 BOM 价值量与降本路径"]["current_points"],
        "supply_validation": factor_map["减速器/丝杠/电机供给验证"]["current_points"],
        "domestic_order_validation": factor_map["国内订单/样机/客户验证"]["current_points"],
        "a_share_crowding": factor_map["A股核心标的价格阶段与拥挤度"]["current_points"],
        "conclusion": summary["conclusion"],
    }
    replaced = False
    for row in history:
        if row.get("date") == RUN_DATE:
            row.update({key: str(value) for key, value in new_row.items()})
            replaced = True
            break
    if not replaced:
        history.append({key: str(value) for key, value in new_row.items()})
    history.sort(key=lambda row: row.get("date", ""))
    write_csv(
        path,
        history,
        [
            "date",
            "industry_trend_score",
            "a_share_operability_score",
            "hotspot_confirmation",
            "tesla_overseas_ramp",
            "bom_value_costdown",
            "supply_validation",
            "domestic_order_validation",
            "a_share_crowding",
            "conclusion",
        ],
    )
    return history


def build_markdown(
    summary: dict[str, Any],
    factor_rows: list[dict[str, Any]],
    market_heat_rows: list[dict[str, Any]],
    heat_summary: dict[str, Any],
    company_research: list[dict[str, Any]],
    watchlist: list[dict[str, Any]],
    chain_layers: list[dict[str, Any]],
    price_radar: list[dict[str, Any]],
    tracking_tasks: list[dict[str, Any]],
    score_history: list[dict[str, Any]],
) -> str:
    md: list[str] = []
    md.append(f"# 机器人执行器/减速器长期趋势跟踪日报（{RUN_DATE}）\n")
    md.append("## 1. 当前系统判断\n")
    md.append(f"- 行业趋势分：{summary['industry_trend_score']}/{summary['industry_trend_max']}，{summary['industry_status']}。\n")
    md.append(f"- A股可操作分：{summary['a_share_operability_score']}/{summary['a_share_operability_max']}，{summary['operability_state']}。\n")
    md.append(f"- 当前结论：{summary['conclusion']}。{summary['current_view']}\n")
    md.append(f"- 卡住原因：{summary['block_reason']}\n")
    md.append(f"- 下一触发：{summary['next_trigger']}\n")
    md.append(f"- 阶段：{summary['stage']}；下一阶段：{summary['next_stage']}。\n")

    md.append("\n## 2. 六因子跟踪卡\n")
    md.append("| 因子 | 得分 | 状态 | 为什么影响趋势 | 之后盯什么 |\n|---|---:|---|---|---|\n")
    for row in factor_rows:
        md.append(
            f"| {row['factor']} | {row['current_points']}/{row['max_points']} | {row['status']} | {row['meaning']} | {row['watch_focus']} |\n"
        )

    md.append("\n## 3. 本地热点确认\n")
    md.append(f"- {heat_summary.get('summary', '')}\n")
    md.append("| 主题 | 出现天数 | Top30 | 最好排名 | 平均热度 | 平均持续性 | 最近出现 | 含义 |\n")
    md.append("|---|---:|---:|---:|---:|---:|---|---|\n")
    for row in market_heat_rows:
        md.append(
            f"| {row['sector_name']} | {row['days_seen']} | {row['top30_days']} | {row['best_rank']} | {row['avg_hot_score']} | {row['avg_persistence_score']} | {row['last_seen']} | {row['signal_meaning']} |\n"
        )

    md.append("\n## 4. 产业分支与公司池结论\n")
    branch_map: dict[str, list[dict[str, Any]]] = {}
    for row in company_research:
        branch_map.setdefault(row["branch"], []).append(row)
    md.append("| 分支 | 研究公司 | 进入观察池 | 当前判断 |\n|---|---|---|---|\n")
    for branch, rows in branch_map.items():
        names = "、".join(f"{row['name']}`{row['symbol']}`" for row in rows)
        in_pool = [row for row in rows if row["include_decision"] == "进入观察池"]
        pool_names = "、".join(row["name"] for row in in_pool) if in_pool else "无"
        if branch == "谐波/精密减速器":
            branch_view = "主链条，优先看订单、出货和毛利。"
        elif branch == "丝杠/轴承":
            branch_view = "弹性高但样件到量产风险最大。"
        elif branch == "执行器总成":
            branch_view = "总成中军价值高，但要拆出机器人收入。"
        elif branch == "电机/控制":
            branch_view = "底座分支，先等机器人客户订单。"
        else:
            branch_view = "成套/自动化底座只作旁路验证。"
        md.append(f"| {branch} | {names} | {pool_names} | {branch_view} |\n")

    md.append("\n## 5. A股观察池\n")
    md.append("| 股票 | 分支 | 池层级 | 为什么进入 | 当前动作 | 下一步盯什么 |\n|---|---|---|---|---|---|\n")
    for row in watchlist:
        md.append(
            f"| {row['name']} `{row['symbol']}` | {row['branch']} | {row['pool_tier']} | {row['trend_link']} {row['profit_driver']} | {row['action']} | {row['next_data_to_watch']} |\n"
        )

    md.append("\n## 6. 未进入观察池但保留研究卡\n")
    md.append("| 股票 | 决策 | 分支 | 不进入原因 | 后续触发 |\n|---|---|---|---|---|\n")
    for row in company_research:
        if row["include_decision"] == "进入观察池":
            continue
        md.append(
            f"| {row['name']} `{row['symbol']}` | {row['include_decision']} / {row['pool_tier']} | {row['branch']} | {row['key_risk']} | {row['next_data_to_watch']} |\n"
        )

    md.append("\n## 7. 产业链传导\n")
    md.append("| 层级 | 节点 | 传导 | A股映射 | 验证数据 | 风险 |\n|---|---|---|---|---|---|\n")
    for row in chain_layers:
        md.append(
            f"| {row['layer']} | {row['node']} | {row['transmission']} | {row['a_share_mapping']} | {row['validation_data']} | {row['risk']} |\n"
        )

    md.append("\n## 8. 每日/每周监控变量\n")
    md.append("| 类别 | 指标 | 当前值 | 状态 | 检查频率 | 决策用途 |\n|---|---|---|---|---|---|\n")
    for row in price_radar:
        md.append(
            f"| {row['category']} | {row['indicator']} | {row['current_value']} | {row['signal_state']} | {row['frequency']} | {row['decision_use']} |\n"
        )

    md.append("\n## 9. 买入/加仓/降级条件\n")
    md.append(f"- 买入观察线：{summary['next_stage_conditions']}\n")
    md.append("- 加仓线：行业分升到75以上，且A股可操作分升到60以上；必须由订单/收入/价格承接三者共同触发。\n")
    md.append(f"- 降级线：{summary['downgrade_conditions']}\n")

    md.append("\n## 10. 跟踪任务\n")
    for row in tracking_tasks:
        md.append(
            f"- [{row['priority']}] {row['task']}：{row['status']}；检查：{row['next_check']}；升级用途：{row['upgrade_use']}；降级用途：{row['downgrade_use']}。\n"
        )

    md.append("\n## 11. 来源入口\n")
    md.append(f"- Tesla Q1 Update：{TESLA_Q1_PDF_URL}\n")
    md.append(f"- Tesla Optimus财报电话会报道：{TESLA_CALL_URL}\n")
    md.append(f"- 工信部《人形机器人创新发展指导意见》：{MIIT_HUMANOID_URL}\n")
    md.append(f"- IFR World Robotics 2025：{IFR_WR2025_URL}\n")
    md.append(f"- 三花智控投资者关系：{SANHUA_IR_URL}\n")
    md.append(f"- 双环传动投资者关系：{SHUANGHUAN_IR_URL}\n")

    md.append("\n## 12. 分数历史\n")
    for row in score_history[-5:]:
        md.append(
            f"- {row['date']}：行业 {row['industry_trend_score']} / A股 {row['a_share_operability_score']} / 结论 {row['conclusion']}\n"
        )
    return "".join(md)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOC_DIR.mkdir(parents=True, exist_ok=True)

    market_heat_rows, heat_summary = build_market_heat()
    company_research = build_company_research()
    watchlist = build_watchlist(company_research)
    factor_rows, factor_summary = build_factor_scorecard(heat_summary, company_research, watchlist)
    summary = build_decision_summary(factor_summary, watchlist)
    chain_layers = build_chain_layers()
    industry_signal_log = build_industry_signal_log(heat_summary)
    price_radar = build_price_radar(heat_summary)
    data_source_matrix = build_data_source_matrix()
    tracking_tasks = build_tracking_tasks()
    score_history = upsert_score_history(summary, factor_rows)

    write_csv(DATA_DIR / f"robot_actuator_decision_summary_{RUN_DATE}.csv", [summary], DECISION_FIELDS)
    write_csv(DATA_DIR / f"robot_actuator_factor_scorecard_{RUN_DATE}.csv", factor_rows, FACTOR_FIELDS)
    write_csv(DATA_DIR / f"robot_actuator_market_heat_{RUN_DATE}.csv", market_heat_rows, heat_summary["fields"])
    write_csv(DATA_DIR / f"robot_actuator_company_research_{RUN_DATE}.csv", company_research, COMPANY_RESEARCH_FIELDS)
    write_csv(DATA_DIR / "robot_actuator_watchlist.csv", watchlist, COMPANY_RESEARCH_FIELDS)
    write_csv(DATA_DIR / "a_share_mapping_score.csv", watchlist, COMPANY_RESEARCH_FIELDS)
    write_csv(DATA_DIR / "chain_layers.csv", chain_layers, list(chain_layers[0].keys()))
    write_csv(DATA_DIR / "industry_signal_log.csv", industry_signal_log, list(industry_signal_log[0].keys()))
    write_csv(DATA_DIR / "price_radar.csv", price_radar, list(price_radar[0].keys()))
    write_csv(DATA_DIR / "data_source_matrix.csv", data_source_matrix, list(data_source_matrix[0].keys()))
    write_csv(DATA_DIR / "tracking_tasks.csv", tracking_tasks, list(tracking_tasks[0].keys()))

    report = build_markdown(
        summary,
        factor_rows,
        market_heat_rows,
        heat_summary,
        company_research,
        watchlist,
        chain_layers,
        price_radar,
        tracking_tasks,
        score_history,
    )
    report_path = DOC_DIR / f"robot_actuator_tracking_report_{RUN_DATE}.md"
    report_path.write_text(report, encoding="utf-8")

    outputs = [
        DATA_DIR / f"robot_actuator_decision_summary_{RUN_DATE}.csv",
        DATA_DIR / f"robot_actuator_factor_scorecard_{RUN_DATE}.csv",
        DATA_DIR / f"robot_actuator_market_heat_{RUN_DATE}.csv",
        DATA_DIR / f"robot_actuator_company_research_{RUN_DATE}.csv",
        DATA_DIR / "robot_actuator_watchlist.csv",
        DATA_DIR / "robot_actuator_score_history.csv",
        DATA_DIR / "chain_layers.csv",
        DATA_DIR / "industry_signal_log.csv",
        DATA_DIR / "price_radar.csv",
        DATA_DIR / "a_share_mapping_score.csv",
        DATA_DIR / "data_source_matrix.csv",
        DATA_DIR / "tracking_tasks.csv",
        report_path,
    ]
    for path in outputs:
        print(path)


if __name__ == "__main__":
    main()
