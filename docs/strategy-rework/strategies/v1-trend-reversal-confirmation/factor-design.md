# v1 因子设计

## 1. 启动前资金价格背离因子

### `pre20_super_price_divergence`

```text
pre20_super_net_ratio - pre20_return_pct / 100
```

含义：过去 20 日价格越弱、超大单越不弱，分越高。

### `pre20_main_price_divergence`

```text
pre20_main_net_ratio - pre20_return_pct / 100
```

含义：用 L2 主力资金补充识别拆单潜伏。

### `pre5_super_price_divergence`

```text
pre5_super_net_ratio - pre5_return_pct / 100
```

含义：启动前 5 日是否出现短期压盘/洗盘后的资金背离。

## 2. 启动质量因子

### `launch3_quality_score`

关注：

- `launch3_return_pct`：启动 3 日涨幅。
- `launch3_super_net_ratio`：启动 3 日累计超大单净流入。
- `launch3_main_net_ratio`：启动 3 日累计主力净流入。
- `launch3_max_drawdown_pct`：启动 3 日最大回撤。

目标：过滤只冲一天就回落的假启动。

## 3. 回调承接因子

### `pullback_absorption_score`

关注：

- `pullback_super_net_ratio`
- `pullback_main_net_ratio`
- `pullback_support_spread_avg`
- `pullback_main_positive_day_ratio`
- `pullback_add_buy_ratio`

目标：识别“砸盘洗筹”而非“抢跑出货”。

## 4. 累计超大单持有因子

从买入锚点开始累计：

```text
anchor_cum_super_net_ratio = 累计 L2 超大单净流入 / 累计成交额
```

风险判断：

```text
累计值继续增加：安全/持有
累计值走平：观察
累计值下降：当日超大单净流出，风险开始
累计值连续下降或从峰值明显回撤：出货确认
```

注意：不能把“增速下降”直接当出货。只要累计值还在增加，就不能判定资金撤退。

## 5. 挂单行为因子

当前优先验证：

- `pullback_support_spread_avg`
- `pullback_add_buy_ratio`
- `launch3_add_buy_ratio`

暂缓直接使用：

- `cancel_sell_ratio`
- `oib_ratio` 极值

原因：当前统计里出现异常极值，需要先做截尾/清洗。
