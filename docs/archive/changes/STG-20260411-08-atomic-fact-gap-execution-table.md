# STG-20260411-08 原子事实层字段差异执行表

> **历史过程卡。**
> 当前项目主线 / 当前目录 / 当前版本 / 当前分支纪律，请优先看：`docs/changes/MOD-20260421-01-project-current-state-and-doc-governance-normalization.md`
> 当前数据治理主题真实状态，请优先看：`docs/changes/MOD-20260411-14-market-data-governance-current-state.md`


## 1. 基本信息
- 标题：原子事实层字段差异执行表
- 状态：ACTIVE
- 负责人：Codex
- 关联 CAP：`CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`, `CAP-WIN-PIPELINE`
- 关联 Task ID：`CHG-20260411-08`

## 2. 这份文档解决什么问题
上一张文档已经回答了“目标表应该长什么样”。

这张文档继续往下走一步，只回答执行层最关键的 4 件事：

1. **哪些字段现在已经有了，可以直接映射**
2. **哪些字段不用回 raw，现有表就能直接算出来**
3. **哪些字段必须补清洗，当前正式表根本没有**
4. **先做哪一批字段，才能尽量一次性把数据底座做厚**

目标是把“设计”变成“施工清单”。

---

## 3. 读法说明

### 3.1 状态定义
- `已有`：现有正式表已经有，直接映射即可
- `可算`：现有正式表没有成列，但可以直接聚合/派生，不必回 raw
- `必补`：现有正式表和现有派生都没有，必须在清洗阶段新增产出

### 3.2 优先级定义
- `P0`：现在就该做，否则未来还会反复回 raw
- `P1`：强烈建议补，能明显提升研究深度
- `P2`：后续增强，不补也不影响一期主线

### 3.3 时间边界
- `2025-01 ~ 2026-02`：只有成交 raw，**不支持真实挂单事件层**
- `2026-03+`：有成交 + 挂单 raw，支持完整事件层

### 3.4 这轮新增的评审结论
- **复权因子**：采纳，但不直接塞进 atomic price 主表；建议独立因子表
- **集合竞价隔离**：采纳，而且属于高优先级；但具体落库形态仍待下轮讨论
- **涨跌停状态**：采纳，列为 P1 增强
- **截面索引**：采纳，直接补到 DDL
- **盘口存量状态**：方向正确，但暂不进入 P0 主线
- **时间桶开闭约定**：采纳，并已冻结为前闭后开

---

## 4. 一眼看明白：总执行结论

| 目标表 | 已有 | 可算 | 必补 | 当前结论 |
|---|---:|---:|---:|---|
| `atomic_trade_5m` | 多 | 中 | 多 | 先做，老/新数据都适用，是全局底座 |
| `atomic_trade_daily` | 多 | 多 | 少 | 可快速落地，优先服务日级研究与回测 |
| `atomic_order_5m` | 少 | 少 | 中 | 只对 `2026-03+` 生效，是新数据增强核心 |
| `atomic_order_daily` | 无日表现成品 | 多 | 少 | 依赖 `atomic_order_5m` 或直接从现有 `history_5m_l2` 汇总 |
| `atomic_data_manifest` | 无 | 少 | 多 | 必须新建，用于验收、删 raw 前判断 |

### 当前最值得先做的 P0 顺序
1. `atomic_trade_5m`
2. `atomic_trade_daily`
3. `atomic_order_5m`
4. `atomic_order_daily`
5. `atomic_data_manifest`

---

# 5. `atomic_trade_5m` 执行表

## 5.1 已有：可直接映射

