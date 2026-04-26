# 给后续开发 AI 的交接说明

## 1. 当前工作区

- Worktree：`/Users/dong/Desktop/AIGC/market-live-terminal-selection-strategy-rework`
- Branch：`codex/selection-strategy-rework`

当前已新增实验代码，但还没有接入现有业务主链路。
当前实验能力：

- `candidates`：某历史日候选筛选。
- `symbol-replay`：单票逐日状态回放。
- `day-replay`：某历史日候选 + 该日信号对应的模拟交易结果。
- `range-backtest`：区间批量回测汇总。
- `research-card`：单票历史时点研究卡片。

最新状态补充：

- Layer 2 已有 `research card v0.1`，集成到 `day-replay` 输出中。
- `research card v0.1` 目前可读取：
  - `stock_universe_meta`
  - `stock_events`
  - `sentiment_events`
  - `sentiment_daily_scores`
- 已验证历史截断：研究卡片只读取 `signal_date` 当时可见数据，不使用未来事件。
- 已新增单测覆盖研究卡片基础行为。
- Layer 3 已补第一版真实交易约束：
  - next-open 入场 / next-open 出场
  - 近似涨停买不进
  - 近似跌停卖不出
  - 买卖滑点与往返手续费
  - 最大同时持仓数
  - 单日最大新增仓位数
  - 简化 equity curve 输出
- Layer 1 / Layer 3 之间又补了一层 `intent_profile`：
  - `accumulation_score`
  - `attack_score`
  - `distribution_score`
  - `washout_score`
  - `repair_score`
  - 以及 `launch_attack / washout / panic_distribution / pull_up_distribution` 等意图标签

## 2. 必读文档顺序

1. `docs/strategy-rework/REQ-20260425-selection-strategy-rework.md`
2. `docs/strategy-rework/project-roadmap.md`
3. `docs/strategy-rework/data-map-current.md`
4. `docs/strategy-rework/layer-1-quant-candidate-discovery.md`
5. `docs/strategy-rework/layer-2-company-event-research.md`
6. `docs/strategy-rework/layer-3-trading-state-and-backtest.md`
7. `docs/strategy-rework/cases/litong-electronics-603629.md`
8. `docs/strategy-rework/notes/20260425-conversation-memory.md`
9. `docs/strategy-rework/implementation-map-and-tuning.md`
10. `docs/strategy-rework/frontend-history-range-root-cause.md`
11. `docs/strategy-rework/cases/litong-v2-tuning-pass-01.md`

## 3. 当前业务代码入口

- 策略计算旧入口：`backend/app/services/selection_research.py`
- 新实验服务：`backend/app/services/selection_strategy_v2.py`
- 选股 DB：`backend/app/db/selection_db.py`
- API：`backend/app/routers/selection.py`
- 新实验 CLI：`backend/scripts/run_selection_strategy_v2.py`
- 前端选股页：`src/components/selection/SelectionResearchPage.tsx`
- 右侧复盘决策：`src/components/selection/SelectionDecisionPanel.tsx`
- 新测试：`backend/tests/test_selection_strategy_v2.py`

## 4. 正式数据路径

本地正式研究数据不在 repo 内 `data/`，而在：

```text
/Users/dong/Desktop/AIGC/market-data/market_data.db
/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_full_reverse.db
/Users/dong/Desktop/AIGC/market-data/selection/selection_research.db
```

启动脚本：`ops/start_local_research_station.sh`

注意：repo 内 `data/` 可能是旧数据/残缺数据，开发策略时默认不要误读。

## 5. 开发原则

1. 先沿着 `selection_strategy_v2.py` 扩展离线实验，不要直接改现有选股主链路。
2. 所有阈值参数化，不要写死。
3. 每个信号必须能解释来源字段和公式。
4. 历史回放不能使用未来数据。
5. LLM 只做公司/事件解释，不直接替代量化买卖。
6. 先跑利通电子单票，再跑全市场批量。
7. 先输出 JSON/CSV，稳定后再写库和接页面。

## 6. 建议第一批代码任务

### Task A：补强实验数据读取器

读取：

- `atomic_trade_daily`
- `atomic_order_daily`
- `selection_feature_daily`
- `selection_signal_daily`

输出单票/单日窗口 DataFrame。

### Task B：补强 Layer 1 指标计算器

实现：

- `l2_main_net_ratio`
- `l2_super_net_ratio`
- `active_buy_strength`
- `order_imbalance_ratio`
- `cvd_ratio`
- `support_pressure_spread`
- `amount_anomaly_20d`
- `breakout_vs_prev20_high_pct`

### Task C：补强单票状态回放

输入：`symbol`, `start_date`, `end_date`, `params`

输出：逐日状态序列。

### Task D：补强历史日候选回放

输入：`trade_date`, `params`

输出：候选 TopN + 模拟交易结果。

### Task E：补强月度回测

输入：`start_date`, `end_date`, `params`

输出：绩效统计。

当前状态：Task D / E 已有第一版实现，但仓位管理、去重策略、真实成交约束仍较粗。

新增状态：Layer 2 的 Task 雏形已开始落地，但仍缺公司主营/利润来源/估值弹性等更厚的研究信息。

更新：Layer 3 已经不再只是“信号日收盘买卖”的粗回放，已经进入第一版可用回测执行层，但仍缺：

- 停牌约束
- 不同板块真实涨跌停规则
- 更真实的组合资金曲线
- 分仓收益归因
- 部分止盈/减仓

按最新用户反馈，下一优先级不是继续做资金管理细节，而是继续调优“进出场点识别”本身，尤其是：

- 主力什么时候真在吸筹
- 主力什么时候真在出货
- 爆拉/暴跌到底是攻击、洗盘、恐慌，还是派发

## 7. 第一验收样本

股票：`sh603629` 利通电子

时间：`2026-01-05 ~ 2026-04-24`

目标：

- 能解释早期资金介入。
- 能识别 2026-02-27 / 2026-03-02 附近启动或强修复。
- 能识别中间洗盘/分歧不等于立即出货。
- 能在 2026-04 下旬识别高位风险抬升。

## 8. 不要踩的坑

- 不要用未来新闻解释过去信号。
- 不要用当前最新公司逻辑反推历史买点，除非当时已有公开信息。
- 不要让 `breakout` 继续硬依赖旧 `stealth_score`。
- 不要把出货简单写成吸筹反向。
- 不要只做固定持有回测，必须支持动态退出。
- 不要第一步就做复杂 UI。
