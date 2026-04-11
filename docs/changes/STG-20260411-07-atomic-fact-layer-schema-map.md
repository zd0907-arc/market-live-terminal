# STG-20260411-07 原子事实层表设计与字段对应总表

## 1. 基本信息
- 标题：原子事实层表设计与字段对应总表
- 状态：ACTIVE
- 负责人：Codex
- 关联 CAP：`CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`, `CAP-WIN-PIPELINE`
- 关联 Task ID：`CHG-20260411-07`

## 2. 这份文档解决什么问题
这份文档专门回答你要的这件事：

1. **原子事实层到底设计成哪些表**
2. **每张表有哪些字段**
3. **每个字段是什么意思**
4. **这些字段现在对应到哪张现有表**
5. **老数据能不能支持**
6. **新数据能不能支持**
7. **哪些字段必须补清洗，哪些字段可以后算**

目标就是做到：

## 你一眼就能看清：
- 现在有什么
- 以后要有什么
- 缺的到底是什么

---

## 3. 设计总原则

## 3.1 不改旧表口径，新增原子事实层
为了不干扰现有盯盘/复盘/选股模块，原子事实层建议**单独落库**：

- 建议路径：
  - `data/atomic_facts/market_atomic.db`

理由：
- 不污染现有主库
- 不改旧表字段
- 可以独立重跑
- 方便后续研究迭代

---

## 3.2 原子事实层只做“事实”，不做“结论”
原子事实层只存：
- 成交事实
- 挂单事实
- 统计事实
- 质量事实

不直接存：
- 买点
- 卖点
- score
- signal

这些属于后面的研究层和策略层。

---

## 3.3 老数据与新数据分开建事实层

### 老数据（`2025-01 ~ 2026-02`）
- 只有成交 raw
- 只能写 `trade_atomic`
- 不写真实 `order_atomic`

### 新数据（`2026-03+`）
- 有成交 + 挂单 raw
- 同时写：
  - `trade_atomic`
  - `order_atomic`

---

## 4. 建议的原子事实层对象

建议冻结为 **4 张核心事实表 + 1 张清单表 + 1 张统一视图**：

### 核心事实表
1. `atomic_trade_5m`
2. `atomic_trade_daily`
3. `atomic_order_5m`
4. `atomic_order_daily`

### 管理与验收表
5. `atomic_data_manifest`

### 研究读取统一视图
6. `v_atomic_daily_unified`

---

# 5. 表一：`atomic_trade_5m`

## 5.1 用途
这是老数据和新数据都能支撑的**成交级 5 分钟原子事实表**。

它的定位是：
- 保留 5m 粒度的成交结构
- 支撑后续大多数资金流向研究
- 未来尽量不再回 raw

## 5.2 主键
- `PRIMARY KEY(symbol, bucket_start)`

## 5.3 字段总表

