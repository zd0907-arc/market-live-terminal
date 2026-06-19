# 实验产物命名与归档规范

更新时间：2026-06-19

## 结论

以后模型训练和策略研究产物，先分清楚是：

- 长期入口文档
- 研究方向文档
- 单次实验结论
- 机器产物
- 产品接入说明

不要把它们混在一个目录里。代码仓只放人读材料；机器产物默认进数据仓。

## 1. 四类产物分别放哪

### A. 长期入口文档

放在：

- `docs/model-research/`

### B. 研究方向文档

优先放在：

- `docs/selection/`
- `docs/strategy-rework/`

### C. 单次实验结论

放在：

- `docs/selection/<topic>_<YYYY-MM-DD>/`
- `docs/strategy-rework/strategies/<strategy>/experiments/<EXP-name>/`

只保留：

- `README.md`
- `research_conclusion.md`
- `model_selection_reason.md`
- 必要的小型样例

旧目录中已经存在的 CSV/JSON 先按历史实验包保留，不再扩大。

### D. 机器产物

默认放在：

- `/Users/dong/ZhangData/market-data/artifacts/selection/`
- `/Users/dong/ZhangData/market-data/artifacts/research_payloads/`
- `/Users/dong/ZhangData/market-data/runs/`

包括：

- 模型文件
- 大型 CSV/JSON
- 回测明细
- 页面 payload 源产物
- 跑数现场和中间包

### E. 产品接入说明

放在：

- `docs/selection/daily_candidate_source_contract.md`
- `docs/changes/*`
- 必要时补到 `docs/contracts/*`

## 2. 单次实验最小交付

以后一轮完整实验至少包含一份人读结论包：

1. `README.md`
2. `research_conclusion.md`
3. 关键指标摘要
4. 机器产物位置说明

如果是最终选中模型，再补：

5. `model_selection_reason.md`
6. 模型文件与特征清单

机器产物不再要求复制进 `docs`，只在结论包里写清楚数据仓位置和用途。

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

## 5. 当前签收状态

本轮本地收口后，旧研究材料按下面口径签收：

1. `docs/selection/*_2026-*` 和 `docs/strategy-rework/**/experiments/*`：历史实验包，保留可追溯性，不再作为新产物默认落点。
2. `public/research/*`：代码仓内不再保留；页面 `/research` 由后端从 `market-data/artifacts/research_payloads/` 提供。
3. `.run/*`：代码仓内不再保留；跑数现场落到 `market-data/runs/`。
4. 新增研究若继续直接写代码仓，视为违反当前规范，必须先改输出路径或在任务说明中显式说明原因。
