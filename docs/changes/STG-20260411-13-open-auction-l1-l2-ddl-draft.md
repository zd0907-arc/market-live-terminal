# STG-20260411-13 集合竞价 L1/L2 摘要表与 DDL 草案

> **历史过程卡。**
> 当前项目主线 / 当前目录 / 当前版本 / 当前分支纪律，请优先看：`docs/changes/MOD-20260421-01-project-current-state-and-doc-governance-normalization.md`
> 当前数据治理主题真实状态，请优先看：`docs/changes/MOD-20260411-14-market-data-governance-current-state.md`


## 1. 基本信息
- 标题：集合竞价 L1/L2 摘要表与 DDL 草案
- 状态：ACTIVE
- 负责人：Codex
- 关联 CAP：`CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`, `CAP-WIN-PIPELINE`
- 关联 Task ID：`CHG-20260411-13`

## 2. 这份文档现在只解决一件事
## 先把集合竞价的数据层设计清楚，不碰决策层。

也就是说，这轮只回答：
1. 集合竞价要不要单独成表；
2. L1 和 L2 要不要分层存；
3. 字段大概长什么样；
4. DDL 草案怎么写。

不回答：
- 明天该不该买
- 该不该卖
- 怎么打分
- 怎么触发策略

---

## 3. 当前冻结原则

### 3.1 集合竞价独立于连续竞价
- 不并入 `atomic_trade_5m / atomic_order_5m`
- 单独成表

### 3.2 L1 / L2 分层保留
因为你的真实使用场景是：
- 白天当时只能看到 **L1**
- 晚上盘后才能拿到 **L2**

所以数据层必须把这两层都保留下来，不能混成一份“神视角结果”。

### 3.3 当前只做“摘要层”
先不做竞价逐笔明细事实库，先做：
- 按 `symbol + trade_date` 一天一行的竞价摘要表

这样比较稳，也够支撑后续研究。

---

## 4. 推荐对象（V1）
建议最终先落 3 张表：

1. `atomic_open_auction_l1_daily`
2. `atomic_open_auction_l2_daily`
3. `atomic_open_auction_manifest`

解释：
- `l1_daily`：保留白天真实可见的竞价结果
- `l2_daily`：保留盘后补齐后的竞价增强结果
- `manifest`：记录该天该票有没有 L1/L2、质量如何、来源是什么

---

# 5. 表一：`atomic_open_auction_l1_daily`

## 5.1 定位
这张表代表：

## “如果只站在盘前/白天可见视角，我能看到的集合竞价摘要是什么？”

主要基于：
- `行情.csv`
- 能直接归到 L1 语义的成交/量价统计

## 5.2 推荐字段

| 字段名 | 类型 | 含义 |
|---|---|---|
| `symbol` | TEXT | 股票代码 |
| `trade_date` | TEXT | 交易日 |
| `auction_price` | REAL | 竞价最终价格（若可得） |
| `auction_match_volume` | REAL | 竞价撮合量 |
| `auction_match_amount` | REAL | 竞价撮合额 |
| `auction_price_change_pct_vs_prev_close` | REAL | 相对昨收涨跌幅 |
| `auction_trade_count_total` | INTEGER | 竞价阶段成交笔数 |
| `auction_trade_volume_total` | REAL | 竞价阶段总成交量 |
| `auction_trade_amount_total` | REAL | 竞价阶段总成交额 |
| `auction_trade_count_0915_0920` | INTEGER | `09:15~09:20` 成交笔数 |
| `auction_trade_count_0920_0925` | INTEGER | `09:20~09:25` 成交笔数 |
| `auction_trade_count_0925_match` | INTEGER | `09:25` 撮合成交笔数 |
| `auction_trade_amount_0915_0920` | REAL | `09:15~09:20` 成交额 |
| `auction_trade_amount_0920_0925` | REAL | `09:20~09:25` 成交额 |
| `auction_trade_amount_0925_match` | REAL | `09:25` 撮合成交额 |
| `auction_first_trade_time` | TEXT | 竞价最早成交时间 |
| `auction_last_trade_time` | TEXT | 竞价最晚成交时间 |
| `auction_exact_0925_trade_count` | INTEGER | 精确 `09:25:00/01` 成交笔数 |
| `quote_preopen_row_count` | INTEGER | 竞价阶段 quote 行数 |
| `quote_has_0925_snapshot` | INTEGER | 是否有 `09:25` 快照 |
| `quality_info` | TEXT | 质量提示 |
| `source_type` | TEXT | 固定 `l1_visible` |
| `created_at` | TEXT | 创建时间 |
| `updated_at` | TEXT | 更新时间 |

## 5.3 说明
- 这张表不承诺包含真实挂单 add/cancel 语义；
- 它代表的是：**当时白天真正能看到的竞价层摘要**。

---

# 6. 表二：`atomic_open_auction_l2_daily`

## 6.1 定位
这张表代表：

## “盘后 L2 原始包回补后，集合竞价阶段真正发生了什么？”

