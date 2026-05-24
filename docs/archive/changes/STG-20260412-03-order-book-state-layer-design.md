# STG-20260412-03 盘口存量快照层设计

> 当前母卡入口：`docs/changes/MOD-20260411-14-market-data-governance-current-state.md`
> 相关前置：`STG-20260411-16-atomic-p1-enhancement-design.md`

## 1. 这张卡解决什么问题
当前我们已经有：
- 成交层：`atomic_trade_*`
- 挂单流量层：`atomic_order_*`
- 竞价摘要与 phase 层
- 涨跌停状态层设计

但还缺一个很关键的视角：

> **到某个时点，盘口上还“剩着”多少买盘 / 卖盘。**

也就是：
- 现在买盘托单厚不厚；
- 现在卖盘压单重不重；
- 主力是“边撤边骗”，还是“真把盘面托住了”；
- 一只票为什么能高位稳住，而不是拉完就掉。

这类问题，单看流量不够，需要补一层：

## 盘口存量快照层（Order Book State Layer）

---

## 2. 当前结论（已更新）
这层已经进入主线实现，但当前只落**基础版**：

### 已实现
- `atomic_book_state_5m`
- `atomic_book_state_daily`
- 来源：`行情.csv`
- 落点：独立治理库
- 接入：`run_symbol_atomic_validation.py`

### 当前基础版口径
- `5m` 取 **该 bucket 内最后一个盘口快照**
- `end_*_resting_volume`
  - 优先用 `叫买总量 / 叫卖总量`
  - 若缺失，则 fallback 为十档量求和
- `end_*_resting_amount`
  - 当前先按**十档金额和**落值
- `top1/top5` 金额和量同步保留
- `book_imbalance_ratio / book_depth_ratio / book_state_label` 同步产出

### 仍未完全锁死的点
- `end_*_resting_amount` 现在是“十档金额”，不代表绝对全盘口金额；
- 价格/量单位虽然抽样看起来可直接使用，但仍需要在 Windows 样板库继续核对；
- 后续若发现 `行情.csv` 还有更稳定的盘口总额口径，再升级，不改旧表语义。

---

## 3. 这层到底是什么

### 3.1 当前 `atomic_order_*` 是什么
当前 `atomic_order_*` 记录的是：
- 新增挂单多少
- 撤单多少
- OIB / CVD 怎么变

这是一层**流量（flow / delta）事实**。

### 3.2 存量快照是什么
存量快照记录的是：

> 在某个时点，盘口上还挂着多少买单 / 卖单。

也就是**状态（state / snapshot）事实**。

### 3.3 为什么这两者不能混
因为：
- 流量回答“这段时间发生了什么”
- 存量回答“现在盘面长什么样”

两者都重要，但语义完全不同。

---

## 4. 这层为什么重要
它主要解决 3 类高价值问题：

### 4.1 高位稳住
为什么有些票涨上去后，能横着不掉？
- 可能不是继续大笔流入；
- 而是盘口买盘一直很厚，承接持续存在。

### 4.2 假强与真强
有些票看起来：
- 挂单流量很强；
- 但盘口实际上很薄；
- 一砸就掉。

另一些票：
- 流量没那么夸张；
- 但盘口长期厚实；
- 更像真承接。

### 4.3 主力托而不拉 / 压而不砸
主力很多时候不会直接大买大卖，
而是通过：
- 盘口托单
- 盘口压单
- 撤单配合

来控制市场预期。

这层对研究这类行为尤其关键。

---

## 5. 建议落点
建议新增两张表：

1. `atomic_book_state_5m`
2. `atomic_book_state_daily`

不建议塞进：
- `atomic_order_5m`
- `atomic_order_daily`

原因：
- `order_*` 是流量层；
- `book_state_*` 是状态层；
- 拆开后逻辑清晰，后续不会互相污染。

---

## 6. 推荐字段

## 6.1 `atomic_book_state_5m`
按 `symbol + bucket_start` 一行，记录该 5m 结束时盘口状态。

建议最小字段：
- `symbol`
- `trade_date`
- `bucket_start`
- `end_bid_resting_volume`
- `end_ask_resting_volume`
- `end_bid_resting_amount`
- `end_ask_resting_amount`
- `top1_bid_volume`
- `top1_ask_volume`
- `top5_bid_volume`
- `top5_ask_volume`
- `top1_bid_amount`
- `top1_ask_amount`
- `top5_bid_amount`
- `top5_ask_amount`
- `book_imbalance_ratio`
- `book_depth_ratio`
- `book_state_label`
- `source_type`
- `quality_info`

### 指标解释
- `book_imbalance_ratio`
  - 衡量买卖盘不平衡程度
- `book_depth_ratio`
  - 衡量盘口整体厚度
- `book_state_label`
  - 简单标签：`balanced` / `bid_dominant` / `ask_dominant` / `thin` / `unknown`

---

## 6.2 `atomic_book_state_daily`
按 `symbol + trade_date` 一行，记录当天盘口状态的日级摘要。

