# STG-20260411-16 原子事实层 P1 增强设计

> 当前母卡入口：`docs/changes/MOD-20260411-14-market-data-governance-current-state.md`

## 1. 这张卡解决什么问题
P0 已经把连续竞价成交层、挂单层、竞价摘要层的主骨架搭起来了。

这张卡单独冻结：
- 为了识别“偷偷吃货 / 先藏后打”，还要补哪些 **P1 原子字段**；
- 这些字段分别来自哪里；
- 老数据段 / 新数据段是否都能支撑；
- 哪些本轮就进入利通重跑，哪些先记为下一阶段增强。

一句话：

**P0 解决“能不能跑起来”，P1 解决“以后少回 raw、研究更稳”。**

---

## 2. P1 分两层

### 2.1 P1-A：本轮直接进入执行
目标：先把最值钱、最容易复用、最不容易以后返工的字段补上。

### 2.2 P1-B：先冻结设计，暂不阻塞本轮跑数
目标：把重要但还需要进一步口径确认的内容先写清楚，避免后面忘掉。

---

## 3. P1-A 字段总表（本轮进入利通重跑）

| 分组 | 字段名 | 落表 | 含义 | 原始来源 | 2025-01~2026-02 | 2026-03+ | 价值 |
|---|---|---|---|---|---|---|---|
| 成交计数 | `l1_main_buy_count` / `l1_main_sell_count` | `atomic_trade_5m`, `atomic_trade_daily` | 单笔成交达到主力阈值的笔数 | 逐笔成交 | 支持 | 支持 | 看是不是很多中大成交持续参与，而不是只看净额 |
| 成交计数 | `l1_super_buy_count` / `l1_super_sell_count` | `atomic_trade_5m`, `atomic_trade_daily` | 单笔成交达到超大单阈值的笔数 | 逐笔成交 | 支持 | 支持 | 看是不是少数超大成交直接点火 |
| 母单计数 | `l2_main_buy_count` / `l2_main_sell_count` | `atomic_trade_5m`, `atomic_trade_daily` | 母单成交额达到主力阈值的母单数 | 成交 + OrderID 归并 | 支持 | 支持 | 识别“拆单后仍有母单聚集” |
| 母单计数 | `l2_super_buy_count` / `l2_super_sell_count` | `atomic_trade_5m`, `atomic_trade_daily` | 母单成交额达到超大单阈值的母单数 | 成交 + OrderID 归并 | 支持 | 支持 | 区分“很多中等母单吸筹” vs “少数超大母单明牌拉” |
| 单笔强度 | `max_trade_amount` | `atomic_trade_5m`, `atomic_trade_daily` | 当前粒度内最大单笔成交额 | 逐笔成交 | 支持 | 支持 | 判断是否出现明牌大单 |
| 单笔强度 | `avg_trade_amount` | `atomic_trade_5m`, `atomic_trade_daily` | 当前粒度内平均单笔成交额 | 逐笔成交 | 支持 | 支持 | 判断成交是否整体抬级 |
| 母单强度 | `max_parent_order_amount` | `atomic_trade_5m`, `atomic_trade_daily` | 当前粒度内最大母单成交额 | 成交 + OrderID 归并 | 支持 | 支持 | 看是否存在单一强母单主导 |
| 母单集中度 | `top5_parent_concentration_ratio` | `atomic_trade_5m`, `atomic_trade_daily` | 前 5 大母单成交额 / 当前总成交额 | 成交 + OrderID 归并 | 支持 | 支持 | 看是“少数母单主导”还是“均匀吸筹” |
| 挂单活跃度 | `order_event_count` | `atomic_order_5m`, `atomic_order_daily` | 当前粒度内有效挂单事件数 | 逐笔委托 | 不支持 | 支持 | 看盘口动作是稀疏还是持续不断 |
| OIB 集中度 | `oib_top3_concentration_ratio` | `atomic_order_daily` | 当日正向 OIB 中，前三根 bar 占比 | 逐笔委托聚合 | 不支持 | 支持 | 区分“全天稳步吸”还是“靠几根极端 bar” |
| OIB 扩散度 | `moderate_positive_oib_bar_count` | `atomic_order_daily` | 中等强度正 OIB bar 数 | 逐笔委托聚合 | 不支持 | 支持 | 看正向承接是否扩散到全天 |
| OIB 扩散度 | `moderate_positive_oib_bar_ratio` | `atomic_order_daily` | 中等强度正 OIB bar 占正 OIB bar 的比例 | 逐笔委托聚合 | 不支持 | 支持 | 辅助判断“不是一两根极值 bar 假强” |
| OIB 连续性 | `positive_oib_streak_max` | `atomic_order_daily` | 最大连续正 OIB bar 段长度 | 逐笔委托聚合 | 不支持 | 支持 | 看有没有持续托单 / 吸筹段 |

