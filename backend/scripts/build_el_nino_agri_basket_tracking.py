#!/usr/bin/env python3
"""Build El Nino agri basket tracking seed data."""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data/selection/long_term_trends/el_nino"
DOC_DIR = ROOT / "docs/selection/long_term_trends/cases"
RUN_DATE = date.today().isoformat()
CN_TZ = timezone(timedelta(hours=8))
UPDATED_AT = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M Asia/Shanghai")
SCORE_HISTORY_PATH = DATA_DIR / "agri_basket_score_history.csv"


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


def pct_text(value: float) -> str:
    return f"{value:.1f}%"


PRICE_ROWS: list[dict[str, Any]] = [
    {
        "category": "白糖",
        "latest_value": "18.7",
        "unit": "c/lb",
        "change_20d_pct": "8.4",
        "change_60d_pct": "13.8",
        "price_status": "趋势走强",
        "split_research": "预备拆分",
        "climate_regions": "印度/泰国/巴西中南部",
        "transmission_logic": "干旱和降雨偏差先影响甘蔗单产，再传到糖价。",
        "tracking_price": "ICE Sugar No.11",
        "split_trigger": "连续维持60日线上方 + 主产国产量继续下修",
        "a_share_mapping": "制糖、农业种植、糖业贸易",
        "source": "seed/ICE proxy",
        "data_status": "seed",
    },
    {
        "category": "棕榈油",
        "latest_value": "4020",
        "unit": "MYR/ton",
        "change_20d_pct": "5.6",
        "change_60d_pct": "11.2",
        "price_status": "走强观察",
        "split_research": "继续观察",
        "climate_regions": "印尼/马来西亚",
        "transmission_logic": "东南亚降雨异常影响棕榈鲜果串产量与库存。",
        "tracking_price": "Bursa Malaysia CPO",
        "split_trigger": "库存连续回落 + 价格突破前高",
        "a_share_mapping": "油脂油料、饲料链",
        "source": "seed/BMD proxy",
        "data_status": "seed",
    },
    {
        "category": "咖啡",
        "latest_value": "212.0",
        "unit": "c/lb",
        "change_20d_pct": "4.8",
        "change_60d_pct": "9.5",
        "price_status": "偏强未确认",
        "split_research": "继续观察",
        "climate_regions": "巴西/越南",
        "transmission_logic": "高温、干旱和降雨异常会影响开花与结实。",
        "tracking_price": "ICE Coffee C",
        "split_trigger": "天气扰动持续 + 产量预估再下修",
        "a_share_mapping": "咖啡加工、饮品原料",
        "source": "seed/ICE proxy",
        "data_status": "seed",
    },
    {
        "category": "可可",
        "latest_value": "7860",
        "unit": "USD/ton",
        "change_20d_pct": "6.9",
        "change_60d_pct": "16.4",
        "price_status": "强趋势",
        "split_research": "预备拆分",
        "climate_regions": "西非/东南亚",
        "transmission_logic": "异常高温和降雨扰动会放大病虫害与减产。",
        "tracking_price": "ICE Cocoa",
        "split_trigger": "价格维持强势 + 西非到港/研磨继续偏紧",
        "a_share_mapping": "食品原料、可可加工",
        "source": "seed/ICE proxy",
        "data_status": "seed",
    },
    {
        "category": "玉米",
        "latest_value": "468",
        "unit": "c/bu",
        "change_20d_pct": "-0.9",
        "change_60d_pct": "2.2",
        "price_status": "未确认",
        "split_research": "不拆分",
        "climate_regions": "美国中西部/巴西/阿根廷",
        "transmission_logic": "北美和南美天气偏差影响单产，但当前价格未形成扩散。",
        "tracking_price": "CBOT Corn",
        "split_trigger": "主产区高温少雨 + USDA 单产下修",
        "a_share_mapping": "饲料、深加工",
        "source": "seed/CBOT proxy",
        "data_status": "seed",
    },
    {
        "category": "小麦",
        "latest_value": "601",
        "unit": "c/bu",
        "change_20d_pct": "1.1",
        "change_60d_pct": "3.8",
        "price_status": "弱反弹",
        "split_research": "不拆分",
        "climate_regions": "北美/黑海/澳洲",
        "transmission_logic": "气候异常影响全球平衡表，但当前库存缓冲仍在。",
        "tracking_price": "CBOT Wheat",
        "split_trigger": "出口受限 + 主产区减产共振",
        "a_share_mapping": "面粉、粮油加工",
        "source": "seed/CBOT proxy",
        "data_status": "seed",
    },
    {
        "category": "大豆/豆粕",
        "latest_value": "3520",
        "unit": "CNY/ton",
        "change_20d_pct": "1.7",
        "change_60d_pct": "4.1",
        "price_status": "观察中",
        "split_research": "不拆分",
        "climate_regions": "巴西/阿根廷/美国",
        "transmission_logic": "南美天气偏差可扰动产量，但目前价格传导偏弱。",
        "tracking_price": "DCE 豆粕主连",
        "split_trigger": "南美产量下修 + 豆粕跟随上破",
        "a_share_mapping": "饲料、油脂油料",
        "source": "seed/DCE proxy",
        "data_status": "seed",
    },
    {
        "category": "稻米",
        "latest_value": "17.4",
        "unit": "USD/cwt",
        "change_20d_pct": "2.4",
        "change_60d_pct": "6.7",
        "price_status": "边际走强",
        "split_research": "继续观察",
        "climate_regions": "印度/泰国/越南",
        "transmission_logic": "季风偏差和出口政策更容易传到稻米价格。",
        "tracking_price": "Rough Rice",
        "split_trigger": "出口限制收紧 + 主产区天气恶化",
        "a_share_mapping": "种植、粮食加工",
        "source": "seed/CBOT proxy",
        "data_status": "seed",
    },
]


