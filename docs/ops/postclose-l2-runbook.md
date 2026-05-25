# 盘后正式主链与兼容旧链路

> 本文只覆盖当前正式日跑；`full_reverse / atomic backfill / bench / snapshot` 脚本族属于历史或专项工具，默认不作为本 runbook 的替代入口。
> 具体边界见：`docs/ops/atomic-script-families-boundary.md`

## 1. 当前正式语义
当前正式日跑主路径是：
1. Windows 产出原始包与正式跑数结果
2. 通过新框架主链刷新 `atomic_compact_main`、`selection_research_main`、`model_feature_store_main`
3. 必要结果同步到 Mac；轻量盯盘结果同步到 Cloud
4. `run_postclose_l2.sh` 只按兼容旧链路理解，不再作为当前默认主线阅读入口

当前要区分两条链：

1. **正式主链**：`ops/run_daily_new_framework.sh`
2. **兼容旧链路**：`ops/run_postclose_l2.sh`

## 2. 当前正式入口
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
./ops/run_daily_new_framework.sh --json
./ops/check_windows_new_framework_months_status.sh
```

## 2.1 当前正式日常指令
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
bash ops/run_daily_new_framework.sh --json
```

默认不传 `--date`。脚本会扫描 Windows `D:\MarketData` 下最近日包，和 Mac 正式库对比：
- `atomic_trade_daily`、`atomic_order_daily`、`atomic_book_state_daily`、`atomic_limit_state_daily`
- `selection_feature_daily`、`selection_signal_daily`
- `model_feature_daily_v1`、`model_feature_intraday_shape_v1`
- `selection_strategy_runs` 中当天活跃来源的 success 记录

只自动选择“最新完整日之后”的缺失日期补跑；早于最新完整日的历史缺口进入 `historical_missing_dates`，不作为日常自动补跑对象。

需要人工指定日期排障时才使用：
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
bash ops/run_daily_new_framework.sh --date 20260525 --json
```

## 2.1.0 兼容旧链路
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
bash ops/run_postclose_l2.sh
```

如果你只是要正常完成当前盘后正式日跑，不要执行这条旧链路。

## 2.1.1 指数缓存刷新
每日盘后模型特征构建前，需要低频刷新本地指数缓存。新框架主链会在 Windows 本地刷新 `atomic_compact_main` 与 `selection_research_main` 后增加非阻塞指数刷新：

```bash
python3 backend/scripts/sync_model_market_index_daily.py --source baostock --daily --lookback-days 10
```

产物：

```text
/Users/dong/Desktop/AIGC/market-data/selection/model_market_index_daily.db
```

`model_feature_store_main` 日跑只读这个本地 DB，不把外部网络放进强依赖。完整运行卡见：

```text
docs/selection/model_market_index_daily_runbook.md
```

## 2.2 当前同步铁律
- Windows -> Mac **禁止**走 SSH/scp 直拉。
- 只允许两条正式路径：
  1. 局域网 HTTP relay
  2. Cloud relay 中转
- 脚本当前已内置：
  - 局域网优先
  - 局域网失败自动回退云中转
  - 若某交易日已经完整成功，后续再次触发时不会被自动选中重复全链路重跑

## 2.3 状态检查
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
bash ops/check_windows_new_framework_months_status.sh
```
这个脚本当前更适合看新框架月批 / 阶段状态，不等同于每个交易日的逐日状态面板。

兼容旧链路状态：
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
bash ops/check_postclose_l2_status.sh
```
新框架与旧链路的状态文件不同，不要混用旧 `postclose_daily_run_*.log` 去判断新框架日跑是否失败。

## 3. 当前目标
- 日跑稳定
- 失败可追溯
- repair queue 可导出
- 结果可被 Mac 本地研究站消费

## 3.1 已验证样本
- `2026-04-24` 已完成收口验证：
  - Mac `history_daily_l2 = 7644`
  - Mac `history_5m_l2 = 346154`
  - Mac `atomic_trade_daily = 3184`
  - Mac `selection_feature_daily = 3184`
  - Cloud 同日 verify 已通过

## 4. 当前待完成问题
- 是否继续推进完全无人值守
- 全链路 `prepare + run` 是否稳定压到 `30m` 目标线
- 存量旧表依赖是否可以继续剥离

## 5. 相关变更卡
- `docs/changes/MOD-20260315-02-l2-march-backfill-review-and-postclose-runbook.md`
- `docs/archive/changes/MOD-20260411-14-market-data-governance-current-state.md`
- `docs/archive/changes/MOD-20260417-01-local-research-current-state.md`
- `docs/changes/MOD-20260425-04-postclose-l2-command-solidification.md`

## 6. 当前阅读提醒

- 当前正式日跑只看 `ops/run_daily_new_framework.sh`。
- 旧变更卡只用于追溯，不再作为日常操作起点。
