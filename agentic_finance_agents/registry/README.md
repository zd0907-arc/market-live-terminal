# Agent 注册表

## 结论

本文件是 Agent 编号、中文名、来源、状态和默认模型的准绳。具体怎么调度看 `../codex-agent-playbook.md`，单个 Agent 怎么工作看 `../agents/*.md`。

## 当前 Agent

| 编号 | 中文名 | 英文原型/定位 | 来源 | 状态 | 默认模型 |
|---|---|---|---|---|---|
| 01 | 研究总签 Agent | Pitch Builder | Anthropic 10 金融 Agent 改造 | active | `5.5 high` |
| 02 | 任务拆解与研究 Brief Agent | Meeting Preparer | Anthropic 10 金融 Agent 改造 | active | `5.5 high` |
| 03 | 财报与管理层信号 Agent | Earnings Reviewer | Anthropic 10 金融 Agent 改造 | active | `5.5 high` |
| 04 | 轻量财务建模 Agent | Model Builder | Anthropic 10 金融 Agent 改造 | active | `5.5 high`，复杂勾稽可升 `5.5 xhigh` |
| 05 | 市场与行业研究 Agent | Market Researcher | Anthropic 10 金融 Agent 改造 | active | `5.5 high` |
| 06 | 估值与股价驱动核查 Agent | Valuation Reviewer | Anthropic 10 金融 Agent 改造 | active | `5.5 high`，关键估值分歧可升 `5.5 xhigh` |
| 07 | 事实一致性对账 Agent | General Ledger Reconciler | Anthropic 10 金融 Agent 改造 | active | `5.5 high`，重大冲突裁决可升 `5.5 xhigh` |
| 08 | 研究收口与晋级 Agent | Month-end Closer | Anthropic 10 金融 Agent 改造 | active | `5.5 high` |
| 09 | 财务质量审查 Agent | Statement Auditor | Anthropic 10 金融 Agent 改造 | active | `5.5 high`，复杂财务质量可升 `5.5 xhigh` |
| 10 | 实体、监管与舆情风险 Agent | KYC Screener | Anthropic 10 金融 Agent 改造 | active | `5.5 high` |
| 11 | 研究页面生成 Agent | Research Page Composer | 本项目新增表达层 | active | `5.5 high` |

说明：

- 01 到 10 是官方 10 金融 Agent 的 A 股研究化改造。
- 11 不是官方金融研究 Agent，只负责把已对账研究结果转成页面产物。
- 默认研究 A 股，不研究美股。

## Agent 文件映射

| 编号 | 定义文件 |
|---|---|
| 01 | `../agents/01-pitch-builder.md` |
| 02 | `../agents/02-meeting-preparer.md` |
| 03 | `../agents/03-earnings-reviewer.md` |
| 04 | `../agents/04-model-builder.md` |
| 05 | `../agents/05-market-researcher.md` |
| 06 | `../agents/06-valuation-reviewer.md` |
| 07 | `../agents/07-gl-reconciler.md` |
| 08 | `../agents/08-month-end-closer.md` |
| 09 | `../agents/09-statement-auditor.md` |
| 10 | `../agents/10-kyc-screener.md` |
| 11 | `../agents/11-research-page-composer.md` |

## 状态定义

| 状态 | 含义 |
|---|---|
| `active` | 可被主控调度 |
| `experimental` | 可试跑，但不能默认进正式流程 |
| `deprecated` | 不再新调用，只保留历史 run 可读性 |

## 扩展规则

新增 Agent 时必须：

1. 使用下一个连续编号。
2. 给中文名和英文定位。
3. 标注来源：官方改造、本项目新增、实验 Agent。
4. 给默认模型和可升级条件。
5. 在 `../agents/` 新增定义文件。
6. 在必要 workflow 中显式写入它什么时候被调用。
7. 如果会产出新字段，同步 schema。
