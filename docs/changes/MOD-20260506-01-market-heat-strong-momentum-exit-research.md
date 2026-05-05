# MOD-20260506-01 小主题热点强者恒强与卖点研究收口

## 1. 基本信息
- 状态：DONE
- 负责人：Codex
- 关联 CAP：`CAP-SELECTION-RESEARCH`
- 关联请求：小主题热点数据用于选股/验证，强者恒强样本卖点与 100 万实盘约束回测

## 2. 背景
- 纯热点趋势图无法直接给出可交易规律。
- 旧热点买点策略容易追到尖峰，入场效果接近随机。
- 用户要求引入 L2 资金、后20日冲高样本和真实资金占用约束，验证策略是否能落地。

## 3. 本次处理
- 反向分析热点大涨股前置形态，确认“低位埋伏”不是主来源，强势样本多数来自价格先行或事件日同步爆发。
- 建立后20日冲高筛选规则，确认强者恒强规则最有效。
- 生成强者恒强 K线 + L2 资金案例页，修正重复样本与20日高点标记。
- 复盘卖点：真实高点中位数在买入后第5个交易日，10日内见高点比例超过80%。
- 完成 2025 年 100 万单账户实盘约束回测。
- 对比去掉分批止盈和固定持有20日两种卖点。

## 4. 关键结论
- 纯小主题热点不能直接买，L2 单因子不能稳定定买点。
- 强者恒强规则能把后20日最高涨幅超过20%的命中率从 `18.7%` 提升到 `55.9%`。
- 2025 年 100 万单账户回测：
  - 分批止盈版：`124.20万`，收益 `+24.2%`
  - 去掉半仓、原规则全仓卖出：`101.89万`，收益 `+1.9%`
  - 固定持有20日：`85.85万`，收益 `-14.2%`
- `+10% 半仓止盈` 是当前收益核心，不是可省略动作。

## 5. 产物
- `docs/selection/market_heat/README.md`
- `docs/selection/market_heat/backtests/hot_theme_fwd20_screen_rules.md`
- `docs/selection/market_heat/backtests/hot_theme_strong_momentum_l2_cases.html`
- `docs/selection/market_heat/backtests/hot_theme_strong_momentum_sell_points.md`
- `docs/selection/market_heat/backtests/strong_momentum_portfolio_2025.md`
- `docs/selection/market_heat/backtests/strong_momentum_exit_compare_2025.md`
- `backend/scripts/backtest_strong_momentum_portfolio_2025.py`
- `backend/scripts/backtest_strong_momentum_exit_compare_2025.py`

## 6. 使用边界
- 当前不能作为自动交易系统。
- 强者恒强只能作为追强候选池，必须结合实际盘口、涨停可买性、资金占用、卖点纪律。
- 后续应继续验证多仓位版本、不同市场阶段、不同热点生命周期。
