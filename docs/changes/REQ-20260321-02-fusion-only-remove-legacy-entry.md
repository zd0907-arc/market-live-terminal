# REQ-20260321-02-fusion-only-remove-legacy-entry

## 1. 基本信息
- 标题：首页去掉旧版入口，只保留新版信息架构
- 状态：ACTIVE
- 负责人：Codex
- 关联 Task ID：`CHG-20260321-02`
- 关联 CAP：`CAP-REALTIME-FLOW`, `CAP-HISTORY-30M`, `CAP-L2-HISTORY-FOUNDATION`
- 前置依赖：`ARC-CHG-20260321-v4-2-28-last-legacy-toggle-baseline`
- 目标分支：`codex/fusion-only-remove-legacy`

## 2. 背景与目标
- 当前首页仍同时保留 `旧版 / 新版` 两套入口：
  - 旧版：`当日分时 / 30分钟线 / 日线`
  - 新版：`当日分时 / 历史多维`
- 但截至 `v4.2.28`：
  - 当日分时已经共用同一个 `RealtimeView`；
  - 历史多维已经覆盖 `5m / 15m / 30m / 1h / 1d`；
  - 复盘页已独立走正式 `/api/review/*`；
  - 用户不再希望继续保留“旧版/新版切换”心智。
- 本卡目标：**从首页信息架构上彻底收敛到新版，只保留“当日分时 + 历史多维”两大主入口。**

## 3. 方案与边界
### 3.1 做什么
1. 去掉首页顶部 `旧版 / 新版` 切换按钮；
2. 移除 `pageVersion` 与 `legacyViewMode` 的运行时分支；
3. 首页只保留：
   - `当日分时`
   - `历史多维`
   - 底部 `散户情绪监测`
4. 根路由默认直接进入新版壳层；
5. 保留 `/sandbox-review` 路由，不受本卡影响；
6. 不改当前 `RealtimeView`、`HistoryMultiframeFusionView`、正式复盘页的数据接口语义。

### 3.2 首期不做什么
1. **首期不强制物理删除** `HistoryView`、旧接口或旧数据表；
2. 不改 `/api/review/*` 与 `/api/sandbox/*` 的角色边界；
3. 不同时做“旧 30m / 旧日线 API”全量清理；
4. 不在本卡内重构散户情绪模块。

### 3.3 回滚缓冲策略
- 为降低风险，首期采用“**先下入口、后删代码**”策略：
  - UI 与可达路径上不再暴露旧版；
  - 但 `HistoryView` 与相关旧后端接口可先保留一个版本，作为暗桩回滚缓冲；
  - 如新版稳定，再另开清理卡删除死代码。

## 4. 目标页面结构（冻结）
### 4.1 根路由 `/`
- 保留：
  - 搜索/报价头
  - `当日分时`
  - `历史多维`
  - `散户情绪监测`
- 删除：
  - `旧版 / 新版` 顶部按钮
  - `30分钟线`
  - `日线`
  - 所有仅服务旧版入口的首页按钮态

### 4.2 复盘与 sandbox
- `/sandbox-review` 继续保留；
- 正式复盘仍使用 `/api/review/pool`、`/api/review/data`；
- sandbox `/api/sandbox/*` 继续保留实验角色。

## 5. 实施步骤
1. 先在 `App.tsx` 收敛首页状态机，只保留 fusion 路径；
2. 清理首页与旧版入口绑定的按钮、默认态、文案；
3. 回归验证：
   - 当日分时
   - 历史多维
   - 散户情绪
   - `/sandbox-review`
4. 确认无误后，再评估是否开启第二张清理卡删除旧组件/旧接口。

## 6. 验收标准（Given / When / Then）
- Given `2026-03-21 18:00`，When 打开首页，Then 不再看到 `旧版 / 新版` 切换按钮。
- Given `2026-03-21 18:01`，When 选择任意股票，Then 首页只显示 `当日分时 + 历史多维 + 散户情绪监测`。
- Given `2026-03-21 18:02`，When 打开首页，Then 默认展示新版壳层，且当日分时仍可正常请求 `/api/realtime/dashboard` 与 `/api/realtime/intraday_fusion`。
- Given `2026-03-21 18:03`，When 切到历史多维，Then `5m / 15m / 30m / 1h / 1d` 粒度保持可用。
- Given `2026-03-21 18:04`，When 打开 `/sandbox-review`，Then 正式复盘页仍可正常查询 `/api/review/pool` 与 `/api/review/data`。
- Given 新版上线后出现严重问题，When 执行版本回滚，Then 可直接回滚到 `v4.2.28`，恢复旧版/新版并存形态。

## 7. 风险与回滚
- 风险：
  1. 首页状态裁剪时，容易误伤当前共用的 `RealtimeView` 默认参数；
  2. 若直接物理删除 `HistoryView`，回滚成本会明显提高；
  3. 若遗漏某些旧版按钮态或默认 state，可能出现首页空白或错误默认 tab。
- 回滚：
  - 产品回滚锚点固定为 `v4.2.28 / c1eec34`；
  - 当前完整基线说明见：`docs/archive/changes/ARC-CHG-20260321-v4-2-28-last-legacy-toggle-baseline.md`。

## 8. 结果回填
- 当前状态：已在分支 `codex/fusion-only-remove-legacy` 完成首页入口收敛第一步，正式移除首页 `旧版 / 新版` 按钮与旧版三分支入口；首页现只保留 `当日分时 + 历史多维 + 散户情绪监测`。
- 保留策略：当前仅做“下入口”，未物理删除 `HistoryView` 文件与旧接口，继续保留一版暗桩回滚缓冲。
- 验证结果：
  - `npm run build` 通过；
  - `npm run check:baseline` 通过（`84 passed`）。
- 下一步：如需发布，再继续走合并 / 发版流程；若后续确认稳定，可另开清理卡物理删除死代码。
