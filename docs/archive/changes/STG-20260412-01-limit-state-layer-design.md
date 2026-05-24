# STG-20260412-01 涨跌停状态层设计

> 当前母卡入口：`docs/changes/MOD-20260411-14-market-data-governance-current-state.md`

## 1. 这张卡解决什么问题
当前 `atomic_trade_*` 与 `atomic_order_*` 已经能解释：
- 成交层资金强弱
- 挂单层托压变化
- 尾盘与盘中承接

但还不能稳定回答一个关键问题：

> **这些资金行为发生时，股票是不是正处在“涨停/跌停/炸板/临近板”的特殊市场状态里。**

A 股里这件事非常关键。因为：
- 普通状态下的强 `OIB/CVD`，和封板状态下的强 `OIB/CVD`，含义完全不同；
- 高位稳住、炸板回封、冲板失败，都会直接影响复盘和选股解释。

所以需要补一层：**涨跌停状态事实层**。

---

## 2. 设计目标
这层不是策略层，也不是新闻层，而是**市场状态事实层**。

它的目标是：
1. 给盯盘 / 复盘 / 选股提供“当前是否处在涨跌停特殊状态”的统一事实；
2. 让后续研究可以过滤掉“板上失真流量”；
3. 让未来的策略层能区分：
   - 隐蔽吸筹
   - 明牌冲板
   - 炸板分歧
   - 封板稳住

---

## 3. 建议落点
不改旧表，不原地侵入旧主库。

建议在**独立治理库**新增两张表：

1. `atomic_limit_state_daily`
2. `atomic_limit_state_5m`

原因：
- 语义独立，避免把状态字段和成交/挂单字段混成一锅；
- 后续要接入页面或研究层时，更容易按需 join；
- 若未来还要补“连板状态 / 异常波动 / 停牌状态”，可以继续扩同一层。

---

## 4. 推荐字段

### 4.1 `atomic_limit_state_daily`

| 字段 | 含义 |
|---|---|
| `symbol` | 股票代码 |
| `trade_date` | 交易日 |
| `board_type` | 板块类型：`sh_main` / `sz_main` / `gem` / `star` / `bse` 等 |
| `risk_flag_type` | 风险标识：`normal` / `st` / `delist_sorting` 等 |
| `prev_close` | 前收 |
| `up_limit_price` | 当日涨停价 |
| `down_limit_price` | 当日跌停价 |
| `limit_pct` | 当日适用涨跌幅比例 |
| `open_price` | 开盘价 |
| `high_price` | 最高价 |
| `low_price` | 最低价 |
| `close_price` | 收盘价 |
| `touch_limit_up` | 盘中是否触及涨停 |
| `touch_limit_down` | 盘中是否触及跌停 |
| `is_limit_up_close` | 是否涨停收盘 |
| `is_limit_down_close` | 是否跌停收盘 |
| `touch_limit_up_count_5m` | 5m 粒度触板次数汇总 |
| `touch_limit_down_count_5m` | 5m 粒度触板次数汇总 |
| `first_touch_limit_up_time` | 首次触及涨停时间 |
| `last_touch_limit_up_time` | 最后一次触及涨停时间 |
| `first_touch_limit_down_time` | 首次触及跌停时间 |
| `last_touch_limit_down_time` | 最后一次触及跌停时间 |
| `broken_limit_up` | 盘中曾涨停但收盘未封住 |
| `broken_limit_down` | 盘中曾跌停但收盘未封住 |
| `limit_state_label` | 日级状态标签：`normal` / `touched_up` / `sealed_up` / `broken_up` / `touched_down` / `sealed_down` / `broken_down` |
| `source_type` | 来源类型 |
| `quality_info` | 质量说明 |

### 4.2 `atomic_limit_state_5m`

| 字段 | 含义 |
|---|---|
| `symbol` | 股票代码 |
| `trade_date` | 交易日 |
| `bucket_start` | 5m 桶起始时间 |
| `prev_close` | 前收 |
| `up_limit_price` | 当日涨停价 |
| `down_limit_price` | 当日跌停价 |
| `limit_pct` | 当日适用涨跌幅比例 |
| `open_price` | 该 5m 开 |
| `high_price` | 该 5m 高 |
| `low_price` | 该 5m 低 |
| `close_price` | 该 5m 收 |
| `touch_limit_up` | 该 5m 是否触及涨停 |
| `touch_limit_down` | 该 5m 是否触及跌停 |
| `is_limit_up_close_5m` | 该 5m 收盘是否处于涨停价 |
| `is_limit_down_close_5m` | 该 5m 收盘是否处于跌停价 |
| `near_limit_up_ratio` | 距涨停的接近程度 |
| `near_limit_down_ratio` | 距跌停的接近程度 |
| `state_label_5m` | `normal` / `near_up` / `touch_up` / `seal_up` / `near_down` / `touch_down` / `seal_down` |
| `source_type` | 来源类型 |
| `quality_info` | 质量说明 |

---

## 5. 核心计算逻辑

### 5.1 基础思路
先确定：
1. 这只股票当天适用的涨跌幅比例 `limit_pct`
2. 由 `prev_close` 推出：
   - `up_limit_price`
   - `down_limit_price`
3. 再用当日 / 5m 的 OHLC 去判断：
   - 有没有触板
   - 是不是封住
   - 是否炸板

