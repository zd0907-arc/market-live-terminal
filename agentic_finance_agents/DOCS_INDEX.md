# Agentic Finance Agents 文档索引

## 结论

新会话接手时，先读 `HANDOFF.md`，再读本文件。本文件回答三个问题：

1. 这些文档分别管什么。
2. 未来不同任务应该读哪几份。
3. 如果文档之间有重复或冲突，哪一份是准绳。

`agentic_finance_agents/` 是 Codex 对话内的 A 股金融研究 Agent 领域目录，不是前端页面功能，也不是正式数据库。

## 文档分层

| 层级 | 文件 | 谁读 | 职责 |
|---|---|---|---|
| 新会话交接 | `HANDOFF.md` | 新开的 Codex 会话 | 快速接手、推荐提示词、当前已知不足 |
| 总入口 | `README.md` | 用户和 Codex | 解释这个目录是什么、不是什么，以及下一步读哪里 |
| 文档地图 | `DOCS_INDEX.md` | 用户和 Codex | 维护阅读路径、单一事实来源和冲突处理规则 |
| 领域结构 | `ARCHITECTURE.md` | 用户、Codex、后续开发者 | 说明这个领域目录怎么放、怎么扩展、和项目其他部分怎么衔接 |
| Agent 注册 | `registry/README.md` | Codex 主控、后续维护者 | Agent 编号、中文名、来源、状态、默认模型 |
| 调度手册 | `codex-agent-playbook.md` | Codex 主控 | 默认调度、模型升级条件、用户交互方式 |
| Agent 定义 | `agents/*.md` | Codex 主控、对应 Agent | 每个 Agent 的职责、工具、工作流、输出和护栏 |
| 数据与工具 | `tools/free-data-and-tools.md` | 所有取数 Agent | 本地数据、免费信息源、source_ref、禁用项 |
| 研究规则 | `rules/research-governance.md` | 所有 Agent、Codex 主控 | 独立性、证据、估值、保存、晋级、页面表达规则 |
| 流程 | `workflows/company-research.md` | 单公司研究 | 单公司研究的标准流程和最终报告要求 |
| 流程 | `workflows/industry-research.md` | 行业/赛道研究 | 行业、热点赛道、全新领域研究的标准流程 |
| 编排机制 | `workflows/codex-orchestration.md` | Codex 主控 | 分批调度、失败处理、保存和复查机制 |
| 升级路线 | `roadmap/research-output-upgrade-plan.md` | 后续迭代者 | 记录当前研究质量缺口和待升级方向 |
| 输出 Schema | `schemas/*.md` | Codex 主控、后续开发者 | Agent 输出、run 目录、最终报告、页面产物、历史库草案 |
| 临时样例 | `runs/` | 审阅者 | 示例 run 和试验产物；不是规则来源 |

## 推荐读取路径

### 新会话接手

1. `agentic_finance_agents/HANDOFF.md`
2. `agentic_finance_agents/DOCS_INDEX.md`
3. `agentic_finance_agents/ARCHITECTURE.md`
4. 按任务类型继续读取下面对应路径。

### 单公司研究

1. `codex-agent-playbook.md`
2. `registry/README.md`
3. `workflows/company-research.md`
4. `workflows/codex-orchestration.md`
5. `rules/research-governance.md`
6. `tools/free-data-and-tools.md`
7. 本次需要的 `agents/*.md`
8. `schemas/run-layout.md`
9. `schemas/agent-output.schema.md`
10. `schemas/company-final-report-template.md`

如果用户要求页面产物，再读：

1. `agents/11-research-page-composer.md`
2. `schemas/research-ui-artifact.schema.md`

如果是同一公司重跑，再读：

1. `schemas/research-history-storage.md`
2. 最近一次 `runs/<run_id>/final_report.md`
3. 最近一次 `runs/<run_id>/close_pack.md`

### 行业或热点赛道研究

1. `codex-agent-playbook.md`
2. `registry/README.md`
3. `workflows/industry-research.md`
4. `workflows/codex-orchestration.md`
5. `rules/research-governance.md`
6. `tools/free-data-and-tools.md`
7. `agents/05-market-researcher.md`
8. 视情况读取 `03/06/09/10/07/01/08`

