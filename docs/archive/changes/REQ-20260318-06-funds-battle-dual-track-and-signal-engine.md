# REQ-20260318-06-funds-battle-dual-track-and-signal-engine

## 1. 基本信息
- 标题：Phase 4｜资金博弈双轨 UI 与前端信号引擎
- 状态：ACTIVE
- 负责人：Codex / 前端 AI
- 关联 Task ID：`CHG-20260319-01`
- 关联 CAP：`CAP-REALTIME-FLOW`, `CAP-L2-HISTORY-FOUNDATION`
- 关联 STG：`STG-20260318-03`

## 2. 背景与目标
- 当前 `SentimentTrend` 仍基于旧 `/api/sentiment*` 与 3 分钟/快照口径，信号体系也沿用 `砖头 / 冰 / 火` 等高噪音表达；
- 本阶段目标是：
  1. 以统一 `5m bars[]` 重写资金博弈模块；
  2. 盘中保留 L1 单轨，盘后/历史展示 L1 vs L2 双轨；
  3. 把信号生成收口到前端，并冻结 VWAP + 空间位置 + 共振过滤规则。

## 3. 方案与边界
- 做什么：
  - 用新组件替换旧 `SentimentTrend`；
  - 冻结盘中/盘后标题文案；
  - 前端计算 VWAP、波动率通道、成交量共振与文字信号；
  - 首期开放“仅当前页面会话生效”的高级调参 UI。
- 不做什么：
  - 本阶段不保留旧 `砖头/冰火` 图标体系；
  - 本阶段不把信号计算挪回后端。

## 4. 标题态与布局（必须写死）
### 4.1 盘中模式
- 标题：`[ 🕒 盘中 L1 快照估算 ]`
- 展示：单张 L1 5m 资金博弈图
- 行为：不触发撤单/隐藏单信号系统

### 4.2 盘后/历史双轨
- 上图标题：`[ L1 表象资金博弈 (快照推演) ]`
- 下图标题：`[ L2 真实资金博弈 (逐笔穿透) ]`
- 两图结构保持同构：
  - CVD 面图
  - OIB 柱状图
  - 共用同一 5m 时间轴与 tooltip 锚点

## 5. 前端信号引擎（冻结）
### 5.1 前端职责
- 前端收到 `bars[]` 后，按当日累计 `Σ total_amount / Σ total_volume` 计算 VWAP；
- 同时计算：
  - VWAP 空间位置
  - 波动率通道（首期前端常量）
  - 成交量共振（首期前端常量）
- 仅当前模式为 `postclose_dual_track` 或 `historical_dual_track` 时允许生成信号。

### 5.2 首期文字标签
- `吃`（红）
- `诱空`（红）
- `出`（绿）
- `诱多`（绿）

### 5.3 首期触发规则
1. `吃`
   - 条件：`(l2_net_inflow - l1_net_inflow > 5_000_000) AND (close < vwap)`
2. `诱空`
   - 条件：`(cancel_sell_amount > 5_000_000) AND (close < vwap OR close 位于低位通道)`
3. `出`
   - 条件：`(l1_net_inflow - l2_net_inflow > 5_000_000) AND (close > vwap)`
4. `诱多`
   - 条件：`(cancel_buy_amount > 5_000_000) AND (close > vwap OR close 位于高位通道)`

### 5.4 参数预留与首期页面级调参
- 首期页面级调参 UI 暴露 5 个核心参数：
  - `diffThreshold`
  - `cancelThreshold`
  - `vwapDistanceThreshold`
  - `volatilityChannelRatio`
  - `volumeResonanceRatio`
- 首期默认值（放宽后的联调默认）：
  - `diffThreshold = 2_000_000`
  - `cancelThreshold = 2_000_000`
  - `vwapDistanceThreshold = 0.0015`
  - `volatilityChannelRatio = 0.005`
  - `volumeResonanceRatio = 1.0`
- 调参边界：
  - 仅写浏览器本地，不写后端配置；
  - 按 `symbol` 分股票持久化；
  - 同一股票刷新页面后沿用上次调参值；
  - 点击“恢复默认”后清除该股票的本地覆盖值。

## 6. 执行步骤（按顺序）
1. 下线旧 `SentimentTrend` 的正式职责，改接统一接口；
2. 用新组件重建单轨/双轨布局与标题态；
3. 前端接入 VWAP 与信号计算；
4. 完成盘中禁信号、盘后/历史启信号的模式联调。

## 7. 验收标准（Given/When/Then，绝对时间）
- Given `2026-03-18 10:00`，When 打开资金博弈分析，Then 标题显示 `[ 🕒 盘中 L1 快照估算 ]`，且页面不出现 `吃/出/诱空/诱多` 标记。
- Given `2026-03-18 22:00`，When 当天 finalized L2 已到位，Then 资金博弈区自动显示上下双轨，标题分别为 `[ L1 表象资金博弈 (快照推演) ]` 与 `[ L2 真实资金博弈 (逐笔穿透) ]`。
- Given `2026-03-17 14:35` 某个 5m bar 满足 `cancel_sell_amount > 5_000_000` 且 `close < vwap`，When 前端渲染 L2 图，Then 该 bar 可生成 `诱空` 文字标签。
- Given `2026-03-17 14:40` 处于历史双轨模式，When 前端重新计算 VWAP，Then 结果必须只依赖接口返回的 `total_amount/total_volume`，不得再向后端请求专用 VWAP 字段。

## 8. 风险与回滚
- 风险：
  1. 若仍保留旧图标体系，会与新的低噪音策略冲突；
  2. 若 VWAP 继续由后端和前端双算，会导致信号阈值不可解释；
  3. 若盘中也开放撤单信号，会制造大量伪信号。
- 回滚：
  - 文档阶段不改代码；
  - 实施阶段若新组件未稳定，可临时保留旧组件隐藏入口，但正式验收以新组件为准。

## 9. 结果回填
- 实际改动：当前仅冻结资金博弈双轨 UI、标题态与前端信号引擎规则。
- 验证结果：VWAP 与信号职责边界已明确为“后端给绝对值，前端做策略”。
- 遗留问题：调参结果是否需要页面持久化/全局配置化、历史复盘页是否复用同一信号引擎、`U` 事件若后续拆分是否要影响 `诱空/诱多`。

## 10. 归档信息
- 归档时间：
- Archive ID：
- 归档路径：