| 字段名 | 字段说明 | 当前来源 | 支持范围 | 优先级 | 备注 |
|---|---|---|---|---|---|
| `symbol` | 股票代码 | `history_5m_l2.symbol` | 老/新 | P0 | 直接复用 |
| `trade_date` | 交易日 | `history_5m_l2.source_date` | 老/新 | P0 | 直接复用 |
| `bucket_start` | 5 分钟桶起点 | `history_5m_l2.datetime` | 老/新 | P0 | 直接复用 |
| `open` | 5m 开盘价 | `history_5m_l2.open` | 老/新 | P0 | 直接复用 |
| `high` | 5m 最高价 | `history_5m_l2.high` | 老/新 | P0 | 直接复用 |
| `low` | 5m 最低价 | `history_5m_l2.low` | 老/新 | P0 | 直接复用 |
| `close` | 5m 收盘价 | `history_5m_l2.close` | 老/新 | P0 | 直接复用 |
| `total_amount` | 5m 总成交额 | `history_5m_l2.total_amount` | 老/新 | P0 | 直接复用 |
| `l1_main_buy_amount` | L1 主力买入额 | `history_5m_l2.l1_main_buy` | 老/新 | P0 | 直接复用 |
| `l1_main_sell_amount` | L1 主力卖出额 | `history_5m_l2.l1_main_sell` | 老/新 | P0 | 直接复用 |
| `l1_super_buy_amount` | L1 超大单买入额 | `history_5m_l2.l1_super_buy` | 老/新 | P0 | 直接复用 |
| `l1_super_sell_amount` | L1 超大单卖出额 | `history_5m_l2.l1_super_sell` | 老/新 | P0 | 直接复用 |
| `l2_main_buy_amount` | L2 主力买入额 | `history_5m_l2.l2_main_buy` | 老/新 | P0 | 直接复用 |
| `l2_main_sell_amount` | L2 主力卖出额 | `history_5m_l2.l2_main_sell` | 老/新 | P0 | 直接复用 |
| `l2_super_buy_amount` | L2 超大单买入额 | `history_5m_l2.l2_super_buy` | 老/新 | P0 | 直接复用 |
| `l2_super_sell_amount` | L2 超大单卖出额 | `history_5m_l2.l2_super_sell` | 老/新 | P0 | 直接复用 |
| `quality_info` | 质量提示 | `history_5m_l2.quality_info` | 老/新 | P0 | 直接复用 |

## 5.2 可算：不必回 raw

| 字段名 | 字段说明 | 当前来源/算法 | 支持范围 | 优先级 | 备注 |
|---|---|---|---|---|---|
| `l1_main_net_amount` | L1 主力净额 | `l1_main_buy_amount - l1_main_sell_amount` | 老/新 | P0 | 建议落库，避免研究层重复算 |
| `l1_super_net_amount` | L1 超大单净额 | `buy - sell` | 老/新 | P0 | 同上 |
| `l2_main_net_amount` | L2 主力净额 | `buy - sell` | 老/新 | P0 | 同上 |
| `l2_super_net_amount` | L2 超大单净额 | `buy - sell` | 老/新 | P0 | 同上 |
| `source_type` | 数据类型 | 日期段派生 `trade_only / trade_order` | 老/新 | P0 | 很关键，研究层要知道能不能信挂单字段 |
| `total_volume` | 5m 总成交量 | `history_5m_l2.total_volume` 直读；为空时标记缺口 | 老部分/新 | P0 | 新数据大多可用；老数据覆盖需单独补齐 |
| `session_phase` | 交易阶段标记 | 需由时间段/竞价识别规则派生 | 待定 | P0-doc | 原则已定，具体落库待讨论 |

## 5.3 必补：必须新增清洗产出

