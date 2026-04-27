from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

load_dotenv(ROOT_DIR / ".env.local", override=False)

from backend.app.services.selection_research_context import get_selection_research_context, prepare_selection_research_context
from backend.app.services.selection_stable_callback import STRATEGY_INTERNAL_ID as DEFAULT_STRATEGY


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="导出候选票研究上下文包（页面/Codex 共用口径）")
    parser.add_argument("--symbol", required=True, help="股票代码，如 sh603629 / 603629")
    parser.add_argument("--date", default=None, help="历史查询日期 YYYY-MM-DD；事件按该日 23:59:59 截断")
    parser.add_argument("--strategy", default=DEFAULT_STRATEGY, help="策略 ID，默认 stable_capital_callback")
    parser.add_argument("--event-limit", type=int, default=50)
    parser.add_argument("--event-days", type=int, default=365)
    parser.add_argument("--series-days", type=int, default=60)
    parser.add_argument("--prepare", action="store_true", help="先补拉事件、公司介绍、财务快照，并尝试生成研究卡")
    parser.add_argument("--no-llm", action="store_true", help="配合 --prepare 使用：不调用 LLM，只补拉结构化数据")
    parser.add_argument("--compact", action="store_true", help="输出单行 JSON")
    args = parser.parse_args()

    if args.prepare:
        payload = prepare_selection_research_context(
            args.symbol,
            trade_date=args.date,
            strategy=args.strategy,
            use_llm=not args.no_llm,
            announcement_days=max(int(args.event_days), 365),
            qa_days=180,
            news_days=45,
            event_limit=int(args.event_limit),
            series_days=int(args.series_days),
        )
    else:
        payload = get_selection_research_context(
            args.symbol,
            trade_date=args.date,
            strategy=args.strategy,
            event_limit=int(args.event_limit),
            event_days=int(args.event_days),
            series_days=int(args.series_days),
        )
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=None if args.compact else 2,
            default=_json_default,
        )
    )


if __name__ == "__main__":
    main()
