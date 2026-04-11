# STG-20260411-09 原子事实层 P0 落库方案与跑批顺序

## 1. 基本信息
- 标题：原子事实层 P0 落库方案与跑批顺序
- 状态：ACTIVE
- 负责人：Codex
- 关联 CAP：`CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`, `CAP-WIN-PIPELINE`
- 关联 Task ID：`CHG-20260411-09`

## 2. 这份文档解决什么问题
前两张文档已经把：
- 目标表结构
- 字段差异

都讲清楚了。

这张文档只继续回答 3 个执行问题：

1. **P0 到底先落哪些字段**
2. **这些表用什么 DDL 建**
3. **跑批顺序怎么排，才能最省重复劳动**

目标是让下一步可以直接开始写脚本，而不是再抽象讨论。

---

## 3. P0 冻结原则

### 3.1 P0 只做“以后最不想回 raw 的那批字段”
这批字段的标准不是“最完整”，而是：
- 对选股/复盘/中线资金流研究最常用；
- 一旦没有，未来大概率会反复回 raw；
- 但又不要求这次把所有 P1/P2 一次做完。

### 3.2 P0 仍坚持老/新数据边界
- `2025-01 ~ 2026-02`：只做 **成交原子层**
- `2026-03+`：做 **成交原子层 + 挂单原子层**
- 不能因为想统一字段，就伪造老数据的挂单事件层

### 3.3 P0 只写新库，不改旧库口径
- 旧库继续服务盯盘 / 复盘 / 舆情 / 选股现有链路
- 新原子层独立落库：
  - 建议路径：`data/atomic_facts/market_atomic.db`

### 3.4 本轮新增冻结的 4 条边界
1. 价格按 **Raw Price** 存，复权单独处理
2. 5m 时间桶统一按 **前闭后开 `[t, t+5m)`**
3. 集合竞价必须与连续竞价隔离
4. 但集合竞价的**具体落库形态暂未最终冻结**，需后续专题讨论

---

## 4. P0 最小可用表范围

### 4.1 本次就建 5 张表
1. `atomic_trade_5m`
2. `atomic_trade_daily`
3. `atomic_order_5m`
4. `atomic_order_daily`
5. `atomic_data_manifest`

### 4.2 本次不做的
以下先不进 P0 落库，只保留在后续增强范围：
- `max_parent_order_amount`
- `top5_parent_concentration_ratio`
- 各类 `*_count` 的 L1/L2 主力/超大单细分笔数
- 更细的盘口微结构字段
- 完整盘口存量状态重建（如 `end_bid_resting_volume / end_ask_resting_volume`）

原因：
- 这些字段虽然有价值，但它们会显著抬高第一次清洗复杂度；
- 当前更重要的是先把日后 80% 研究都够用的公共底座做出来。
- 集合竞价虽然重要，但当前更需要先完成 raw 审计，再决定最终落库形态。

### 4.3 本轮新增但不直接进入 P0 DDL 的对象
1. `price_adjustment_factors`
   - 用于复权读取
   - 建议独立表，不污染 atomic trade 主表
2. `limit_state_daily / limit_state_5m`（或等价状态字段）
   - 用于涨跌停/触板研究
   - 当前先记为 P1 增强

---

## 5. P0 字段冻结

# 5.1 `atomic_trade_5m` P0 字段