| 字段名 | 字段说明 | 为什么现状不够 | 支持范围 | 优先级 | 备注 |
|---|---|---|---|---|---|
| `trade_count` | 5m 成交笔数 | 正式表没有 | 老/新 | P0 | 很多“异动但不持续”研究都要看笔数密度 |
| `l1_main_buy_count` | L1 主力买单笔数 | 正式表没有 | 老/新 | P1 | 用于区分“大额少笔”还是“持续小单堆积” |
| `l1_main_sell_count` | L1 主力卖单笔数 | 正式表没有 | 老/新 | P1 | 同上 |
| `l1_super_buy_count` | L1 超大单买单笔数 | 正式表没有 | 老/新 | P1 | |
| `l1_super_sell_count` | L1 超大单卖单笔数 | 正式表没有 | 老/新 | P1 | |
| `l2_main_buy_count` | L2 主力买母单数 | 正式表没有 | 老/新 | P1 | |
| `l2_main_sell_count` | L2 主力卖母单数 | 正式表没有 | 老/新 | P1 | |
| `l2_super_buy_count` | L2 超大单买母单数 | 正式表没有 | 老/新 | P1 | |
| `l2_super_sell_count` | L2 超大单卖母单数 | 正式表没有 | 老/新 | P1 | |
| `max_trade_amount` | 5m 内最大单笔成交额 | 正式表没有 | 老/新 | P1 | 识别“单笔硬打”很有用 |
| `avg_trade_amount` | 5m 平均单笔成交额 | 正式表没有 | 老/新 | P1 | |
| `max_parent_order_amount` | 5m 最大母单金额 | 正式表没有 | 老/新 | P1 | 支撑主力埋伏/强承接研究 |
| `top5_parent_concentration_ratio` | 前 5 大母单集中度 | 正式表没有 | 老/新 | P1 | 识别是否极少数大资金主导 |
| `auction isolated bar` | 集合竞价独立 bar / 独立 phase | 当前未冻结 | 待定 | P0-doc | 必须先做 raw 审计与专题讨论 |

## 5.4 结论
- `atomic_trade_5m` 是**最该先做的 P0 底座**。
- 老数据虽没有挂单，但只要把成交级 `5m 原子层` 做厚，未来大量研究都不用再回 raw。

---

# 6. `atomic_trade_daily` 执行表

## 6.1 已有：可直接映射

| 字段名 | 字段说明 | 当前来源 | 支持范围 | 优先级 | 备注 |
|---|---|---|---|---|---|
| `symbol` | 股票代码 | `history_daily_l2.symbol` | 老/新 | P0 | 直接复用 |
| `trade_date` | 交易日 | `history_daily_l2.date` | 老/新 | P0 | 直接复用 |
| `open` | 开盘价 | `history_daily_l2.open` | 老/新 | P0 | 直接复用 |
| `high` | 最高价 | `history_daily_l2.high` | 老/新 | P0 | 直接复用 |
| `low` | 最低价 | `history_daily_l2.low` | 老/新 | P0 | 直接复用 |
| `close` | 收盘价 | `history_daily_l2.close` | 老/新 | P0 | 直接复用 |
| `total_amount` | 日成交额 | `history_daily_l2.total_amount` | 老/新 | P0 | 直接复用 |
| `l1_main_buy_amount` | L1 主力买入额 | `history_daily_l2.l1_main_buy` | 老/新 | P0 | 直接复用 |
| `l1_main_sell_amount` | L1 主力卖出额 | `history_daily_l2.l1_main_sell` | 老/新 | P0 | 直接复用 |
| `l1_main_net_amount` | L1 主力净额 | `history_daily_l2.l1_main_net` | 老/新 | P0 | 直接复用 |
| `l1_super_buy_amount` | L1 超大单买入额 | `history_daily_l2.l1_super_buy` | 老/新 | P0 | 直接复用 |
| `l1_super_sell_amount` | L1 超大单卖出额 | `history_daily_l2.l1_super_sell` | 老/新 | P0 | 直接复用 |
| `l1_super_net_amount` | L1 超大单净额 | `history_daily_l2.l1_super_net` | 老/新 | P0 | 直接复用 |
| `l2_main_buy_amount` | L2 主力买入额 | `history_daily_l2.l2_main_buy` | 老/新 | P0 | 直接复用 |
| `l2_main_sell_amount` | L2 主力卖出额 | `history_daily_l2.l2_main_sell` | 老/新 | P0 | 直接复用 |
| `l2_main_net_amount` | L2 主力净额 | `history_daily_l2.l2_main_net` | 老/新 | P0 | 直接复用 |
| `l2_super_buy_amount` | L2 超大单买入额 | `history_daily_l2.l2_super_buy` | 老/新 | P0 | 直接复用 |
| `l2_super_sell_amount` | L2 超大单卖出额 | `history_daily_l2.l2_super_sell` | 老/新 | P0 | 直接复用 |
| `l2_super_net_amount` | L2 超大单净额 | `history_daily_l2.l2_super_net` | 老/新 | P0 | 直接复用 |
| `l1_activity_ratio` | L1 参与度 | `history_daily_l2.l1_activity_ratio` | 老/新 | P0 | 直接复用 |
| `l2_activity_ratio` | L2 参与度 | `history_daily_l2.l2_activity_ratio` | 老/新 | P0 | 直接复用 |
| `l1_buy_ratio` | L1 买入占比 | `history_daily_l2.l1_buy_ratio` | 老/新 | P0 | 直接复用 |
| `l1_sell_ratio` | L1 卖出占比 | `history_daily_l2.l1_sell_ratio` | 老/新 | P0 | 直接复用 |
| `l2_buy_ratio` | L2 买入占比 | `history_daily_l2.l2_buy_ratio` | 老/新 | P0 | 直接复用 |
| `l2_sell_ratio` | L2 卖出占比 | `history_daily_l2.l2_sell_ratio` | 老/新 | P0 | 直接复用 |
| `quality_info` | 质量提示 | `history_daily_l2.quality_info` | 老/新 | P0 | 直接复用 |

