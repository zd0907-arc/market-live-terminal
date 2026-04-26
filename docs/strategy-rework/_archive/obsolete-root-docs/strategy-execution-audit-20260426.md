# 选股策略执行链路盘点（2026-04-26）

## 1. 当前页面入口

- 页面只保留一个入口：`趋势波段策略`。
- 前端仍用内部参数 `strategy=v2` 调后端，原因只是兼容接口；业务上不要再理解成“第二版验证”，而是当前主策略。
- 旧入口 `启动确认 Top10`、`吸筹前置 Top10` 已从页面下拉框删除；后端旧接口暂未删除，避免影响历史代码。

## 2. 当前策略目标

不是“稳定把利通电子打进 Top10”，而是：

1. 给定任意历史交易日；
2. 从当日全市场可计算股票里筛出 Top10 候选；
3. 对每只候选模拟：次日开盘买入，之后逐日识别持有/洗盘/出货/止损/到期；
4. 输出每笔交易的入场日、出场信号日、实际出场日、收益率；
5. 用胜率、平均收益、盈亏比、最大回撤等结果反推参数。

## 3. 底层数据源

### 3.1 原子行情库

路径：`/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_full_reverse.db`

#### `atomic_trade_daily`

业务含义：每天每只股票的 L1/L2 成交结果汇总，是当前策略最核心的数据。

当前覆盖：

- 日期：`2025-01-02` ~ `2026-04-24`
- 总行数：约 100 万
- 股票数：约 3222
- 典型交易日覆盖：约 3180 只股票/日

主要字段含义：

| 字段 | 业务含义 | 策略用途 |
|---|---|---|
| `open/high/low/close` | 当日开高低收 | 算涨跌、突破、买入/卖出模拟价格 |
| `total_amount` | 当日成交额 | 流动性门槛、放量程度 |
| `total_volume` | 成交量 | 辅助量能判断 |
| `trade_count` | 成交笔数 | 成交活跃度，识别突然活跃 |
| `l1_main_net_amount` | L1 口径主力净流入 | 只作参考，L1 是估算口径 |
| `l2_main_net_amount` | L2 口径主力净流入 | 判断资金是否真实进入 |
| `l1_super_net_amount` | L1 超大单净流入 | 参考 |
| `l2_super_net_amount` | L2 超大单净流入 | 判断大资金攻击性 |
| `l2_buy_ratio/l2_sell_ratio` | L2 主动买/卖强度 | 判断主动买盘是否压过主动卖盘 |
| `positive_l2_net_bar_count/negative_l2_net_bar_count` | 分钟/切片级 L2 净流入为正/负的次数 | 判断资金流入是否持续，而不是单点脉冲 |

#### `atomic_order_daily`

业务含义：每天每只股票的 L2 挂单/撤单结果汇总，用来识别托单、压单、撤单、承接、派发。

当前覆盖：

- 日期：`2026-03-02` ~ `2026-04-24`
- 总行数：约 11.8 万
- 股票数：约 3195
- 重要限制：`2026-03-02` 以前没有挂单数据，所以 1 月、2 月的回测只能用成交资金，不能完整验证挂单/撤单行为。

主要字段含义：

| 字段 | 业务含义 | 策略用途 |
|---|---|---|
| `add_buy_amount` | 新增买挂单金额 | 看买盘支撑是否增强 |
| `add_sell_amount` | 新增卖挂单金额 | 看上方压单/派发压力 |
| `cancel_buy_amount` | 撤买单金额 | 高时可能代表下方支撑撤退 |
| `cancel_sell_amount` | 撤卖单金额 | 高时可能代表压单撤走、上攻阻力减轻 |
| `cvd_delta_amount` | 成交主动净额变化 | 判断主动成交方向 |
| `oib_delta_amount` | 订单簿不平衡变化 | 判断挂单结构偏买还是偏卖 |
| `buy_support_ratio` | 买盘支撑比例 | 承接/托盘强弱 |
| `sell_pressure_ratio` | 卖盘压力比例 | 压盘/出货压力 |
| `order_event_count` | 挂单事件数 | 挂单数据活跃度 |

### 3.2 主库 / 新闻公司研究数据

路径：`/Users/dong/Desktop/AIGC/market-data/market_data.db`

