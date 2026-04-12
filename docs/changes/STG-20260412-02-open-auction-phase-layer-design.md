# STG-20260412-02 集合竞价 phase 过程层设计

> 当前母卡入口：`docs/changes/MOD-20260411-14-market-data-governance-current-state.md`
> 前置草案：`STG-20260411-12-open-auction-storage-v1.md`、`STG-20260411-13-open-auction-l1-l2-ddl-draft.md`

## 1. 这张卡解决什么问题
前面的竞价文档已经确认两件事：
1. 集合竞价必须和连续竞价隔离；
2. L1 / L2 摘要层应该分开保留。

但用户本轮进一步确认的需求是：

> 以后不只是要看“竞价最终怎么样”，还要看竞价过程中 **前段试探 / 后段强化 / 最终撮合** 是怎么演化的。

所以这张卡单独回答：

## 所谓“更细的竞价层”到底是什么，应该加到什么程度，才既有研究价值，又不会把表炸太多。

---

## 2. 当前结论
我不建议直接上“逐笔竞价明细事实库”。

当前更合理的收敛方案是：

### 在现有竞价摘要层之上，再补一层 `phase 过程层`

也就是：
- 保留现有：
  - `atomic_open_auction_l1_daily`
  - `atomic_open_auction_l2_daily`
- 新增：
  - `atomic_open_auction_phase_l1_daily`
  - `atomic_open_auction_phase_l2_daily`

定位是：
- 仍然是 **日级摘要表**；
- 但把竞价拆成若干固定 phase 分段统计；
- 不直接保存逐笔 raw 明细。

这样能兼顾：
- 表数量可控；
- 历史批量回补可行；
- 研究价值明显提升。

---

## 3. 为什么不能只保留一个竞价总摘要
因为竞价总摘要只能告诉你：
- 今天竞价总成交多少
- 总挂单多少
- 最终 `09:25` 怎么样

但回答不了：
- 是不是前面虚强、后面转弱；
- 是不是 `09:20` 后才真正开始抢；
- 是不是最后一刻撤单；
- 白天看到的 L1 强，盘后 L2 回补后到底是不是同样成立。

对你未来最重要的两个场景：
1. **前一天有信号，第二天竞价要不要上**
2. **盘后复盘时，竞价是真强还是假强**

这些都需要 phase 层。

---

## 4. 我建议的 phase 拆法
当前先冻结成 3 段：

1. `phase_0915_0920`
2. `phase_0920_0925`
3. `phase_0925_match`

原因：
- 这个拆法和我们前面 raw 审计结论一致；
- 结构简单；
- 足够回答大多数研究问题；
- 不会把表膨胀成时间序列明细库。

### 当前不再细拆
暂时不再拆：
- `09:24:30~09:25:00`
- 秒级竞价轨迹
- 逐笔 order/trade 事件表

这些先不进主线。

---

## 5. 推荐表设计

## 5.1 `atomic_open_auction_phase_l1_daily`
定位：

> 白天真实可见视角下，竞价过程分段统计是什么样。

最小字段建议：
- `symbol`
- `trade_date`
- `auction_price`
- `auction_match_volume`
- `auction_match_amount`
- `phase_0915_0920_trade_count`
- `phase_0915_0920_trade_amount`
- `phase_0920_0925_trade_count`
- `phase_0920_0925_trade_amount`
- `phase_0925_match_trade_count`
- `phase_0925_match_trade_amount`
- `phase_0915_0920_quote_row_count`
- `phase_0920_0925_quote_row_count`
- `phase_0925_has_snapshot`
- `phase_strength_shift_label`
- `quality_info`
- `source_type`

### `phase_strength_shift_label` 建议枚举
- `early_strong_late_strong`
- `early_strong_late_weak`
- `early_weak_late_strong`
- `flat`
- `unknown`

这不是策略判断，只是过程标签。

---

## 5.2 `atomic_open_auction_phase_l2_daily`
定位：

> 盘后 L2 回补视角下，竞价过程分段统计是什么样。