| 字段名 | 类型 | 说明 | 来源 |
|---|---|---|---|
| `symbol` | TEXT | 股票代码 | `history_5m_l2` |
| `trade_date` | TEXT | 交易日 | `history_5m_l2.source_date` |
| `bucket_start` | TEXT | 5m 桶起点 | `history_5m_l2.datetime` |
| `open` | REAL | 开盘价 | `history_5m_l2.open` |
| `high` | REAL | 最高价 | `history_5m_l2.high` |
| `low` | REAL | 最低价 | `history_5m_l2.low` |
| `close` | REAL | 收盘价 | `history_5m_l2.close` |
| `total_amount` | REAL | 总成交额 | `history_5m_l2.total_amount` |
| `total_volume` | REAL | 总成交量 | `history_5m_l2.total_volume` / raw 重算 |
| `trade_count` | INTEGER | 5m 成交笔数 | raw / 新增清洗 |
| `l1_main_buy_amount` | REAL | L1 主力买入额 | `history_5m_l2.l1_main_buy` |
| `l1_main_sell_amount` | REAL | L1 主力卖出额 | `history_5m_l2.l1_main_sell` |
| `l1_main_net_amount` | REAL | L1 主力净额 | 派生 |
| `l1_super_buy_amount` | REAL | L1 超大单买入额 | `history_5m_l2.l1_super_buy` |
| `l1_super_sell_amount` | REAL | L1 超大单卖出额 | `history_5m_l2.l1_super_sell` |
| `l1_super_net_amount` | REAL | L1 超大单净额 | 派生 |
| `l2_main_buy_amount` | REAL | L2 主力买入额 | `history_5m_l2.l2_main_buy` |
| `l2_main_sell_amount` | REAL | L2 主力卖出额 | `history_5m_l2.l2_main_sell` |
| `l2_main_net_amount` | REAL | L2 主力净额 | 派生 |
| `l2_super_buy_amount` | REAL | L2 超大单买入额 | `history_5m_l2.l2_super_buy` |
| `l2_super_sell_amount` | REAL | L2 超大单卖出额 | `history_5m_l2.l2_super_sell` |
| `l2_super_net_amount` | REAL | L2 超大单净额 | 派生 |
| `source_type` | TEXT | `trade_only / trade_order` | 日期段派生 |
| `quality_info` | TEXT | 质量提示 | `history_5m_l2.quality_info` |

> 备注：
> - 本表当前未把 `session_phase` 写入 P0 DDL，不是因为不重要，而是因为集合竞价具体落库形态尚未冻结；
> - 在专题方案拍板前，相关逻辑只允许在文档中预留，不允许脚本自行拍脑袋并桶。

---

# 5.2 `atomic_trade_daily` P0 字段

| 字段名 | 类型 | 说明 | 来源 |
|---|---|---|---|
| `symbol` | TEXT | 股票代码 | `history_daily_l2` |
| `trade_date` | TEXT | 交易日 | `history_daily_l2.date` |
| `open` | REAL | 开盘价 | `history_daily_l2.open` |
| `high` | REAL | 最高价 | `history_daily_l2.high` |
| `low` | REAL | 最低价 | `history_daily_l2.low` |
| `close` | REAL | 收盘价 | `history_daily_l2.close` |
| `total_amount` | REAL | 总成交额 | `history_daily_l2.total_amount` |
| `total_volume` | REAL | 总成交量 | 5m 汇总 |
| `trade_count` | INTEGER | 日成交笔数 | 5m 汇总 |
| `l1_main_buy_amount` | REAL | L1 主力买入额 | `history_daily_l2.l1_main_buy` |
| `l1_main_sell_amount` | REAL | L1 主力卖出额 | `history_daily_l2.l1_main_sell` |
| `l1_main_net_amount` | REAL | L1 主力净额 | `history_daily_l2.l1_main_net` |
| `l1_super_buy_amount` | REAL | L1 超大单买入额 | `history_daily_l2.l1_super_buy` |
| `l1_super_sell_amount` | REAL | L1 超大单卖出额 | `history_daily_l2.l1_super_sell` |
| `l1_super_net_amount` | REAL | L1 超大单净额 | `history_daily_l2.l1_super_net` |
| `l2_main_buy_amount` | REAL | L2 主力买入额 | `history_daily_l2.l2_main_buy` |
| `l2_main_sell_amount` | REAL | L2 主力卖出额 | `history_daily_l2.l2_main_sell` |
| `l2_main_net_amount` | REAL | L2 主力净额 | `history_daily_l2.l2_main_net` |
| `l2_super_buy_amount` | REAL | L2 超大单买入额 | `history_daily_l2.l2_super_buy` |
| `l2_super_sell_amount` | REAL | L2 超大单卖出额 | `history_daily_l2.l2_super_sell` |
| `l2_super_net_amount` | REAL | L2 超大单净额 | `history_daily_l2.l2_super_net` |
| `l1_activity_ratio` | REAL | L1 参与度 | `history_daily_l2.l1_activity_ratio` |
| `l2_activity_ratio` | REAL | L2 参与度 | `history_daily_l2.l2_activity_ratio` |
| `l1_buy_ratio` | REAL | L1 买入占比 | `history_daily_l2.l1_buy_ratio` |
| `l1_sell_ratio` | REAL | L1 卖出占比 | `history_daily_l2.l1_sell_ratio` |
| `l2_buy_ratio` | REAL | L2 买入占比 | `history_daily_l2.l2_buy_ratio` |
| `l2_sell_ratio` | REAL | L2 卖出占比 | `history_daily_l2.l2_sell_ratio` |
| `am_l2_main_net_amount` | REAL | 上午 L2 主力净额 | 5m 汇总 |
| `pm_l2_main_net_amount` | REAL | 下午 L2 主力净额 | 5m 汇总 |
| `open_30m_l2_main_net_amount` | REAL | 开盘 30m 主力净额 | 5m 汇总 |
| `last_30m_l2_main_net_amount` | REAL | 尾盘 30m 主力净额 | 5m 汇总 |
| `positive_l2_net_bar_count` | INTEGER | 正净流入 bar 数 | 5m 汇总 |
| `negative_l2_net_bar_count` | INTEGER | 负净流入 bar 数 | 5m 汇总 |
| `source_type` | TEXT | `trade_only / trade_order` | 日期段派生 |
| `quality_info` | TEXT | 质量提示 | `history_daily_l2.quality_info` |