WATCHLIST_ROWS: list[dict[str, Any]] = [
    {
        "category": row["category"],
        "climate_regions": row["climate_regions"],
        "transmission_logic": row["transmission_logic"],
        "tracking_price": row["tracking_price"],
        "trigger_condition": row["split_trigger"],
        "a_share_mapping": row["a_share_mapping"],
        "current_status": row["price_status"],
    }
    for row in PRICE_ROWS
]


FACTOR_ROWS: list[dict[str, Any]] = [
    {
        "factor": "ENSO确认度",
        "current_points": "14",
        "max_points": "20",
        "score_pct": "70",
        "weight_pct": "20",
        "status": "已升温但未满分",
        "logic": "先确认 ENSO 本身，再谈农产品价格传导。",
        "score_rule": "NOAA/CPC 与 ONI/Nino3.4 同步上行时加分；未正式确认前不给满分。",
        "watch_focus": "NOAA/CPC 口径、ONI 连续性、Nino3.4 海温。",
        "source": "NOAA/CPC + seed baseline",
        "evidence_1": "NOAA/CPC 口径偏向升温，但尚未进入完全确认。",
        "evidence_2": "ONI/Nino3.4 已抬升，持续性还需跟踪。",
        "evidence_3": "当前更像预警期，不是事件完全落地期。",
    },
    {
        "factor": "主产区天气异常",
        "current_points": "12",
        "max_points": "20",
        "score_pct": "60",
        "weight_pct": "20",
        "status": "局部异常",
        "logic": "东南亚、南美、印度/泰国、北美异常才会传到不同农产品。",
        "score_rule": "多主产区同时出现高温/少雨/暴雨并持续时提高评分。",
        "watch_focus": "印尼马来、巴西、印度、美国中西部天气偏差。",
        "source": "Open-Meteo/NOAA proxy seed",
        "evidence_1": "东南亚油脂链天气已有边际扰动。",
        "evidence_2": "南美软商品产区异常仍是结构性的，不是全面共振。",
        "evidence_3": "北美粮食天气暂未形成大范围减产预警。",
    },
    {
        "factor": "产量预估变化",
        "current_points": "10",
        "max_points": "15",
        "score_pct": "67",
        "weight_pct": "15",
        "status": "局部下修",
        "logic": "只有减产预估落地，价格扩散才更容易持续。",
        "score_rule": "USDA/FAO/主产国机构连续下修才给高分。",
        "watch_focus": "糖、可可、棕榈油主产国产量调整。",
        "source": "USDA/FAO/proxy seed",
        "evidence_1": "白糖和可可链条存在减产预期支撑。",
        "evidence_2": "粮食主链暂未出现一致性大幅下修。",
        "evidence_3": "当前仍以结构性减产而非全面减产为主。",
    },
    {
        "factor": "商品价格趋势",
        "current_points": "15",
        "max_points": "20",
        "score_pct": "75",
        "weight_pct": "20",
        "status": "开始扩散",
        "logic": "篮子里越多核心品类走强，传导可信度越高。",
        "score_rule": "20日和60日同时走强的品类越多，得分越高。",
        "watch_focus": "白糖、棕榈油、可可、咖啡是否维持强势。",
        "source": "seed futures basket",
        "evidence_1": "白糖、可可、棕榈油已经出现相对明确的价格强势。",
        "evidence_2": "咖啡、稻米边际走强，但确认度还不够。",
        "evidence_3": "玉米、小麦、大豆/豆粕暂未全面跟上。",
    },
    {
        "factor": "库存/进出口压力",
        "current_points": "8",
        "max_points": "15",
        "score_pct": "53",
        "weight_pct": "15",
        "status": "有支撑但不强",
        "logic": "库存消费比、出口限制、进口需求决定涨价是否放大。",
        "score_rule": "库存偏低或出口限制明显时加分，否则中性。",
        "watch_focus": "稻米出口政策、棕榈油库存、糖进口节奏。",
        "source": "FAO/proxy seed",
        "evidence_1": "稻米更受出口限制与政策影响。",
        "evidence_2": "棕榈油库存方向偏支持价格，但力度一般。",
        "evidence_3": "大宗粮食库存缓冲仍压制全面扩散。",
    },
    {
        "factor": "A股映射可操作性",
        "current_points": "4",
        "max_points": "10",
        "score_pct": "40",
        "weight_pct": "10",
        "status": "还早",
        "logic": "这里先判断能不能拆单品，不做行业股评分堆叠。",
        "score_rule": "只有价格确认和产业传导都更清晰时才加分。",
        "watch_focus": "先看价格，再决定是否拆白糖/棕榈油等单品页。",
        "source": "internal seed",
        "evidence_1": "当前更适合先做商品篮子，不急着堆 A 股映射。",
        "evidence_2": "白糖具备预备拆分条件，其余多数仍早。",
        "evidence_3": "可操作性分保持保守，避免过早落到股票交易。",
    },
]