---

## 4. P1-B 先冻结设计（本轮不阻塞）

| 分组 | 字段/对象 | 建议落点 | 当前状态 | 备注 |
|---|---|---|---|---|
| 涨跌停状态 | `is_limit_up`, `is_limit_down`, `touch_limit_up`, `touch_limit_down` | 优先独立状态表 | 已单独立卡 | 详见 `STG-20260412-01-limit-state-layer-design.md` |
| 复权 | `adj_factor` / 独立复权因子表 | 独立 `adjustment_factor_daily` | 待补 | 原子层继续存 Raw Price，不在主表做复权价 |
| 事件层 | 新闻 / 公告 / 财报 / 题材 | 独立事件层 | 待补 | 不塞进 atomic 主表，但未来复盘解释必须有 |
| 竞价 phase 细分 | `09:15-09:20 / 09:20-09:25 / 09:25` | 独立竞价摘要层 | 待讨论 | 已冻结“竞价独立成组”，但 phase 细拆暂未最终定稿 |
| 盘口存量 | `end_bid_resting_volume`, `end_ask_resting_volume` | `atomic_order_5m` 或快照层 | 待补 | 对“高位稳住”有帮助，但当前不插队主线 |

---

## 5. 老数据段 / 新数据段差异

### 5.1 老数据段（2025-01 ~ 2026-02）
- 能做：
  - 成交计数
  - 母单计数
  - 单笔强度
  - 母单集中度
- 不能做：
  - `order_event_count`
  - `oib_*`
  - 任何真实挂单事件字段

所以老数据段的使命是：

**把成交级研究价值一次性榨干。**

### 5.2 新数据段（2026-03+）
- 能做老数据段全部内容；
- 还能补挂单流量层、竞价摘要层、后续的涨跌停状态层。

所以新数据段的使命是：

**把“成交 + 挂单 + 竞价”三层一次性做厚。**

---

## 6. 本轮实现口径说明

### 6.1 母单计数口径
- 以当前粒度内的 **母单成交额** 为准；
- `5m` 看 5 分钟桶内母单成交额；
- `daily` 看全天母单成交额；
- 这样更贴近“这一段到底有没有母单在持续吃货”。

### 6.2 集中度口径
- `top5_parent_concentration_ratio`：前 5 大母单成交额 / 当前粒度总成交额；
- `oib_top3_concentration_ratio`：前三根正 OIB bar / 全部正 OIB 之和。

### 6.3 中等强度 OIB 口径
- 当前先用“正 OIB bar 中位数及以上”作为中等强度的临时口径；
- 这是 **研究口径**，后续可以再调；
- 但字段先落下，避免以后还要重回 raw 才能补。

---

## 7. 为什么这些字段值得现在就补
因为我们现在最担心的不是“跑一次慢一点”，而是：

**以后每想到一个新研究点，就被迫再回 raw。**

这批 P1-A 字段的共同特点是：
- 都直接来自 raw；
- 都是以后高频复用的事实字段；
- 一旦没存，后面大概率还会回 raw 重算；
- 存了以后，上层策略可以反复改，不必频繁重跑底层。

---

## 8. 本轮与利通样板的关系
本轮不是先做全量，而是：
1. 先把 P1-A 字段补进 schema / 脚本；
2. 先在利通样板票验证这些字段是否有值、是否能解释“先藏后打”；
3. 利通跑通后，再定全量回补方案。

---

## 9. 当前结论
- **P1-A：现在就补，直接进入利通重跑。**
- **P1-B：先写入总方案，不阻塞当前跑数。**
- 这样做的目标是：
  - 不把主线拖慢；
  - 但也不把未来会反复用到的字段漏掉。