| 字段名 | 含义 | 当前来源 | 老数据支持 | 新数据支持 | 处理方式 |
|---|---|---|---|---|---|
| `symbol` | 股票代码，如 `sh603629` | `history_5m_l2.symbol` | 是 | 是 | 直接复用 |
| `trade_date` | 交易日 `%Y-%m-%d` | `history_5m_l2.source_date` | 是 | 是 | 直接复用 |
| `bucket_start` | 5m 桶起点 `%Y-%m-%d %H:%M:%S` | `history_5m_l2.datetime` | 是 | 是 | 直接复用 |
| `open` | 5m 开盘价 | `history_5m_l2.open` | 是 | 是 | 直接复用 |
| `high` | 5m 最高价 | `history_5m_l2.high` | 是 | 是 | 直接复用 |
| `low` | 5m 最低价 | `history_5m_l2.low` | 是 | 是 | 直接复用 |
| `close` | 5m 收盘价 | `history_5m_l2.close` | 是 | 是 | 直接复用 |
| `total_amount` | 5m 总成交额 | `history_5m_l2.total_amount` | 是 | 是 | 直接复用 |
| `total_volume` | 5m 总成交量 | `history_5m_l2.total_volume` | 部分 | 是 | 老数据需补清洗/或从 raw 重算 |
| `trade_count` | 5m 成交笔数 | 无正式字段 | 否 | 否 | 新增清洗产出 |
| `l1_main_buy_amount` | L1 主力买入额 | `history_5m_l2.l1_main_buy` | 是 | 是 | 直接复用 |
| `l1_main_sell_amount` | L1 主力卖出额 | `history_5m_l2.l1_main_sell` | 是 | 是 | 直接复用 |
| `l1_main_net_amount` | L1 主力净额 | 可由 buy-sell 派生 | 是 | 是 | 后算/可落库 |
| `l1_super_buy_amount` | L1 超大单买入额 | `history_5m_l2.l1_super_buy` | 是 | 是 | 直接复用 |
| `l1_super_sell_amount` | L1 超大单卖出额 | `history_5m_l2.l1_super_sell` | 是 | 是 | 直接复用 |
| `l1_super_net_amount` | L1 超大单净额 | 可由 buy-sell 派生 | 是 | 是 | 后算/可落库 |
| `l2_main_buy_amount` | L2 主力买入额 | `history_5m_l2.l2_main_buy` | 是 | 是 | 直接复用 |
| `l2_main_sell_amount` | L2 主力卖出额 | `history_5m_l2.l2_main_sell` | 是 | 是 | 直接复用 |
| `l2_main_net_amount` | L2 主力净额 | 可由 buy-sell 派生 | 是 | 是 | 后算/可落库 |
| `l2_super_buy_amount` | L2 超大单买入额 | `history_5m_l2.l2_super_buy` | 是 | 是 | 直接复用 |
| `l2_super_sell_amount` | L2 超大单卖出额 | `history_5m_l2.l2_super_sell` | 是 | 是 | 直接复用 |
| `l2_super_net_amount` | L2 超大单净额 | 可由 buy-sell 派生 | 是 | 是 | 后算/可落库 |
| `l1_main_buy_count` | L1 主力买单笔数 | 无正式字段 | 否 | 否 | 新增清洗产出 |
| `l1_main_sell_count` | L1 主力卖单笔数 | 无正式字段 | 否 | 否 | 新增清洗产出 |
| `l1_super_buy_count` | L1 超大单买单笔数 | 无正式字段 | 否 | 否 | 新增清洗产出 |
| `l1_super_sell_count` | L1 超大单卖单笔数 | 无正式字段 | 否 | 否 | 新增清洗产出 |
| `l2_main_buy_count` | L2 主力买母单数 | 无正式字段 | 否 | 否 | 新增清洗产出 |
| `l2_main_sell_count` | L2 主力卖母单数 | 无正式字段 | 否 | 否 | 新增清洗产出 |
| `l2_super_buy_count` | L2 超大单买母单数 | 无正式字段 | 否 | 否 | 新增清洗产出 |
| `l2_super_sell_count` | L2 超大单卖母单数 | 无正式字段 | 否 | 否 | 新增清洗产出 |
| `max_trade_amount` | 5m 内最大单笔成交额 | 无正式字段 | 否 | 否 | 新增清洗产出 |
| `avg_trade_amount` | 5m 平均单笔成交额 | 无正式字段 | 否 | 否 | 新增清洗产出 |
| `max_parent_order_amount` | 5m 内最大母单金额 | 无正式字段 | 否 | 否 | 新增清洗产出 |
| `top5_parent_concentration_ratio` | 前5大母单金额占比 | 无正式字段 | 否 | 否 | 新增清洗产出 |
| `source_type` | `trade_only / trade_order` | 可由日期段判断 | 是 | 是 | 新增派生字段 |
| `quality_info` | 质量提示 | `history_5m_l2.quality_info` | 部分 | 是 | 直接复用 |

## 5.4 判断
### 现在已经基本有的
- OHLC
- total_amount
- L1/L2 买卖额

### 现在还缺的
- 笔数类
- 母单集中度类
- 最大单笔/母单额
- 老数据的 total_volume 覆盖一致性

---

# 6. 表二：`atomic_trade_daily`

## 6.1 用途
这是按日聚合后的成交级原子事实表，用于：
- 波段研究
- 日级回测
- 启动前 / 加速 / 高位阶段分析

## 6.2 主键
- `PRIMARY KEY(symbol, trade_date)`

## 6.3 字段总表

