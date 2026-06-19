from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.core.config import FORMAL_MARKET_DATA_ROOT, SELECTION_ARTIFACTS_ROOT, first_existing_path

ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = Path(
    first_existing_path(
        str(Path(SELECTION_ARTIFACTS_ROOT) / "long_term_trends"),
        str(Path(FORMAL_MARKET_DATA_ROOT) / "selection/long_term_trends"),
        str(ROOT / "data/selection/long_term_trends"),
    )
)
DOC_ROOT = ROOT / "docs/selection/long_term_trends"
IDEA_CONFIG: Dict[str, Dict[str, Any]] = {
    "storage": {
        "name": "AI 存储 / 内存涨价",
        "status": "tracking",
        "rating": "A 级长期趋势候选",
        "stage": "一致加速 / 高位确认",
        "list_action": "不追长期主仓；等分歧后确认；Q2 财报验证后再升级。",
        "dashboard_action": "入长期趋势池，但当前只适合观察仓/研究仓前置；不直接上长期主仓。",
        "report_pattern": "storage_tracking_report_*.md",
        "watchlist_file": "a_share_storage_watchlist.csv",
        "verdict": {
            "industry": "TrendForce 价格与 CSP CapEx 仍支持高景气，产业未证伪。",
            "market": "A 股核心存储股处于一致加速/高位确认，不是低位启动。",
            "position": "等待分歧后龙头守位，再考虑观察仓；Q2 毛利率、存货、合同负债验证后再升级研究仓。",
        },
        "upgrade_rules": [
            "DRAM/NAND/Enterprise SSD 价格继续上修",
            "海外原厂继续新高或财报指引继续强",
            "江波龙/德明利/佰维分歧后不破关键位",
            "Q2 毛利率没有明显塌",
            "存货增长有合同负债/收入支撑",
            "经营现金流没有明显恶化",
        ],
        "downgrade_rules": [
            "TrendForce/CFM 开始下修 DRAM/NAND 价格",
            "海外 Micron / SK hynix / Samsung 利好不涨",
            "A 股龙头放量长阴或跌破弱触发位",
            "Q2 毛利率大幅低于 Q1",
            "存货继续暴增但合同负债没跟上",
        ],
    },
    "el_nino_rubber": {
        "name": "厄尔尼诺-橡胶",
        "status": "tracking",
        "rating": "A- 级商品分支观察",
        "stage": "研究观察 / 等价格确认",
        "list_action": "综合分已到观察线，但价格确认未完成；只等 RU/NR 同步突破或回踩不破。",
        "dashboard_action": "直接看监控盘：结论、综合分、价格确认、变化摘要和六分类因子。",
        "data_dir": "el_nino",
        "doc_dir": "cases",
        "report_pattern": "el_nino_rubber_operational_framework_*.md",
        "watchlist_file": "",
        "rubber_only": True,
        "verdict": {
            "industry": "橡胶监控盘已成型：需求、库存、天气都有加分。",
            "market": "RU/NR 偏强，但价格确认还没做满。",
            "position": "研究观察，当前不建仓。",
        },
        "upgrade_rules": [
            "总分 >=75 且价格确认=2/2",
            "库存或天气至少一项连续确认",
            "RU/NR 同步突破或回踩不破",
        ],
        "downgrade_rules": [
            "总分 <65",
            "RU/NR 跌破60日线",
            "库存转累或天气扰动消失",
        ],
    },
    "el_nino_agri_basket": {
        "name": "厄尔尼诺-农产品价格篮子",
        "status": "tracking",
        "rating": "A- 级商品篮子观察",
        "stage": "价格扩散观察 / 未全面确认",
        "list_action": "先看农产品/软商品价格篮子，确认谁真的走强，再决定是否拆单品页。",
        "dashboard_action": "先跟踪价格篮子，不一开始深挖每个单品；优先看传导是否成立、最强品类和拆分触发。",
        "report_pattern": "el_nino_agri_basket_*.md",
        "watchlist_file": "agri_basket_watchlist.csv",
        "data_dir": "el_nino",
        "doc_dir": "cases",
        "agri_basket_only": True,
        "verdict": {
            "industry": "先看农产品价格是否真的被厄尔尼诺传导，而不是先假设所有单品都成立。",
            "market": "当前是商品篮子观察阶段，价格扩散已有苗头，但还没到全面确认。",
            "position": "先不扩成多单品研究页，优先跟踪白糖、棕榈油、可可这些先走强的品类。",
        },
        "upgrade_rules": [
            "2个以上核心品类连续维持60日线上方",
            "主产国/机构继续下修糖、油脂、软商品产量预估",
            "价格强势从白糖/可可扩散到更多核心品类",
        ],
        "downgrade_rules": [
            "强势品类跌回60日线下并失去持续性",
            "ENSO 与主产区天气异常回落",
            "产量预估与库存压力没有继续支持涨价",
        ],
    },
    "power": {
        "name": "AI 电力 / 数据中心供电",
        "status": "tracking",
        "rating": "A 级长期趋势候选",
        "stage": "预期扩散 / 订单验证",
        "list_action": "入池观察；先补订单、招标、毛利率、现金流验证。",
        "dashboard_action": "长期逻辑成立，但还缺少像存储涨价那样的强价格证据；当前以观察池和研究池为主。",
        "report_pattern": "power_tracking_report_*.md",
        "watchlist_file": "a_share_power_watchlist.csv",
        "verdict": {
            "industry": "CSP CapEx 与数据中心装机功率上修支持 AI 电力长期需求。",
            "market": "A 股映射分散在电网设备、UPS、电源、液冷，当前更像订单验证前期。",
            "position": "不追主仓；先跟踪设备订单、液冷收入占比、毛利率、现金流。",
        },
        "upgrade_rules": [
            "CSP CapEx / 数据中心装机功率继续上修",
            "变压器、配电设备、UPS、液冷订单开始结构化兑现",
            "英维克/科华数据/中国西电等核心标的分歧后抗跌",
            "中报收入、毛利率、现金流同步改善",
        ],
        "downgrade_rules": [
            "云厂商资本开支下修或数据中心建设放缓",
            "只有 AI 电力叙事，没有订单和收入兑现",
            "液冷/电源相关公司毛利率下滑",
            "核心标的利好不涨或高位放量回落",
        ],
    },
    "ai_advanced_packaging": {
        "name": "AI先进封装与材料",
        "status": "tracking",
        "rating": "A 级热点趋势候选",
        "stage": "热点确认 / 等产业验证",
        "list_action": "先入热点趋势池；重点盯先进封装、封测、材料、玻璃基板是否从热度扩散到订单/财报。",
        "dashboard_action": "看行业趋势分、热点持续性、产业验证和A股可操作分；不把半导体普涨直接当买点。",
        "report_pattern": "ai_advanced_packaging_tracking_report_*.md",
        "watchlist_file": "ai_advanced_packaging_watchlist.csv",
        "generic_only": True,
        "verdict": {
            "industry": "5月11日半导体链热度最强，先进封装/封测/材料/玻璃基板具备独立研究价值。",
            "market": "当前先按热点确认与产业验证处理，不直接等同于长期主升。",
            "position": "建监控盘；等热度持续、订单/产能/材料价格或核心公司财报验证后再升级。",
        },
        "upgrade_rules": [
            "先进封装/封测/材料连续进入热点前排，且不是单日脉冲",
            "HBM、CoWoS/Chiplet、玻璃基板或载板产能/良率出现可验证进展",
            "核心A股标的回踩不破并重新转强",
            "订单、收入、毛利率验证先进封装链景气",
        ],
        "downgrade_rules": [
            "半导体链热度快速退潮，先进封装分支不再独立走强",
            "产业验证停留在概念，订单和财报没有跟上",
            "核心标的利好不涨或放量长阴",
        ],
    },
    "ai_interconnect": {
        "name": "AI高速互联",
        "status": "tracking",
        "rating": "A- 级热点趋势候选",
        "stage": "主线回踩 / 等再确认",
        "list_action": "入热点趋势池；重点盯CPO、光通信、PCB、连接器和高速线缆的热度修复与订单验证。",
        "dashboard_action": "先区分行业趋势和A股位置；CPO/PCB有持续性，但当前更适合等回踩后的再确认。",
        "report_pattern": "ai_interconnect_tracking_report_*.md",
        "watchlist_file": "ai_interconnect_watchlist.csv",
        "generic_only": True,
        "verdict": {
            "industry": "AI集群带宽需求长期存在，光模块、CPO、PCB、高速连接是核心传导链。",
            "market": "近月多次进热区，但部分分支已有退潮警告，需要二次确认。",
            "position": "先建监控盘；等热度回升、海外龙头和订单继续验证后再考虑研究仓。",
        },
        "upgrade_rules": [
            "CPO/光通信/PCB 至少两个分支重新进入热区并持续",
            "海外光模块/交换机链股价继续确认AI带宽需求",
            "A股核心标的分歧后不破关键位",
            "订单、出货、毛利率验证高速互联景气",
        ],
        "downgrade_rules": [
            "CPO/PCB热度只是一日反弹，随后连续退出热区",
            "海外龙头或客户CapEx转弱",
            "核心标的跌破关键位且利好不涨",
        ],
    },
    "robot_actuator": {
        "name": "机器人执行器/减速器",
        "status": "tracking",
        "rating": "B+ 级提前观察候选",
        "stage": "提前观察 / 等量产催化",
        "list_action": "入提前观察池；重点盯机器人执行器、减速器、丝杠、电机的热度回归和量产催化。",
        "dashboard_action": "这条不是当前最强热点，重点看是否从阶段性脉冲走成量产和订单验证。",
        "report_pattern": "robot_actuator_tracking_report_*.md",
        "watchlist_file": "robot_actuator_watchlist.csv",
        "generic_only": True,
        "verdict": {
            "industry": "机器人执行器/减速器在近月反复出现热点，但还缺少量产订单的强确认。",
            "market": "适合提前研究，不适合按当前热度追高。",
            "position": "先建观察盘；等特斯拉/国内客户量产节奏、订单和核心标的价格确认。",
        },
        "upgrade_rules": [
            "机器人/执行器/减速器重新进入热区并持续",
            "人形机器人量产节奏或订单出现强催化",
            "减速器、丝杠、电机等核心环节出现客户验证",
            "核心标的回踩不破并重新走强",
        ],
        "downgrade_rules": [
            "热点只停留在脉冲，连续退出热区",
            "量产时间表后移或订单验证不足",
            "核心标的高位杀估值且没有基本面承接",
        ],
    },
}