### 5.2 `limit_pct` 计算原则
对 `2025-01 ~ 2026-04` 这段，我们先按**可配置映射**处理，不把比例写死在逻辑里。

建议配置表：`cfg_limit_rule_map`

最小配置字段：
- `board_type`
- `risk_flag_type`
- `limit_pct`
- `effective_from`
- `effective_to`
- `note`

### 5.3 当前建议默认映射（2026-04-12 设计口径）
- 上深主板普通股：`10%`
- 主板 `ST/*ST` 风险警示股：`5%`
- 创业板普通股：`20%`
- 创业板风险警示股：`20%`
- 科创板普通股：`20%`
- 科创板风险警示股：`20%`
- 北交所普通股：`30%`

说明：
- 当前你的研究主线先聚焦上交所 / 深交所股票；
- 科创板、北交所先保留配置能力，不强行进入当前主战场；
- ST / 非 ST 必须分开，否则涨跌停判断会系统性错误。

### 5.4 价格计算
建议统一按交易规则的价格最小变动单位处理，先封装工具函数：
- `calc_up_limit(prev_close, limit_pct, tick_size)`
- `calc_down_limit(prev_close, limit_pct, tick_size)`

先按 A 股股票最常见 tick size `0.01` 处理；
后续若扩展到 ETF / 可转债 / B 股，再单独扩配置。

### 5.5 5m 触板判断
- `touch_limit_up = high_price >= up_limit_price - eps`
- `touch_limit_down = low_price <= down_limit_price + eps`
- `is_limit_up_close_5m = abs(close_price - up_limit_price) <= eps`
- `is_limit_down_close_5m = abs(close_price - down_limit_price) <= eps`

`eps` 建议先用 `0.005` 或按 tick size 做容差。

### 5.6 日级炸板判断
- `broken_limit_up = touch_limit_up = 1 and is_limit_up_close = 0`
- `broken_limit_down = touch_limit_down = 1 and is_limit_down_close = 0`

---

## 6. 数据来源与可行性

### 6.1 老数据段（2025-01 ~ 2026-02）
**可以做基础版**。

可做原因：
- 已有成交数据，能得到日级 / 5m `OHLC`；
- 只要能拿到 `prev_close`，就能计算涨跌停价；
- 即使没有真实挂单事件，也不影响涨跌停状态判断。

老数据段可支持：
- `atomic_limit_state_daily`
- `atomic_limit_state_5m`
- 但做不了“板上挂单厚度”这种更深解释。

### 6.2 新数据段（2026-03+）
**可做增强版**。

除基础版外，还能和：
- `atomic_order_*`
- `atomic_open_auction_*`

联动解释：
- 封板时的挂单强弱
- 炸板时的撤单/抛压
- 竞价直接一字 / 高开冲板等形态

---

## 7. 为什么这层现在就值得补
它有三个特点：
1. **成本低**：主要依赖 `prev_close + OHLC + 规则映射`；
2. **复用极高**：盯盘 / 复盘 / 选股都要用；
3. **解释力极强**：能明显减少“把板上行为误判成普通吸筹”的风险。

所以它不属于“以后再说”的附属项，而是：

> **当前数据治理主线里优先级很高的一层状态事实。**

---

## 8. 和当前原子层的关系
当前原子层负责：
- 成交流
- 挂单流
- 竞价摘要

涨跌停状态层负责：
- 这些流量发生时，股票处在什么市场状态里。

也就是：
- `trade/order/auction` 回答“发生了什么”
- `limit_state` 回答“发生时处在哪种板态”

它们是互补关系，不替代。

---

## 9. 本轮建议执行顺序
1. 先冻结 `cfg_limit_rule_map` 设计；
2. 先落 `atomic_limit_state_daily`；
3. 再落 `atomic_limit_state_5m`；
4. 先用利通 + 中百 + 贝因美 + 粤桂做样板验证；
5. 验证通过后，再纳入后续批量回补计划。

---

## 10. 当前结论
- 涨跌停状态层**应纳入原子事实层体系**；
- 但建议作为**独立状态子层**，不直接塞进旧表；
- 老数据能做基础版，新数据能做增强解释版；
- 这是当前数据治理主线里最值得先补的下一层。

补充：`2026-04-12` 当前已不是“待补”，而是：
- `backend/scripts/build_limit_state_from_atomic.py` 已实现；
- `backend/scripts/sql/limit_state_schema.sql` 已实现；
- 4 只样板票验证已完成：
  - 利通：`atomic_limit_state_daily=44`、`atomic_limit_state_5m=2148`
  - 中百/贝因美/粤桂：各 `29 / 1421`
- 样例核验：利通 `2026-04-08` 已识别为 `sealed_up`

所以当前真实状态是：
> **涨跌停状态层已落地、已在4只样板票验证通过。**

---

## 11. 规则来源说明（2026-04-12 校验）
本设计在 `2026-04-12` 参考了交易所公开资料，用于冻结当前默认配置方向：
- 深交所投教问答：主板普通股上市后价格涨跌幅限制 `10%`，主板风险警示股 `5%`；创业板存量股票涨跌幅限制 `20%`。
- 上交所公开规则/资料：主板普通股票价格涨跌幅限制 `10%`，`ST` 风险警示股票 `5%`，科创板股票 `20%`。

由于交易规则未来可能调整，所以：
- **实现上必须走配置表，不把比例硬编码在事实层脚本里。**