| 字段名 | 含义 | 当前来源 | 老数据支持 | 新数据支持 | 处理方式 |
|---|---|---|---|---|---|
| `symbol` | 股票代码 | `history_daily_l2.symbol` | 是 | 是 | 直接复用 |
| `trade_date` | 交易日 | `history_daily_l2.date` | 是 | 是 | 直接复用 |
| `open` | 开盘价 | `history_daily_l2.open` | 是 | 是 | 直接复用 |
| `high` | 最高价 | `history_daily_l2.high` | 是 | 是 | 直接复用 |
| `low` | 最低价 | `history_daily_l2.low` | 是 | 是 | 直接复用 |
| `close` | 收盘价 | `history_daily_l2.close` | 是 | 是 | 直接复用 |
| `total_amount` | 总成交额 | `history_daily_l2.total_amount` | 是 | 是 | 直接复用 |
| `total_volume` | 总成交量 | 需从 5m 汇总 | 部分 | 是 | 从 `atomic_trade_5m` 汇总 |
| `trade_count` | 当日成交笔数 | 无正式字段 | 否 | 否 | 从 5m 汇总/清洗新增 |
| `l1_main_buy_amount` | L1 主力买入额 | `history_daily_l2.l1_main_buy` | 是 | 是 | 直接复用 |
| `l1_main_sell_amount` | L1 主力卖出额 | `history_daily_l2.l1_main_sell` | 是 | 是 | 直接复用 |
| `l1_main_net_amount` | L1 主力净额 | `history_daily_l2.l1_main_net` | 是 | 是 | 直接复用 |
| `l1_super_buy_amount` | L1 超大单买入额 | `history_daily_l2.l1_super_buy` | 是 | 是 | 直接复用 |
| `l1_super_sell_amount` | L1 超大单卖出额 | `history_daily_l2.l1_super_sell` | 是 | 是 | 直接复用 |
| `l1_super_net_amount` | L1 超大单净额 | `history_daily_l2.l1_super_net` | 是 | 是 | 直接复用 |
| `l2_main_buy_amount` | L2 主力买入额 | `history_daily_l2.l2_main_buy` | 是 | 是 | 直接复用 |
| `l2_main_sell_amount` | L2 主力卖出额 | `history_daily_l2.l2_main_sell` | 是 | 是 | 直接复用 |
| `l2_main_net_amount` | L2 主力净额 | `history_daily_l2.l2_main_net` | 是 | 是 | 直接复用 |
| `l2_super_buy_amount` | L2 超大单买入额 | `history_daily_l2.l2_super_buy` | 是 | 是 | 直接复用 |
| `l2_super_sell_amount` | L2 超大单卖出额 | `history_daily_l2.l2_super_sell` | 是 | 是 | 直接复用 |
| `l2_super_net_amount` | L2 超大单净额 | `history_daily_l2.l2_super_net` | 是 | 是 | 直接复用 |
| `l1_activity_ratio` | L1 参与度 | `history_daily_l2.l1_activity_ratio` | 是 | 是 | 直接复用 |
| `l2_activity_ratio` | L2 参与度 | `history_daily_l2.l2_activity_ratio` | 是 | 是 | 直接复用 |
| `l1_buy_ratio` | L1 买入占比 | `history_daily_l2.l1_buy_ratio` | 是 | 是 | 直接复用 |
| `l1_sell_ratio` | L1 卖出占比 | `history_daily_l2.l1_sell_ratio` | 是 | 是 | 直接复用 |
| `l2_buy_ratio` | L2 买入占比 | `history_daily_l2.l2_buy_ratio` | 是 | 是 | 直接复用 |
| `l2_sell_ratio` | L2 卖出占比 | `history_daily_l2.l2_sell_ratio` | 是 | 是 | 直接复用 |
| `am_l2_main_net_amount` | 上午 L2 主力净额 | 无正式字段 | 否 | 否 | 从 `atomic_trade_5m` 汇总 |
| `pm_l2_main_net_amount` | 下午 L2 主力净额 | 无正式字段 | 否 | 否 | 从 `atomic_trade_5m` 汇总 |
| `open_30m_l2_main_net_amount` | 开盘30m L2 主力净额 | 无正式字段 | 否 | 否 | 从 `atomic_trade_5m` 汇总 |
| `last_30m_l2_main_net_amount` | 尾盘30m L2 主力净额 | 无正式字段 | 否 | 否 | 从 `atomic_trade_5m` 汇总 |
| `positive_l2_net_bar_count` | 5m 正 L2 净流入 bar 数 | 无正式字段 | 否 | 否 | 从 `atomic_trade_5m` 汇总 |
| `negative_l2_net_bar_count` | 5m 负 L2 净流入 bar 数 | 无正式字段 | 否 | 否 | 从 `atomic_trade_5m` 汇总 |
| `max_trade_amount` | 当日最大单笔成交额 | 无正式字段 | 否 | 否 | 从 `atomic_trade_5m`/清洗新增 |
| `max_parent_order_amount` | 当日最大母单额 | 无正式字段 | 否 | 否 | 从 `atomic_trade_5m`/清洗新增 |
| `top5_parent_concentration_ratio` | 前5母单集中度 | 无正式字段 | 否 | 否 | 从 `atomic_trade_5m` 汇总 |
| `source_type` | `trade_only / trade_order` | 可由日期段判断 | 是 | 是 | 新增派生字段 |
| `quality_info` | 质量提示 | `history_daily_l2.quality_info` | 部分 | 是 | 直接复用 |

