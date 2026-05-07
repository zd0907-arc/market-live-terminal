from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = ROOT / "data/selection/long_term_trends"
DOC_ROOT = ROOT / "docs/selection/long_term_trends"


def _read_csv(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return [dict(row) for row in csv.DictReader(f)]


def _latest_file(folder: Path, pattern: str) -> Optional[Path]:
    files = sorted(folder.glob(pattern))
    return files[-1] if files else None


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


def list_trend_ideas() -> Dict[str, Any]:
    # 当前先把已经成体系的 storage 暴露出来；后续新增线索时按同样目录约定扩展。
    ideas = []
    storage_dir = DATA_ROOT / "storage"
    if storage_dir.exists():
        latest_report = _latest_file(DOC_ROOT / "storage", "storage_tracking_report_*.md")
        report = _read_text(latest_report, max_chars=8000)
        summary = _extract_report_summary(report)
        ideas.append({
            "id": "storage",
            "name": "AI 存储 / 内存涨价",
            "status": "tracking",
            "rating": "A 级长期趋势候选",
            "stage": "一致加速 / 高位确认",
            "action": "不追长期主仓；等分歧后确认；Q2 财报验证后再升级。",
            "latest_report": str(latest_report.relative_to(ROOT)) if latest_report else "",
            "summary": summary,
        })
    return {"items": ideas}


def get_trend_dashboard(idea_id: str) -> Dict[str, Any]:
    if idea_id != "storage":
        raise ValueError(f"未知趋势线索: {idea_id}")

    data_dir = DATA_ROOT / "storage"
    doc_dir = DOC_ROOT / "storage"
    latest_price = _latest_file(data_dir, "a_share_price_stage_*.csv")
    latest_company = _latest_file(data_dir, "a_share_company_snapshot_*.csv")
    latest_global = _latest_file(data_dir, "global_peer_price_stage_*.csv")
    latest_valuation = _latest_file(data_dir, "valuation_scenarios_*.csv")
    latest_report = _latest_file(doc_dir, "storage_tracking_report_*.md")

    report_text = _read_text(latest_report)
    summary = _extract_report_summary(report_text)
    report_date = ""
    if latest_report:
        match = re.search(r"(\d{4}-\d{2}-\d{2})", latest_report.name)
        report_date = match.group(1) if match else ""

    return {
        "idea": {
            "id": "storage",
            "name": "AI 存储 / 内存涨价",
            "status": "tracking",
            "rating": "A 级长期趋势候选",
            "stage": "一致加速 / 高位确认",
            "action": "入长期趋势池，但当前只适合观察仓/研究仓前置；不直接上长期主仓。",
            "report_date": report_date,
        },
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
        "industry_signals": _read_csv(data_dir / "industry_signal_log.csv"),
        "watchlist": _read_csv(data_dir / "a_share_storage_watchlist.csv"),
        "a_share_price_stage": _read_csv(latest_price) if latest_price else [],
        "company_snapshot": _read_csv(latest_company) if latest_company else [],
        "global_peer_stage": _read_csv(latest_global) if latest_global else [],
        "valuation_scenarios": _read_csv(latest_valuation) if latest_valuation else [],
        "report": {
            "path": str(latest_report.relative_to(ROOT)) if latest_report else "",
            "summary": summary,
            "markdown": report_text,
        },
        "sources": {
            "latest_price": str(latest_price.relative_to(ROOT)) if latest_price else "",
            "latest_company": str(latest_company.relative_to(ROOT)) if latest_company else "",
            "latest_global": str(latest_global.relative_to(ROOT)) if latest_global else "",
            "latest_valuation": str(latest_valuation.relative_to(ROOT)) if latest_valuation else "",
        },
    }
