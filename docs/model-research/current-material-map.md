# 现有资料映射表

更新时间：2026-06-04

## 结论

这份表不新增结论，只做一件事：

- 把当前仓库里模型训练相关的高频资料，映射到 5 层结构里；
- 以后新增文档时，可以先对照这里判断该往哪放；
- 后续逐批收口历史文档时，也可以拿它当迁移清单。

## 1. 当前真相层

这些文档是以后每次开新研究都应该先读的：

| 文档 | 作用 |
|---|---|
| `docs/03_DATA_CONTRACTS.md` | 数据契约与正式数据根目录 |
| `docs/selection/daily_candidate_source_contract.md` | 每日候选统一输出契约 |
| `docs/selection/model_development_sop.md` | 模型如何标准化交付到系统 |
| `docs/strategy-rework/current-research-operating-summary.md` | 当前策略研究到底推进到哪 |
| `docs/model-research/README.md` | 模型训练资料总入口 |
| `docs/model-research/research-directions-index.md` | 当前有哪些研究方向 |
| `docs/model-research/evaluation-metrics-dictionary.md` | 指标的业务解释 |

## 2. 研究方向层

这些文档是在讲“某个方向本身”。

| 方向 | 当前主入口 |
|---|---|
| 星火 1.0 机会发现 | `docs/selection/opportunity_discovery_model_final.md` |
| 星火持仓 / 卖点 | `docs/archive/changes/MOD-20260525-01-spark-exit-watchlist-integration.md` |
| 热点板块研究 | `docs/selection/market_heat/README.md` |
| 市场环境过滤 | `docs/strategy-rework/strategies/S05-market-regime-filter/README.md` |
| 自进化训练环境 | `docs/strategy-rework/evolution-lab/README.md` |
| 试盘识别 | `docs/strategy-rework/experiments/20260603-probe-lift-research/README.md` |

注意：

- `星火 v2 纯选股`
- `低痛感次日`
- `超短方向`

这些已经补出正式方向卡：

- `docs/selection/spark_v2_pure_selection_direction_status_2026-06-05.md`
- `docs/selection/nextday_short_horizon_direction_status_2026-06-05.md`

## 3. 训练与验证层

这些文档解决的是共性训练问题，不属于某一条策略本身：

| 文档 | 作用 |
|---|---|
| `docs/selection/model_development_sop.md` | 模型交付规范 |
| `docs/selection/model_market_index_daily_runbook.md` | 市场环境指数更新与使用口径 |
| `docs/strategy-rework/evolution-lab/README.md` | 自进化训练环境与回放规则 |
| `docs/model-research/evaluation-metrics-dictionary.md` | 统一指标解释 |
| `docs/model-research/experiment-artifact-governance.md` | 实验产物命名与归档规范 |

## 4. 实验记录层

这些目录默认理解为“单次实验结果”，不是总入口：

| 目录 | 说明 |
|---|---|
| `docs/selection/*_2026-*` | 单轮训练 / 回测 / 样本研究 |
| `docs/selection/market_heat/backtests/` | 热点方向回测与规则验证 |
| `docs/strategy-rework/strategies/*/experiments/*` | 策略、买点、卖点、过滤实验 |
| `docs/strategy-rework/experiments/*` | 非策略目录下的专题实验 |
| `docs/strategy-rework/_archive/early-experiments/*` | 历史实验，默认不当当前真相 |

## 5. 产品接入层

这些文档在讲“研究结果如何进系统”：

| 文档 | 作用 |
|---|---|
| `docs/selection/daily_candidate_source_contract.md` | 候选怎么标准化输出 |
| `docs/contracts/review-selection.md` | 复盘 / 选股接口契约 |
| `docs/archive/changes/MOD-20260525-01-spark-exit-watchlist-integration.md` | 星火买入 / 持仓 / 卖出接到工作台的真实例子 |

## 6. 当前明显缺口

现在还缺 2 类关键资料：

1. 点时安全 / 防未来函数审计文档
2. 研究结果接入工作台 checklist