## 6.4 判断
### 现在已经基本有的
- 日线价格
- 日线主力/超大单 L1/L2 绝对值与比例

### 现在还缺的
- 上午/下午/尾盘拆解
- 连续性 bar 计数
- 笔数与集中度

---

# 7. 表三：`atomic_order_5m`

## 7.1 用途
这是只在 `2026-03+` 有意义的 **挂单事件 5m 原子事实表**。

它是未来研究：
- 诱多
- 承接
- 高位稳住
- 出货风险

最关键的底层表。

## 7.2 主键
- `PRIMARY KEY(symbol, bucket_start)`

## 7.3 字段总表

| 字段名 | 含义 | 当前来源 | 老数据支持 | 新数据支持 | 处理方式 |
|---|---|---|---|---|---|
| `symbol` | 股票代码 | `history_5m_l2.symbol` | 否 | 是 | 直接复用 |
| `trade_date` | 交易日 | `history_5m_l2.source_date` | 否 | 是 | 直接复用 |
| `bucket_start` | 5m 桶起点 | `history_5m_l2.datetime` | 否 | 是 | 直接复用 |
| `add_buy_amount` | 买侧新增挂单额 | `history_5m_l2.l2_add_buy_amount` | 否 | 是 | 直接复用 |
| `add_sell_amount` | 卖侧新增挂单额 | `history_5m_l2.l2_add_sell_amount` | 否 | 是 | 直接复用 |
| `cancel_buy_amount` | 买侧撤单额 | `history_5m_l2.l2_cancel_buy_amount` | 否 | 是 | 直接复用 |
| `cancel_sell_amount` | 卖侧撤单额 | `history_5m_l2.l2_cancel_sell_amount` | 否 | 是 | 直接复用 |
| `cvd_delta_amount` | 成交净主动差额 | `history_5m_l2.l2_cvd_delta` | 否 | 是 | 直接复用 |
| `oib_delta_amount` | 挂单失衡变化 | `history_5m_l2.l2_oib_delta` | 否 | 是 | 直接复用 |
| `add_buy_count` | 买侧新增挂单笔数 | 无正式字段 | 否 | 否 | 新增清洗产出 |
| `add_sell_count` | 卖侧新增挂单笔数 | 无正式字段 | 否 | 否 | 新增清洗产出 |
| `cancel_buy_count` | 买侧撤单笔数 | 无正式字段 | 否 | 否 | 新增清洗产出 |
| `cancel_sell_count` | 卖侧撤单笔数 | 无正式字段 | 否 | 否 | 新增清洗产出 |
| `add_buy_volume` | 买侧新增挂单量 | 无正式字段 | 否 | 否 | 新增清洗产出 |
| `add_sell_volume` | 卖侧新增挂单量 | 无正式字段 | 否 | 否 | 新增清洗产出 |
| `cancel_buy_volume` | 买侧撤单量 | 无正式字段 | 否 | 否 | 新增清洗产出 |
| `cancel_sell_volume` | 卖侧撤单量 | 无正式字段 | 否 | 否 | 新增清洗产出 |
| `buy_add_cancel_net_amount` | 买侧 add-cancel 净额 | 可由字段派生 | 否 | 是 | 后算/可落库 |
| `sell_add_cancel_net_amount` | 卖侧 add-cancel 净额 | 可由字段派生 | 否 | 是 | 后算/可落库 |
| `order_event_count` | 5m 有效委托事件数 | 无正式字段 | 否 | 否 | 新增清洗产出 |
| `source_type` | 固定 `trade_order` | 日期段派生 | 否 | 是 | 新增派生字段 |
| `quality_info` | 质量提示 | `history_5m_l2.quality_info` | 否 | 是 | 直接复用 |

## 7.4 判断
### 现在已经有的
- add/cancel 金额
- cvd/oib

### 现在还缺的
- 挂撤单笔数
- 挂撤单量
- 事件覆盖率