def _to_float(value: Any) -> Optional[float]:
    try:
        if value in ("", None):
            return None
        return float(value)
    except Exception:
        return None


def _mean(values: List[float]) -> Optional[float]:
    clean = [value for value in values if isinstance(value, (int, float))]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _build_futures_snapshot(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    parsed: List[Dict[str, Any]] = []
    for row in rows:
        close = _to_float(row.get("close"))
        high = _to_float(row.get("high"))
        if close is None:
            continue
        parsed.append({"date": row.get("date", ""), "close": close, "high": high})
    if not parsed:
        return {}

    latest = parsed[-1]
    closes = [row["close"] for row in parsed]
    highs = [row["high"] for row in parsed if row.get("high") is not None]
    ma20 = _mean(closes[-20:])
    ma60 = _mean(closes[-60:])
    high_since_2024 = max(highs) if highs else None
    drawdown = ((latest["close"] / high_since_2024) - 1) * 100 if high_since_2024 else None
    return {
        "date": latest["date"],
        "close": latest["close"],
        "ma20": ma20,
        "ma60": ma60,
        "high_since_2024": high_since_2024,
        "drawdown_from_high_pct": drawdown,
        "above_ma20": bool(ma20 and latest["close"] > ma20),
        "above_ma60": bool(ma60 and latest["close"] > ma60),
    }


def _build_rubber_dashboard(data_dir: Path) -> Dict[str, Any]:
    summary_file = _latest_file(data_dir, "rubber_decision_summary_*.csv")
    factor_file = _latest_file(data_dir, "rubber_factor_scorecard_*.csv")
    monitor_file = _latest_file(data_dir, "rubber_operational_monitor_*.csv")
    weather_file = _latest_file(data_dir, "rubber_weather_dashboard_*.csv")
    trigger_file = _latest_file(data_dir, "rubber_trade_trigger_rules_*.csv")
    company_file = _latest_file(data_dir, "rubber_company_transmission_*.csv")
    score_history_file = data_dir / "rubber_score_history.csv"
    long_cycle_file = data_dir / "rubber_worldbank_monthly_1960_2026.csv"
    report_file = _latest_file(DOC_ROOT / "cases", "el_nino_rubber_operational_framework_*.md")
    summary_rows = _read_csv(summary_file) if summary_file else []
    ru_history = _read_csv(data_dir / "rubber_ru_main_daily_2024_2026.csv")
    nr_history = _read_csv(data_dir / "rubber_nr_main_daily_2024_2026.csv")
    ru_snapshot = _build_futures_snapshot(ru_history)
    nr_snapshot = _build_futures_snapshot(nr_history)
    nr_by_date = {row.get("date", ""): row for row in nr_history}
    price_history: List[Dict[str, Any]] = []
    for row in ru_history:
        d = row.get("date", "")
        nr = nr_by_date.get(d, {})
        price_history.append({
            "date": d,
            "ru_close": row.get("close", ""),
            "nr_close": nr.get("close", ""),
        })
    long_cycle_history = [
        {
            "date": row.get("date", ""),
            "year": row.get("year", ""),
            "month": row.get("month", ""),
            "rss3": row.get("rubber_rss3_usd_kg", ""),
            "tsr20": row.get("rubber_tsr20_usd_kg", ""),
            "rss3_vs_2011_peak_pct": row.get("rss3_vs_2011_peak_pct", ""),
        }
        for row in _read_csv(long_cycle_file)
        if row.get("date")
    ]
    return {
        "summary": summary_rows[0] if summary_rows else {},
        "factor_scorecard": _read_csv(factor_file) if factor_file else [],
        "monitor": _read_csv(monitor_file) if monitor_file else [],
        "weather": _read_csv(weather_file) if weather_file else [],
        "trigger_rules": _read_csv(trigger_file) if trigger_file else [],
        "company_transmission": _read_csv(company_file) if company_file else [],
        "score_history": _read_csv(score_history_file),
        "price_history": price_history,
        "long_cycle_price_history": long_cycle_history,
        "price_snapshot": {
            "ru": ru_snapshot,
            "nr": nr_snapshot,
            "price_confirm_score": (summary_rows[0] if summary_rows else {}).get("price_confirm_score") or (summary_rows[0] if summary_rows else {}).get("price_gate_score", ""),
            "price_confirm_max": (summary_rows[0] if summary_rows else {}).get("price_confirm_max") or (summary_rows[0] if summary_rows else {}).get("price_gate_max", ""),
            "price_confirm_state": (summary_rows[0] if summary_rows else {}).get("price_confirm_state") or (summary_rows[0] if summary_rows else {}).get("price_gate_status", ""),
        },
        "report_path": _source_path(report_file),
        "sources": {
            "summary": _source_path(summary_file),
            "factor_scorecard": _source_path(factor_file),
            "monitor": _source_path(monitor_file),
            "weather": _source_path(weather_file),
            "trigger_rules": _source_path(trigger_file),
            "company_transmission": _source_path(company_file),
            "score_history": _source_path(score_history_file),
            "long_cycle_price_history": _source_path(long_cycle_file),
        },
    }


def _build_storage_dashboard(data_dir: Path) -> Dict[str, Any]:
    summary_file = _latest_file(data_dir, "storage_decision_summary_*.csv")
    factor_file = _latest_file(data_dir, "storage_industry_factor_scorecard_*.csv")
    operability_file = _latest_file(data_dir, "storage_operability_summary_*.csv")
    score_history_file = data_dir / "storage_score_history.csv"
    summary_rows = _read_csv(summary_file) if summary_file else []
    return {
        "summary": summary_rows[0] if summary_rows else {},
        "factor_scorecard": _read_csv(factor_file) if factor_file else [],
        "operability_summary": _read_csv(operability_file) if operability_file else [],
        "score_history": _read_csv(score_history_file),
        "sources": {
            "summary": _source_path(summary_file),
            "factor_scorecard": _source_path(factor_file),
            "operability_summary": _source_path(operability_file),
            "score_history": _source_path(score_history_file),
        },
    }


def _build_agri_basket_dashboard(data_dir: Path) -> Dict[str, Any]:
    summary_file = _latest_file(data_dir, "agri_basket_summary_*.csv")
    factor_file = _latest_file(data_dir, "agri_basket_factor_scorecard_*.csv")
    price_file = _latest_file(data_dir, "agri_basket_price_basket_*.csv")
    watchlist_file = data_dir / "agri_basket_watchlist.csv"
    score_history_file = data_dir / "agri_basket_score_history.csv"
    summary_rows = _read_csv(summary_file) if summary_file else []
    return {
        "summary": summary_rows[0] if summary_rows else {},
        "factor_scorecard": _read_csv(factor_file) if factor_file else [],
        "price_basket": _read_csv(price_file) if price_file else [],
        "watchlist": _read_csv(watchlist_file),
        "score_history": _read_csv(score_history_file),
        "sources": {
            "summary": _source_path(summary_file),
            "factor_scorecard": _source_path(factor_file),
            "price_basket": _source_path(price_file),
            "watchlist": _source_path(watchlist_file),
            "score_history": _source_path(score_history_file),
        },
    }


def _build_generic_dashboard(data_dir: Path, idea_id: str) -> Dict[str, Any]:
    summary_file = _latest_file(data_dir, f"{idea_id}_decision_summary_*.csv")
    factor_file = _latest_file(data_dir, f"{idea_id}_factor_scorecard_*.csv")
    heat_file = _latest_file(data_dir, f"{idea_id}_market_heat_*.csv")
    company_file = _latest_file(data_dir, f"{idea_id}_company_research_*.csv")
    watchlist_file = data_dir / f"{idea_id}_watchlist.csv"
    score_history_file = data_dir / f"{idea_id}_score_history.csv"
    summary_rows = _read_csv(summary_file) if summary_file else []
    return {
        "summary": summary_rows[0] if summary_rows else {},
        "factor_scorecard": _read_csv(factor_file) if factor_file else [],
        "market_heat": _read_csv(heat_file) if heat_file else [],
        "company_research": _read_csv(company_file) if company_file else [],
        "watchlist": _read_csv(watchlist_file),
        "score_history": _read_csv(score_history_file),
        "sources": {
            "summary": _source_path(summary_file),
            "factor_scorecard": _source_path(factor_file),
            "market_heat": _source_path(heat_file),
            "company_research": _source_path(company_file),
            "watchlist": _source_path(watchlist_file),
            "score_history": _source_path(score_history_file),
        },
    }


def _read_csv(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return [dict(row) for row in csv.DictReader(f)]


def _latest_file(folder: Path, pattern: str) -> Optional[Path]:
    files = sorted(folder.glob(pattern))
    return files[-1] if files else None


def _source_path(path: Optional[Path]) -> str:
    if not path or not path.exists():
        return ""
    for base in (ROOT, Path(FORMAL_MARKET_DATA_ROOT)):
        try:
            return str(path.relative_to(base))
        except ValueError:
            continue
    return str(path)


def _read_text(path: Optional[Path], max_chars: int = 40000) -> str:
    if not path or not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="ignore")
    return text[:max_chars]


def _extract_report_summary(report: str) -> Dict[str, Any]:
    lines = [line.strip() for line in report.splitlines()]
    bullets = [line[2:].strip() for line in lines if line.startswith("- ")]
    title = next((line.lstrip("# ").strip() for line in lines if line.startswith("# ")), "")
    return {
        "title": title,
        "bullets": bullets[:8],
    }


def _config_data_dir(idea_id: str, cfg: Dict[str, Any]) -> Path:
    return DATA_ROOT / str(cfg.get("data_dir") or idea_id)


def _config_doc_dir(idea_id: str, cfg: Dict[str, Any]) -> Path:
    return DOC_ROOT / str(cfg.get("doc_dir") or idea_id)


def list_trend_ideas() -> Dict[str, Any]:
    ideas = []
    for idea_id, cfg in IDEA_CONFIG.items():
        idea_dir = _config_data_dir(idea_id, cfg)
        if not idea_dir.exists():
            continue
        latest_report = _latest_file(_config_doc_dir(idea_id, cfg), cfg["report_pattern"])
        report = _read_text(latest_report, max_chars=8000)
        summary = _extract_report_summary(report)
        ideas.append({
            "id": idea_id,
            "name": cfg["name"],
            "status": cfg["status"],
            "rating": cfg["rating"],
            "stage": cfg["stage"],
            "action": cfg["list_action"],
            "latest_report": _source_path(latest_report),
            "summary": summary,
        })
    return {"items": ideas}


def get_trend_dashboard(idea_id: str) -> Dict[str, Any]:
    cfg = IDEA_CONFIG.get(idea_id)
    if not cfg:
        raise ValueError(f"未知趋势线索: {idea_id}")

    data_dir = _config_data_dir(idea_id, cfg)
    doc_dir = _config_doc_dir(idea_id, cfg)
    latest_price = _latest_file(data_dir, "a_share_price_stage_*.csv")
    latest_price_history = _latest_file(data_dir, "a_share_price_history_*.csv")
    latest_company = _latest_file(data_dir, "a_share_company_snapshot_*.csv")
    latest_validation = _latest_file(data_dir, "company_validation_*.csv")
    latest_global = _latest_file(data_dir, "global_peer_price_stage_*.csv")
    latest_global_history = _latest_file(data_dir, "global_peer_price_history_*.csv")
    latest_valuation = _latest_file(data_dir, "valuation_scenarios_*.csv")
    latest_decision = _latest_file(data_dir, "decision_matrix_*.csv")
    latest_report = _latest_file(doc_dir, cfg["report_pattern"])

    report_text = _read_text(latest_report)
    summary = _extract_report_summary(report_text)
    report_date = ""
    if latest_report:
        match = re.search(r"(\d{4}-\d{2}-\d{2})", latest_report.name)
        report_date = match.group(1) if match else ""

    return {
        "idea": {
            "id": idea_id,
            "name": cfg["name"],
            "status": cfg["status"],
            "rating": cfg["rating"],
            "stage": cfg["stage"],
            "action": cfg["dashboard_action"],
            "report_date": report_date,
        },
        "verdict": cfg["verdict"],
        "upgrade_rules": cfg["upgrade_rules"],
        "downgrade_rules": cfg["downgrade_rules"],
        "industry_signals": _read_csv(data_dir / "industry_signal_log.csv"),
        "chain_layers": _read_csv(data_dir / "chain_layers.csv"),
        "price_radar": _read_csv(data_dir / "price_radar.csv"),
        "foundry_supply": _read_csv(data_dir / "foundry_supply_tracking.csv"),
        "downstream_demand": _read_csv(data_dir / "downstream_ai_demand.csv"),
        "a_share_mapping_score": _read_csv(data_dir / "a_share_mapping_score.csv"),
        "pre_earnings_warning": _read_csv(data_dir / "pre_earnings_warning.csv"),
        "data_source_matrix": _read_csv(data_dir / "data_source_matrix.csv"),
        "watchlist": _read_csv(data_dir / cfg["watchlist_file"]) if cfg.get("watchlist_file") else [],
        "a_share_price_stage": _read_csv(latest_price) if latest_price else [],
        "a_share_price_history": _read_csv(latest_price_history) if latest_price_history else [],
        "company_snapshot": _read_csv(latest_company) if latest_company else [],
        "company_validation": _read_csv(latest_validation) if latest_validation else [],
        "global_peer_stage": _read_csv(latest_global) if latest_global else [],
        "global_peer_history": _read_csv(latest_global_history) if latest_global_history else [],
        "valuation_scenarios": _read_csv(latest_valuation) if latest_valuation else [],
        "decision_matrix": _read_csv(latest_decision) if latest_decision else [],
        "storage_dashboard": _build_storage_dashboard(data_dir) if idea_id == "storage" else None,
        "rubber_dashboard": _build_rubber_dashboard(data_dir) if cfg.get("rubber_only") else None,
        "agri_basket_dashboard": _build_agri_basket_dashboard(data_dir) if cfg.get("agri_basket_only") else None,
        "generic_dashboard": _build_generic_dashboard(data_dir, idea_id) if cfg.get("generic_only") else None,
        "tracking_tasks": _read_csv(data_dir / "tracking_tasks.csv"),
        "report": {
            "path": _source_path(latest_report),
            "summary": summary,
            "markdown": report_text,
        },
        "sources": {
            "latest_price": _source_path(latest_price),
            "latest_price_history": _source_path(latest_price_history),
            "latest_company": _source_path(latest_company),
            "latest_validation": _source_path(latest_validation),
            "latest_global": _source_path(latest_global),
            "latest_global_history": _source_path(latest_global_history),
            "latest_valuation": _source_path(latest_valuation),
            "latest_decision": _source_path(latest_decision),
        },
    }
