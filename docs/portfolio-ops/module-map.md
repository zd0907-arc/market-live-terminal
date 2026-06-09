# 操盘跟踪模块使用清单

## 数据优先级

1. 当前原子库：`/Users/dong/Desktop/AIGC/market-data/research/current/atomic_facts/market_atomic_mainboard_compact_current.db`
2. 选股研究库：`/Users/dong/Desktop/AIGC/market-data/research/current/selection/selection_research.db`
3. 热点数据：`/Users/dong/Desktop/AIGC/market-data/market_heat/` 下最新 JSON/cache
4. 旧 `market_data.db` 只在明确需要兼容页面时使用，不作为当前判断主数据源。

## 原始交易数据

- `atomic_trade_daily`：日线、成交额、L2 主力/超大单/L1、开盘 30 分钟和尾盘 30 分钟资金。
- `atomic_trade_5m`：分钟级走势、日内拉升/回落、资金分布。
- `atomic_order_daily`：OIB、CVD、主动买卖、买盘支撑、卖压。
- `atomic_book_state_daily`：盘口委买委卖、挂单不平衡、尾盘盘口状态。

## 选股与策略数据

- `selection_candidate_daily`：统一候选池，先看这里。
- `selection_candidate_sources`：候选来自哪个模型或策略。
- `selection_signal_daily`：吸筹、突破、出货、退出、资金质量等因子。
- `selection_feature_daily`：候选解释和基础特征。
- `selection_exit_watchlist_daily`：退出观察或风险提示。
- `selection_strategy_registry`：策略登记、版本、状态。

## 热点与主题

- 先用最新 `market_heat` JSON/cache 判断当日主线和细分板块强度。
- 热点只做三件事：
  - 解释持仓为什么涨跌；
  - 判断候选是否有主线共振；
  - 提醒拥挤和退潮风险。
- 不把热点本身当成自动买入理由。

## 外部信息

必须按需查：

- 指数、港股、美股、中概、商品、汇率；
- 公司公告、业绩、监管问询；
- 行业新闻和政策；
- 突发事件。

外部信息只作为补充证据，不能替代系统数据。

## 建议输出结构

1. 先给组合结论。
2. 分别说每只持仓：继续拿的理由、风险、触发动作。
3. 说新候选是否强于当前持仓。
4. 给明日可执行计划。
5. 写入 `trade-log.md` 或 `method-log.md` 中需要沉淀的内容。
