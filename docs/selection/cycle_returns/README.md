# 牛市区间涨幅水位

## 定位

这张表不是买入信号，而是单票研究的基础水位尺。

核心问题：一只股票从本轮牛市启动前到现在，已经涨到什么位置；它在全市场里是普通上涨、强势、极高水位，还是低位补涨。

## 当前主口径

- 主基准：`2024-08` 全月前复权收盘均价。
- 最新价：指定交易日收盘价，当前已生成 `2026-04-30`。
- 牛市启动事件日：`2024-09-24`，只记录价格，不作为主涨幅口径。
- 贸易战回调低点：`2025-04-07`。
- 复权：默认使用东方财富前复权日线，避免送转分红扭曲长期涨幅。

## 数据表

表：`market-data/research/current/selection/selection_research.db::stock_cycle_return_daily`

关键字段：

| 字段 | 含义 |
| --- | --- |
| `baseline_avg_close` | 2024 年 8 月前复权均价。 |
| `return_from_baseline_avg_pct` | 从 2024 年 8 月均价到当前的涨幅。 |
| `policy_start_close` | 2024-09-24 收盘价，仅作为事件节点。 |
| `return_from_policy_start_pct` | 从 2024-09-24 到当前涨幅。 |
| `crash_low_close` | 2025-04-07 收盘价。 |
| `return_from_crash_low_pct` | 从 2025-04-07 到当前涨幅。 |
| `return_ytd_pct` | 年初至当前涨幅。 |
| `max_return_since_baseline_pct` | 从 2024 年 8 月以来按最高收盘价算的最大涨幅。 |
| `drawdown_from_cycle_high_pct` | 当前价相对本轮最高收盘价的回撤。 |
| `market_percentile_from_baseline` | 牛市涨幅在全市场的分位。 |

## 生成脚本

```bash
python3 backend/scripts/build_cycle_return_snapshot.py --as-of-date 2026-04-30 --workers 12
```

单票验证：

```bash
python3 backend/scripts/build_cycle_return_snapshot.py \
  --as-of-date 2026-04-30 \
  --symbols sz001309,sh603629,sz301308 \
  --workers 3
```

默认读取 `RESEARCH_CURRENT_ROOT/selection/selection_research.db`；repo 内 `data/selection/selection_research.db` 只按回退副本理解。

## 当前 2026-04-30 快照

- 处理股票：`5528`
- 已有 2024-08 基准：`5006`
- 无 2024-08 基准：`145`
- 停牌或当日无精确价格但有前值：`89`
- 无 K 线：`288`

按 2024 年 8 月均价至 2026-04-30：

| 水位 | 数量 |
| --- | ---: |
| 涨幅 >= 100% | 1584 |
| 涨幅 >= 300% | 316 |
| 涨幅 >= 500% | 111 |
| 涨幅 >= 900% | 22 |

## 使用规则

单票研究时先看水位，再看基本面。

| 状态 | 含义 |
| --- | --- |
| 牛市涨幅极高且继续新高 | 只能按强趋势和强业绩验证处理，不能当低估票。 |
| 牛市涨幅高但资金转负 | 优先警惕业绩兑现后的派发。 |
| 牛市涨幅低、行业强、资金转强 | 可能是补涨或二波修复候选。 |
| 牛市涨幅低但行业弱 | 不等于便宜，可能是市场长期不认可。 |
