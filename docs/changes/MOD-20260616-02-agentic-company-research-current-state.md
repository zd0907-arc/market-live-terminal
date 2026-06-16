# MOD-20260616-02 Agentic 公司研究与选股卡片现状盘点

日期：2026-06-16

## 结论

当前已经恢复的是 `agentic_finance_agents/` 的 Agent 定义、调度流程和页面产物规范。2026-06-16 第一阶段新增了 1 个 `sz002137 / 实益达` 候选级 UI 接入验证 run，用于打通 manifest/compact/full 读取链路，但它不是正式 10+1 Agent 研究结论。选股页里原有一套轻量“公司概况 / 决策解释 / 研究依据”上下文链路，它也不是 10+1 Agent 的正式研究产物。

## 当前已恢复内容

`agentic_finance_agents/` 当前包含：

- `agents/01` 到 `agents/10`：官方 10 个金融 Agent 的 A 股研究化定义。
- `agents/11-research-page-composer.md`：本项目新增的研究页面生成 Agent。
- `workflows/company-research.md`：单公司研究流程。
- `workflows/codex-orchestration.md`：Codex 主控调度流程。
- `schemas/run-layout.md`：run 目录结构。
- `schemas/agent-output.schema.md`：单 Agent 输出结构。
- `schemas/company-final-report-template.md`：最终研究报告结构。
- `schemas/research-ui-artifact.schema.md`：页面产物结构。
- `schemas/research-history-storage.md`：未来 `company_research.db` 草案。

本轮接入前没有看到：

- `agentic_finance_agents/runs/`
- `final_report.md`
- `close_pack.md`
- `ui/compact.html`
- `ui/full.html`
- `ui/research_ui_manifest.json`

本轮第一阶段已新增：

```text
agentic_finance_agents/runs/20260616-2130-sz002137-company/
  final_report.md
  close_pack.md
  ui/compact.html
  ui/full.html
  ui/research_ui_manifest.json
  ui/data.json
```

该 run 的 `promotion_readiness=candidate_only`，只用于页面读取链路验证。

## Agent 研究的目标产物

按当前文档，单公司正式研究的最小输出应落在：

```text
agentic_finance_agents/runs/<run_id>/
  00-meeting-brief.md
  run_context.json
  source_registry.json
  evidence_cache.jsonl
  retrieval_log.jsonl
  agents/*.md
  agents/*.json
  final_report.md
  close_pack.md
```

如果要进入页面展示，还应由 `11` 生成：

```text
agentic_finance_agents/runs/<run_id>/ui/
  compact.html
  full.html
  research_ui_manifest.json
  data.json
```

## 选股页当前真实链路

当前选股页主入口是：

```text
src/components/selection/SelectionResearchPage.tsx
```

它右侧挂的是：

```text
src/components/selection/SelectionDecisionPanel.tsx
```

`SelectionDecisionPanel` 当前展示：

- 多日 / 单日走势。
- 信号链路、入场结论、市场环境。
- 公司概况。
- 决策解释。
- 研究依据。

这些内容来自：

```text
GET /api/selection/research-context/{symbol}
POST /api/selection/research-context/{symbol}/prepare
```

后端实现：

```text
backend/app/services/selection_research_context.py
backend/app/routers/selection.py
```

正式库位置：

```text
/Users/dong/ZhangData/market-data/live/market_data.db
```

相关表当前存在：

- `stock_company_profiles`
- `stock_financial_snapshots`
- `stock_research_cards`
- `stock_selection_decision_briefs`
- `stock_selection_decision_explanations`
- `stock_selection_research_evidence`

2026-06-16 本地核查结果：

- `stock_company_profiles`：181 条。
- `stock_research_cards`：0 条。
- `stock_financial_snapshots`：0 条。
- `stock_selection_decision_briefs`：0 条。
- `stock_selection_decision_explanations`：0 条。
- `stock_selection_research_evidence`：1 条，且是 `sh600519 / 2026-06-09` 的测试性质证据。

## Agentic HTML 原型状态

当前存在：

```text
src/components/selection/AgenticCompanyResearchEmbed.tsx
```

这个组件原本内置了 `compactHtml()` 和 `fullHtml()`，旧状态是：

- 只对 `sz002137 / 实益达` 生效。
- HTML 内容是样式占位，不是正式研究结论。
- 没有读取 `agentic_finance_agents/runs/<run_id>/ui/research_ui_manifest.json`。
- 没有读取磁盘上的 `compact.html` / `full.html`。
- 当前没有在 `SelectionResearchPage.tsx` 或 `SelectionDecisionPanel.tsx` 中接入。

因此它只能算页面形态原型，不能算正式功能链路。

2026-06-16 第一阶段已改为：

- 后端新增只读接口 `GET /api/selection/agentic-company-research/{symbol}`。
- 前端读取磁盘 `research_ui_manifest.json`、`compact.html`、`full.html` 和 `data.json`。
- `SelectionDecisionPanel` 已接入真实 iframe 卡片和完整研究 overlay。
- 当前只验证 1 只公司，仍保留 `candidate_only` 标识。

## 其他公司卡片材料

当前还存在手写持仓卡：

```text
docs/portfolio-ops/company-cards/sh603301-振德医疗.md
docs/portfolio-ops/company-cards/sz000833-粤桂股份.md
docs/portfolio-ops/company-cards/sz002600-领益智造.md
```

这些文件是实盘 / 持仓运营文档，不是 10+1 Agent 的标准 run 产物，也没有自动进入选股页。

## 缺口

1. 没有恢复历史 `runs/`，无法直接复用旧 Agent 研究结果。
2. 没有正式 `company_research.db`。
3. 轻量研究上下文表存在，但核心卡片、财务快照、决策 brief 基本为空。
4. Agentic HTML 页面产物 schema 已定义，当前只有本地只读接口，还没有发布/索引/历史库。
5. 前端已能读取 1 只公司的 `research_ui_manifest.json` 并嵌入真实 `compact/full` 产物，但还没有批量标的和正式 run 生产链。
6. `AgenticCompanyResearchEmbed.tsx` 已从实益达硬编码 demo 改为真实读取组件，但当前样例 run 仍是候选级接入种子。

## 后续单独会话建议目标

建议新会话目标定为：

```text
把 agentic_finance_agents 单公司研究产物正式接入选股页：
1. 跑一批新标的的 10+1 Agent 研究；
2. 每家公司产出 final_report.md、close_pack.md、compact.html、full.html、research_ui_manifest.json、data.json；
3. 定义本地正式存储位置；
4. 提供后端 manifest/HTML 读取接口；
5. 在 SelectionDecisionPanel 底部接入真实 compact 卡片，并支持打开 full 详情；
6. 保留候选态标识，未经过 evidence/retrieval ledger 的研究不要标成正式结论。
```

推荐先用 1 只公司打通端到端，再批量跑新标的。