> 备注：
> - 日级层后续应支持通过复权因子做 adjusted read，但 P0 原子事实表仍只存 raw OHLC；
> - 涨跌停状态字段当前记为 P1，不插队这轮 P0 落库。

---

# 5.3 `atomic_order_5m` P0 字段（仅 `2026-03+`）

| 字段名 | 类型 | 说明 | 来源 |
|---|---|---|---|
| `symbol` | TEXT | 股票代码 | `history_5m_l2` |
| `trade_date` | TEXT | 交易日 | `history_5m_l2.source_date` |
| `bucket_start` | TEXT | 5m 桶起点 | `history_5m_l2.datetime` |
| `add_buy_amount` | REAL | 买侧新增挂单额 | `history_5m_l2.l2_add_buy_amount` |
| `add_sell_amount` | REAL | 卖侧新增挂单额 | `history_5m_l2.l2_add_sell_amount` |
| `cancel_buy_amount` | REAL | 买侧撤单额 | `history_5m_l2.l2_cancel_buy_amount` |
| `cancel_sell_amount` | REAL | 卖侧撤单额 | `history_5m_l2.l2_cancel_sell_amount` |
| `cvd_delta_amount` | REAL | CVD 变化 | `history_5m_l2.l2_cvd_delta` |
| `oib_delta_amount` | REAL | OIB 变化 | `history_5m_l2.l2_oib_delta` |
| `add_buy_count` | INTEGER | 买侧新增挂单笔数 | raw / 新增清洗 |
| `add_sell_count` | INTEGER | 卖侧新增挂单笔数 | raw / 新增清洗 |
| `cancel_buy_count` | INTEGER | 买侧撤单笔数 | raw / 新增清洗 |
| `cancel_sell_count` | INTEGER | 卖侧撤单笔数 | raw / 新增清洗 |
| `add_buy_volume` | REAL | 买侧新增挂单量 | raw / 新增清洗 |
| `add_sell_volume` | REAL | 卖侧新增挂单量 | raw / 新增清洗 |
| `cancel_buy_volume` | REAL | 买侧撤单量 | raw / 新增清洗 |
| `cancel_sell_volume` | REAL | 卖侧撤单量 | raw / 新增清洗 |
| `buy_add_cancel_net_amount` | REAL | 买侧挂撤净额 | 派生 |
| `sell_add_cancel_net_amount` | REAL | 卖侧挂撤净额 | 派生 |
| `source_type` | TEXT | 固定 `trade_order` | 固定值 |
| `quality_info` | TEXT | 质量提示 | `history_5m_l2.quality_info` |

---

# 5.4 `atomic_order_daily` P0 字段（仅 `2026-03+`）