### 审阅或修改 Agent

1. `schemas/agent-definition-template.md`
2. 对应 `agents/<id>.md`
3. `registry/README.md`
4. `codex-agent-playbook.md`
5. `rules/research-governance.md`
6. `tools/free-data-and-tools.md`

### 实现正式数据库或页面接入

1. `schemas/research-history-storage.md`
2. `schemas/research-ui-artifact.schema.md`
3. `schemas/run-layout.md`
4. `rules/research-governance.md`
5. `roadmap/research-output-upgrade-plan.md`
6. `runs/README.md`

## 单一事实来源

| 问题 | 准绳文件 | 允许在哪里短摘要 |
|---|---|---|
| 这个目录的边界是什么 | `README.md` | `HANDOFF.md` |
| 新会话怎么接手 | `HANDOFF.md` | 无 |
| 文档应该怎么读 | `DOCS_INDEX.md` | `README.md` |
| 领域目录怎么规划和放置 | `ARCHITECTURE.md` | `README.md` |
| 10+1 Agent 编号、中文名和状态 | `registry/README.md` | `codex-agent-playbook.md` 可列调度摘要 |
| Agent 默认调用 | `codex-agent-playbook.md` | `workflows/*.md` |
| 某个 Agent 到底怎么工作 | `agents/<id>.md` | `codex-agent-playbook.md` 可列职责摘要 |
| 单公司研究怎么跑 | `workflows/company-research.md` | `HANDOFF.md` 可给启动提示词 |
| 行业研究怎么跑 | `workflows/industry-research.md` | `codex-agent-playbook.md` 可给默认调度 |
| 主控怎么分批、打回、保存 | `workflows/codex-orchestration.md` | 无 |
| 数据源和工具边界 | `tools/free-data-and-tools.md` | Agent 文档可列本 Agent 常用项 |
| 研究治理和晋级规则 | `rules/research-governance.md` | `README.md` 可一句话概括 |
| Agent 输出结构 | `schemas/agent-output.schema.md` | Agent 文档可列本 Agent 字段 |
| run 目录结构 | `schemas/run-layout.md` | `runs/README.md` |
| 最终报告结构 | `schemas/company-final-report-template.md` | `workflows/company-research.md` |
| 估值最低标准 | `codex-agent-playbook.md` 与 `agents/06-valuation-reviewer.md` | `roadmap/research-output-upgrade-plan.md` 可记录升级背景 |
| 页面产物结构 | `agents/11-research-page-composer.md` 与 `schemas/research-ui-artifact.schema.md` | 无 |
| 历史研究怎么存 | `schemas/research-history-storage.md` | `roadmap/research-output-upgrade-plan.md` |
| 哪些是未来升级项 | `roadmap/research-output-upgrade-plan.md` | 无 |

## 冲突处理

如果文档之间出现冲突，按这个顺序处理：

1. 当前用户明确要求。
2. 项目级 `AGENTS.md` 和系统/开发者指令。
3. 本文件的“单一事实来源”表。
4. 对应 Agent 的 `agents/<id>.md`。
5. 示例 run。

`runs/` 下的历史研究只能作为样例和对比基准，不能反过来覆盖流程、schema 或 Agent 定义。

## 维护规则

1. `README.md` 只讲定位和入口，不重复完整流程。
2. `HANDOFF.md` 只讲新会话怎么接手，不复制所有规则。
3. 新增或改名 Agent 时，必须同步 `registry/README.md`、`codex-agent-playbook.md` 和对应 `agents/*.md`。
4. 修改单公司流程时，只改 `workflows/company-research.md`，必要时在 `HANDOFF.md` 放一句提示。
5. 修改输出字段时，先改 `schemas/*.md`，再改相关 Agent 文档。
6. `roadmap/research-output-upgrade-plan.md` 是升级清单；已采纳的规则必须落回对应准绳文件。
7. 不再把本领域日常入口放到 `docs/changes/`。
