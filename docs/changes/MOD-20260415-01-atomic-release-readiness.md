# MOD-20260415-01-atomic-release-readiness

## 1. 基本信息
- 标题：原子事实层切换与数据治理生产发布准备
- 状态：DRAFT
- 负责人：Codex
- 关联 Task ID：`CHG-20260415-01`
- 关联 CAP：`CAP-L2-HISTORY-FOUNDATION`, `CAP-HISTORY-30M`, `CAP-SELECTION-RESEARCH`, `CAP-WIN-PIPELINE`
- 关联 STG：
  - `STG-20260412-04-atomic-formal-backfill-runbook.md`
  - `MOD-20260412-05-selection-atomic-backfill-retrospective.md`

## 2. 背景与目标

截至 `2026-04-15`：

1. **当前生产冻结基线**仍是 `v4.2.32 / 9bbdd3d`，且已归档：
   - Tag：`v4.2.32`
   - 归档卡：`docs/archive/changes/ARC-CHG-20260324-retail-sentiment-v2-release-and-backfill.md`
2. Windows 正式原子库主板全量回补已完成：
   - 库：`D:\market-live-terminal\data\atomic_facts\market_atomic_mainboard_full_reverse.db`
   - 状态：`done`
3. 本地/工作分支已完成：
   - 复盘页 atomic fallback
   - 历史多维 atomic fallback
   - 选股 research atomic fallback
   - `local` 历史入口 atomic 优先

本卡目标不是立即发布，而是冻结“**从当前生产版 -> 原子事实层版**”的真实切换路径，并明确发布 gate。

## 3. 方案与边界

- 做什么：
  - 确认当前生产版本已有正式归档锚点；
  - 确认当前数据治理阶段已进入“可准备发版”状态；
  - 以**直接切 atomic 主链路**为方向，而不是继续长期维护旧表兼容；
  - 冻结生产发布前的最小 gate 与冒烟点。
- 不做什么：
  - 本卡不直接执行生产 deploy；
  - 本卡不把旧表立即删除；
  - 本卡不处理新闻/公告等独立新数据域。

## 4. 当前状态判断

### 4.1 版本/分支判断
- `origin/main` 当前头：`1ef5720`
- 最新正式 tag：`v4.2.32`
- 当前工作分支：`codex/atomic-integration-migration`
- 当前本地开发版：`v4.2.36`

### 4.2 判断结论
- 当前状态属于：**UNRELEASED_WORK + STAGE_READY_TO_NORMALIZE**
- 原因：
  1. 数据治理/atomic 切换已经形成完整阶段成果；
  2. 当前生产版 `v4.2.32` 已有 tag + 归档卡，可作为回滚锚点；
  3. 这次变更会影响复盘/历史/选股的数据底座，已不是普通 patch；
  4. 发布时不建议继续沿用碎片化 `4.2.33~4.2.36` 作为正式 tag，应重新**归一化为一个正式发布版本**。

### 4.3 建议版本策略
- **建议正式发布版本：`v4.3.0`**
- 理由：
  - 这次不是单点 bugfix，而是“原子事实层 + 页面数据主链路切换 + 选股研究底座上线”；
  - 对用户而言是新阶段，不适合继续堆 patch 号。

## 5. 发布前必须完成的最小 gate

1. **代码面**
   - `main` 分支接入当前 atomic 集成结果；
   - 版本号统一收口到同一个正式版本（建议 `v4.3.0`）；
   - `npm run check:baseline` 通过；
   - 本地 smoke 通过。

2. **数据面**
   - 生产 Docker / 服务端能稳定挂到正式 atomic DB；
   - 至少验证：
     - 复盘页
     - 首页历史多维
     - 选股页
   - 使用同一份正式 atomic 主板库。

3. **页面 smoke**
   - 首页搜索 `sz000977`：历史多维正常
   - 复盘页打开一只主板票：日线/5m 正常
   - 选股页 `2026-04-10`：Top10 正常出数

4. **回滚锚点**
   - 旧生产锚点：`v4.2.32 / 9bbdd3d`
   - 新发布锚点：待正式 cut tag 后记录

## 6. 推荐执行顺序

1. 把当前 `codex/atomic-integration-migration` 继续做成“直接切 atomic 主链路”版本；
2. 完成最后一轮本地 smoke；
3. 合回 `main`；
4. 把版本统一归一到 `v4.3.0`；
5. 生成 release commit + tag；
6. 再执行生产部署与冒烟。

## 7. 风险与回滚

- 风险：
  - 生产环境若 atomic DB 挂载路径不一致，会导致页面空白；
  - 若仍有少量接口在读旧表，可能出现“同一页面不同模块口径不一致”；
  - 选股页若生产未同步 selection DB / feature 结果，只切 atomic 不等于立即有候选。
- 回滚：
  - 若生产 smoke 不通过，回滚到 `v4.2.32 / 9bbdd3d`；
  - atomic DB 保留，不影响回滚旧生产代码。

## 8. 结果回填
- 实际改动：
  - 新增发布准备母卡；
  - 确认当前生产版本已存在正式归档锚点；
  - 把本轮阶段归类为“可准备正式 release normalize”。
- 验证结果：
  - `v4.2.32` 已存在 tag 与归档卡；
  - 当前开发版四处版本号已统一到 `4.2.36`；
  - baseline 在修平版本面后应作为后续 release gate 执行。
- 遗留问题：
  - 尚未正式把当前分支合回 `main`；
  - 尚未真正 cut `v4.3.0`；
  - 尚未执行生产部署。

## 9. 归档信息
- 归档时间：
- Archive ID：
- 归档路径：