| 字段名 | 类型 | 说明 | 来源 |
|---|---|---|---|
| `symbol` | TEXT | 股票代码 | 5m 汇总 |
| `trade_date` | TEXT | 交易日 | 5m 汇总 |
| `add_buy_amount` | REAL | 买侧新增挂单额 | 5m 汇总 |
| `add_sell_amount` | REAL | 卖侧新增挂单额 | 5m 汇总 |
| `cancel_buy_amount` | REAL | 买侧撤单额 | 5m 汇总 |
| `cancel_sell_amount` | REAL | 卖侧撤单额 | 5m 汇总 |
| `cvd_delta_amount` | REAL | 日级 CVD 变化 | 5m 汇总 |
| `oib_delta_amount` | REAL | 日级 OIB 变化 | 5m 汇总 |
| `add_buy_count` | INTEGER | 日级买侧新增挂单笔数 | 5m 汇总 |
| `add_sell_count` | INTEGER | 日级卖侧新增挂单笔数 | 5m 汇总 |
| `cancel_buy_count` | INTEGER | 日级买侧撤单笔数 | 5m 汇总 |
| `cancel_sell_count` | INTEGER | 日级卖侧撤单笔数 | 5m 汇总 |
| `am_oib_delta_amount` | REAL | 上午 OIB 变化 | 5m 汇总 |
| `pm_oib_delta_amount` | REAL | 下午 OIB 变化 | 5m 汇总 |
| `open_60m_oib_delta_amount` | REAL | 开盘 60m OIB 变化 | 5m 汇总 |
| `last_30m_oib_delta_amount` | REAL | 尾盘 30m OIB 变化 | 5m 汇总 |
| `open_60m_cvd_delta_amount` | REAL | 开盘 60m CVD 变化 | 5m 汇总 |
| `last_30m_cvd_delta_amount` | REAL | 尾盘 30m CVD 变化 | 5m 汇总 |
| `positive_oib_bar_count` | INTEGER | 正 OIB bar 数 | 5m 汇总 |
| `negative_oib_bar_count` | INTEGER | 负 OIB bar 数 | 5m 汇总 |
| `positive_cvd_bar_count` | INTEGER | 正 CVD bar 数 | 5m 汇总 |
| `negative_cvd_bar_count` | INTEGER | 负 CVD bar 数 | 5m 汇总 |
| `buy_support_ratio` | REAL | 买侧支撑比 | 派生 |
| `sell_pressure_ratio` | REAL | 卖侧压力比 | 派生 |
| `quality_info` | TEXT | 质量提示 | 5m 合并 |

---

# 5.5 `atomic_data_manifest` P0 字段

| 字段名 | 类型 | 说明 |
|---|---|---|
| `dataset_key` | TEXT | 数据集名 |
| `period_key` | TEXT | 周期键，建议 `YYYY-MM` |
| `source_type` | TEXT | `trade_only / trade_order` |
| `trade_day_count` | INTEGER | 交易日数 |
| `symbol_day_count` | INTEGER | 股票日覆盖数 |
| `row_count` | INTEGER | 记录数 |
| `has_order_atomic` | INTEGER | 是否具备挂单原子层 |
| `quality_issue_count` | INTEGER | 质量问题记录数 |
| `parser_version` | TEXT | 清洗器版本 |
| `generated_at` | TEXT | 生成时间 |
| `validation_status` | TEXT | `pending / passed / failed` |
| `notes` | TEXT | 备注 |

---

## 6. DDL 文件
本次已同步新增：

- `/Users/dong/Desktop/AIGC/market-live-terminal-data-governance/backend/scripts/sql/atomic_fact_p0_schema.sql`

它就是下一步落库脚本可直接执行的起点。

本轮已顺手补充：
- 截面研究索引：
  - `idx_atomic_trade_5m_time_symbol`
  - `idx_atomic_trade_daily_time_symbol`
  - `idx_atomic_order_5m_time_symbol`
  - `idx_atomic_order_daily_time_symbol`

---

## 7. 跑批顺序（冻结版）

### Phase 1：初始化原子库
1. 建库：`data/atomic_facts/market_atomic.db`
2. 执行 `atomic_fact_p0_schema.sql`
3. 建立基础索引

#### Phase 1.5：竞价阶段 raw 审计（待下一步）
1. 抽样确认 raw 是否稳定覆盖：
   - `09:15 ~ 09:25`
   - 是否有逐笔竞价事件 / 仅撮合结果
