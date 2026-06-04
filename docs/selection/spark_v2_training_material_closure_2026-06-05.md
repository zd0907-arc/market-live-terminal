# 星火 v2 训练线资料收口

更新时间：2026-06-05

## 结论

这条 `spark-v2-training` worktree 不是单一模型分支，而是一条训练主线。

它包含三类产物：

1. `星火 v2 纯选股` 主线训练结果
2. `次日 / 超短` 方向训练结果
3. `短持有 / 次日退出` 这类交易验证结果

本次收口按资料治理框架处理：

- 方向层：补方向状态文档
- 实验层：保留正式结果目录
- 历史层：保留 smoke / raw / 首轮版本，但明确不当当前真相

不保留到主分支的内容：

- 训练脚本草稿
- 前端页面草稿
- `tmp/`

## 按治理框架的归类

### 一、方向层

#### 星火 v2 纯选股

- 方向状态文档：`docs/selection/spark_v2_pure_selection_direction_status_2026-06-05.md`
- 当前定位：继续保留为正式研究方向

#### 次日 / 超短

- 方向状态文档：`docs/selection/nextday_short_horizon_direction_status_2026-06-05.md`
- 当前定位：继续保留，但还不允许直接接产品

### 二、实验层：正式保留目录

这些目录保留到主分支，作为后续研究和复核入口：

| 目录 | 性质 | 当前判断 |
|---|---|---|
| `docs/selection/spark_v2_training_field_upgrade_2026-05-27/` | 训练场升级主报告 | 保留 |
| `docs/selection/spark_v2_pure_selection_train_2026-05-27/` | 纯选股正式候选 | 保留 |
| `docs/selection/spark_v2_selection_high_hit_final_2026-05-27/` | 高命中专项最终验证 | 保留 |
| `docs/selection/spark_v2_stable_runup_profiles_2026-05-28/` | 稳定冲高正式结果 | 保留 |
| `docs/selection/blitz_1d_fast_feedback_2026-05-28/` | 闪击 1 天正式结果 | 保留 |
| `docs/selection/low_pain_nextday_2026-05-28_v2/` | 次日低痛正式第二版 | 保留 |
| `docs/selection/spark_v2_fixed_short_hold_2026-05-28/` | 固定短持有验证 | 保留 |
| `docs/selection/spark_v2_intraday_nextday_exit_2026-05-28/` | 次日退出策略验证 | 保留 |

### 三、实验层：历史参考，但不当当前真相

这些目录也保留，但只作为过程证据，不当成当前正式结论：

| 目录 | 原因 |
|---|---|
| `docs/selection/blitz_1d_fast_feedback_2026-05-28_smoke/` | smoke |
| `docs/selection/low_pain_nextday_2026-05-28/` | 首轮正式版，已被 v2 覆盖 |
| `docs/selection/low_pain_nextday_2026-05-28_smoke/` | smoke |
| `docs/selection/low_pain_nextday_2026-05-28_smoke_v2/` | smoke |
| `docs/selection/spark_v2_stable_runup_profiles_2026-05-28_raw/` | 原始试跑结果，已被正式版覆盖 |

## 当前最重要的业务判断

### 星火 v2 纯选股

- 已经不是“训练不出来”
- 但还没有稳定超过星火 1.0 原始机会分
- 当前更适合保留为 `watch_only / research_only` 研究线

### 次日 / 超短

- 训练链路和结果已经跑通
- 低痛和快反馈还没有被单模型统一学好
- 最值得继续的是组合排序，而不是继续硬堆单模型

### 交易验证

- 短持有和次日退出有结果
- 但当前是验证层，不是正式候选来源
- 不应直接包装成可接入工作台的新正式模型

## 一句话收口

这条分支的价值，不是“已经产出一个统一的新正式模型”，而是把 `星火 v2 纯选股`、`次日 / 超短`、`短持有验证` 三条研究线的正式结果和历史过程文档都沉淀清楚，然后把 worktree 删掉。
