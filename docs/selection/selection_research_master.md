# Selection Research Master（选股研究总册）

> 当前定位：一期先做 **Top10 启动确认候选 + 右侧复盘决策视图 + 详情内出货风险识别**，把“选股 -> 看图 -> 决策”主工作流跑通。

## 1. 目标
- 风格：盘后研究、次日及后续波段参考
- 核心工作流：
  - 按规则扫描全市场
  - 每日输出 `Top10` 启动确认候选
  - 点击候选后，右侧直接复用复盘能力看价格/L1/L2/累计净流入
  - 同时给出选中原因、出货风险、事件时间线
- 案例反推：保留为文档化研究分支，不做系统入口

## 2. 红线
- 只读旧主库：`local_history / history_daily_l2 / history_5m_l2 / sentiment_* / stock_universe_meta`
- 不改旧接口返回结构，不插手旧定时器，不改变原盯盘/复盘/舆情主路径
- 选股派生结果全部写入独立库：`data/selection/selection_research.db`
- 复盘能力采用**嵌入式复用**，不把选股逻辑塞回原复盘模块
- 如策略定义或公式调整，先更新文档卡，再改实现

## 3. 一期冻结方案（V2）
- 左侧：仅展示 `breakout` 候选，默认 `Top10`
- `stealth`：内部前置与解释信号，不单独做主列表入口
- `distribution`：不做全市场榜单，只在右侧详情给当前票输出风险判断
- 右侧：复用现有复盘成熟能力，新增：
  - 当前综合判断
  - 为什么选中它
  - 出货风险判断
  - 事件时间线
- 回测：输出两套口径
  - 固定持有结果
  - 持有窗口内最高机会结果

## 4. 当前实现状态（2026-04-04）
- 已落地独立库与 schema
- 已落地 `/api/selection/*`
- 已落地 `/selection-research`
- 已改为 **Top10 启动确认候选池 + 右侧复盘决策视图**
- 已在右侧详情补上：
  - 当前综合判断
  - 选中原因解释
  - 出货风险说明
  - 事件时间线
- 已完成回测口径升级：
  - 固定持有收益
  - `max_runup_within_holding_pct`
  - `max_drawdown_within_holding_pct`
- 已完成首轮真实数据落库：
  - `selection_feature_daily`：`603,675` 行
  - `selection_signal_daily`：`413,204` 行
  - 最新信号日：`2026-02-27`
- 已新增当前收口：
  - 候选默认只看沪深A（先排除科创板/北交所）
  - 右侧默认切到日线
  - 顶部判断区收紧为横向摘要，主图区域明显放大
  - 新增信号后窗口控制：`40天 / 90天 / 到现在 + 起止日期`
  - 图表主视图优先使用 `HistoryMultiframeFusionView` 展示 L1/L2 资金图
  - 右侧图表已改成**本地优先 + 云端只读 fallback**
  - 若无正式 L2，再回退旧 `HistoryView(local_history)` 做日级资金补充

## 5. 当前样例
- 候选池：`2026-02-27` 的 breakout Top10
- 回测样例：`run_id=1`
  - `5D` 固定胜率：`58.43%`
  - `10D` 固定胜率：`52.50%`
- 现在页面更适合做“先筛后看”的日常研究，不再只是看数表

## 6. 当前限制
- `stock_universe_meta` 仍为空，所以名称优先通过前端 fallback 展示；正式元数据仍需后续补齐
- 本地主库 `2026-03+` 全市场连续覆盖不完整，因此全市场研究仍以 `2026-02-27` 前为主
- 动态出货退出回测尚未做，一期先只输出固定持有 + 窗口最高机会
- 右侧分时/L2 复盘是否完整，取决于本地 `history_daily_l2/history_5m_l2` 是否已补到对应股票/日期；这和左侧选股信号是否能跑不是同一层
- 已确认 Windows 上存在 `2026-03-02 ~ 2026-03-13` 的 8,111 symbols 正式 L2，可作为本地下阶段同步优先源
- 云端 fallback 当前只接在**选股模块右侧**，不改原盯盘/复盘主链路

## 7. 文档入口
- 当前真实状态母卡：`docs/changes/MOD-20260404-01-selection-research-current-state.md`
- 数据底座：`docs/changes/REQ-20260404-01-selection-data-foundation.md`
- 特征与信号：`docs/changes/REQ-20260404-02-selection-features-and-signals.md`
- 回测引擎：`docs/changes/REQ-20260404-03-selection-backtest-engine.md`
- 页面与接口：`docs/changes/REQ-20260404-04-selection-api-and-research-page.md`
- 数据对齐与补齐：`docs/changes/REQ-20260404-05-selection-data-alignment-and-backfill.md`

## 8. 下一步
1. 优先补齐 `stock_universe_meta` 正式名称映射
2. 对齐本地 `history_daily_l2/history_5m_l2` 正式覆盖
3. 扩大回测窗口到 `2025-10 ~ 2026-02`
4. 增加 L2 确认 / 热度过滤 / 市值层分层统计
5. 二期再做动态出货退出回测
