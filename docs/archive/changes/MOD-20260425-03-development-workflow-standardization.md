# MOD-20260425-03 开发流程固化与收尾标准化

## 1. 基本信息
- ID：`MOD-20260425-03`
- 类型：`MOD`
- 状态：`ACTIVE`
- 发起时间：`2026-04-25 01:20 CST`
- 执行分支：`codex/chore-repo-prune-audit-20260424`

## 2. 背景
- 当前长记忆结构已经完成瘦身，但“需求从开始到结束如何收尾”仍散落在多个文档；
- 过去出现过的主要问题不是不会写文档，而是**只加不减**：
  - 需求做完后不回流长期事实；
  - `07_PENDING_TODO` 已解决项不移出；
  - `AI_HANDOFF_LOG` 老窗口不归档；
  - 合并后分支 / worktree / 文档状态不做统一收口。

## 3. 本轮目标
1. 输出一份正式、可执行的开发流程文档；
2. 覆盖：需求开启 → 分支/worktree 决策 → 开发 → 验证 → 合并 → 文档收尾 → 归档；
3. 将该流程接入 `04 / 06 / 08 / AI_QUICK_START / README / 00`。

## 4. 验收
- 至少有一份单独流程文档可作为默认执行标准；
- 核心入口文档都能跳到该流程；
- 明确写出：
  - 默认只开分支，何时才开 worktree；
  - 合并前检查项；
  - 合并后清理项；
  - 文档回流 / handoff 压缩 / pending 清理的固定动作。

## 5. 结果回填
- 当前进度（`2026-04-25 01:25 CST`）：
  - 已新增 `docs/ops/development-workflow.md`，覆盖：
    - 需求何时开始
    - 先建卡再开发
    - 分支 / worktree 决策
    - baseline 与文档回流
    - merge 前 gate
    - merge 后清理
    - archive 时机
  - 已将该流程接入：
    - `README.md`
    - `docs/AI_QUICK_START.md`
    - `docs/04_OPS_AND_DEV.md`
    - `docs/06_CHANGE_MANAGEMENT.md`
    - `docs/08_DOCS_GOVERNANCE.md`
    - `docs/00_AI_HANDOFF_PROTOCOL.md`
  - 目标是把“只加不减”的旧工作方式改成“每次需求必须完成回流 + 清理 + 收尾”。
