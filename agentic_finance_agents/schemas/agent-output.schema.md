# Agent 输出格式

每个 Agent 同时输出 Markdown 和 JSON。Markdown 用于人读，JSON 用于后续晋级为页面或数据库字段。

## Markdown 文件

路径：

```text
runs/<run_id>/agents/<agent_id>.md
```

结构：

```markdown
# <Agent Name> - <subject>

## 结论
先给结论，说明可信度。

## 关键发现
只写本 Agent 职责范围内的新信息。

## 证据
列出事实、数字、source_ref。

## 风险与缺口
列出 data_gaps、source_conflicts、需要用户确认的问题。

## 模型与取数
列出实际模型级别、是否升级到 `5.5 xhigh`、取数动作摘要和是否拆内部子任务。

## 可晋级字段
列出可进入正式页面/数据库的候选字段。
```

## JSON 文件

路径：

```text
runs/<run_id>/agents/<agent_id>.json
```

字段：

```json
{
  "run_id": "",
  "agent_id": "",
  "agent_name": "",
  "subject": "",
  "mode": "company",
  "status": "complete",
  "model_used": "5.5 high",
  "model_escalated": false,
  "model_escalation_reason": "",
  "internal_subtasks": [],
  "confidence": 0.0,
  "brief": "",
  "findings": [],
  "metrics": [],
  "evidence_cache_writes": [],
  "retrieval_log_refs": [],
  "source_refs": [],
  "data_gaps": [],
  "source_conflicts": [],
  "promotion_candidates": [],
  "business_snapshot": {},
  "revenue_breakdown": [],
  "profit_source": [],
  "price_driver_map": [],
  "watch_variables": [],
  "next_questions": [],
  "period_compare": [],
  "earnings_bridge": {},
  "valuation_bridge": {},
  "ui_artifacts": {},
  "prior_run_comparison": {},
  "persistence_metadata": {}
}
```

## 字段规则

- `status` 只能是 `complete`、`partial`、`failed`、`skipped`。
- `model_used` 默认是 `5.5 high`；如使用 `5.5 xhigh`，必须填写 `model_escalation_reason`。
- `internal_subtasks` 只记录该 Agent 内部拆分，不代表默认另起完整 Agent。
- `confidence` 取值 0 到 1，低于 0.6 的结论不得进入正式库。
- `metrics` 每项必须包含 `name`、`value`、`unit`、`as_of_date`、`source_ref`。
- `source_refs` 必须能追溯到本地文件、数据库表、API、脚本输出或外部 URL。
- `evidence_cache_writes` 记录本 Agent 写入 `evidence_cache.jsonl` 的证据 id 或摘要。
- `retrieval_log_refs` 记录本 Agent 对应的取数日志 id 或摘要。
- `promotion_candidates` 只是候选，不代表已经正式入库。
- 单公司研究中，`business_snapshot`、`revenue_breakdown`、`profit_source`、`price_driver_map`、`watch_variables` 是推荐字段。没有数据时写缺口，不用模型记忆补全。
- 正式公司研究中，`period_compare`、`earnings_bridge`、`valuation_bridge` 是推荐字段，用于支持历史对比、估值分析和页面展示。
- `ui_artifacts` 只由 `11-research-page-composer` 写入。
- `prior_run_comparison` 用于同一公司再次研究时记录新旧变化。
