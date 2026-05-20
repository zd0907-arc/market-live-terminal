# REQ-20260513-01-hot-theme-forecasting-roadmap

> 说明：这是 forecasting 方向的历史路线稿，不是当前唯一执行口径。
> 当前入口先读：[MOD-20260421-01-project-current-state-and-doc-governance-normalization](docs/changes/MOD-20260421-01-project-current-state-and-doc-governance-normalization.md)。
> 若要看 market-heat 主线落地结果，再读：[REL-20260512-v5.1.4-market-heat-mainline-dashboard](docs/changes/REL-20260512-v5.1.4-market-heat-mainline-dashboard.md)。
> 本文档现在主要适合用来回看 forecasting 设想、建模边界和当时的 roadmap。

## 目标

把市场热点页的 6 个池子升级为“主线延续预警”输入层，先判断当前已有热度记忆的主题在未来 5 个交易日是否还能延续。暂不预测冷启动新热点，暂不进入个股买点模型。

## 核心原则

1. 只使用当前 canonical 后的细颗粒主题池。
2. 统一成一张历史长表，不再区分长窗口/短窗口缓存作为训练输入。
3. 不新增更多热点池。现有 6 池只做生命周期分层和预警语义。
4. 先把板块层定义做准，不直接做个股买点。
5. 训练时保留连续排名，不把热度只压成 0/1 标签。

## 数据口径

### 统一主题池

- 主题总数：当前 canonical 细颗粒主题 633 个。
- 目标时间范围：`2025-01-02 → 最新交易日`。
- 粒度：`trade_date + theme_id`。

### 统一长表建议

建议生成 `fine_theme_heat_daily_v2`，字段分三层：

#### A. 当日事实

- `trade_date`
- `theme_id`
- `theme_name`
- `sector_type`
- `member_count`
- `rank_today`
- `hot_score`
- `pct_change`
- `up_ratio`
- `amount_ratio`
- `l2_net_inflow_yi`
- `limit_up_count`
- `touch_limit_up_count`
- `broken_limit_up_count`

#### B. 历史状态特征

- `rank_delta_1d`
- `rank_improve_3d`
- `rank_improve_5d`
- `hot_change_3d`
- `hot_change_5d`
- `top5_hits_5d`
- `top10_hits_5d`
- `top15_hits_5d`
- `top30_hits_5d`
- `top5_hits_20d`
- `top10_hits_20d`
- `top15_hits_20d`
- `top30_hits_20d`
- `best_rank_20d`
- `out_top30_streak`

#### C. 生命周期标签

- `today_strong`
- `first_hot`
- `mainline_accel`
- `warming`
- `mainline_continue`
- `fading_watch`

## 预测目标

### 当前主目标

`future_mainline_extension_5d`：未来 5 个交易日主线延续。

判定条件：

- 当前候选来自近期有热度记忆的 `continuation_reheat` 宇宙；
- 未来 5 日内至少一次进入 Top15；
- 未来 5 日内至少 2 次位于 Top30；
- 进入 Top15 的有效日不能明显由单票拉动。

### 辅助观察

- `future_top10_5d`
- `future_top15_5d`
- `future_top30_5d`

这些只用于解释，不再作为页面默认预测目标。

## 设计约束

- `主线再加速` 和 `退潮观察` 要做互斥区分，不能再额外增加“回流池”。
- 训练时不能只用 Top15 / 非 Top15 二值，必须保留连续 rank 和 rank percentile。
- 第一阶段只做板块预警，成分股模型作为第二阶段。
- 不设置成分股数量硬下限；用广度和单票拉动软惩罚降低小样本扰动。

## 交付顺序

1. 重建统一长表。
2. 先做规则基线，验证未来 3/5 日命中率。
3. 再做正式模型回测。
4. 最后把预测候选接入市场热点页。

## 本轮执行结果

- 已重建 `fine_theme_heat_daily_v2`，覆盖 `2025-01-02 ~ 2026-05-13`，主题数 `633`，样本数 `202473`。
- 已验证 6 池对未来 3/5 日热区有显著提升，其中 `主线再加速` 最强，`持续主线` 次之。
- 已补基线报告：`docs/selection/market_heat/fine_theme_heat_forecast_baseline_2026-05-13.md`
- 已把预测目标收敛为 `future_mainline_extension_5d`。
- 已训练当前模型 `fine_theme_heat_hgb_focus_20260515_002504`，预测日 `2026-05-13`，候选池 `68`，页面默认 Top5。
- 验证期 `2026-02-25 ~ 2026-05-06`：候选池基线 `17.02%`，Top5 命中 `24.89%`，lift `1.46x`。
- 月度滚动回测 `2025-04-29 ~ 2026-05-06`：Top5 单主题命中 `19.43%`，每天5个至少1个命中 `62.30%`。
