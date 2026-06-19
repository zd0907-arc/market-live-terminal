# 试盘事件每日计算与交付口径

## 结论

- `probe_day0_watch` 和 `probe_d3_confirmed` 现在都不是静态研究提示，而是盘后可重算的动态 source。
- “历史同类”统一从 `selection_candidate_sources` 历史 source 快照 + `atomic_trade_daily` 后续表现动态计算，严格按当日已知特征匹配，且只使用已经走完后续 `10` 个交易日窗口的历史样本。
- 研究页 payload、daily candidate 详情、后续日跑接入现在都共用同一套后端输出字段。

## 每日计算顺序

1. 先完成基础日跑
   - `atomic_trade_daily`
   - `atomic_limit_state_daily`
   - `model_feature_daily_v1`
   - `selection_feature_daily`

2. 再跑试盘 source
   - `probe_day0_watch`
   - `probe_d3_confirmed`

3. source 生成时同步计算动态“历史同类”
   - 先从 `selection_candidate_sources` 读取同 source 历史样本
   - 只保留已经走完后续 `10` 个交易日窗口的样本
   - 用当日可见特征做分层和近邻匹配
   - 统计胜率、冲高率、回撤率、回本能力、最像案例

4. 再写入 unified daily candidate
   - `selection_candidate_sources`
   - `selection_candidate_daily`

5. 如需交付页面，再导出
   - `public/research/probe_signal_research_payload.json`

## 输入表

- `selection_feature_daily`
  - 日级名字、基础画像、日跑可用交易日
- `selection_candidate_sources`
  - 试盘 source 历史快照
  - 动态历史同类引擎优先从这里取历史样本
- `model_feature_daily_v1`
  - 试盘当日 / D3 确认日特征
- `atomic_trade_daily`
  - 后续 `1/3/5/10` 日收盘、最高、最低表现
- `atomic_trade_5m`
  - 当天试盘事件识别
- `atomic_order_5m`
  - OIB / CVD / 撤单 / 挂单特征
- `atomic_book_state_5m`
  - 盘口承接 / 抛压特征
- `atomic_limit_state_daily`
  - 触板 / 涨停状态

## 输出表与关键字段

### `selection_candidate_sources`

每个试盘 source 行都会写入：

- `explain_factors`
  - `history_sample_count`
  - `history_close_win_rate_1d/3d/5d/10d`
  - `history_avg_return_5d_pct`
  - `history_avg_return_10d_pct`
  - `history_drawdown_hit_-3_5d_rate`
  - `history_drawdown_hit_-5_5d_rate`
  - `history_breakout_hit_+5_10d_rate`
  - `history_breakout_hit_+8_10d_rate`
  - `history_first_hit_+5_best_day`
  - `history_never_break_even_5d_rate`
  - `history_never_break_even_10d_rate`
  - `history_group_label`
  - `history_summary_text`
  - `history_similar_cases`

- `raw_payload`
  - `historical_similar_stats`
  - `historical_hint_lines`
  - `sequence_label`
  - `probe_trade_date` / `confirm_trade_date`

### `selection_candidate_daily`

- `source_details`
  - 直接透传每个 source 的动态历史同类结果

## 观察池与确认池边界

### `probe_day0_watch`

- 触发时点：试盘当天盘后
- 只使用当天事件和当天 feature
- 只给观察解释，不给直接买点

### `probe_d3_confirmed`

- 触发时点：试盘后第 `3` 个交易日盘后
- 允许读取 `D3` 当日 feature
- 不回填到试盘当日
- 强确认时给 `明日可买`

## 历史同类引擎口径

### 同类定义

先按以下层次做约束和排序：

1. 按 `source_id` 分开
2. 按 `sequence_label` 分层
   - `首次试盘`
   - `连续试盘`
   - `重新试盘`
3. 按 bucket / 近邻匹配
   - `probe_strength_score`
   - `oib_ratio`
   - `same_day_pullback_ratio`
   - `price_position_20d`
   - `hot_theme_best_rank`
   - `buy_support_ratio`
   - `support_pressure_spread`
4. D3 确认池额外加入
   - `d3_oib_ratio`
   - `d3_l2_super_net_ratio`
   - `d3_l2_main_net_ratio`
   - `d3_support_pressure_spread`

### 统计输出

- 同类样本数
- `1/3/5/10` 日收盘胜率
- `5/10` 日平均收益
- `5` 日内打到 `-3% / -5%` 概率
- `10` 日内冲到 `+5% / +8%` 概率
- 最常在第几天先摸到 `+5%`
- `5/10` 日内最高价仍未回到成本上的比例
- `2~3` 个最像历史案例

## 严格避免未来数据

动态“历史同类”严格遵守：

- 匹配使用的特征只能来自当前 source 当天可见字段
- `probe_day0_watch` 不看 `D1/D3` 之后数据
- `probe_d3_confirmed` 只看确认日收盘前已知字段
- 历史样本只有在后续 `10` 个交易日都已经完整落表后才会进入统计
- 当前候选自身不会进入自己的历史样本池

## 日跑接入方式

### 盘后主链

正式主链仍是：

- `bash ops/run_daily_new_framework.sh --json --sync-nas`

试盘这条线的接法不需要单独起新框架，仍挂在：

- `backend/scripts/run_daily_model_signals.py`

因为 `run_daily_model_signals.py` 内部已经调用：

- `run_daily_selection_sources(...)`

而 `run_daily_selection_sources(...)` 已包含：

- `probe_day0_watch`
- `probe_d3_confirmed`

### 建议融合步骤

1. 先跑基础日表和 `model_feature_store`
2. 再跑 `run_daily_model_signals.py --date YYYY-MM-DD`
3. 若当天要更新研究页，再跑：

```bash
/opt/homebrew/opt/python@3.11/bin/python3.11 backend/scripts/build_probe_signal_historical_similar.py \
  --start-date 2026-04-01 \
  --end-date 2026-06-05 \
  --export-payload
```

### 区间回填

```bash
/opt/homebrew/opt/python@3.11/bin/python3.11 backend/scripts/build_probe_signal_historical_similar.py \
  --start-date 2026-04-01 \
  --end-date 2026-06-05
```

### 只导出页面 payload

```bash
/opt/homebrew/opt/python@3.11/bin/python3.11 backend/scripts/build_probe_signal_historical_similar.py \
  --start-date 2026-04-01 \
  --end-date 2026-06-05 \
  --skip-backfill \
  --export-payload
```