---

# 8. 表四：`atomic_order_daily`

## 8.1 用途
这是挂单事件的日级原子事实表，用于：
- 高位稳住研究
- 出货风险研究
- 次日执行过滤研究

## 8.2 主键
- `PRIMARY KEY(symbol, trade_date)`

## 8.3 字段总表

| 字段名 | 含义 | 当前来源 | 老数据支持 | 新数据支持 | 处理方式 |
|---|---|---|---|---|---|
| `symbol` | 股票代码 | 从 `atomic_order_5m` 汇总 | 否 | 是 | 汇总生成 |
| `trade_date` | 交易日 | 从 `atomic_order_5m` 汇总 | 否 | 是 | 汇总生成 |
| `add_buy_amount` | 日级买侧新增挂单额 | 5m 汇总 | 否 | 是 | 汇总生成 |
| `add_sell_amount` | 日级卖侧新增挂单额 | 5m 汇总 | 否 | 是 | 汇总生成 |
| `cancel_buy_amount` | 日级买侧撤单额 | 5m 汇总 | 否 | 是 | 汇总生成 |
| `cancel_sell_amount` | 日级卖侧撤单额 | 5m 汇总 | 否 | 是 | 汇总生成 |
| `cvd_delta_amount` | 日级 CVD 变化 | 5m 汇总 | 否 | 是 | 汇总生成 |
| `oib_delta_amount` | 日级 OIB 变化 | 5m 汇总 | 否 | 是 | 汇总生成 |
| `add_buy_count` | 日级买侧新增挂单笔数 | 5m 汇总 | 否 | 否 | 汇总生成（前提是 5m 有） |
| `add_sell_count` | 日级卖侧新增挂单笔数 | 5m 汇总 | 否 | 否 | 汇总生成 |
| `cancel_buy_count` | 日级买侧撤单笔数 | 5m 汇总 | 否 | 否 | 汇总生成 |
| `cancel_sell_count` | 日级卖侧撤单笔数 | 5m 汇总 | 否 | 否 | 汇总生成 |
| `am_oib_delta_amount` | 上午 OIB 变化 | 无正式字段 | 否 | 否 | 从 `atomic_order_5m` 汇总 |
| `pm_oib_delta_amount` | 下午 OIB 变化 | 无正式字段 | 否 | 否 | 从 `atomic_order_5m` 汇总 |
| `open_60m_oib_delta_amount` | 开盘 60m OIB 变化 | 无正式字段 | 否 | 否 | 从 `atomic_order_5m` 汇总 |
| `last_30m_oib_delta_amount` | 尾盘 30m OIB 变化 | 无正式字段 | 否 | 否 | 从 `atomic_order_5m` 汇总 |
| `open_60m_cvd_delta_amount` | 开盘 60m CVD 变化 | 无正式字段 | 否 | 否 | 从 `atomic_order_5m` 汇总 |
| `last_30m_cvd_delta_amount` | 尾盘 30m CVD 变化 | 无正式字段 | 否 | 否 | 从 `atomic_order_5m` 汇总 |
| `positive_oib_bar_count` | 正 OIB 的 5m bar 数 | 无正式字段 | 否 | 否 | 从 `atomic_order_5m` 汇总 |
| `negative_oib_bar_count` | 负 OIB 的 5m bar 数 | 无正式字段 | 否 | 否 | 从 `atomic_order_5m` 汇总 |
| `positive_cvd_bar_count` | 正 CVD 的 5m bar 数 | 无正式字段 | 否 | 否 | 从 `atomic_order_5m` 汇总 |
| `negative_cvd_bar_count` | 负 CVD 的 5m bar 数 | 无正式字段 | 否 | 否 | 从 `atomic_order_5m` 汇总 |
| `buy_support_ratio` | 买侧支撑比，建议定义 `(add_buy-cancel_buy)/total_amount` | 无正式字段 | 否 | 否 | 汇总后派生 |
| `sell_pressure_ratio` | 卖侧压力比，建议定义 `(add_sell-cancel_sell)/total_amount` | 无正式字段 | 否 | 否 | 汇总后派生 |
| `quality_info` | 日级质量提示 | 从 5m 合并 | 否 | 是 | 汇总生成 |

## 8.4 判断
### 现在已经有的
- 日级金额总和可以直接从现有 5m 聚合出来

### 现在还缺的
- 笔数类
- 分时结构类
- 支撑/压力比

---

# 9. 表五：`atomic_data_manifest`

