# 实验产物命名与归档规范

更新时间：2026-06-03

## 结论

以后模型训练相关产物，先分清楚是：

- 长期入口文档
- 研究方向文档
- 单次实验结果
- 产品接入说明

不要把它们混在一个目录里，也不要让临时 smoke 结果长期占顶层入口。

## 1. 四类产物分别放哪

### A. 长期入口文档

放在：

- `docs/model-research/`

### B. 研究方向文档

优先放在：

- `docs/selection/`
- `docs/strategy-rework/`

### C. 单次实验结果

保留现有两种主落点：

1. 方向性模型训练结果
   - `docs/selection/<topic>_<YYYY-MM-DD>/`
2. 策略 / 持仓 / 环境类实验
   - `docs/strategy-rework/strategies/<strategy>/experiments/<EXP-name>/`

### D. 产品接入说明

放在：

- `docs/selection/daily_candidate_source_contract.md`
- `docs/changes/*`
- 必要时补到 `docs/contracts/*`

## 2. 单次实验最小产物包

以后一轮完整实验至少包含：

1. `README.md`
2. `run_summary.json`
3. `leaderboard.csv`
4. `monthly_metrics.csv`
5. `daily_candidates.csv` 或同类明细
6. `research_conclusion.md`

如果是最终选中模型，再补：

7. `model_selection_reason.md`
8. 模型文件与特征清单

## 3. 命名规则

### 目录名

统一优先使用：

```text
<topic>_<YYYY-MM-DD>
```

如果是 smoke，明确加后缀：

```text
<topic>_<YYYY-MM-DD>_smoke
```

### 文件名

推荐固定名称：

- `training_plan.md`
- `research_conclusion.md`
- `model_selection_reason.md`
- `run_summary.json`
- `leaderboard.csv`
- `monthly_metrics.csv`
- `final_holdout_metrics.csv`

## 4. 什么时候该进 archive

满足下面任一条件，就应该降级为历史材料：

1. 结果已经被后续更稳定版本替代
2. 这轮只是 smoke 或中途探索
3. 当前产品和研究主线已经不再引用它
4. 继续留在顶层只会误导后续 AI

归档的目标是防误读，不是清空历史。