## 6.2 可算：不必回 raw

| 字段名 | 字段说明 | 当前来源/算法 | 支持范围 | 优先级 | 备注 |
|---|---|---|---|---|---|
| `total_volume` | 日成交量 | 汇总 `history_5m_l2.total_volume` | 老部分/新 | P0 | 老数据缺口需补 5m 层 |
| `trade_count` | 日成交笔数 | 汇总 `atomic_trade_5m.trade_count` | 老/新 | P0 | 依赖上游 5m 先补 |
| `am_l2_main_net_amount` | 上午 L2 主力净额 | 汇总上午 5m | 老/新 | P0 | 识别“上午先埋伏” |
| `pm_l2_main_net_amount` | 下午 L2 主力净额 | 汇总下午 5m | 老/新 | P0 | 识别“尾盘抢筹/出逃” |
| `open_30m_l2_main_net_amount` | 开盘 30m 主力净额 | 汇总开盘前 6 根 5m | 老/新 | P1 | |
| `last_30m_l2_main_net_amount` | 尾盘 30m 主力净额 | 汇总尾盘 6 根 5m | 老/新 | P1 | |
| `positive_l2_net_bar_count` | 正净流入 bar 数 | 统计 `l2_main_net_amount > 0` 的 5m 数量 | 老/新 | P1 | |
| `negative_l2_net_bar_count` | 负净流入 bar 数 | 同上 | 老/新 | P1 | |
| `source_type` | 数据类型 | 日期段派生 | 老/新 | P0 | 必须显式带给研究层 |
| `adj_factor` | 复权因子 | 建议来自独立 `price_adjustment_factors` | 老/新 | P0-doc | 不建议塞回 atomic daily 主表 |
| `limit_up/down states` | 涨跌停状态组 | 需结合板块/规则计算 | 老/新 | P1 | A股强相关增强项 |

## 6.3 必补：必须新增清洗产出

| 字段名 | 字段说明 | 为什么现状不够 | 支持范围 | 优先级 | 备注 |
|---|---|---|---|---|---|
| `max_trade_amount` | 日内最大单笔成交额 | 现表没有 | 老/新 | P1 | 依赖 5m/成交原子层 |
| `max_parent_order_amount` | 日内最大母单金额 | 现表没有 | 老/新 | P1 | 依赖成交清洗 |
| `top5_parent_concentration_ratio` | 前 5 母单集中度 | 现表没有 | 老/新 | P1 | 依赖成交清洗 |

## 6.4 结论
- `atomic_trade_daily` 其实离落地已经很近。
- 只要 `atomic_trade_5m` 补齐，日级研究、选股、回测的大部分需求都能稳定支撑。

