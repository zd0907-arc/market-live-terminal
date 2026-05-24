# REQ-20260429-04 热门主题领先性验证

## 目标

验证一个实战假设：

```text
D 日收盘识别出的热门主题，是否能显著提高 D+1 之后全市场强股的命中概率。
```

如果验证成立，后续买票原则是：

```text
策略信号 = 买点触发
热门主题 = 优先级/仓位放大器
```

不把“板块热”单独作为买入触发器。

## 核心验证口径

以每个交易日 D 为截面：

1. D 日收盘后计算交易主题热度。
2. 取热门主题 TopK，例如 Top5。
3. 从 D+1 开盘到 D+N 收盘，统计全市场未来涨幅 TopN 股票。
4. 判断这些未来强股在 D 日是否属于热门主题。

## 细颗粒热点层

18 个交易主题适合给人理解市场主线，但颗粒度太粗，Top3 会覆盖过多股票。
策略过滤/提权要使用更细的热点层：

```text
clean_sector_hotspot = 清洗后的细概念/细行业板块
```

第一版规则：

```text
成员数 5~80
排除指数、融资融券、持仓、市值风格、昨日涨停、财报、地域、破净破发等标签
保留 CPO、液冷、低空经济、商业航天、稀土永磁、固态电池等细概念
```

验证目标：

```text
细颗粒 Top15 热点池 Coverage 约 5%~10%
同时保持 Recall / Lift 明显高于随机基准
```

对应脚本：

```text
backend/scripts/analyze_hot_sector_granularity.py
```

验证周期：

```text
D+1：次日溢价
D+3：短线题材发酵
D+5：短线/波段过渡
D+10：持续主线
```

## 指标

### 1. Coverage

热门主题覆盖了全市场可交易股票的比例：

```text
hot_theme_coverage = 热门主题股票数 / 全市场可交易股票数
```

### 2. Recall

未来强股里有多少来自 D 日热门主题：

```text
winner_recall = 未来 TopN 强股中命中热门主题的数量 / 未来 TopN 强股数量
```

### 3. Lift

消除大板块天然覆盖股票多带来的偏差：

```text
lift = winner_recall / hot_theme_coverage
```

如果 lift 明显大于 1，说明热门主题对未来强股有解释力。

### 4. Precision / Expected Return

不能只看未来强股是否来自热门主题，还要看热门主题整体是否赚钱：

```text
hot_theme_avg_return
hot_theme_win_rate
market_avg_return
market_win_rate
hot_theme_alpha = hot_theme_avg_return - market_avg_return
```

只有同时满足：

```text
lift > 1
hot_theme_alpha > 0
hot_theme_win_rate > market_win_rate
```

热门主题才适合作为策略信号的加分项。

## 可交易性过滤

为避免 A 股回测幻觉，Winner 池和收益池要过滤：

```text
剔除 D 日成交额 < 3000 万
剔除 ST / *ST
剔除上市或本地历史不足 60 个交易日
剔除 D+1 一字涨停开盘买不到的股票
```

一字涨停优先使用：

```text
atomic_limit_state_daily.up_limit_price
```

没有涨停价时，用近似判断：

```text
D+1 open / D close >= 1.095
```

同时报告：

```text
unbuyable_limit_up_ratio
```

用于观察热点强股里有多少其实买不到。

## 热度阶段

同样是热门主题，要区分：

```text
new_hot：首次进入 TopK
continuing_hot：连续 2~3 天进入 TopK
climax_hot：连续 4 天以上进入 TopK
```

额外记录：

```text
hot_acceleration = 今日 hot_score - 昨日 hot_score
```

重点验证：

```text
new_hot 是否比 climax_hot 更适合进场。
```

实际实现不能只用“绝对连续上榜”，因为 A 股主线经常有分歧日。第一版采用滑动窗口：

```text
过去 5 个交易日内进入 TopK：
  1 次：new_hot
  2~3 次：continuing_hot
  4 次以上：climax_hot
```

这样能保留“分歧后回流”的主线，不会因为中间一天掉出 TopK 就重置。

## 多标签污染控制

A 股概念标签高度重叠，一只股票可能同时属于多个主题。判断“命中热门主题”时，不能只看静态标签。

增加日内共振约束：

```text
股票 D 日涨幅 > 0
且 股票 D 日涨跌方向与该热门主题 D 日涨跌方向一致
```

严格模式下，只有满足共振约束，才算真正命中热门主题。
宽松模式下，仍保留静态标签命中，用于对照。

## 热门主题内 L2 过滤

热门主题覆盖强股不等于板块内所有股票都能买。后续验证：

```text
热门主题 TopK
+ 板块内 L2 主力净流入/活跃度 Top 分位
```

但要避免误杀缩量龙头：

```text
如果 D 日收盘封死涨停，则不要求 L2 净流入分位，直接视为强势核心。
否则要求板块内 L2 主力净流入分位进入 Top 10% / Top 20%。
```

细颗粒板块有微小样本问题，Top 分位必须有保底：

```text
板块内保留数量 = max(1, floor(N * top_pct))
```

例如一个细板块只有 5 只股票，Top20% 至少保留资金最强的 1 只。

涨停豁免必须严格使用“收盘封死涨停”：

```text
is_limit_up_close = 1 才豁免 L2
盘中触板但收盘炸板，不豁免，必须接受 L2 过滤
```

这条规则用于“排雷不杀牛”：

```text
保留缩量封板真龙
过滤缩量跟风杂毛
避免只买到爆量烂板后排
```

## 输出报告

脚本：

```text
backend/scripts/analyze_hot_theme_winner_lead_lag.py
```

输出：

```text
/Users/dong/Desktop/AIGC/market-data/market_heat/hot_theme_winner_lead_lag_*.json
/Users/dong/Desktop/AIGC/market-data/market_heat/hot_theme_winner_lead_lag_*.md
```

报告包含：

```text
1. 不同 horizon 的 Coverage / Recall / Lift
2. 热门主题整体收益、胜率、alpha
3. 一字板不可买比例
4. new_hot / continuing_hot / climax_hot 分阶段收益
5. 未来强股命中的主题分布
6. 最近若干交易日的日级样本
```

## 够用标准

第一阶段不追求复杂模型，只验证以下问题：

```text
1. D 日热门主题 Top5 是否能显著命中 D+1~D+5 的未来强股。
2. 命中不是因为覆盖股票太多，lift 是否明显 > 1。
3. 热门主题池整体收益是否跑赢全市场可交易池。
4. 可交易过滤后，结论是否仍然成立。
5. 新启动热门主题是否优于连续高潮主题。
```
