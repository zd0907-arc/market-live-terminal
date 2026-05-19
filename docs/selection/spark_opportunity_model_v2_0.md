# 星火机会模型 2.0 研究记录

更新时间：2026-05-19

## 结论

`spark_opportunity_selector@2.0` 已完成 2026-only 首轮训练。它不是投产版，只是为了先用 2026 年已跑出的完整 L2/挂单特征验证方向、暴露数据问题。

当前结果：

- 22 日机会模型：训练 `2026-01-05 ~ 2026-02-27`，验证 `2026-04-01 ~ 2026-04-09`。
- 5 日短线确认模型：训练 `2026-01-05 ~ 2026-04-17`，验证 `2026-05-06 ~ 2026-05-11`。
- 最新候选日：`2026-05-18`。
- 状态：`research_only`，不要接生产自动买入。

## 产物

目录：

```text
data/selection/models/spark_opportunity_selector/2.0/
```

核心文件：

| 文件 | 说明 |
|---|---|
| `model_22d.joblib` | 22 日冲高机会模型 |
| `model_5d.joblib` | 5 日短线确认模型 |
| `feature_columns.json` | 点时安全特征列 |
| `backtest_summary.json` | 训练/验证摘要 |
| `latest_candidates.csv` | `2026-05-18` 候选 |
| `sample_candidates_2026-05-18.json` | 工作台候选契约样例 |
| `source_manifest.json` | 模型版本 manifest |

训练脚本：

```text
backend/scripts/train_spark_opportunity_v2.py
```

## 数据来源

本轮使用临时构建的 feature store：

| DB | 作用 |
|---|---|
| `/Users/dong/Desktop/AIGC/market-data/selection/model_feature_store_v2_2026_train.db` | 2026-01-05 ~ 2026-04-17 训练/验证 |
| `/Users/dong/Desktop/AIGC/market-data/selection/model_feature_store_v2_may.db` | 2026-05-06 ~ 2026-05-18 5 日验证和最新候选 |

注意：

- 当前正式 `model_feature_store.db` 只有 5 月窗口，不能直接训练 2.0。
- 指数字段仍缺失，`csi1000_*` 未参与有效训练。
- 5 月个股 heat 为空，5 月候选不能用热点个股归因。

## 点时安全

训练特征只使用信号日 `D` 盘后可得字段。

已排除：

- `entry_open`
- `entry_gap_pct`
- `entry_buyable`
- `signal_close`
- `label_end_date`
- `label_complete_asof_date`
- 所有 `max_runup / hit / future` 标签字段

验证和收益计算仍会使用 `D+1` 开盘价、未来高低点和未来收盘价，但只用于标签与回测，不进入模型特征。

## 首轮结果

22 日模型验证窗口只有 6 个交易日，结论不能放大：

| 口径 | top1 | top2 | top3 |
|---|---:|---:|---:|
| hit15 | 33.33% | 50.00% | 55.56% |
| 平均最大冲高 | 8.95% | 16.73% | 26.01% |
| 平均收盘收益 | -10.29% | -3.66% | 6.39% |

5 日模型在 5 月只有 4 个可验证信号日：

| 口径 | top1 | top2 |
|---|---:|---:|
| hit8 | 50.00% | 62.50% |
| hit15 | 25.00% | 50.00% |
| 平均最大冲高 | 8.37% | 13.21% |
| 平均收盘收益 | 0.73% | 5.31% |

当前更像说明：`top1` 不稳定，`top2/top3` 可能比单点 top1 更适合后续工作台呈现和人工二次确认。

## 发现的问题

1. `model_feature_store.db` 需要全量同步，不能只留 5 月窗口。
2. 5 月没有成熟 22 日标签，所以不能拿 5 月上半月评价 22 日模型。
3. 指数环境字段缺失，后续需要训练侧或数据侧补 `csi1000_above_ma20` 等字段。
4. 5 月 heat 个股字段为空，热点解释能力在最近窗口缺失。
5. 只用 2026 年样本训练，样本太短，模型稳定性不足。

## 下一步

等 2025 数据跑完后，重新训练 2.0 正式候选：

1. 训练窗口扩大到 `2025-01 ~ 2026-04`。
2. 验证窗口保留 `2026-05`、按 5/10/22 日成熟标签分别评估。
3. 增加 walk-forward：每月只用该月之前已完成标签训练。
4. 再决定 `top1`、`top2` 还是 `top3 + 工作台人工确认`。
