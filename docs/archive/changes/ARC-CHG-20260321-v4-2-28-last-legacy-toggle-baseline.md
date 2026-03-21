> Archive-Meta
- Archive-ID: ARC-CHG-20260321-v4-2-28-last-legacy-toggle-baseline
- Archive-Type: CHG
- Archived-At: 2026-03-21
- Source-Path: docs/changes/MOD-20260321-01-v4-2-28-page-baseline-freeze.md
- Status: FROZEN

# MOD-20260321-01 最后一个支持“旧版 / 新版切换”的生产基线（v4.2.28）

## 1. 基本信息
- 标题：最后一个支持“旧版 / 新版切换”的生产基线（`v4.2.28`）
- 状态：DONE / ARCHIVED
- 负责人：Codex
- 关联 Task ID：`CHG-20260321-01`
- 关联 CAP：`CAP-REALTIME-FLOW`, `CAP-HISTORY-30M`, `CAP-L2-HISTORY-FOUNDATION`, `CAP-SANDBOX-REVIEW`
- 冻结目的：为下一阶段“去掉旧版、只保留新版”提供**明确可回滚的产品基线**，并把“还能切换旧版/新版的最后一版”作为长期可检索锚点固定下来。
- 检索关键词：`旧版/新版切换`、`legacy toggle baseline`、`v4.2.28`
- GitHub 长期锚点：建议保留别名 tag `baseline-v4.2.28-legacy-toggle`

## 2. 回滚锚点（冻结）
- 当前生产版本：`v4.2.28`
- 当前基线 commit：`c1eec34`
- 当前回滚 tag：`v4.2.28`
- 显式回滚别名 tag：`baseline-v4.2.28-legacy-toggle`
- 上一生产版本：`v4.2.27`
- 上一版本 commit：`9917998`
- 深度治理快照：`snapshot-20260318-pre-governance`
- 深度治理回滚分支：`codex/archive-pre-governance-20260318`
- 当前首页信息架构：**旧版 / 新版并存**
- 当前复盘主链路：**正式 `/api/review/*`**，sandbox 仅保留实验入口

## 3. 当前生产数据底座覆盖（按 2026-03-21 基线核对）

### 3.1 正式 L2 历史底座
| 表 | 作用 | 覆盖范围 | 股票数/说明 |
|---|---|---|---|
| `history_daily_l2` | 正式日线 L1/L2 历史 | `2025-01-02 ~ 2026-03-20` | `878,117` 行，`8,286` symbols |
| `history_5m_l2` | 正式 5m L1/L2 历史 | `2025-01-02 ~ 2026-03-20` | `42,447,483` 行，`8,286` symbols |
| `stock_universe_meta` | 正式复盘股票元数据 | `as_of_date=2026-03-11` | `8,286` 行 |

### 3.2 历史分段
| 区间 | `history_daily_l2` | `history_5m_l2` | 含义 |
|---|---:|---:|---|
| `2025-01-01 ~ 2026-02-28` | `764,803` 行 / `2,787` symbols | `37,344,224` 行 / `2,787` symbols | 已购历史池整体提升结果 |
| `2026-03-01 ~ 2026-03-20` | `113,314` 行 / `8,285` symbols | `5,103,259` 行 / `8,285` symbols | 每日盘后正式日更 |
| `2026-03-20` 单日 | `7,628` symbols | `345,076` 行 / `7,628` symbols | 最新正式入库日 |

### 3.3 盘中/当日预览层与实时层
| 表 | 作用 | 覆盖范围 | 备注 |
|---|---|---|---|
| `realtime_daily_preview` | 盘中当日日级 L1 preview | `2026-03-13 ~ 2026-03-20` | `17` 行，`6` symbols |
| `realtime_5m_preview` | 盘中当日 5m L1 preview | `2026-03-13 ~ 2026-03-20` | `627` 行，`6` symbols |
| `history_1m` | 当日/近日本地分钟聚合 | `2026-02-27 ~ 2026-03-20` | `5,159` 行，`12` symbols |
| `trade_ticks` | 当日逐笔底座 | `2026-02-27 ~ 2026-03-20` | `388,041` 行，`13` symbols |

### 3.4 旧链路存量表
| 表 | 当前用途 | 覆盖范围 |
|---|---|---|
| `local_history` | 旧版日线 / 本地自算兜底 | `2025-01-02 ~ 2026-03-20`，`1,429,297` 行，`5,221` symbols |
| `history_30m` | 旧版 30m 趋势兜底 | `2025-01-02 ~ 2026-03-20`，`11,434,581` 行，`5,221` symbols |
| `data/sandbox/review_v2/*` | sandbox 实验复盘池 | `2025-01-01 ~ 2026-02-28`，约 `2,788` symbols |

## 4. 当前页面信息架构（冻结）