建议最小字段：
- `symbol`
- `trade_date`
- `avg_bid_resting_amount`
- `avg_ask_resting_amount`
- `avg_book_imbalance_ratio`
- `avg_book_depth_ratio`
- `max_bid_resting_amount`
- `max_ask_resting_amount`
- `close_bid_resting_amount`
- `close_ask_resting_amount`
- `close_book_imbalance_ratio`
- `bid_dominant_bar_count`
- `ask_dominant_bar_count`
- `thin_book_bar_count`
- `source_type`
- `quality_info`

这张表不是为了精细还原盘口，而是为了：
- 给日级复盘 / 日级研究提供盘口状态摘要。

---

## 7. 为什么当时没有直接承诺、现在又进入实现
因为关键一直都不在“想不想做”，而在 raw 可行性。

### 7.1 如果 raw 里有盘口快照
比如 `行情.csv` 真有：
- 买一到买五价量
- 卖一到卖五价量
- 且频率稳定

那这层可以做，而且价值很高。

### 7.2 如果 raw 里没有稳定盘口快照
只靠：
- 逐笔委托
- 逐笔成交

去重建“某时刻盘口还剩多少挂单”，会遇到很多问题：
- 中间快照缺失
- 撮合/撤单时序误差
- order id 对齐不完整
- 很难保证状态是真的“当时留存量”而不是估出来的幻觉

现在这一步已经完成到：

> **raw 已确认存在稳定盘口十档字段，因此基础版可以先落。**

---

## 8. 老数据段 / 新数据段可行性（保持不变）

### 8.1 老数据段（2025-01 ~ 2026-02）
基本不可做。

原因：
- 只有成交 raw；
- 没有足够盘口状态信息；
- 无法可靠重建盘口留存量。

### 8.2 新数据段（2026-03+）
有可能做，但必须看 `行情.csv` 具体覆盖。

所以：
- 这层如果要落，只服务新数据段；
- 不强行要求老数据段补齐。

---

## 9. 这层和当前系统的关系
### 对盯盘
未来可增强：
- 看当前盘口是托单更强还是压单更强
- 看盘面是否越来越薄

### 对复盘
能回答：
- 为什么某票高位稳住
- 为什么某票炸板后还能回封
- 为什么某票看着强，结果一砸就散

### 对选股
未来可以增强：
- 把“盘口承接稳定”作为趋势持有确认
- 把“盘口持续变薄”作为风险提示

但当前仍然是：
- **事实层能力预研**
- 不是马上进策略层

---

## 10. 当前执行结果
已完成：
1. 抽 raw 样本确认 `行情.csv` 存在盘口十档与总量字段；
2. 新增 `book_state_schema.sql`；
3. 新增 `build_book_state_from_raw.py`；
4. 已接入 `run_symbol_atomic_validation.py`；
5. 已补单测，验证：
   - `15:00` 快照归到 `14:55` bucket；
   - `5m + daily` 可正常落表。

下一步只剩：
1. 已同步到 Windows 并重跑 4 只样板：
   - 利通 `sh603629`
   - 中百 `sz000759`
   - 贝因美 `sz002570`
   - 粤桂 `sz000833`
2. 当前样板结论：
   - 4 只票全部成功；
   - `book_state_daily` 条数均与新数据交易日对齐；
   - `limit_state` 也已在新验证库内同步重建。
3. 剩余问题：
   - 继续核对 `resting_amount=十档金额和` 对复盘是否足够；
   - 再决定是否直接进入批量回补。

---

## 11. 4只样板票 raw 审核结果（2026-04-12）
已对 `2026-03-11` 的 4 只样板票执行盘口快照 raw 审核：
- 利通 `sh603629`
- 中百 `sz000759`
- 贝因美 `sz002570`
- 粤桂 `sz000833`

使用脚本：
- `backend/scripts/audit_book_snapshot_raw.py`

审核结果：
- `support_distribution = sufficient_for_book_state_basic: 4`
- 4 只票全部具备：
  - 十档盘口列齐全；
  - `叫买总量 / 叫卖总量` 字段存在；
  - 连续竞价阶段大多数快照盘口非零；
  - `14:55 ~ 15:00` 存在稳定收盘快照。

补充观察：
- 粤桂在 `2026-03-11` 的卖一/卖五非零行数明显少于买盘，但十档和总量字段仍然存在，因此当前判断仍是：
  - **足够支撑基础版 book state**
  - 但后续做更强盘口解释时，要关注“某边长期稀薄”这种市场特征，而不是误判成原始缺失。

所以当前真实结论是：
> **盘口快照 raw 已足够支撑 `atomic_book_state_*` 基础版进入批量回补。**

---

## 11. 当前结论
- 盘口存量快照层非常有价值；
- 但它是当前三项里**最依赖 raw 能力**的一层；
- 所以现在最合理的处理方式是：
  - **正式纳入总设计**
  - **先不承诺立即实现**
  - **待 raw 审核通过后再进入主线开发**
