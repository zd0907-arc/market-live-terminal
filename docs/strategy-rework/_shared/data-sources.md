# 共用数据源说明

## 原子事实库

路径：`/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_full_reverse.db`

### `atomic_trade_daily`

用途：日级 L1/L2 成交资金汇总。

覆盖：`2025-01-02` ~ `2026-04-24`，约 3222 只股票。

核心字段：

| 字段 | 业务含义 |
|---|---|
| `open/high/low/close` | 日线价格 |
| `total_amount` | 当日成交额 |
| `trade_count` | 成交笔数 |
| `l2_main_net_amount` | L2 主力净流入 |
| `l2_super_net_amount` | L2 超大单净流入 |
| `l2_buy_ratio/l2_sell_ratio` | L2 主动买/卖强度 |
| `positive_l2_net_bar_count/negative_l2_net_bar_count` | L2 正/负净流入切片数量 |

### `atomic_order_daily`

用途：日级 L2 挂单/撤单/订单簿行为。

覆盖：`2026-03-02` ~ `2026-04-24`。

核心字段：

| 字段 | 业务含义 |
|---|---|
| `add_buy_amount` | 新增买挂单金额 |
| `add_sell_amount` | 新增卖挂单金额 |
| `cancel_buy_amount` | 撤买单金额 |
| `cancel_sell_amount` | 撤卖单金额 |
| `cvd_delta_amount` | 主动成交净额变化 |
| `oib_delta_amount` | 订单簿不平衡变化 |
| `buy_support_ratio` | 买盘支撑比例 |
| `sell_pressure_ratio` | 卖盘压力比例 |
| `order_event_count` | 挂单事件数量 |

## 当前限制

- 2026-03-02 以前缺完整挂单数据。
- 新闻/公司事件层暂不纳入 v1，后续单独补。
- 市值元数据当前不完整，暂不严格过滤 50亿~500亿。
