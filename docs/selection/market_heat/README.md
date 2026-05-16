# 小主题热点研究总览

## 当前结论

热点数据有用，但不能直接当买点。当前页面已经收口为“市场主线情报看板”，旧版近 3 个月趋势、最近每日热门板块、热点排行和旧详情区已移除。

当前最有价值的用法有两类：

1. 用小颗粒主题判断市场资金正在交易什么，给个股研究提供背景。
2. 在主线板块内快速查看成分股最近 K 线、5/10 日均线、20 日位置、量能和 L2 方向，辅助判断是否值得继续研究。
3. 从热点样本里反推“哪些形态未来 20 日有冲高”，再用 L2 和卖点规则做交易验证。

## 已落地数据

- 小主题日度热度：`/Users/dong/Desktop/AIGC/market-data/market_heat/fine_theme_heat_daily.db`
- 个股 L1/L2 底座：`/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_full_reverse.db`
- 当前细颗粒看板缓存：`/Users/dong/Desktop/AIGC/market-data/market_heat/cache/fine_heat_snapshots_*_m5_80.json`
- 热点大涨样本：`/Users/dong/Desktop/AIGC/market-live-terminal/data/selection/market_heat/backtests/hot_theme_big_mover_l2_precondition_events.csv`
- 板块口径管理：`docs/selection/market_heat/theme_taxonomy_management.md`
- 本轮板块审计：`docs/selection/market_heat/theme_taxonomy_audit_2026-05-10.md`
- 主线看板发布说明：`docs/changes/REL-20260512-v5.1.4-market-heat-mainline-dashboard.md`

## 当前页面能力

### 1. 市场主线情报看板

页面只保留顶部主线看板，左侧 6 个池子，右侧为选中板块详情和成分股卡片。

6 个池子：

| 池子 | 口径 |
|---|---|
| 今日最强 | 今日热度排名 Top5，只表示当天最强，不判断新旧 |
| 首次新热 | 今日进入 Top15；过去 20 日进 Top30 不超过 2 次、进 Top15 不超过 1 次、未进 Top5；且近 5 日热度或排名明显抬升 |
| 主线再加速 | 今日进入 Top10；近 20 日已反复活跃，满足 Top30 >=6 次、Top15 >=3 次或 Top5 >=2 次 |
| 持续升温 | 今日位于 Top6~Top30；尚未满足成熟主线条件；近 5 日热度或排名明显抬升 |
| 持续主线 | 今日仍在 Top30；近 20 日反复进入 Top30/Top15/Top5 |
| 退潮观察 | 今日跌出 Top30；过去 20 日曾活跃；且近期从前排明显掉队 |

排名阈值含义：

```text
Top5  = 当日最强
Top10 = 前排强热点
Top15 = 热区
Top30 = 观察边界，不直接等同强热点
```

回测复核显示，Top30 仍有正收益统计意义，但强度明显弱于 Top10/Top15，因此页面只把 Top30 用作观察边界。

### 2. 成分股微型 K 线卡片

选中板块后，右侧成分股卡片展示：

- 股票名称、当日涨跌幅。
- 20 日位置、5 日收益、量能倍数、L2 方向。
- 最近 30 个交易日微型 K 线，叠加 MA5/MA10。
- 点击成分股后，左侧 6 池区域临时切换为单票详情，复用现有复盘详情页；关闭后回到 6 池。

### 3. 日期与刷新

- `查询`：按选中交易日读取对应细颗粒热点缓存。
- `刷新最新数据`：按最新交易日重建最近 63 个交易日的细颗粒热点快照缓存。
- 日期选择器标记：
  - 绿色线：该交易日已有热点缓存。
  - 黄色点：底层交易数据存在，但热点缓存未生成。

当前 2026-05-11 抽样：

```text
今日最强：集成电路封测、先进封装、半导体、华为海思、半导体材料
首次新热：中芯概念、IGBT概念
主线再加速：先进封装、玻璃基板、数字芯片设计、半导体、集成电路封测等
退潮观察：航天航空、减速器、航天装备、纺织服装设备、机器人执行器等
```

## 当前接口

```text
GET  /api/market_heat/fine_dashboard
POST /api/market_heat/fine_dashboard/refresh
GET  /api/market_heat/fine_dates
GET  /api/market_heat/fine_theme_stock_detail
```

接口说明：

- `fine_dashboard`：读取细颗粒热点缓存，生成 6 池生命周期看板。
- `fine_dashboard/refresh`：重建最近 N 个交易日细颗粒热点快照。
- `fine_dates`：返回可查询交易日及缓存状态。
- `fine_theme_stock_detail`：返回单个细颗粒主题的成分股、微型 K 线和排序辅助字段。

## 关键研究结论

### 1. 纯热点不能买

细颗粒热点能提高未来强股覆盖率，但热点池内部后排票太多，直接买 Alpha 不稳定。

### 2. L2 单因子不能定买点

近 3/5/10/20 日主力或超大单净流入，与未来收益没有稳定线性关系。当前较有解释价值的是：

```text
近5日超大单净流入 / 近5日成交额
```

它更像“未来几天有没有冲高”的辅助变量，不是独立买入信号。

### 3. 强者恒强能筛出后20日冲高样本

当前最有效的冲高筛选规则：

```text
热点日涨幅 >= 7%
热点前20日已涨 > 20%
热点前5日超大单占成交额 > 2%
主题成交放大 >= 1.5
```

历史表现：

```text
全样本后20日最高 >=20%：18.7%
强者恒强规则后20日最高 >=20%：55.9%
```

这个规则适合找“未来有冲高概率”的票，但买点已经偏右侧，必须配合卖点。

### 4. 卖点比继续持有更重要

2025 年单账户 100 万实盘约束回测：

| 策略 | 最终资金 | 总收益 | 交易数 | 胜率 | 最大单笔亏损 |
|---|---:|---:|---:|---:|---:|
| +10% 半仓止盈，剩余按回撤/L2/时间退出 | 124.20万 | +24.2% | 9 | 77.8% | -14.7% |
| 去掉半仓，原规则全仓卖出 | 101.89万 | +1.9% | 9 | 55.6% | -14.7% |
| 固定持有20日 | 85.85万 | -14.2% | 5 | 40.0% | -29.7% |

当前判断：

```text
+10% 半仓止盈是策略收益核心，不是可有可无的风控动作。
固定持有 20 日最差，因为强者恒强样本的真实高点来得很快，后面容易回吐。
```

## 核心文件

- 冲高筛选规则：`docs/selection/market_heat/backtests/hot_theme_fwd20_screen_rules.md`
- 强者恒强样本页：`docs/selection/market_heat/backtests/hot_theme_strong_momentum_l2_cases.html`
- 卖点复盘：`docs/selection/market_heat/backtests/hot_theme_strong_momentum_sell_points.md`
- 100万单账户回测：`docs/selection/market_heat/backtests/strong_momentum_portfolio_2025.md`
- 去掉分批止盈对比：`docs/selection/market_heat/backtests/strong_momentum_exit_compare_2025.md`
- L2 资金相关性：`docs/selection/market_heat/backtests/l2_flow_forward_return_correlation.md`

## 当前使用边界

- 不能把热点排名直接等同于买入信号。
- 强者恒强规则可以作为“追强候选池”，但不是稳定自动交易系统。
- 买入后必须按交易规则执行，尤其是第一止盈和回撤退出。
- 后续需要继续测多仓位版本、不同市场阶段、不同板块生命周期。