---

# 7. `atomic_order_5m` 执行表

## 7.1 已有：可直接映射

| 字段名 | 字段说明 | 当前来源 | 支持范围 | 优先级 | 备注 |
|---|---|---|---|---|---|
| `symbol` | 股票代码 | `history_5m_l2.symbol` | 新 | P0 | 老数据不支持 |
| `trade_date` | 交易日 | `history_5m_l2.source_date` | 新 | P0 | |
| `bucket_start` | 5 分钟桶起点 | `history_5m_l2.datetime` | 新 | P0 | |
| `add_buy_amount` | 买侧新增挂单额 | `history_5m_l2.l2_add_buy_amount` | 新 | P0 | |
| `add_sell_amount` | 卖侧新增挂单额 | `history_5m_l2.l2_add_sell_amount` | 新 | P0 | |
| `cancel_buy_amount` | 买侧撤单额 | `history_5m_l2.l2_cancel_buy_amount` | 新 | P0 | |
| `cancel_sell_amount` | 卖侧撤单额 | `history_5m_l2.l2_cancel_sell_amount` | 新 | P0 | |
| `cvd_delta_amount` | 成交主动差额 | `history_5m_l2.l2_cvd_delta` | 新 | P0 | |
| `oib_delta_amount` | 挂单失衡变化 | `history_5m_l2.l2_oib_delta` | 新 | P0 | |
| `quality_info` | 质量提示 | `history_5m_l2.quality_info` | 新 | P0 | |
| `end_bid_resting_volume` | 5m 结束时买盘留存量 | 现阶段无稳定来源 | 新 | P2 | 盘口存量重建，暂不进 P0 |
| `end_ask_resting_volume` | 5m 结束时卖盘留存量 | 现阶段无稳定来源 | 新 | P2 | 同上 |

## 7.2 可算：不必回 raw

| 字段名 | 字段说明 | 当前来源/算法 | 支持范围 | 优先级 | 备注 |
|---|---|---|---|---|---|
| `buy_add_cancel_net_amount` | 买侧挂撤净额 | `add_buy_amount - cancel_buy_amount` | 新 | P0 | 很关键 |
| `sell_add_cancel_net_amount` | 卖侧挂撤净额 | `add_sell_amount - cancel_sell_amount` | 新 | P0 | 很关键 |
| `source_type` | 数据类型 | 固定 `trade_order` | 新 | P0 | |

## 7.3 必补：必须新增清洗产出

| 字段名 | 字段说明 | 为什么现状不够 | 支持范围 | 优先级 | 备注 |
|---|---|---|---|---|---|
| `add_buy_count` | 买侧新增挂单笔数 | 正式表没有 | 新 | P0 | |
| `add_sell_count` | 卖侧新增挂单笔数 | 正式表没有 | 新 | P0 | |
| `cancel_buy_count` | 买侧撤单笔数 | 正式表没有 | 新 | P0 | |
| `cancel_sell_count` | 卖侧撤单笔数 | 正式表没有 | 新 | P0 | |
| `add_buy_volume` | 买侧新增挂单量 | 正式表没有 | 新 | P0 | |
| `add_sell_volume` | 卖侧新增挂单量 | 正式表没有 | 新 | P0 | |
| `cancel_buy_volume` | 买侧撤单量 | 正式表没有 | 新 | P0 | |
| `cancel_sell_volume` | 卖侧撤单量 | 正式表没有 | 新 | P0 | |
| `order_event_count` | 5m 有效委托事件数 | 正式表没有 | 新 | P1 | 用于判断样本可靠性 |

## 7.4 结论
- `atomic_order_5m` 是未来识别“承接、诱多、出货、稳住”的关键表。
- 但它只属于 `2026-03+`，不能误用到老数据区间。

---

# 8. `atomic_order_daily` 执行表

## 8.1 已有：可直接映射
- 当前**没有现成日表**可以直接映射。
- 正确做法是：从现有 `history_5m_l2` 的事件字段直接汇总，或先落 `atomic_order_5m` 再汇总。

