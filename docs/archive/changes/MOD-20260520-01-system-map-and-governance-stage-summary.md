# MOD-20260520-01-system-map-and-governance-stage-summary

## 1. 基本信息
- 标题：系统地图与治理阶段摘要
- 状态：DRAFT
- 负责人：Codex
- 关联 Task ID：`MOD-20260520-01-system-map-and-governance-stage-summary`
- 关联 CAP：`CAP-REALTIME-FLOW`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`, `CAP-HISTORY-30M`, `CAP-WIN-PIPELINE`
- 关联 STG：`N/A`

## 2. 当前系统地图

### 2.1 主链
- `盯盘`
- `正式复盘`
- `选股研究工作台`

### 2.2 研究主线
- `市场热点 / market-heat`

### 2.3 专题 / 实验层
- `趋势研究`
- `模型训练`
- `PPO 回测复盘`
- `机会发现交易复盘`
- `热点低位样本`

### 2.4 三端职责
- `Windows`：数据主站、外采、盘后正式跑数、结果产出
- `Mac`：本地研究站、复盘、选股、文档治理
- `Cloud`：轻量盯盘 / 应急查看

### 2.5 页面 / 契约对照

| 页面 / 模块 | 当前定位 | 主要入口 |
|---|---|---|
| 盯盘首页 | 主链 | `docs/02_BUSINESS_DOMAIN.md` / `docs/01_SYSTEM_ARCHITECTURE.md` |
| 正式复盘页 | 主链 | `docs/contracts/review-selection.md` / `docs/03_DATA_CONTRACTS.md` |
| 选股研究工作台 | 主链 | `docs/selection/daily_candidate_source_contract.md` / `docs/selection/opportunity_discovery_model_final.md` |
| 市场热点 / market-heat | 研究主线 | `docs/selection/market_heat/README.md` |
| 趋势研究 | 专题层 | `docs/selection/long_term_trends/README.md` |
| 模型训练 | 专题层 | `docs/selection/model_development_sop.md` |
| 数据治理 / atomic / compact | 底座治理 | `docs/changes/MOD-20260411-14-market-data-governance-current-state.md` |
| 运维与日跑 | 运行入口 | `docs/04_OPS_AND_DEV.md` / `docs/ops/postclose-l2-runbook.md` |

### 2.6 数据源 / 存储对照

| 数据源 / 存储 | 当前角色 | 核心入口 |
|---|---|---|
| `data/market_data.db` | Mac 本地研究消费库 / Cloud 轻量库 | `docs/03_DATA_CONTRACTS.md` / `docs/01_SYSTEM_ARCHITECTURE.md` |
| `data/atomic_facts/*` | atomic / compact 治理底座 | `docs/changes/MOD-20260411-14-market-data-governance-current-state.md` |
| `data/selection/selection_research.db` | 选股研究独立库 | `docs/selection/daily_candidate_source_contract.md` / `docs/contracts/review-selection.md` |
| `docs/selection/long_term_trends/*` | 长期趋势专题知识库 | `docs/selection/long_term_trends/README.md` |
| `docs/selection/market_heat/*` | 热点研究专题库 | `docs/selection/market_heat/README.md` |
| Windows 盘后正式产物 | 真相源 / 跑数主站 | `docs/01_SYSTEM_ARCHITECTURE.md` / `docs/ops/postclose-l2-runbook.md` |

### 2.7 atomic / compact 收口

- 当前主链可用数据底座已切到 `compact`。
- `atomic_limit_state_daily` 承担日级涨跌停状态，`atomic_limit_state_5m` 不再是默认长期表。
- 盘中触板 / 炸板 / 封板变化按需由 `atomic_trade_5m + atomic_limit_state_daily` 推导。
- 仍需继续跟踪 `history_*_l2`、`stock_universe_meta`、旧表依赖剥离。

## 3. 已完成的治理

1. 入口文档已收口到 `README / 01 / 02 / 03 / 04 / AI_QUICK_START`。
2. `strategy-rework` 顶层旧状态卡已迁 archive，默认入口改为三件套。
3. `selection` 顶层一次性清理文档已迁 archive，并补压缩摘要。
4. `ops` 正式白名单已明确，`full_reverse / atomic backfill / bench / snapshot` 已单独做边界说明。
5. `Windows -> Mac` 同步铁律已经固定为 `HTTP relay / Cloud relay`，不再走 SSH/scp 直拉。
6. `snapshot` 已降级为过渡验证 / 应急工具，不再是正式主方案。
7. `atomic / compact` 已收口为当前主链底座，`atomic_limit_state_daily` 取代 `atomic_limit_state_5m` 成为日级主表。

## 4. 还必须继续做的

1. 继续清理 `docs/changes`、`strategy-rework`、`selection`、`ops` 中仍会误导 AI 的历史材料。
2. 继续补齐阶段摘要，压缩 v2/v3、v4、v5 这几段历史。
3. 继续跟踪活待办：`T-014 / T-016 / T-019 / T-020 / T-022 / T-027 / T-031 / T-033`。

## 5. 不该再当作当前真相的内容

- `snapshot` 作为正式主路径
- `full_reverse / atomic backfill / bench` 作为默认入口
- Cloud 作为研究主站
- Mac 直接读 Windows sqlite 主库
- 旧过程卡当现状真相

## 6. 历史阶段压缩

| 阶段 | 关键词 | 当前结论 |
|---|---|---|
| `v2 / 早期实验` | `v2`、`stealth`、`breakout`、`distribution` | 只保留为研究与兼容语义，不再是日常入口 |
| `v4 / 数据治理` | `L2`、`atomic`、`ETL`、`正式复盘` | 已成为底座的一部分，但历史补齐和旧依赖收口仍在继续 |
| `v5 / 选股工作台` | `selection-research`、`daily review`、`market-heat`、`strategy-rework` | 已进入当前主线的研究/观察工作台，但热点与部分模型线仍是探索态 |
| `当前治理批次` | `archive`、`ops boundary`、`system map` | 正在把入口、历史材料、脚本边界压成可交接总图 |

补充判断：
- `v2` 相关文件、旧实验目录、旧编号页面名，都不应再被理解为当前主路径。
- `v4` 的数据治理成果是当前主链底座，但它的历史过程卡不能再当运行步骤。
- `v5` 的选股与策略研究已经进主线，但当前仍是研究/观察，不等于稳定自动买入系统。