### 4.1 根路由 `/`
- 顶部有**页面版本切换**：`旧版` / `新版`
- `pageVersion='legacy'` 时：
  - `当日分时` → `RealtimeView`
  - `30分钟线` → `HistoryView forceViewMode="intraday"`
  - `日线` → `HistoryView forceViewMode="daily"`
- `pageVersion='fusion_v1'` 时：
  - `当日分时` → `RealtimeView`
  - `历史多维` → `HistoryMultiframeFusionView`
- 只要已选股票，底部都会额外挂一块：`SentimentDashboard`

### 4.2 复盘路由 `/sandbox-review`
- 组件名仍是 `SandboxReviewPage`
- 但**正式主链路已经切到**：
  - `GET /api/review/pool`
  - `GET /api/review/data`
- sandbox `/api/sandbox/*` 仍保留，但不是当前正式复盘页主路径

## 5. 逐页面 / 逐模块冻结说明

### 5.1 首页壳层（搜索 + 实时报价 + 版本切换）
- 入口组件：`src/App.tsx`
- 搜索：新浪 suggest
- 实时报价头：腾讯 `qt.gtimg.cn`
- 现状：首页壳层仍是**旧版/新版共存态**，这是下一阶段准备删除的核心对象
- 风险：若未来只删按钮、不梳理默认状态与 fallback 组件，很容易让首页出现“无入口但仍保留旧 state 分支”的半收敛状态

### 5.2 当日分时（旧版入口）
- 组件：`src/components/dashboard/RealtimeView.tsx`
- 对应入口：`旧版 -> 当日分时`
- 实际与新版关系：**与新版当日分时完全共用同一个组件**，不是两套实现
- 主要接口：
  - `GET /api/realtime/dashboard`
  - `GET /api/realtime/intraday_fusion`
  - `POST /api/watchlist/heartbeat`
- 数据来源：
  - 行情头：腾讯 L1 实时报价
  - 逐笔/主力图：`trade_ticks`、`history_1m`
  - 盘中 preview：`realtime_5m_preview / realtime_daily_preview`
  - 历史/盘后 finalized：`history_5m_l2`
- 当前功能冻结：
  1. `主力动态` 已完成 `5m` 化；
  2. `资金博弈分析` 已完成 `L1/L2 双轨`；
  3. 盘中只显示 `L1` 单轨；
  4. 盘后/历史显示上下双轨；
  5. 调参 UI 已完成，按 `symbol` 写浏览器本地存储。
- 当前数据覆盖语义：
  - **今天**：依赖实时层 / preview 层，覆盖明显小于正式历史库；
  - **历史指定日**：凡正式 `history_5m_l2` 已覆盖的日期，均可回放 L1/L2 双轨；
  - 按 `2026-03-21` 基线，正式历史可追溯到 `2025-01-02`，但盘中 preview 仅覆盖近几日、少量 symbol。

### 5.3 30分钟线（仅旧版入口）
- 组件：`src/components/dashboard/HistoryView.tsx`
- 对应入口：`旧版 -> 30分钟线`
- 主接口：`GET /api/history/trend`
- 当前后端优先级：
  1. `history_5m_l2` 聚合 `30m`
  2. 若没有正式 L2，则回退 `history_30m`
  3. 若是今天，还会尝试把 today realtime ticks merge 进末端
- 当前覆盖：
  - 正式 L2 可覆盖部分：`2025-01-02 ~ 2026-03-20`（8,286 symbols）
  - 旧 30m fallback：`2025-01-02 ~ 2026-03-20`（5,221 symbols）
- 当前定位：**这是旧版独有页面**；新版不再单独提供 30m Tab，而是吸收入历史多维粒度切换

### 5.4 日线（仅旧版入口）
- 组件：`src/components/dashboard/HistoryView.tsx`
- 对应入口：`旧版 -> 日线`
- 主接口：`GET /api/history_analysis`
- 当前后端优先级：
  1. `history_daily_l2`
  2. 若无正式结果则回退新浪历史接口
  3. 若 source 切到 `local`，则读 `local_history`
  4. 今天还会尝试用 `realtime_daily_preview` 覆盖未 finalized 的当日行
- 当前覆盖：
  - 正式日线：`2025-01-02 ~ 2026-03-20`（8,286 symbols）
  - 旧 `local_history`：`2025-01-02 ~ 2026-03-20`（5,221 symbols）
- 当前定位：仍是旧版入口；新版日线逻辑已被历史多维 `1d` 吸收

### 5.5 当日分时（新版入口）
- 组件：仍为 `RealtimeView`
- 对应入口：`新版 -> 当日分时`
- 与旧版差异：**仅入口不同，模块本体完全相同**
- 冻结结论：
  - 如果未来去掉旧版入口，`RealtimeView` 不需要删除；
  - 只需要保证首页默认直接走新版壳层即可。

