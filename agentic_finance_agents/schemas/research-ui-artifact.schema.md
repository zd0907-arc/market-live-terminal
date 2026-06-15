# 研究页面产物 Schema

本 schema 服务 `11 研究页面生成 Agent`。它定义研究结果转成页面后应该生成什么文件，而不是定义主应用 React 组件。

## 文件布局

```text
runs/<run_id>/ui/
  compact.html
  full.html
  research_ui_manifest.json
  data.json
```

## research_ui_manifest.json

```json
{
  "run_id": "20260611-1617-sz000833-company",
  "subject": "sz000833",
  "company_name": "粤桂股份",
  "as_of_date": "2026-06-11",
  "generated_at": "2026-06-11T18:00:00+08:00",
  "status": "candidate_only",
  "compact": {
    "path": "ui/compact.html",
    "title": "粤桂股份研究摘要",
    "height": {
      "min_px": 420,
      "preferred_px": 560,
      "max_px": 760
    },
    "scroll_mode": "page",
    "summary_focus": [
      "business_change",
      "valuation_bridge",
      "price_driver"
    ]
  },
  "full": {
    "path": "ui/full.html",
    "title": "粤桂股份完整研究",
    "display_mode": "overlay",
    "preferred_width": "90vw",
    "preferred_height": "90vh"
  },
  "data_path": "ui/data.json",
  "source_refs": [
    "final_report.md",
    "promotion_candidates.json",
    "agents/07-gl-reconciler.md"
  ],
  "blocked_claims": [],
  "data_gaps": [],
  "promotion_readiness": "candidate_only"
}
```

## data.json

`data.json` 是页面重构时的备用结构化数据。第一阶段允许 HTML 内联数据，但仍建议写出：

```json
{
  "identity": {},
  "business_modules": [],
  "period_compare": [],
  "valuation_bridge": {},
  "revenue_mix": [],
  "profit_sources": [],
  "price_driver_modules": [],
  "watch_variables": [],
  "risk_flags": [],
  "agent_sources": [],
  "evidence_status": {}
}
```

## compact.html 内容原则

简版不是固定字段卡，而是自适应图文摘要。必须短，但不能浅。优先展示“变化”和“判断依据”：

- 2025A 到最新季度发生了什么变化。
- 利润分母变化后估值怎么看。
- 与行业/同业相比是贵、便宜还是无法判断。
- 股价主要在交易什么。
- 最大反证是什么。

## full.html 内容原则

完整版可以长，但不能堆纯文字。必须以模块组织：

- 业务地图。
- 收入/毛利结构。
- 财务变化。
- 估值桥。
- 股价驱动图。
- 事件和证据。
- 风险和缺口。

## 安全约束

- 禁外链 JS。
- 禁网络请求。
- 禁 iframe 逃逸。
- 禁自动交易指令。
- 禁未来源数字。
- 禁把数据缺口伪装成确定结论。

