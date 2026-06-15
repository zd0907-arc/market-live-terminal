# 公司研究历史存储方案

## 目标

每次正式 Agent 研究都必须能按公司和研究时间反查。未来同一家公司再次研究时，要能读取旧研究，比较业务、财务、估值、股价驱动和风险判断的变化。

当前 `runs/` 是临时产物目录，不等同于正式库。稳定后应晋级为独立研究库，不写入行情库、选股库、模型特征库或官方事件事实层。

## 建议数据库

建议新增独立库：

```text
company_research.db
```

定位：研究结论库，不是事实行情库。

## 表设计草案

### company_research_runs

记录每次研究 run。

| 字段 | 说明 |
|---|---|
| `run_id` | 稳定 run id |
| `symbol` | 标准代码，如 `sz000833` |
| `company_name` | 公司简称 |
| `mode` | company/industry/theme |
| `as_of_date` | 研究基准日 |
| `created_at` | 创建时间 |
| `closed_at` | 收口时间 |
| `status` | running/closed_with_notes/complete/failed |
| `depth` | quick/standard/deep |
| `template_version` | 模板版本 |
| `workflow_version` | 工作流版本 |
| `summary` | 最终一句话摘要 |
| `confidence` | 总体置信度 |
| `artifact_root` | run 文件目录 |

### company_research_agent_outputs

保存每个 Agent 的独立结论。

| 字段 | 说明 |
|---|---|
| `run_id` | 所属 run |
| `agent_id` | Agent 编号 |
| `agent_name` | 中文名 |
| `status` | complete/partial/failed/skipped |
| `model_used` | 模型 |
| `confidence` | Agent 置信度 |
| `markdown_path` | Markdown 产物 |
| `json_path` | JSON 产物 |
| `summary_json` | 可查询摘要 |
| `data_gaps_json` | 缺口 |
| `source_refs_json` | 来源 |

### company_research_facts

保存可晋级事实和指标。不是所有 Agent 文字都进这里。

| 字段 | 说明 |
|---|---|
| `fact_id` | 稳定事实 id |
| `run_id` | 来源 run |
| `symbol` | 股票代码 |
| `field_name` | 字段名，如 `revenue_mix_2025` |
| `value_json` | 结构化值 |
| `period` | 2025A/2026Q1/TTM 等 |
| `as_of_date` | 研究时点 |
| `source_type` | 年报/季报/公告/行情/本地库/公开源 |
| `source_ref` | 原始来源 |
| `confidence` | high/medium/low |
| `promotion_status` | candidate/ready/blocked |

### company_research_valuation_snapshots

保存估值研究，支持未来对比。

| 字段 | 说明 |
|---|---|
| `run_id` | 来源 run |
| `symbol` | 股票代码 |
| `as_of_date` | 估值基准日 |
| `market_cap` | 市值 |
| `price` | 股价 |
| `pe_static` | 静态 PE |
| `pe_ttm` | TTM PE |
| `pe_latest_quarter_annualized` | 最新季度年化 PE |
| `profit_2025a` | 上年利润 |
| `profit_ttm` | TTM 利润 |
| `profit_latest_quarter` | 最新单季利润 |
| `peer_median_pe` | 同业中位数 |
| `peer_percentile` | 同业分位 |
| `valuation_view` | high/fair/low/inconclusive |
| `notes` | 口径说明 |

### company_research_ui_artifacts

保存页面产物索引。

| 字段 | 说明 |
|---|---|
| `run_id` | 来源 run |
| `symbol` | 股票代码 |
| `compact_html_path` | 简版 HTML |
| `full_html_path` | 完整 HTML |
| `manifest_path` | UI manifest |
| `data_path` | data.json |
| `status` | candidate/ready/blocked |

### company_research_comparisons

保存新旧研究对比结果。

| 字段 | 说明 |
|---|---|
| `comparison_id` | 对比 id |
| `symbol` | 股票代码 |
| `old_run_id` | 旧研究 |
| `new_run_id` | 新研究 |
| `changed_fields_json` | 变化字段 |
| `valuation_change_json` | 估值变化 |
| `thesis_change` | 主线变化 |
| `risk_change` | 风险变化 |
| `summary` | 对比摘要 |

## 研究重跑流程

当 3 个月后再次研究同一家公司：

1. 主控先查 `company_research_runs`，找到最近一次 closed run。
2. `02 Brief Agent` 把旧 run 摘要放入研究上下文。
3. `03/04/05/06/09/10` 各自只比较自己职责范围内的变化。
4. `06` 必须输出估值变化桥。
5. `07` 检查新旧口径是否一致。
6. `01` 输出“本次相对上次研究发生了什么变化”。
7. `08` 写入新 run，并生成 `company_research_comparisons` 候选。

## 当前与正式库的关系

现阶段只定义方案，不直接建表、不迁移历史、不写正式库。等用户确认字段和页面形态后，再做数据库实现任务。