2. 再决定：
   - 是否单独落 `09:25` bar
   - 是否加入 `session_phase`
3. 这一步在下一轮讨论前，不直接进正式 P0 DDL

### Phase 2：先回填成交原子层
#### 2.1 `2025-01 ~ 2026-02`
- 优先来源：
  - 旧正式表：`history_5m_l2 / history_daily_l2`
  - 缺失字段：从 raw 成交清洗补：
    - `trade_count`
    - `total_volume`（若旧表为空）
- 先落：
  - `atomic_trade_5m`
  - `atomic_trade_daily`

#### 2.2 `2026-03+`
- 先同样落成交层，保持全时段统一
- 这一步不要和挂单层混在同一个脚本里，避免调试复杂

### Phase 3：再回填挂单原子层（只跑 `2026-03+`）
- 来源：
  - 现有 `history_5m_l2` 可直读金额类事件字段
  - raw `逐笔委托.csv` 用于补：
    - `add/cancel count`
    - `add/cancel volume`
- 先落：
  - `atomic_order_5m`
- 再汇总：
  - `atomic_order_daily`

### Phase 4：回填 manifest
- 以月为单位写入：
  - 覆盖范围
  - 质量问题数量
  - 清洗版本
  - 验证状态

---

## 8. 脚本拆分建议

### 8.1 不建议一个大脚本全做完
建议拆成 4 个脚本；其中前 2 个本轮已落地：

1. `init_atomic_fact_db.py`
   - 建库
   - 执行 schema SQL

2. `build_atomic_trade_from_history.py`
   - 先从现有 `history_5m_l2 / history_daily_l2` 批量落可直映/可算部分

3. `backfill_atomic_trade_from_raw.py`
   - 只补成交 raw 才有的字段
   - 如：`trade_count`, `total_volume` 缺口

4. `backfill_atomic_order_from_raw.py`
   - 只跑 `2026-03+`
   - 补 `add/cancel count/volume`
   - 汇总 `atomic_order_daily`

当前已存在文件：
- `/Users/dong/Desktop/AIGC/market-live-terminal-data-governance/backend/scripts/init_atomic_fact_db.py`
- `/Users/dong/Desktop/AIGC/market-live-terminal-data-governance/backend/scripts/build_atomic_trade_from_history.py`

### 8.2 为什么这么拆
因为这 4 段的风险完全不同：
- 初始化风险低
- 现表映射风险低
- 成交 raw 回填风险中
- 挂单 raw 回填风险最高

拆开后出问题更好定位，不会一锅粥。

---

## 9. Windows 执行建议

### 9.1 老数据成交 raw
- 继续沿用原先的：
  - 解压到 `E:` staging
  - 当天处理完即删解压目录
  - 6~8 worker 并发
- 输出不要直接写主库，先写：
  - 月度中间库 / 原子库分片

### 9.2 新数据挂单 raw
- 先做 **单日演练**，确认：
  - 事件码兼容正常
  - count/volume 统计正常
  - `quality_info` 没明显失真
- 演练过后再扩到整月

### 9.3 不建议现在就全量推翻重跑旧正式库
- 先建独立原子层
- 先把研究底座做厚
- 等原子层稳定后，再决定要不要反向增强正式链路

---

## 10. 删 `2025` raw 前的最低条件
必须同时满足：

1. `2025-01 ~ 2025-12` 的 `atomic_trade_5m` 完整
2. `2025-01 ~ 2025-12` 的 `atomic_trade_daily` 完整
3. `trade_count / total_volume / 主力超大单买卖额` 已可稳定复算
4. 每月都有 `atomic_data_manifest`
5. 至少抽样验证一轮：
   - 单票
   - 单月
   - 跨月
   - 高成交票 / 低成交票

只要这 5 条没同时满足，就**不建议删**。

---

## 11. 当前短结论
- 下一步已经不是“想不想做”，而是可以直接开始做：
  - 先建 `market_atomic.db`
  - 先落 `trade_5m / trade_daily`
  - 再补 `2026-03+ order_5m / order_daily`
- 本次新增的 DDL 文件，已经把 P0 表结构冻结成可执行版本。
- 同时也明确记下了一个重要未决项：
  - **集合竞价需要隔离，但具体设计暂未完全明确，后续必须单独讨论后再补。**