当前与策略相关的表：

| 表 | 业务含义 | 当前状态 | 影响 |
|---|---|---|---|
| `history_daily_l2` | 较旧的日线 L2 汇总 | 有约 15 万行 | 主要被历史复盘图使用，不是 V2 主计算入口 |
| `local_history` | 老资金流历史 | 有约 142 万行 | 旧策略使用较多，V2 暂不作为主入口 |
| `stock_events` | 公告/新闻/问答等事件明细 | 当前为空 | Layer2 公司解释层还没有真正接上 |
| `stock_event_daily_rollup` | 每日事件聚合 | 当前为空 | 无法做“当天为什么涨停”的事件解释 |
| `stock_universe_meta` | 股票名称、市值、元信息 | 当前为空 | 目前无法严格执行 50亿~500亿市值过滤 |
| `sentiment_events` | 评论/舆情原始事件 | 有约 5.7 万行 | 后续可用于热度/分歧解释 |
| `sentiment_daily_scores` | 舆情日评分 | 只有 4 行 | 当前不可作为稳定量化因子 |

结论：现在 Layer1/Layer3 能跑，Layer2 公司/新闻解释层还很薄；市值过滤也因为元数据缺失没有真正落地。

## 4. 当前计算流程

### 4.1 候选筛选

入口：`get_candidates_v2_api(date, limit=10)`

实际执行：

1. 后端不会只拿前 10 只股票算。
2. 它会先从 `atomic_trade_daily` 读取目标日前 90 天到目标日的全市场数据。
3. 如果不指定股票，覆盖当日 `atomic_trade_daily` 里所有股票，典型约 3180 只。
4. 先内部筛出最多 120 只候选，再按生命周期分数排序，最后返回页面 Top10。

这一点已经修过：不是“只从前 10 里再算排序”。

### 4.2 基础衍生指标

| 指标 | 公式 | 业务含义 |
|---|---|---|
| `return_1d_pct` | `close / prev_close - 1` | 当日涨跌幅 |
| `return_20d_pct` | `close / close_20d_ago - 1` | 最近 20 日涨幅，判断是否过热 |
| `amount_anomaly_20d` | `total_amount / 20日平均成交额` | 放量程度，>1 代表比平时活跃 |
| `trade_count_anomaly_20d` | `trade_count / 20日平均成交笔数` | 成交笔数是否异常增加 |
| `breakout_vs_prev20_high_pct` | `close / 昨日前20日最高收盘 - 1` | 是否突破近期平台 |
| `l2_main_net_ratio` | `l2_main_net_amount / total_amount` | L2 主力净流入占成交额比例 |
| `l2_super_net_ratio` | `l2_super_net_amount / total_amount` | L2 超大单净流入占成交额比例 |
| `active_buy_strength` | `l2_buy_ratio - l2_sell_ratio` | 主动买是否强于主动卖 |
| `positive_l2_bar_ratio` | `正净流入切片数 / 正负切片总数` | 资金流入是否持续 |
| `support_pressure_spread` | `buy_support_ratio - sell_pressure_ratio` | 下方承接与上方压力的差值 |
| `order_imbalance_ratio` | `oib_delta_amount / total_amount` | 挂单结构偏买还是偏卖 |
| `cvd_ratio` | `cvd_delta_amount / total_amount` | 主动成交方向偏买还是偏卖 |
| `cancel_buy_ratio` | `cancel_buy_amount / total_amount` | 买盘支撑撤退程度 |
| `add_sell_ratio` | `add_sell_amount / total_amount` | 卖压新增程度 |

### 4.3 五个意图分数

这些不是最终买卖结论，而是把“当日行为”量化。

| 分数 | 业务含义 | 主要看什么 |
|---|---|---|
| `accumulation_score` 吸筹分 | 主力是否在低调持续拿货 | 5日 L2 主力净流入、L2 正流入持续性、买盘支撑、挂单不平衡、CVD |
| `attack_score` 攻击分 | 是否在放量突破/主动进攻 | 涨幅、放量、突破、主动买强度、L2 主力/超大单净流入 |
| `distribution_score` 出货分 | 是否资金撤退/卖压增强 | L2 主力流出、主动卖强、买盘撤退、新增卖压、OIB/CVD 转弱 |
| `washout_score` 洗盘分 | 急跌是否更像洗盘而非崩盘 | 跌幅、放量、资金是否还在、承接是否存在、卖单撤单 |
| `repair_score` 修复分 | 急跌后是否被资金快速修复 | 前3日急跌、当日 L2 主力回补、主动买、承接、放量修复 |