## 8.2 可算：不必回 raw

| 字段名 | 字段说明 | 当前来源/算法 | 支持范围 | 优先级 | 备注 |
|---|---|---|---|---|---|
| `symbol` | 股票代码 | 按 5m 汇总取维度 | 新 | P0 | |
| `trade_date` | 交易日 | 按 5m 汇总取维度 | 新 | P0 | |
| `add_buy_amount` | 日级买侧新增挂单额 | 汇总 `history_5m_l2.l2_add_buy_amount` | 新 | P0 | |
| `add_sell_amount` | 日级卖侧新增挂单额 | 汇总 `history_5m_l2.l2_add_sell_amount` | 新 | P0 | |
| `cancel_buy_amount` | 日级买侧撤单额 | 汇总 `history_5m_l2.l2_cancel_buy_amount` | 新 | P0 | |
| `cancel_sell_amount` | 日级卖侧撤单额 | 汇总 `history_5m_l2.l2_cancel_sell_amount` | 新 | P0 | |
| `cvd_delta_amount` | 日级 CVD 变化 | 汇总 `history_5m_l2.l2_cvd_delta` | 新 | P0 | |
| `oib_delta_amount` | 日级 OIB 变化 | 汇总 `history_5m_l2.l2_oib_delta` | 新 | P0 | |
| `am_oib_delta_amount` | 上午 OIB 变化 | 汇总上午 5m | 新 | P1 | |
| `pm_oib_delta_amount` | 下午 OIB 变化 | 汇总下午 5m | 新 | P1 | |
| `open_60m_oib_delta_amount` | 开盘 60m OIB 变化 | 汇总开盘前 12 根 5m | 新 | P1 | |
| `last_30m_oib_delta_amount` | 尾盘 30m OIB 变化 | 汇总尾盘 6 根 5m | 新 | P1 | |
| `open_60m_cvd_delta_amount` | 开盘 60m CVD 变化 | 汇总开盘前 12 根 5m | 新 | P1 | |
| `last_30m_cvd_delta_amount` | 尾盘 30m CVD 变化 | 汇总尾盘 6 根 5m | 新 | P1 | |
| `positive_oib_bar_count` | 正 OIB bar 数 | 统计 `oib_delta_amount > 0` | 新 | P1 | |
| `negative_oib_bar_count` | 负 OIB bar 数 | 统计 `oib_delta_amount < 0` | 新 | P1 | |
| `positive_cvd_bar_count` | 正 CVD bar 数 | 统计 `cvd_delta_amount > 0` | 新 | P1 | |
| `negative_cvd_bar_count` | 负 CVD bar 数 | 统计 `cvd_delta_amount < 0` | 新 | P1 | |
| `buy_support_ratio` | 买侧支撑比 | `(add_buy-cancel_buy)/total_amount` | 新 | P1 | 需 join trade daily |
| `sell_pressure_ratio` | 卖侧压力比 | `(add_sell-cancel_sell)/total_amount` | 新 | P1 | 需 join trade daily |
| `quality_info` | 日级质量提示 | 合并 5m `quality_info` | 新 | P0 | |

## 8.3 必补：必须新增清洗产出

| 字段名 | 字段说明 | 为什么现状不够 | 支持范围 | 优先级 | 备注 |
|---|---|---|---|---|---|
| `add_buy_count` | 日级买侧新增挂单笔数 | 依赖 5m 笔数字段 | 新 | P0 | 上游先补 `atomic_order_5m` |
| `add_sell_count` | 日级卖侧新增挂单笔数 | 同上 | 新 | P0 | |
| `cancel_buy_count` | 日级买侧撤单笔数 | 同上 | 新 | P0 | |
| `cancel_sell_count` | 日级卖侧撤单笔数 | 同上 | 新 | P0 | |

## 8.4 结论
- `atomic_order_daily` 很适合做“右侧风险识别”和“高位稳住分析”。
- 它并不需要重新回 raw 做很多聚合逻辑，前提只是上游 `order_5m` 先补完整。