它主要面向：
- 数据校验
- 研究复盘
- 后续因子提炼

## 6.2 推荐字段

| 字段名 | 类型 | 含义 |
|---|---|---|
| `symbol` | TEXT | 股票代码 |
| `trade_date` | TEXT | 交易日 |
| `auction_trade_count_total` | INTEGER | 竞价阶段成交笔数 |
| `auction_trade_volume_total` | REAL | 竞价阶段总成交量 |
| `auction_trade_amount_total` | REAL | 竞价阶段总成交额 |
| `auction_trade_count_0915_0920` | INTEGER | `09:15~09:20` 成交笔数 |
| `auction_trade_count_0920_0925` | INTEGER | `09:20~09:25` 成交笔数 |
| `auction_trade_count_0925_match` | INTEGER | `09:25` 撮合成交笔数 |
| `auction_trade_amount_0915_0920` | REAL | `09:15~09:20` 成交额 |
| `auction_trade_amount_0920_0925` | REAL | `09:20~09:25` 成交额 |
| `auction_trade_amount_0925_match` | REAL | `09:25` 撮合成交额 |
| `auction_order_add_buy_amount` | REAL | 竞价阶段买侧新增挂单额 |
| `auction_order_add_sell_amount` | REAL | 竞价阶段卖侧新增挂单额 |
| `auction_order_cancel_buy_amount` | REAL | 竞价阶段买侧撤单额 |
| `auction_order_cancel_sell_amount` | REAL | 竞价阶段卖侧撤单额 |
| `auction_order_add_buy_count` | INTEGER | 买侧新增挂单笔数 |
| `auction_order_add_sell_count` | INTEGER | 卖侧新增挂单笔数 |
| `auction_order_cancel_buy_count` | INTEGER | 买侧撤单笔数 |
| `auction_order_cancel_sell_count` | INTEGER | 卖侧撤单笔数 |
| `auction_order_add_buy_amount_0915_0920` | REAL | `09:15~09:20` 买侧新增挂单额 |
| `auction_order_add_buy_amount_0920_0925` | REAL | `09:20~09:25` 买侧新增挂单额 |
| `auction_order_add_sell_amount_0915_0920` | REAL | `09:15~09:20` 卖侧新增挂单额 |
| `auction_order_add_sell_amount_0920_0925` | REAL | `09:20~09:25` 卖侧新增挂单额 |
| `auction_order_cancel_buy_amount_0915_0920` | REAL | `09:15~09:20` 买侧撤单额 |
| `auction_order_cancel_sell_amount_0915_0920` | REAL | `09:15~09:20` 卖侧撤单额 |
| `auction_has_exact_0925_trade` | INTEGER | 是否有 `09:25` 成交边界 |
| `auction_has_exact_0925_order` | INTEGER | 是否有 `09:25` 委托边界 |
| `quality_info` | TEXT | 质量提示 |
| `source_type` | TEXT | 固定 `l2_postclose` |
| `created_at` | TEXT | 创建时间 |
| `updated_at` | TEXT | 更新时间 |

## 6.3 说明
- 这张表允许记录 L2 的增强结果；
- 它和 `l1_daily` 不是替代关系，而是并存关系。

---

# 7. 表三：`atomic_open_auction_manifest`

## 7.1 定位
记录某个 `symbol + trade_date` 的竞价摘要是否齐全。

## 7.2 推荐字段

| 字段名 | 类型 | 含义 |
|---|---|---|
| `symbol` | TEXT | 股票代码 |
| `trade_date` | TEXT | 交易日 |
| `has_l1_auction` | INTEGER | 是否有 L1 竞价摘要 |
| `has_l2_auction` | INTEGER | 是否有 L2 竞价摘要 |
| `l1_quality_info` | TEXT | L1 质量说明 |
| `l2_quality_info` | TEXT | L2 质量说明 |
| `auction_shape` | TEXT | 样本形态，如 `trade+order+quote` |
| `parser_version` | TEXT | 清洗器版本 |
| `generated_at` | TEXT | 生成时间 |
| `notes` | TEXT | 备注 |

---

## 8. 为什么我现在不建议做“单表混合 L1+L2”
如果把 L1/L2 混成一张表，后面很容易出现两个问题：

1. **白天能看到的，和晚上才知道的，混在一起**
2. 研究时分不清：
   - 这是实时可见事实
   - 还是盘后增强事实

所以更稳的办法就是：
- **L1 一张表**
- **L2 一张表**
- manifest 负责对齐关系

---

## 9. DDL 草案
本轮同步新增：
- `/Users/dong/Desktop/AIGC/market-live-terminal-data-governance/backend/scripts/sql/open_auction_summary_schema_draft.sql`

这份 SQL 只是：
- 草案
- 预留
- 供后续评审

当前**不接入正式跑批**。

---

## 10. 当前短结论
如果只看数据层，我现在建议冻结为：

1. 集合竞价独立成表
2. L1 / L2 分层保留
3. 先做日级摘要表
4. 先不碰决策逻辑

这和你刚才的要求是一致的。