### 4.4 当前入场参数

| 参数 | 当前值 | 业务含义 | 调高/调低影响 |
|---|---:|---|---|
| `attack_score_min` | 65 | 攻击分达到多少才认为启动/跟进有效 | 调高会少买、更稳；调低会多买、噪音变大 |
| `repair_score_min` | 60 | 洗盘修复分达到多少才允许识别为修复进场 | 调高会错过低吸修复；调低容易接飞刀 |
| `entry_attack_cvd_floor` | -0.08 | 攻击信号下，CVD 最低不能太差 | 调高更严格，过滤拉高出货；调低更激进 |
| `entry_return_20d_cap` | 80% | 20日涨幅超过多少禁止追 | 调低更防高位接盘；调高更敢追妖股 |
| `min_amount` | 3亿 | 当日最低成交额 | 调高过滤冷门票；调低扩大范围但滑点和噪音更大 |

### 4.5 当前出场参数

| 参数 | 当前值 | 业务含义 | 调高/调低影响 |
|---|---:|---|---|
| `distribution_score_warn` | 70 | 出货分达到多少开始出货预警 | 调高更能拿住；调低更容易提前跑 |
| `panic_distribution_score_exit` | 80 | 强出货/恐慌派发直接退出阈值 | 调高减少误杀；调低更保守 |
| `distribution_confirm_days` | 2 | 连续几天出货预警才确认出场 | 调高更能忍洗盘；调低更快止盈/止损 |
| `stop_loss_pct` | -8% | 从买入价回撤多少止损 | 调低绝对值更快止损；调高绝对值更能扛波动 |
| `max_holding_days` | 40 | 最长持有交易日 | 调高更偏趋势；调低更偏短波段 |

## 5. 当前策略版本的已知大问题

1. **市值范围没有真正过滤**：你的目标是 50亿~500亿中小票，但 `stock_universe_meta` 为空，当前只能靠成交额间接过滤。
2. **2026-03-02 以前缺挂单数据**：利通 1 月启动段无法用 `atomic_order_daily` 验证托单/撤单，只能看 L2 成交资金。
3. **Layer2 公司/新闻解释未闭环**：`stock_events` 和事件聚合为空，当前页面不能稳定回答“为什么涨停、是不是基本面重估”。
4. **当前回测是信号级，不是组合级**：会记录每天 Top10 里每只票的模拟交易；暂时没有资金占用、同票重复持仓、仓位管理，这符合当前阶段要求，但不能直接等同实盘账户收益。
5. **参数还没系统寻优**：目前只是利通案例导向的一版参数，最近小范围回测收益不理想，下一步必须做参数网格/版本对比。

## 6. 下一步优化策略时优先调什么

不建议每个底层指标都一起调。先抓 8 个主旋钮：

1. `attack_score_min`：决定启动信号门槛。
2. `repair_score_min`：决定洗盘修复能不能低吸。
3. `entry_return_20d_cap`：决定是否追高。
4. `entry_attack_cvd_floor`：过滤拉高但主动成交不强的票。
5. `distribution_score_warn`：决定出货预警灵敏度。
6. `panic_distribution_score_exit`：决定强出货退出灵敏度。
7. `distribution_confirm_days`：决定出场确认速度。
8. `stop_loss_pct` / `max_holding_days`：控制亏损和策略周期。

策略方向可以后续拆成多个版本：

| 策略方向 | 参数倾向 | 适合场景 |
|---|---|---|
| 稳健入场 | 提高攻击/修复门槛，降低追高上限 | 少买、降低误入场 |
| 趋势高收益 | 放宽追高上限，提高出货确认天数 | 抓利通这类大波段，但回撤更大 |
| 洗盘低吸 | 提高修复识别权重，降低启动追击权重 | 吃启动后的回踩修复 |
| 快进快出 | 降低出货预警阈值，缩短最大持有 | 防游资一日/数日行情回落 |