---

# 9. `atomic_data_manifest` 执行表

## 9.1 已有：可直接映射
- 当前没有现成表。

## 9.2 可算：不必回 raw

| 字段名 | 字段说明 | 当前来源/算法 | 支持范围 | 优先级 | 备注 |
|---|---|---|---|---|---|
| `source_type` | 数据类型 | 按月份/日期段派生 | 老/新 | P0 | |
| `trade_day_count` | 该周期交易日数 | 按结果表 distinct date 统计 | 老/新 | P0 | |
| `symbol_day_count` | 股票日覆盖数 | 按结果表统计 | 老/新 | P0 | |
| `row_count` | 记录数 | 按结果表统计 | 老/新 | P0 | |
| `has_order_atomic` | 是否具备挂单原子层 | 检查 `order` 表是否有记录 | 老/新 | P0 | 老数据通常为否 |
| `quality_issue_count` | 质量异常数 | 统计 `quality_info` 非空 | 老/新 | P1 | |

## 9.3 必补：必须新增产出

| 字段名 | 字段说明 | 为什么现状不够 | 支持范围 | 优先级 | 备注 |
|---|---|---|---|---|---|
| `dataset_key` | 数据集名 | 现无统一清单表 | 老/新 | P0 | |
| `period_key` | 周期键 | 现无统一清单表 | 老/新 | P0 | 月度最合适 |
| `parser_version` | 清洗器版本 | 现无法追溯 | 老/新 | P0 | 很关键 |
| `generated_at` | 生成时间 | 现无法追溯 | 老/新 | P0 | |
| `validation_status` | 验证状态 | 现无法追溯 | 老/新 | P0 | `pending/passed/failed` |
| `notes` | 备注 | 现无法沉淀异常说明 | 老/新 | P1 | |

## 9.4 结论
- `manifest` 不是策略表，但它决定我们以后敢不敢删 raw。
- 如果没有它，后面还是会反复问“这个月到底跑没跑完、能不能信、能不能删”。

---

## 10. 最终执行顺序（冻结版）

### Phase A：先把老/新共用的成交层做厚
1. 落 `atomic_trade_5m`
2. 落 `atomic_trade_daily`
3. 至少补齐以下 P0：
   - `trade_count`
   - `source_type`
   - 日级 `am/pm/open/last` 结构字段

### Phase B：再把 `2026-03+` 的挂单层补完整
1. 落 `atomic_order_5m`
2. 落 `atomic_order_daily`
3. 至少补齐以下 P0：
   - `add/cancel count`
   - `add/cancel volume`
   - `buy_add_cancel_net_amount`
   - `sell_add_cancel_net_amount`

### Phase B.5：专题讨论后再决定是否扩竞价阶段落库
1. 先审计 raw 是否稳定覆盖 `09:15 ~ 09:25`
2. 再冻结：
   - 是否单独落 `09:25` bar
   - 是否统一增加 `session_phase`
3. 在此之前，不允许默认把竞价撮合并入 `09:30` 连续竞价 bar

### Phase C：补管理清单，建立删 raw 的判断依据
1. 落 `atomic_data_manifest`
2. 每月记录：覆盖、质量、版本、验收状态
3. 达到删除前条件后，再决定是否删 `2025` raw

---

## 11. 当前短结论
- 这张表把原子事实层正式分成了三类：**已有 / 可算 / 必补**。
- 真正最值钱的动作不是先想更多因子，而是先把：
  - `atomic_trade_5m`
  - `atomic_trade_daily`
  - `atomic_order_5m`
  这三层做扎实。
- 但这轮也新增冻结了 3 个重要边界：
  - 价格按 raw 存，复权单独处理；
  - 5m 时间桶按前闭后开；
  - 集合竞价必须隔离，但具体形态待专题讨论后再补。
- 这样后面大多数选股、复盘、风险识别研究，都只是在原子层之上重算，不会动不动回 raw。
