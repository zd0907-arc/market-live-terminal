# 00_AI_HANDOFF_PROTOCOL（多 AI 协作协议）

> 目标：在前端 AI、后端 AI 与人工协作时，确保“需求可控、实现可追溯、交接可执行”。

## 1. 角色边界

- **前端 AI**：`src/` 与前端交互、展示、体验；不改后端业务规则。
- **后端 AI**：`backend/` 与数据链路、聚合、脚本；不改前端渲染结构。
- **人工**：需求裁决与验收标准最终确认。

> 若必须跨边界改动，需先在需求总册登记并标注“跨边界变更”。

## 2. 任务ID与需求卡机制（强制）

- **当前新建变更卡 ID** 统一使用 `docs/changes/` 的类型化编号：
  - `MOD-YYYYMMDD-NN-*`
  - `REQ-YYYYMMDD-NN-*`
  - `INV-YYYYMMDD-NN-*`
  - `CFG-YYYYMMDD-NN-*`
  - `STG-YYYYMMDD-NN-*`
- 历史 `CHG-YYYYMMDD-序号` 仅作为旧日志 / 旧变更记录保留，不再作为当前新卡标准。
- 所有业务改动必须绑定至少一个 `CAP-*` 能力卡（见 `02_BUSINESS_DOMAIN.md`）。
- 不允许“先改代码后补需求卡”；顺序必须是：
  1. 先在 `06_CHANGE_MANAGEMENT.md` 规则下新建变更卡（`docs/changes/`）；
  2. 在 CAP 卡写“拟变更点”；
  3. 实施改动；
  4. 回填同一卡“实现摘要 + 验收结果 + 变更记录（任务ID）”。

## 3. 单一契约源

- 接口与字段：`03_DATA_CONTRACTS.md` 是唯一契约源。
- 业务规则：`02_BUSINESS_DOMAIN.md` 是唯一需求源。
- 运维发布：`04_OPS_AND_DEV.md` 是唯一 SOP 源。
- 动态过程：`06_CHANGE_MANAGEMENT.md` 是唯一流程源。

## 4. 交接日志规则（短日志）

- `AI_HANDOFF_LOG.md` 仅记录短日志，不写长篇过程。
- 每条日志必须包含：
  - `Task ID / Change Card ID`
  - `涉及 CAP ID`
  - `结论`
  - `风险/阻塞`
  - `链接`
- 日志上限：每条不超过 8 行要点。

## 5. 冲突处理与优先级

当文档间冲突时，按以下优先级执行：
1. `02_BUSINESS_DOMAIN.md`（业务与验收）
2. `03_DATA_CONTRACTS.md`（接口与数据）
3. `04_OPS_AND_DEV.md`（运维执行）
4. `AI_HANDOFF_LOG.md`（仅作执行记录，不可覆盖前3者）

## 6. 发布前最小交付清单

每个任务在声明“完成”前必须满足：
- CAP 卡已回填（需求/实现/验收）
- 若接口变更，契约文档已更新
- Handoff 短日志已登记 Task ID
- 阻塞事项已登记到 `07_PENDING_TODO.md`
- 当前需求已按 `docs/ops/development-workflow.md` 完成收尾动作

## 7. 禁止行为（红线）

- 禁止在需求卡未更新时直接实现业务逻辑改动。
- 禁止在 Handoff 里写“无法复现/已修复”但没有 Task ID 与 CAP 链接。
- 禁止使用历史临时结论覆盖主册规则。