## 9.1 用途
这是数据治理和删除前验收用的清单表，不服务策略，但非常重要。

它用来回答：
- 哪个月跑完了没有
- 哪些字段已经有
- 哪些月份只有 trade，没有 order
- 哪些月份可以考虑删除 raw

## 9.2 主键
- `PRIMARY KEY(dataset_key, period_key)`

## 9.3 字段总表

| 字段名 | 含义 | 当前来源 | 老数据支持 | 新数据支持 | 处理方式 |
|---|---|---|---|---|---|
| `dataset_key` | 数据集名，如 `atomic_trade_5m` | 新表 | 是 | 是 | 新增 |
| `period_key` | 周期键，如 `2025-01` | 新表 | 是 | 是 | 新增 |
| `source_type` | `trade_only / trade_order` | 日期段判断 | 是 | 是 | 新增 |
| `trade_day_count` | 该月交易日数量 | 新表 | 是 | 是 | 新增 |
| `symbol_day_count` | 该月股票日覆盖数 | 新表 | 是 | 是 | 新增 |
| `row_count` | 该月记录数 | 新表 | 是 | 是 | 新增 |
| `has_order_atomic` | 是否有挂单原子层 | 新表 | 否 | 是 | 新增 |
| `quality_issue_count` | 质量异常日数 | 新表 | 部分 | 是 | 新增 |
| `parser_version` | 清洗器版本 | 新表 | 是 | 是 | 新增 |
| `generated_at` | 生成时间 | 新表 | 是 | 是 | 新增 |
| `validation_status` | `pending/passed/failed` | 新表 | 是 | 是 | 新增 |
| `notes` | 备注 | 新表 | 是 | 是 | 新增 |

---

# 10. 统一读取视图：`v_atomic_daily_unified`

## 10.1 用途
为了让后续研究不用每次手写 join，建议提供统一视图：

- 左边是 `atomic_trade_daily`
- 左 join `atomic_order_daily`

并显式给出：
- `has_trade_atomic`
- `has_order_atomic`
- `source_type`

这样研究层一眼能知道：
- 这天只有成交
- 还是成交 + 挂单

---

# 11. 一眼看明白：现状 vs 目标

## 11.1 现在已经有的核心能力
| 当前表 | 已覆盖能力 |
|---|---|
| `history_5m_l2` | 5m OHLC、总成交额、L1/L2 主力与超大单 buy/sell、部分 total_volume、新数据的 add/cancel/cvd/oib |
| `history_daily_l2` | 日线 OHLC、L1/L2 主力与超大单 buy/sell/net、参与度与买卖占比 |
| `local_history` | 日级净流入、主力买卖额、收盘价 |

## 11.2 现在还没有系统沉淀的
| 缺口类型 | 代表字段 |
|---|---|
| 笔数类 | `trade_count`, `*_buy_count`, `*_sell_count` |
| 母单集中度类 | `max_parent_order_amount`, `top5_parent_concentration_ratio` |
| 时间结构类 | `am_*`, `pm_*`, `open_30m_*`, `last_30m_*` |
| 挂单笔数/挂单量类 | `add_*_count`, `cancel_*_count`, `add_*_volume`, `cancel_*_volume` |
| 清单验收类 | `atomic_data_manifest` |

---

# 12. 最关键的判断

## 12.1 以后大多数新研究，不该再重跑 raw
如果以上 4 张事实表做出来，
未来大多数新研究都应该只需要：
- 重算 feature
- 重算 signal
- 重算 backtest

## 12.2 真正还会逼你回 raw 的情况
只有：
1. 清洗 bug；
2. 你突然要研究当前根本没抽出的更细字段；
3. 研究范围升级到更深盘口层。

---

# 13. 下一步该怎么干

## Step 1
冻结本文档，不再口头漂移字段目标。

## Step 2
下一张文档直接做：

## 《字段差异执行表》

只做三列：
1. 已有
2. 可由现表直接算
3. 必须补清洗

## Step 3
基于差异表决定：
- 老数据先榨干哪些字段
- 新数据正式链路先补哪些字段

---

# 14. 当前短结论
- 原子事实层建议分成：
  - `atomic_trade_5m`
  - `atomic_trade_daily`
  - `atomic_order_5m`
  - `atomic_order_daily`
  - `atomic_data_manifest`
- 老数据重点做成交原子层；
- 新数据重点补挂单原子层；
- 以后大多数新策略，不该再逼你重跑 raw。
