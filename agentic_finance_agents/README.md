# Agentic Finance Agents

> 当前状态：Codex 对话里的 A 股金融研究 Agent 工作台。这里承接 10 个金融 Agent 的定义、调用方式、输出格式和临时研究产物，并新增 1 个本项目专用的研究页面生成 Agent。

## 结论

这个目录解决的是“在 Codex 对话里如何调度金融研究 Agent”的问题，不解决前端点击式编排，也不直接写正式数据库。

未来新会话或后续开发者应先读：

1. `HANDOFF.md`
2. `DOCS_INDEX.md`
3. `ARCHITECTURE.md`
4. 按任务类型读取对应流程和 Agent 定义

## 边界

这里是什么：

- Codex 对话内的 A 股单公司、行业、热点赛道研究工作台。
- 10 个金融 Agent 的本项目化定义。
- 第 11 个页面表达层 Agent 的定义。
- Agent 输出、run 目录、页面产物和历史存储的草案。
- 临时研究产物和示范 run 的存放地。

这里不是什么：

- 不是前端页面功能。
- 不是正式业务数据库。
- 不是行情、L2、事件或模型特征的事实源。
- 不是固定 skill SOP；Agent 应该能按任务独立判断、取数、分析和交接。

## 文档入口

完整阅读路径、单一事实来源和冲突处理规则见：

```text
agentic_finance_agents/DOCS_INDEX.md
```

日常最常用文件：

| 文件 | 用途 |
|---|---|
| `HANDOFF.md` | 新会话接手 |
| `DOCS_INDEX.md` | 文档地图和准绳 |
| `ARCHITECTURE.md` | 领域目录放置、生命周期和扩展规则 |
| `registry/README.md` | Agent 名册、编号、状态和默认模型 |
| `codex-agent-playbook.md` | 默认调度、模型升级条件和交互方式 |
| `workflows/company-research.md` | 单公司研究流程 |
| `workflows/industry-research.md` | 行业/赛道研究流程 |
| `tools/free-data-and-tools.md` | 本地/免费数据源和工具边界 |
| `rules/research-governance.md` | 证据、估值、保存、晋级和页面表达规则 |
| `agents/*.md` | 单个 Agent 的详细定义 |
| `schemas/*.md` | 输出、页面、run 和历史库结构 |
| `runs/` | 临时研究样例，不是规则来源 |

## 使用方式

用户不需要进页面点击。推荐直接在 Codex 里说：

```text
用 agentic_finance_agents 按新版单公司流程研究 <公司名/股票代码>。
```

如果需要页面产物：

```text
研究 <公司名/股票代码>，并让 11 研究页面生成 Agent 输出 compact/full 页面产物。
```

主控会按 `codex-agent-playbook.md` 和对应 workflow 调度 Agent。正式研究产物先落在：

```text
agentic_finance_agents/runs/<run_id>/
```

这些结果必须经过 `07` 对账、`08` 收口和用户确认，才可以考虑进入正式页面或数据库。

## 当前 Agent 体系

官方参照的 10 个金融 Agent 已在 `agents/01` 到 `agents/10` 中定义。本项目新增：

```text
11 研究页面生成 Agent
```

第 11 个 Agent 不负责新增金融结论，只负责把已对账研究结果生成页面可嵌入的 `compact.html`、`full.html`、`research_ui_manifest.json` 和 `data.json`。

Agent 编号、中文名、状态和默认模型以 `registry/README.md` 为准；默认调用顺序以 `codex-agent-playbook.md` 为准。每个 Agent 的职责、工具、输出字段和护栏以对应 `agents/<id>.md` 为准。

## 当前状态

已经落地：

- 10 个金融 Agent 的本项目定义。
- 第 11 个页面生成 Agent。
- 单公司、行业、Codex 调度流程。
- Agent 输出、run 目录、页面产物和研究历史存储草案。
- 研究产出升级方案，包括估值分母桥、TTM、单季年化 PE、同业位置和历史对比。
- 1 个 `sz002137 / 实益达` 候选级 UI run，用于验证选股页读取 `compact/full` 产物。
- 选股页候选级只读接入 `research_ui_manifest.json`、`compact.html`、`full.html` 和 `data.json`。

尚未完成：

- 历史文档提到的振德医疗、粤桂股份示范 run 需要后续从备份或历史会话另行找回。
- 正式 `company_research.db`。
- 批量标的的正式 `compact/full` 产物生产和索引。
- 生产级 evidence/retrieval ledger。
- 对振德医疗和粤桂股份按新版标准重跑。

示范 run 只能作为样例，不代表最终研究质量。