### 5.6 历史多维（新版主模块）
- 组件：`src/components/dashboard/HistoryMultiframeFusionView.tsx`
- 对应入口：`新版 -> 历史多维`
- 主接口：`GET /api/history/multiframe`
- 粒度：`5m / 15m / 30m / 1h / 1d`
- 数据来源：
  - finalized：`history_5m_l2 / history_daily_l2`
  - today preview：`realtime_5m_preview / realtime_daily_preview`
  - 缺失点：查询层补 `placeholder + quality_info`
- 当前覆盖：
  - 正式主覆盖：`2025-01-02 ~ 2026-03-20`
  - 其中 `2025-01 ~ 2026-02` 主要来自已购历史池提升，`2026-03` 来自正式日更
- 当前定位：**未来首页唯一保留的历史主视图**

### 5.7 散户情绪监测（根路由底部常驻）
- 组件：`src/components/sentiment/SentimentDashboard.tsx`
- 展示逻辑：只要 `activeStock` 存在就显示；与旧版/新版切换无关
- 主接口：
  - `/api/sentiment/dashboard/{symbol}`
  - `/api/sentiment/trend/{symbol}`
  - `/api/sentiment/comments/{symbol}`
  - `/api/sentiment/summary/*`
- 数据源：东方财富股吧 + 本地情绪库
- 覆盖说明：这是**按股票按需抓取型**模块，不存在像 L2 历史那样的固定全市场覆盖窗口
- 冻结结论：下一阶段即使移除旧版入口，这个模块仍保留在首页底部

### 5.8 正式复盘页（当前仍挂在 `/sandbox-review` 路由）
- 组件：`src/components/sandbox/SandboxReviewPage.tsx`
- 正式接口：
  - `GET /api/review/pool`
  - `GET /api/review/data`
- 股票池规则：
  - 基于 `history_daily_l2` 已覆盖 symbols
  - join `stock_universe_meta`
  - 去掉名称含 `ST`
  - 仅保留 `sh60/sh68/sz00/sz30/bj` 正常证券
- 当前接口基线：
  - `total=5188`
  - `latest_date=2026-03-20`
- 当前数据覆盖：
  - 5m / 日线均来自正式生产 `history_5m_l2 / history_daily_l2`
  - 可连续覆盖 `2025-01-02 ~ 2026-03-20`
- 当前产品事实：**页面名字虽然还是 SandboxReviewPage，但业务上已经是正式复盘页**

### 5.9 sandbox 实验复盘链路（保留，但已降级为实验用途）
- 路由/API：
  - `/api/sandbox/pool`
  - `/api/sandbox/review_data`
- 数据底座：`data/sandbox/review_v2/meta.db + symbols/*.db`
- 固定窗口：`2025-01-01 ~ 2026-02-28`
- 固定池：约 `2788` 只
- 当前角色：
  - 实验 / 验真 / 特殊样本研究
  - 不再承担正式复盘页主链路

## 6. 基线结论（供下一阶段删旧版使用）
1. **首页真正重复的只有壳层入口，不是所有模块都重复实现**：
   - `旧版当日分时` 与 `新版当日分时` 共用 `RealtimeView`
   - 真正旧版独有的是：`30分钟线`、`日线` 两个入口，以及顶部 `旧版/新版` 切换
2. **新版已经具备替代首页主路径的条件**：
   - 当日分时：已完成 L1/L2 双轨首轮
   - 历史多维：已覆盖 `5m/15m/30m/1h/1d`
   - 散户情绪：与页面版本无关
3. **正式复盘页已独立于首页旧版/新版切换**，因此首页去旧版不会影响 `/sandbox-review` 当前正式主链路
4. **最安全的下一步**：
   - 先从首页信息架构中移除“旧版”入口与 `pageVersion` 分支
   - 第一阶段允许保留 `HistoryView` 代码文件与相关旧接口作为暗桩回滚缓冲
   - 如新版稳定一个版本后，再另开卡物理删除旧组件/旧入口代码

## 7. 回滚说明（冻结）
- 若“只保留新版”上线后出现严重问题，优先回滚到：`v4.2.28`
- 回滚时的产品形态应恢复为：
  1. 首页可切换 `旧版 / 新版`
  2. 旧版含 `当日分时 / 30分钟线 / 日线`
  3. 新版含 `当日分时 / 历史多维`
  4. 底部保留 `散户情绪监测`
  5. `/sandbox-review` 继续使用正式 `/api/review/*` 主链路
- 该回滚不要求退回到早期 sandbox 时代；`v4.2.28` 本身已是“复盘正式并库后”的稳定基线

## 8. 归档信息
- 归档时间：2026-03-21
- Archive ID：ARC-CHG-20260321-v4-2-28-last-legacy-toggle-baseline
- 归档路径：docs/archive/changes/ARC-CHG-20260321-v4-2-28-last-legacy-toggle-baseline.md
