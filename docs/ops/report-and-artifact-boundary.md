# report / research 产出边界

> 这份文档只回答一个问题：当前仓库里各种 `report / summary / snapshot / payload / artifacts` 到底分别是什么，应该落到哪里。

## 1. 一句话结论

当前没有一个单独的 `report/` 总目录。  
项目里的 report 产出分成 4 层：

1. `market-data/research/current/`：正式研究真相库
2. `docs/selection/`、`docs/strategy-rework/`：人读结论与长期研究材料
3. `market-data/artifacts/`：仓外研究导出、页面快照、专题分析副产物
4. `.run/`、`logs/`、`public/research/`、`dist/research/`：运行态、页面 payload、构建产物

## 2. 当前正式真相层

这些对象是“正式研究真相”，不是 report：

| 路径 | 角色 |
|---|---|
| `market-data/live/market_data.db` | 运行轻量主库 |
| `market-data/live/user_data.db` | 用户态配置主库 |
| `market-data/research/current/atomic_facts/*` | 原子事实正式库 |
| `market-data/research/current/selection/*` | 选股研究正式库 |
| `market-data/research/current/market_heat/*.db` | 热点研究正式库 |

规则：

1. 页面和脚本的“正式读数真相”优先来自这里。
2. 这些库不是人读报告落点。
3. 不把 `artifacts/`、`docs/selection/*`、`logs/*` 误讲成正式研究主库。

## 3. 人读结论层

这些目录用于放长期可读的研究材料：

| 路径 | 角色 |
|---|---|
| `docs/selection/cycle_returns/` | 周期涨幅水位说明、日报、扇区页 |
| `docs/selection/research_watchlist/` | 长期跟踪清单的每日快照与说明 |
| `docs/selection/long_term_trends/` | 长周期主题跟踪与专题研究 |
| `docs/selection/litong_similarity/` | 单票与相似池专题结论 |
| `docs/selection/doublers/` | 翻倍股专题结论 |
| `docs/selection/market_heat/` | 热点研究说明与专题回测结论 |
| `docs/strategy-rework/` | 策略重构、实验说明与阶段总结 |

规则：

1. 这里放的是“给人看”的结论，不是页面必须依赖的唯一数据源。
2. 如果某个目录名字带日期、`v1/v2/v3`、`formal`，默认先当实验包看，不当当前正式版本。
3. 真正当前仍持续维护的方向，需要在 README 或总览文档里显式写清。

## 4. 仓外 artifacts 层

这些目录用于放“机器导出物”和“专题副产物”：

| 路径 | 角色 |
|---|---|
| `market-data/artifacts/market_heat/` | 热点专题分析、快照、案例导出 |
| `market-data/artifacts/selection/` | 选股研究导出与校验结果 |
| `market-data/artifacts/reports/` | 运行态合并报告、历史兼容报告 |

规则：

1. `artifacts/` 不是正式研究真相层。
2. `artifacts/` 适合放 `json / md / csv / html` 这类导出物。
3. 新的一次性专题分析，优先落到 `artifacts/`，不要再混进正式库目录。

## 5. 运行态与页面副产物层

| 路径 | 角色 |
|---|---|
| `.run/*` | 任务现场、阶段报告、临时产物 |
| `logs/*` | 运行日志与临时摘要 |
| `public/research/*` | 前端研究页 payload 源文件 |
| `dist/research/*` | 构建后的静态研究页 payload |

规则：

1. 这层默认不进入“正式研究结论”解释。
2. `public/research/*` 是页面输入，不是正式研究主库。
3. `dist/research/*` 只是 build 结果，永远不是真相源。
4. `.run/` 和 `logs/` 里的 `report.json`、`summary.md` 默认按任务副产物理解。

## 6. 哪些脚本最像 report builder

当前最像正式 report builder 的，不是所有 `build_*`，而是这几类：

1. `build_cycle_return_sector_report.py`
2. `build_research_watchlist_snapshot.py`
3. `build_storage_trend_tracking.py`
4. `build_ai_advanced_packaging_tracking.py`
5. `build_ai_interconnect_tracking.py`
6. `build_robot_actuator_tracking.py`
7. `build_litong_similarity_pool.py`
8. `build_ytd_doubler_analysis.py`

它们共同特点：

1. 从正式研究库读数
2. 生成 `md/json/csv/html`
3. 一部分写到 `docs/selection/*`
4. 一部分写到 `market-data/artifacts/*`

## 7. 当前最容易误判的对象

1. `docs/selection/*_2026-*`：默认先按 dated experiment bundle 理解
2. `docs/selection/*_v3_formal`：名字带 `formal`，但仍可能只是某次实验包
3. `data/selection/selection_research.db`：当前默认已不存在；即使将来被旧兼容链重建，也不当正式真相
4. `public/research/*`：页面 payload，不是正式研究结果
5. `logs/*report*`：运行副产物，不是正式报告总册

## 8. 后续规则

以后默认按这 4 条执行：

1. 正式研究真相只进 `market-data/research/current/`
2. 人读长期材料只进 `docs/selection/*`、`docs/strategy-rework/*`
3. 机器导出物优先进 `market-data/artifacts/*`
4. 运行态和页面 payload 不再拿来充当“正式研究报告”
