# Agent 定义模板

每个 Agent 文件应尽量保持与 Anthropic 官方插件定义同构，但字段要落到本项目可执行的 Codex 调度方式。

## 标准结构

```markdown
---
agent_id: ""
official_name: ""
local_name: ""
mode: "codex_orchestrated"
default_run: true
default_model: "5.5 high"
escalation_model: "5.5 xhigh"
paid_sources: false
---

# <序号> <Agent Name>

## 官方参照
说明 Anthropic 官方 Agent 做什么、依赖什么工具/skills/subagents。

## 本项目深度还原方式
说明哪些官方能力被保留、哪些因 A 股和免费数据源被替换。

## 模型策略
说明默认模型、升级 `5.5 xhigh` 的条件，以及是否需要内部子任务。

## 何时使用
列出触发场景。

## 何时不用
列出边界。

## 可用输入
表格列出本项目免费/本地替代数据。注意：主调度只提供 `run_context.json`、`source_registry.json` 和共享证据缓存；Agent 需要的数据应由本 Agent 按职责自行读取。

## 免费/本地工具
列出 Codex 可用的只读工具能力。

## 内部子任务
映射官方 subagents/skills 到本项目子任务。

## 工作流
可执行步骤。

## 输出文件
Markdown 和 JSON 路径。

## JSON 输出字段
固定字段草案。

## 护栏
数据、发布和结论边界。

## 下游交接
交给哪些 Agent 或用户。

## 用户审阅清单
用户逐个验收时看什么。
```

## 不允许省略的部分

- 官方参照
- 模型策略
- 免费/本地工具
- 工作流
- JSON 输出字段
- 护栏
- 用户审阅清单
