# MOD-20260425-01 长记忆文档重构 Phase 1

## 1. 基本信息
- ID：`MOD-20260425-01`
- 类型：`MOD`
- 状态：`ACTIVE`
- 发起时间：`2026-04-25 00:25 CST`
- 执行分支：`codex/chore-repo-prune-audit-20260424`

## 2. 背景
- 当前项目已经完成 `main / v5.0.0` 的真相归一，但核心文档仍明显过长；
- 核心问题不是“缺文档”，而是**长记忆（稳定事实）和短记忆（需求过程）混杂**；
- 直接后果是：AI 每次读核心文档都被大量历史过程与低优先级细节淹没，当前有效事实反而不够突出。

## 3. 本轮目标
1. 先压缩两个最容易失控的动态核心文档：
   - `AI_HANDOFF_LOG.md`
   - `07_PENDING_TODO.md`
2. 把“需求完成后必须做文档回流 / 待办收口 / 日志归档”的机制固化到 `06 / 08`；
3. 形成后续继续瘦身 `04 / 03 / 02` 的规则基础。

## 4. 本轮原则
- `docs/` 是**长记忆**，只记录系统当前是什么；
- `docs/changes/` 是**短记忆**，记录这次需求是怎么做出来的；
- `AI_HANDOFF_LOG.md` 只保留最近 `1~2` 个版本窗口；
- `07_PENDING_TODO.md` 只保留当前真实还在 pending 的事项；
- 老过程不必继续占核心文档正文，可转为 archive summary。

## 5. 本轮输出
1. 一份精简后的 `AI_HANDOFF_LOG.md`；
2. 一份精简后的 `07_PENDING_TODO.md`；
3. 两份对应 archive summary；
4. `06 / 08` 中正式写入“收尾即清理”的规则。

## 6. 验收
- `AI_HANDOFF_LOG.md` 控制在近期窗口，不再覆盖整个历史阶段；
- `07_PENDING_TODO.md` 只保留当前活跃项；
- `06 / 08` 已明确：
  - 长记忆 / 短记忆分离；
  - 需求完成后必须回流长期事实；
  - 已完成/失效待办必须移出 `07`；
  - 老 handoff 必须定期归档。

## 7. 结果回填
- 当前进度（`2026-04-25 00:40 CST`）：
  - `AI_HANDOFF_LOG.md` 已从 `1370` 行压缩到 `106` 行，仅保留最近 `1~2` 个版本窗口；
  - `07_PENDING_TODO.md` 已从 `422` 行压缩到 `77` 行，仅保留 `8` 个当前活跃项；
  - 已新增两份 archive summary：
    - `docs/archive/ARC-LEG-20260425-ai-handoff-log-pre-v5-summary.md`
    - `docs/archive/ARC-LEG-20260425-pending-todo-pre-v5-summary.md`
  - `06_CHANGE_MANAGEMENT.md` 已新增：
    - 已解决/失效待办必须从 `07` 移除或归档；
    - `AI_HANDOFF_LOG` 超窗必须归档旧窗口；
    - 需求收尾必须做文档回流、待办清理、日志压缩；
  - `08_DOCS_GOVERNANCE.md` 已新增：
    - `docs/` 长记忆 / `docs/changes/` 短记忆边界；
    - `AI_HANDOFF_LOG / 07_PENDING_TODO` 的长度约束；
    - 文档收尾强制动作。
  - `npm run check:baseline` 已通过。