def build_summary(price_rows: list[dict[str, Any]], factor_rows: list[dict[str, Any]]) -> dict[str, Any]:
    transmission_score = sum(int(row["current_points"]) for row in factor_rows)
    confirmed = [
        row for row in price_rows
        if float(row["change_20d_pct"]) >= 5 and float(row["change_60d_pct"]) >= 10
    ]
    strongest = sorted(
        price_rows,
        key=lambda row: (float(row["change_60d_pct"]), float(row["change_20d_pct"])),
        reverse=True,
    )[0]
    split_ready = [row["category"] for row in price_rows if row["split_research"] == "预备拆分"]
    return {
        "idea": "el_nino_agri_basket",
        "title": "厄尔尼诺-农产品价格篮子",
        "transmission_score": str(transmission_score),
        "transmission_max": "100",
        "price_confirm_score": str(len(confirmed)),
        "price_confirm_max": str(len(price_rows)),
        "conclusion": "观察中 / 价格开始扩散，但尚未全面确认",
        "strongest_category": strongest["category"],
        "split_research_needed": "、".join(split_ready) if split_ready else "暂无",
        "current_action": "先跟踪价格篮子，不扩成多单品页；白糖优先进入预备深挖。",
        "next_trigger": "2个以上核心品类维持60日线上方 + 主产国产量预估继续下修",
        "updated_at": UPDATED_AT,
        "change_summary": f"当前 {len(confirmed)}/{len(price_rows)} 个品类满足20日和60日同步走强，最强是{strongest['category']}。",
        "data_status": "seed baseline",
        "source_note": "当前为稳定 seed 基线，可后续替换成实时期货/机构数据。",
    }