最小字段建议：
- `symbol`
- `trade_date`
- `auction_trade_count_total`
- `auction_trade_amount_total`
- `phase_0915_0920_trade_count`
- `phase_0915_0920_trade_amount`
- `phase_0920_0925_trade_count`
- `phase_0920_0925_trade_amount`
- `phase_0925_match_trade_count`
- `phase_0925_match_trade_amount`
- `phase_0915_0920_add_buy_amount`
- `phase_0915_0920_add_sell_amount`
- `phase_0915_0920_cancel_buy_amount`
- `phase_0915_0920_cancel_sell_amount`
- `phase_0920_0925_add_buy_amount`
- `phase_0920_0925_add_sell_amount`
- `phase_0920_0925_cancel_buy_amount`
- `phase_0920_0925_cancel_sell_amount`
- `phase_buy_strength_shift`
- `phase_sell_pressure_shift`
- `has_exact_0925_trade`
- `has_exact_0925_order`
- `quality_info`
- `source_type`

### `phase_buy_strength_shift` / `phase_sell_pressure_shift`
建议先保存简单枚举：
- `up`
- `down`
- `flat`
- `unknown`

这样能支撑后续研究，但不提前做策略打分。

---

## 6. 为什么不是只加字段到现有 `atomic_open_auction_l1_daily / l2_daily`
可以加，但我不推荐直接把所有 phase 字段塞回原摘要表。

原因：
1. 现有摘要表负责“竞价总结果”；
2. phase 表负责“竞价过程演化”；
3. 两者语义不同；
4. 如果硬塞，表会越来越宽，后续还要再塞状态、竞价标签、校验字段。

所以我建议：
- **总摘要层保留总结果**
- **phase 层单独放过程分段**

这是可控扩展，不是无序加表。

---

## 7. 表数量是否还合理
加上这两张后，竞价相关表会变成：
- `atomic_open_auction_l1_daily`
- `atomic_open_auction_l2_daily`
- `atomic_open_auction_phase_l1_daily`
- `atomic_open_auction_phase_l2_daily`
- `atomic_open_auction_manifest`

我评估这是合理的，因为竞价层本身就天然分成：
- **总结果**
- **过程分段**
- **清单与质量**

而且这些表都还是 **symbol + trade_date** 粒度，不是秒级爆炸表。

对全市场来说，这个量是完全可控的。

---

## 8. 老数据段 / 新数据段可行性

### 8.1 老数据段（2025-01 ~ 2026-02）
基本不做 phase 层。

原因：
- 老数据段只有成交 raw；
- 很难稳定还原竞价过程；
- 做出来质量也不会高。

所以老数据段：
- 竞价层可以留空；
- 不强行补 phase。

### 8.2 新数据段（2026-03+）
是 phase 层主战场。

原因：
- 有 `行情.csv`
- 有 `逐笔成交.csv`
- 有 `逐笔委托.csv`
- 更有机会看到 `09:15~09:25` 过程演化

所以 phase 层只对新数据段做，是合理的。

---

## 9. 这层在你整体系统里的价值
### 对盯盘
未来可做：
- 盘前竞价过程观察
- 白天 L1 / 晚上 L2 对照

### 对复盘
可回答：
- 是不是前段虚强后段转弱
- 是不是最后一刻才真抢
- 是不是竞价强但盘中接不住

### 对选股
可作为：
- 前一天信号后的次日确认器
- 或过滤器

但它仍然是 **事实层**，不是策略层。

---

## 10. 当前建议执行顺序
1. 保留现有竞价摘要层设计不动；
2. 新增 phase 过程层设计；
3. 先用少量样板日做 raw 审核；
4. 如果原始文件覆盖稳定，再决定是否实现批量回补；
5. 不做逐笔竞价明细库，除非后面真的发现 phase 层不够用。

---

## 11. 当前结论
- “更细的竞价层”不是指上逐笔明细库；
- 而是指：**在现有竞价摘要层之上，再补一层 phase 过程层**；
- 这样既能满足研究，又不会让表数量和数据量失控；
- 当前主线下，这是合理且克制的做法。

补充：`2026-04-12` 当前已完成两件事：
1. phase 表已实现并接入样板 runner；
2. 已对 4 只样板票做 raw 审核（`2026-03-11`）：
   - 利通 `sh603629`
   - 中百 `sz000759`
   - 贝因美 `sz002570`
   - 粤桂 `sz000833`

审核结果：
- `auction_shape_distribution = trade+order+quote: 4`
- 4 只票都能看到：
  - `09:15~09:24:59` 的 order / quote 过程
  - `09:25` 的 trade 或 quote 边界
- 利通的 trade 更集中在 `09:25`；
- 其余 3 只在 `09:15~09:20` 也能看到零星成交。

所以当前真实结论是：
> **phase raw 覆盖已经足够，phase 层不仅能设计，而且已经具备批量回补前提。**
