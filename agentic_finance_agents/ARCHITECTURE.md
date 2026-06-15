# Agentic Finance Agents 领域结构

## 结论

`agentic_finance_agents/` 是本项目里的独立研究 Agent 领域目录。它和一次普通需求变更不同，不放在 `docs/changes/` 下，也不依附某个前端页面。

它的职责是长期管理：

1. 金融研究 Agent 的定义。
2. 每个 Agent 可用的工具、数据源和规则。
3. Codex 对话里的调度流程。
4. 每次研究的临时产出、对账结果和可晋级候选。
5. 未来进入页面、数据库或训练数据前的中间层。

## 放置决策

根目录保留：

```text
agentic_finance_agents/
```

理由：

- 它是跨页面、跨任务、跨未来研究场景复用的领域能力。
- 它不是 `docs/changes` 这种一次性需求记录。
- 它暂时也不是 `backend/` 服务或 `frontend/` 页面，不能提前绑定实现形态。
- 它未来可能沉淀为服务、数据库、页面数据源或训练数据，但现在先作为独立工作台管理。

## 目录职责

```text
agentic_finance_agents/
  README.md
  HANDOFF.md
  DOCS_INDEX.md
  ARCHITECTURE.md
  registry/
  agents/
  tools/
  rules/
  workflows/
  schemas/
  runs/
  roadmap/
```

| 目录/文件 | 职责 | 变更条件 |
|---|---|---|
| `README.md` | 领域入口，说明是什么、不是什么 | 领域边界变化 |
| `HANDOFF.md` | 新会话快速接手 | 调用入口或关键限制变化 |
| `DOCS_INDEX.md` | 文档地图和单一事实来源 | 新增/移动文档 |
| `ARCHITECTURE.md` | 领域结构和放置规则 | 目录结构或生命周期变化 |
| `registry/` | Agent 名册、编号、状态、扩展规则 | 新增/下线/改名 Agent |
| `agents/` | 单个 Agent 的人格、工具、数据、工作流、输出、护栏 | 某个 Agent 能力变化 |
| `tools/` | 本地数据、免费来源、工具能力、禁用项 | 数据源或工具变化 |
| `rules/` | 研究治理、证据、对账、晋级、保存边界 | 质量标准变化 |
| `workflows/` | 单公司、行业、Codex 编排流程 | 调度链路变化 |
| `schemas/` | JSON/Markdown/run/page/db 结构 | 产物结构变化 |
| `runs/` | 每次研究的临时产出 | 新增研究 run |
| `roadmap/` | 已发现但尚未完全产品化的升级项 | 质量缺口或路线变化 |

## 生命周期

一次正式研究从这里经过：

1. 用户在 Codex 对话里提出研究任务。
2. 主控读取 `HANDOFF.md`、`DOCS_INDEX.md` 和对应 workflow。
3. `02` 生成研究 brief。
4. 主控按 `registry/` 和 `workflows/` 调度需要的 Agent。
5. Agent 按 `agents/`、`tools/`、`rules/` 独立取数、分析、输出。
6. `07` 做事实和口径对账。
7. `01` 汇总研究结论。
8. `08` 判断哪些内容可以晋级，哪些只能留在 run。
9. 如果需要页面，`11` 生成 compact/full 页面产物。
10. 产物先保存在 `runs/<run_id>/`。
11. 等字段稳定后，再由明确代码或用户确认写入正式页面、API 或未来研究库。

## 新增 Agent 的规则

新增第 12 个或后续 Agent 时，必须同时做：

1. 在 `registry/README.md` 增加编号、中文名、英文名、定位、状态和默认模型。
2. 在 `agents/` 新增 `NN-agent-name.md`。
3. 如果它进入默认流程，更新对应 `workflows/*.md`。
4. 如果它新增输出字段，更新 `schemas/agent-output.schema.md` 或新 schema。
5. 如果它需要新工具或数据源，更新 `tools/free-data-and-tools.md`。
6. 如果它改变研究质量标准，更新 `rules/research-governance.md`。
7. 如果它影响新会话接手，更新 `HANDOFF.md`。

## 产出边界

`runs/` 保存研究过程和结果，但不是正式业务数据源。正式接入前必须满足：

1. 关键事实有 `source_ref`。
2. 数据缺口写入 `data_gaps`。
3. `07` 完成事实一致性和估值口径对账。
4. `08` 标注可晋级字段。
5. 用户确认或后续代码显式读取。

禁止把 `runs/` 里的内容静默写入：

- 行情事实库。
- L2/atomic 事实库。
- 选股模型特征库。
- 官方事件原始事实层。

## 和项目其他部分的关系

`agentic_finance_agents/` 先作为研究中间层存在。

未来可能对外输出：

- 页面嵌入 HTML：来自 `11` 和 `schemas/research-ui-artifact.schema.md`。
- 公司研究数据库：来自 `schemas/research-history-storage.md`。
- 研究报告或选股卡片字段：来自 `08` 的晋级候选。
- 模型训练材料：只能使用已对账、已标注来源和时间的字段。

这些接入都应该由明确代码实现，不靠文档暗示自动发生。