def update_score_history(summary: dict[str, Any], factor_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing = [row for row in read_csv(SCORE_HISTORY_PATH) if row.get("date") != RUN_DATE]
    factor_map = {row["factor"]: row["current_points"] for row in factor_rows}
    existing.append(
        {
            "date": RUN_DATE,
            "transmission_score": summary["transmission_score"],
            "price_confirm_score": summary["price_confirm_score"],
            "confirmed_categories": f"{summary['price_confirm_score']}/{summary['price_confirm_max']}",
            "strongest_category": summary["strongest_category"],
            "conclusion": summary["conclusion"],
            "enso": factor_map.get("ENSO确认度", ""),
            "weather": factor_map.get("主产区天气异常", ""),
            "production": factor_map.get("产量预估变化", ""),
            "price_trend": factor_map.get("商品价格趋势", ""),
            "inventory_trade": factor_map.get("库存/进出口压力", ""),
            "a_share_mapping": factor_map.get("A股映射可操作性", ""),
        }
    )
    return sorted(existing, key=lambda row: row.get("date", ""))


def main() -> None:
    summary_row = build_summary(PRICE_ROWS, FACTOR_ROWS)
    score_history_rows = update_score_history(summary_row, FACTOR_ROWS)

    write_csv(
        DATA_DIR / f"agri_basket_summary_{RUN_DATE}.csv",
        [summary_row],
        list(summary_row.keys()),
    )
    write_csv(
        DATA_DIR / f"agri_basket_factor_scorecard_{RUN_DATE}.csv",
        FACTOR_ROWS,
        list(FACTOR_ROWS[0].keys()),
    )
    write_csv(
        DATA_DIR / f"agri_basket_price_basket_{RUN_DATE}.csv",
        PRICE_ROWS,
        list(PRICE_ROWS[0].keys()),
    )
    write_csv(
        DATA_DIR / "agri_basket_watchlist.csv",
        WATCHLIST_ROWS,
        list(WATCHLIST_ROWS[0].keys()),
    )
    write_csv(
        SCORE_HISTORY_PATH,
        score_history_rows,
        list(score_history_rows[0].keys()),
    )

    DOC_DIR.mkdir(parents=True, exist_ok=True)
    md: list[str] = []
    md.append(f"# 厄尔尼诺-农产品价格篮子监控（{RUN_DATE}）\n")
    md.append("## 当前结论\n")
    md.append(f"- 传导分：{summary_row['transmission_score']}/{summary_row['transmission_max']}。\n")
    md.append(f"- 价格确认：{summary_row['price_confirm_score']}/{summary_row['price_confirm_max']}。\n")
    md.append(f"- 当前结论：{summary_row['conclusion']}。\n")
    md.append(f"- 最强品类：{summary_row['strongest_category']}。\n")
    md.append(f"- 拆分深挖：{summary_row['split_research_needed']}。\n")
    md.append(f"- 下一触发：{summary_row['next_trigger']}。\n")
    md.append("\n## 六因子\n")
    md.append("| 因子 | 得分 | 状态 | 重点 |\n|---|---:|---|---|\n")
    for row in FACTOR_ROWS:
        md.append(f"| {row['factor']} | {row['current_points']}/{row['max_points']} | {row['status']} | {row['watch_focus']} |\n")
    md.append("\n## 价格篮子\n")
    md.append("| 品类 | 20日 | 60日 | 状态 | 是否拆分 |\n|---|---:|---:|---|---|\n")
    for row in PRICE_ROWS:
        md.append(f"| {row['category']} | {row['change_20d_pct']}% | {row['change_60d_pct']}% | {row['price_status']} | {row['split_research']} |\n")
    (DOC_DIR / f"el_nino_agri_basket_{RUN_DATE}.md").write_text("".join(md), encoding="utf-8")

    print(DATA_DIR / f"agri_basket_summary_{RUN_DATE}.csv")
    print(DATA_DIR / f"agri_basket_factor_scorecard_{RUN_DATE}.csv")
    print(DATA_DIR / f"agri_basket_price_basket_{RUN_DATE}.csv")
    print(DATA_DIR / "agri_basket_watchlist.csv")
    print(SCORE_HISTORY_PATH)
    print(DOC_DIR / f"el_nino_agri_basket_{RUN_DATE}.md")


if __name__ == "__main__":
    main()
