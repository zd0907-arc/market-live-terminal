# market-data 重分类与迁移映射

更新时间：2026-06-04

关联文档：

- [nas-migration-execution-plan.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/ops/nas-migration-execution-plan.md)
- [nas-migration-master-plan.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/ops/nas-migration-master-plan.md)
- [MOD-20260524-03-canonical-data-artifacts-manifest.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/archive/changes/MOD-20260524-03-canonical-data-artifacts-manifest.md)

## 1. 目的

这份文档服务阶段 C：

- 给 `market-data` 与仓库内 `data` 做正式重分类
- 明确哪些是正式库
- 明确哪些是缓存
- 明确哪些是研究产物
- 明确哪些对象最危险，后续要优先消歧

当前只做识别、映射、迁移顺序，不直接删库。

## 2. 当前执行边界

截至 `2026-06-04`，这份文档面对的现场条件已经变了：

- NAS 已可通过局域网、Tailscale 私网和 Tailscale Funnel 访问
- NAS 查询主链已经切到 `live/` + `research/current/` 新口径
- 但 NAS 当前 `research/current` 仍然是 bootstrap current，不是最终治理完成态
- 当前 NAS 上的正式研究数据大致停在 `2026-05-27`

因此阶段 C 当前不再只是“离线资产建设”，而是要同时服务两件事：

1. Mac 本地 `market-data` 的路径治理
2. NAS 运行态目录的正式治理收口

## 3. 当前目录现状

### 3.1 Mac 外置数据根目录

当前根目录：

- `/Users/dong/Desktop/AIGC/market-data`

当前二级目录：

```text
market-data/
  _incoming/
  atomic_facts/
  market_heat/
  sandbox/
  selection/
```

其中 `market_heat/` 下又混放了：

- 正式热点库
- 缓存
- 研究导出
- 板块映射缓存

### 3.2 仓库内 data 目录

当前根目录：

- `/Users/dong/Desktop/AIGC/market-live-terminal/data`

它不是正式主数据根，而是：

- 兼容数据
- 样例 / shadow / sandbox
- 研究导出
- 历史遗留对象

不能再把它理解成当前生产主链真相源。

## 4. 当前正式库清单

这些对象当前应视为正式主链数据，不应随意挪走或清理。

### 4.1 在线轻量运行库

| 对象 | 当前路径 | 当前作用 | 后续目标目录 |
|---|---|---|---|
| `market_data.db` | `/Users/dong/Desktop/AIGC/market-data/market_data.db` | 首页实时盯盘、基础历史接口、在线轻量消费 | `market-data/live/market_data.db` |
| `user_data.db` | `/Users/dong/Desktop/AIGC/market-data/user_data.db` | watchlist、配置、用户态设置 | `market-data/live/user_data.db` |

### 4.2 正式研究库

| 对象 | 当前路径 | 当前作用 | 后续目标目录 |
|---|---|---|---|
| `market_atomic_mainboard_compact_current.db` | `/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_compact_current.db` | atomic 明细底座 | `market-data/research/current/atomic_facts/` |
| `selection_research.db` | `/Users/dong/Desktop/AIGC/market-data/selection/selection_research.db` | 选股研究正式库 | `market-data/research/current/selection/` |
| `model_feature_store.db` | `/Users/dong/Desktop/AIGC/market-data/selection/model_feature_store.db` | 模型训练特征库 | `market-data/research/current/selection/` |
| `model_market_index_daily.db` | `/Users/dong/Desktop/AIGC/market-data/selection/model_market_index_daily.db` | 模型指数前置库 | `market-data/research/current/selection/` |
| `fine_theme_heat_daily.db` | `/Users/dong/Desktop/AIGC/market-data/market_heat/fine_theme_heat_daily.db` | 热点页面正式日表 | `market-data/research/current/market_heat/` |
| `fine_theme_heat_daily_v2.db` | `/Users/dong/Desktop/AIGC/market-data/market_heat/fine_theme_heat_daily_v2.db` | 热点训练 / 回测长表 | `market-data/research/current/market_heat/` |
| `fine_theme_heat_forecast.db` | `/Users/dong/Desktop/AIGC/market-data/market_heat/fine_theme_heat_forecast.db` | 热点预测结果库 | `market-data/research/current/market_heat/` |
| `stock_sector_map.db` | `/Users/dong/Desktop/AIGC/market-data/market_heat/stock_sector_map.db` | 股票-板块映射库 | `market-data/research/current/market_heat/` |
| `tradable_theme_map.db` | `/Users/dong/Desktop/AIGC/market-data/market_heat/tradable_theme_map.db` | 可交易主题映射库 | `market-data/research/current/market_heat/` |
| `hot_theme_low_position_l2_samples.db` | `/Users/dong/Desktop/AIGC/market-data/market_heat/hot_theme_low_position_l2_samples.db` | 热点低位样本专题库 | `market-data/research/current/market_heat/` |

## 5. 当前高风险误导对象

这些对象不一定该立刻删，但后续必须优先消歧。

| 对象 | 当前路径 | 风险 | 当前判断 |
|---|---|---|---|
| `market_atomic_mainboard_full_reverse.db` | `/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_full_reverse.db` | 名字像正式 atomic 主库，但当前是 `0B` | 高风险历史残留 |
| `fine_theme_member_daily.db` | `/Users/dong/Desktop/AIGC/market-data/market_heat/fine_theme_member_daily.db` | 名字像正式配套库，但当前是 `0B` | 高风险不完整对象 |
| `market_heat.db` | `/Users/dong/Desktop/AIGC/market-live-terminal/data/market_heat/market_heat.db` | 极易被误判为正式热点主库，当前是 `0B` | 高风险仓库内残留 |
| `market_data_history.db` | `/Users/dong/Desktop/AIGC/market-live-terminal/data/market_data_history.db` | 容易被当成正式历史库 | 历史兼容对象 |
| `market_data_history_202602_fix.db` | `/Users/dong/Desktop/AIGC/market-live-terminal/data/market_data_history_202602_fix.db` | 名字不自解释，容易混入正式链路 | 修复产物 |
| `data/selection/selection_research.db` | `/Users/dong/Desktop/AIGC/market-live-terminal/data/selection/selection_research.db` | 名字像正式选股主库，但实际已被外置正式库替代 | 仓库内兼容对象 |

## 6. 当前缓存对象

缓存不是垃圾，但也不是正式真相源。

### 6.1 market-data 下的缓存

| 当前路径 | 类型 | 后续目标目录 |
|---|---|---|
| `market-data/market_heat/cache/fine_heat_snapshots_*.json` | 热点页面 / 脚本缓存 | `market-data/cache/market_heat/` |
| `market-data/market_heat/eastmoney_sector_cache/*.json` | 板块接口缓存 | `market-data/cache/eastmoney_sector_cache/` |
| `market-data/market_heat/models/` | 模型 / 中间对象缓存或输出 | 待复核，优先归入 `artifacts/market_heat/` 或独立 `cache/models/` |
| `market-data/market_heat/shadow_candidates/` | shadow / 兼容候选对象 | 不进入正式 current，后续复核 |

### 6.2 repo data 下的缓存 / shadow

| 当前路径 | 类型 | 后续建议 |
|---|---|---|
| `data/sandbox/` | sandbox 试验数据 | 保留在仓库内，不迁入正式 `market-data/current` |
| `data/sandbox_review.db` | sandbox review 兼容 DB | 保留在仓库内 |
| `data/sandbox_exports/` | sandbox 导出 | 归档或保留为 artifacts，不当正式链 |

## 7. 当前研究产物 / 导出对象

这类对象应统一归到 `artifacts/`，不能再和正式库混放。

### 7.1 market-data 下的研究产物

主要包括：

- `market-data/market_heat/*.json`
- `market-data/market_heat/*.md`
- 非 `.db` 的专题分析输出

代表对象：

- `2026-04-28.json/.md`
- `latest.json`
- `sector_boards_latest.json`
- `stock_sector_map_latest.json`
- `tradable_theme_map_latest.json`
- 各类 `strategy_theme_*.json`
- 各类 `hot_theme_*.json`
- 各类 `selection_alignment_*.json`

建议后续归入：

- `market-data/artifacts/market_heat/`

### 7.2 repo data 下的研究产物

主要包括：

- `data/selection/aggressive_10cm/**`
- `data/selection/evolution_lab/**`
- `data/selection/cycle_returns/**`
- `data/selection/doubler_analysis/**`
- `data/selection/litong_similarity/**`
- `data/selection/long_term_trends/**`
- `data/selection/market_heat/backtests/**`
- `data/selection/opportunity_discovery/**`

这些对象的共同特点：

- 大量 `json / csv / md / README`
- 服务研究、回测、实验、专题页
- 不应作为正式 current 研究库

建议后续归入：

- `market-data/artifacts/selection/`
- 或者继续保留在仓库内 `data/selection/`，但必须文档上明确它们不是正式运行库

## 8. 目录重构目标映射

后续目标结构：

```text
market-data/
  live/
  research/current/
  research/staging/
  research/archive/
  cache/
  artifacts/
  incoming/
```

### 8.1 映射表

| 当前路径 | 目标路径 | 说明 |
|---|---|---|
| `market-data/market_data.db` | `market-data/live/market_data.db` | 在线轻量运行库 |
| `market-data/user_data.db` | `market-data/live/user_data.db` | 用户态配置库 |
| `market-data/atomic_facts/*` | `market-data/research/current/atomic_facts/*` | atomic 正式链 |
| `market-data/selection/*.db` | `market-data/research/current/selection/*.db` | selection 正式链 |
| `market-data/market_heat/*.db` | `market-data/research/current/market_heat/*.db` | 热点正式链 |
| `market-data/market_heat/cache/*` | `market-data/cache/market_heat/*` | 缓存 |
| `market-data/market_heat/eastmoney_sector_cache/*` | `market-data/cache/eastmoney_sector_cache/*` | 缓存 |
| `market-data/market_heat/*.json` | `market-data/artifacts/market_heat/*` | 导出 / 研究产物 |
| `market-data/market_heat/*.md` | `market-data/artifacts/market_heat/*` | 导出 / 研究产物 |
| `market-data/_incoming/*` | `market-data/incoming/*` | 临时导入 |

## 9. 阶段 C 的执行顺序

按风险从低到高：

### C1. 先文档与脚本层收口

- 固化本清单
- 固化脚本和服务应走环境变量，不依赖旧路径

### C2. 先创建新目录，但不搬正式库

先建立：

- `live/`
- `research/current/`
- `research/staging/`
- `research/archive/`
- `cache/`
- `artifacts/`
- `incoming/`

### C3. 先迁缓存和产物

优先迁：

- `market_heat/cache/*`
- `market_heat/eastmoney_sector_cache/*`
- `market_heat/*.json`
- `market_heat/*.md`

因为这批迁移风险最低。

### C4. 最后迁正式库

在确认所有服务都走环境变量后，再迁：

- `market_data.db`
- `user_data.db`
- `atomic_facts/*.db`
- `selection/*.db`
- `market_heat/*.db`

## 10. 当前不做的事情

当前明确不做：

1. 不直接删除高风险误导对象
2. 不在还没切环境变量前搬正式主库
3. 不把仓库内所有研究产物强行一次性外置

## 11. 当前结论

阶段 C 现在最需要做的不是“立即搬目录”，而是：

1. 先把正式库边界钉死
2. 先把缓存和产物边界钉死
3. 先给后续目录迁移建立映射

做完这三件事后，才适合开始物理迁移。

说明：

- 下面 `12` 到 `15` 是按日期追加的历史执行记录
- 其中出现的 “NAS 不可达” 、 `B1a` 阻塞 等表述，只代表当时现场状态
- 当前统一基线以本文 `2. 当前执行边界` 和 `15.6 当前结论` 为准

## 12. 2026-05-29 路径依赖审计与第一批收口

这一轮按阶段 C 执行，先处理“活跃入口”和“高价值盘后主链”，不碰大批研究专题脚本。

### 12.1 本轮已确认的阻塞

- `ssh -o BatchMode=yes -o ConnectTimeout=8 zhangdong@192.168.3.43 'echo ok'`
  - 结果：超时
- `curl --max-time 8 -fsS http://192.168.3.43:8080/api/health`
  - 结果：超时

因此本轮没有继续做阶段 A，转推进阶段 C。

### 12.2 本轮已收口的活跃入口

已改成认识 `FORMAL_MARKET_DATA_ROOT / LIVE_DATA_ROOT / RESEARCH_CURRENT_ROOT`，并开始支持：

- `live/`
  - `market_data.db`
  - `user_data.db`
- `research/current/`
  - `atomic_facts/*`
  - `selection/*`
  - `market_heat/*`

本轮已处理文件：

- `backend/app/core/config.py`
- `backend/app/db/selection_db.py`
- `backend/app/services/fine_theme_heat_db.py`
- `backend/app/services/market_heat.py`
- `backend/app/services/selection_strategy_v2.py`
- `backend/app/services/aggressive_10cm_strategy.py`
- `backend/app/services/spark_opportunity_selector.py`
- `backend/app/services/selection_candidate_store.py`
- `ops/start_local_research_station.sh`
- `ops/start_local_backend_with_atomic.sh`
- `ops/run_model_feature_store_batch.sh`
- `ops/export_market_data_inventory.sh`
- `backend/scripts/build_model_feature_store.py`
- `backend/scripts/backfill_model_feature_store_indexes.py`
- `backend/scripts/sync_model_market_index_daily.py`
- `backend/scripts/validate_model_market_index_daily.py`
- `backend/scripts/validate_model_feature_store.py`
- `backend/scripts/run_daily_new_framework.py`
- `backend/scripts/run_postclose_l2_daily.py`

### 12.3 本轮已解决的具体问题

#### 1. 主服务默认数据根不再只认单层 `market-data/`

现在默认解析规则变成：

- 若存在 `research/current/`，研究链优先走这里
- 若存在 `live/`，轻量运行库优先走这里
- 老目录结构仍兼容
- 也仍可完全靠环境变量显式覆盖

#### 2. 本地研究站启动脚本已区分 live 和 research

`ops/start_local_research_station.sh` 现在会分别注入：

- `DB_PATH / USER_DB_PATH` -> `live/`
- `SELECTION_DB_PATH / ATOMIC_*` -> `research/current/`

这样后面物理迁目录时，不需要再靠“一个 DATA_DIR 装所有库”。

#### 3. Windows 盘后主链的关键脚本已开始按新口径找库

本轮先收了：

- model feature / market index
- 本地盘后总控
- daily new framework
- spark exit watchlist 入口

这是为了后面阶段 B 建立：

- Windows 产物 -> NAS `research/staging`
- 校验后切 `research/current`

#### 4. `/selection/daily-candidates` 不再向前端暴露本机绝对路径

之前 `artifact_path` 会把本机模型文件绝对路径吐给前端。

现在统一收成相对标签，例如：

- `opportunity_discovery_trade_l2_v0_1/model.joblib`

这解决的是：

- 用户接口泄漏本机路径
- 后续 NAS / Windows / Mac 三端路径不一致时前端混乱

### 12.4 本轮验证证据

已执行并通过：

```text
pytest -q backend/tests/test_market_data_path_config.py backend/tests/test_selection_daily_workbench.py
```

结果：

- `11 passed`

覆盖点：

- `config.py` 已能识别 `live/` 和 `research/current/`
- daily candidates 已对 `artifact_path` 做脱敏

已执行并通过：

```text
python3 -m py_compile \
  backend/app/core/config.py \
  backend/app/db/selection_db.py \
  backend/app/services/fine_theme_heat_db.py \
  backend/app/services/market_heat.py \
  backend/app/services/selection_strategy_v2.py \
  backend/app/services/aggressive_10cm_strategy.py \
  backend/app/services/spark_opportunity_selector.py \
  backend/app/services/selection_candidate_store.py \
  backend/scripts/build_model_feature_store.py \
  backend/scripts/backfill_model_feature_store_indexes.py \
  backend/scripts/sync_model_market_index_daily.py \
  backend/scripts/validate_model_market_index_daily.py \
  backend/scripts/validate_model_feature_store.py \
  backend/scripts/run_daily_new_framework.py \
  backend/scripts/run_postclose_l2_daily.py
```

已执行并通过：

```text
bash -n \
  ops/start_local_research_station.sh \
  ops/start_local_backend_with_atomic.sh \
  ops/run_model_feature_store_batch.sh \
  ops/export_market_data_inventory.sh
```

追加执行并通过：

```text
pytest -q \
  backend/tests/test_market_data_path_config.py \
  backend/tests/test_selection_daily_workbench.py \
  backend/tests/test_spark_opportunity_exit_paths.py
```

结果：

- `13 passed`

新增覆盖点：

- `spark_opportunity_exit.py` 模型目录已不依赖机器绝对路径
- `SPARK_OPPORTUNITY_EXIT_MODEL_ROOT` 仍可显式覆盖

### 12.5 当前仍未处理的高命中残留

下面这些对象这轮先入审计，不在本轮直接改：

- `backend/scripts/analyze_theme_lead_stock_lag_strategy.py`
- `backend/scripts/build_hot_theme_strong_momentum_case_page.py`
- `backend/scripts/research_aggressive_10cm_low_position_agent.py`
- `backend/scripts/build_ai_interconnect_tracking.py`
- `backend/scripts/build_ai_advanced_packaging_tracking.py`
- `backend/scripts/research_opportunity_discovery_model.py`
- `backend/scripts/train_spark_opportunity_v2.py`
- `backend/scripts/build_research_watchlist_snapshot.py`
- `backend/scripts/build_litong_similarity_pool.py`
- 以及其他专题页 / 研究导出脚本

共同特点：

- 仍直接写死 `/Users/dong/Desktop/AIGC/market-data`
- 大多不是当前服务主入口
- 更适合按专题批次清理，而不是在当前迁移轮里散着改

### 12.6 下一批阶段 C 建议顺序

下一轮继续阶段 C 时，建议按这个顺序：

1. 给阶段 B 需要的 `research/staging -> current -> archive` 切换脚本打底
2. 收剩余盘后校验 / 发布入口里仍写死老目录的对象
3. 分专题清理 research / report / page builder 脚本
4. 最后再考虑物理迁目录

### 12.7 本轮新增离线资产

这轮又补了两类直接服务阶段 B/C 的资产：

1. NAS full compose 已切到新目录口径：
   - `LIVE_DATA_ROOT=/runtime-data/live`
   - `RESEARCH_CURRENT_ROOT=/runtime-data/research/current`
   - crawler 默认读写 `live/market_data.db` 和 `live/user_data.db`
2. research 发布链脚本和 runbook 已落地：
   - `ops/build_nas_research_release_manifest.sh`
   - `ops/check_nas_research_release.sh`
   - `ops/upload_nas_research_release.sh`
   - `ops/nas_prepare_research_dirs.sh`
   - `ops/nas_publish_research_release.sh`
   - `ops/nas_rollback_research_release.sh`
   - `ops/nas_list_research_releases.sh`
   - [nas-research-release-runbook.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/ops/nas-research-release-runbook.md)

补充事实：

- 当前本机正式数据根仍是 flat 结构，不是物理上已经切完的 `research/current/`
- 但基于 `ops/build_nas_research_release_manifest.sh` 已能从这套 flat 正式库生成一版可发布 release
- `ops/check_nas_research_release.sh /Users/dong/Desktop/AIGC/market-data` 已验证：
  - `atomic_compact_main` 最新交易日：`2026-05-28`
  - `selection_research_main` 最新候选交易日：`2026-05-28`
  - `model_feature_store_main` 最新交易日：`2026-05-28`
  - `market_heat_v2` 最新交易日：`2026-05-28`

## 13. 2026-06-02 阶段 C1 第二批收口

### 13.1 本轮前置判断

本轮先按执行规划做 NAS 可达性分流：

- `ssh -o BatchMode=yes -o ConnectTimeout=8 zhangdong@192.168.3.43 'echo ok'`
  - 结果：超时
- `curl --max-time 8 -fsS http://192.168.3.43:8080/api/health`
  - 结果：连接失败

因此本轮不做 A1 / B1，继续推进 C1。

### 13.2 本轮收口范围

这轮不再散改各种专题脚本，只收一类：

- 研究导出 / payload / 快照入口脚本

目标：

- 让这批脚本默认跟随 `RESEARCH_CURRENT_ROOT`
- 不再把 `/Users/dong/Desktop/AIGC/market-data/...` 写死成唯一默认根

### 13.3 本轮已处理文件

- `backend/scripts/build_research_watchlist_snapshot.py`
- `backend/scripts/export_opportunity_trade_review_payload.py`
- `backend/scripts/export_spark_pattern_research_payloads.py`
- `backend/scripts/research_opportunity_discovery_model.py`

### 13.4 本轮具体收口内容

#### 1. watchlist 快照脚本

`build_research_watchlist_snapshot.py` 现在默认改成：

- `SELECTION_DB_PATH` 优先
- 否则走 `RESEARCH_CURRENT_ROOT/selection/selection_research.db`
- atomic 默认优先顺序：
  - `ATOMIC_MAINBOARD_DB_PATH`
  - `ATOMIC_COMPACT_DB_PATH`
  - `ATOMIC_DB_PATH`
  - `candidate_atomic_db_paths()`
  - 最后回退 `RESEARCH_CURRENT_ROOT/atomic_facts/market_atomic_mainboard_compact_current.db`

#### 2. opportunity trade review payload

`export_opportunity_trade_review_payload.py` 现在默认改成：

- `RESEARCH_CURRENT_ROOT/atomic_facts/market_atomic_mainboard_compact_current.db`
- `RESEARCH_CURRENT_ROOT/selection/selection_research.db`

同时保留显式参数覆盖：

- `--atomic-db`
- `--selection-db`

#### 3. spark pattern research payloads

`export_spark_pattern_research_payloads.py` 现在默认改成：

- `RESEARCH_CURRENT_ROOT/atomic_facts/market_atomic_mainboard_compact_current.db`
- `RESEARCH_CURRENT_ROOT/selection/selection_research.db`

#### 4. opportunity discovery model 研究脚本

`research_opportunity_discovery_model.py` 现在默认改成：

- `RESEARCH_CURRENT_ROOT/atomic_facts/market_atomic_mainboard_compact_current.db`
- `RESEARCH_CURRENT_ROOT/selection/selection_research.db`
- `RESEARCH_CURRENT_ROOT/market_heat/fine_theme_heat_daily_v2.db`

同时保留显式环境变量覆盖：

- `ATOMIC_COMPACT_DB_PATH`
- `ATOMIC_MAINBOARD_DB_PATH`
- `SELECTION_DB_PATH`
- `FINE_THEME_HEAT_DB`
- `FINE_THEME_HEAT_V2_DB`

### 13.5 本轮验证证据

已执行并通过：

```text
pytest -q backend/tests/test_research_script_path_defaults.py
```

结果：

- `4 passed`

覆盖点：

- `build_research_watchlist_snapshot.py`
- `export_opportunity_trade_review_payload.py`
- `export_spark_pattern_research_payloads.py`
- `research_opportunity_discovery_model.py`

已执行并通过：

```text
python3 -m py_compile \
  backend/scripts/build_research_watchlist_snapshot.py \
  backend/scripts/export_opportunity_trade_review_payload.py \
  backend/scripts/export_spark_pattern_research_payloads.py \
  backend/scripts/research_opportunity_discovery_model.py
```

已追加执行并通过：

```text
pytest -q \
  backend/tests/test_market_data_path_config.py \
  backend/tests/test_spark_opportunity_exit_paths.py \
  backend/tests/test_research_script_path_defaults.py
```

结果：

- `7 passed`

已追加执行并通过：

```text
bash -n \
  ops/start_local_research_station.sh \
  ops/start_local_backend_with_atomic.sh \
  ops/run_model_feature_store_batch.sh \
  ops/export_market_data_inventory.sh
```

### 13.6 当前仍未处理的残留

这轮之后，剩余大头仍集中在：

- 大量专题分析 / page builder 脚本
- 研究 agent / backtest / report builder
- 文档中仍举例写死 `/Users/dong/Desktop/AIGC/market-data` 的地方

这些对象下一轮仍建议按专题批次清，而不是散改。

### 13.7 追加一批：market_heat 静态页 builder 默认路径收口

这轮继续阶段 C1，但仍保持同类批次处理，不散改。

本轮收口对象：

- `backend/scripts/build_hot_theme_trade_charts_page.py`
- `backend/scripts/build_hot_theme_trade_l2_window_page.py`
- `backend/scripts/build_fine_theme_heat_trend_page.py`
- `backend/scripts/build_fine_theme_heat_trend_2025_2026_top10.py`
- `backend/scripts/build_hot_theme_strong_momentum_case_page.py`
- `backend/scripts/build_hot_theme_april_rule_hit_page_2026.py`

收口方式：

- 项目根不再写死 `/Users/dong/Desktop/AIGC/market-live-terminal`
- 统一改成 `Path(__file__).resolve().parents[2]`
- atomic 默认统一改成：
  - `ATOMIC_COMPACT_DB_PATH`
  - `ATOMIC_MAINBOARD_DB_PATH`
  - 否则回退 `RESEARCH_CURRENT_ROOT/atomic_facts/market_atomic_mainboard_compact_current.db`
- 热点趋势页额外统一改成：
  - `FINE_THEME_HEAT_DB`
  - `TRADABLE_THEME_MAP_DB`
  - 否则回退 `RESEARCH_CURRENT_ROOT/market_heat/...`

这批脚本的共同边界：

- 都是静态页 / 回测图页 builder
- 默认读取 atomic / market_heat / theme map
- 不直接参与主服务请求链
- 适合按一个专题批次统一清理

本轮新增验证证据：

已执行并通过：

```text
pytest -q backend/tests/test_research_script_path_defaults.py
```

结果：

- `5 passed`

新增覆盖点：

- 上述 6 个 `market_heat` 静态页 builder 默认路径

已执行并通过：

```text
python3 -m py_compile \
  backend/scripts/build_hot_theme_trade_charts_page.py \
  backend/scripts/build_hot_theme_trade_l2_window_page.py \
  backend/scripts/build_fine_theme_heat_trend_page.py \
  backend/scripts/build_fine_theme_heat_trend_2025_2026_top10.py \
  backend/scripts/build_hot_theme_strong_momentum_case_page.py \
  backend/scripts/build_hot_theme_april_rule_hit_page_2026.py
```

已追加执行并通过：

```text
pytest -q \
  backend/tests/test_market_data_path_config.py \
  backend/tests/test_spark_opportunity_exit_paths.py \
  backend/tests/test_research_script_path_defaults.py
```

结果：

- `8 passed`

## 14. 2026-06-03 阶段 C1 第三批收口

### 14.1 本轮前置判断

本轮先按执行规划继续尝试 `B1a`：

- `ssh -o BatchMode=yes -o ConnectTimeout=8 zhangdong@192.168.3.43 'echo ok'`
  - 结果：`Operation timed out`
- `ssh -o BatchMode=yes -o ConnectTimeout=20 zhangdong@192.168.3.43 'echo ok'`
  - 结果：`Operation timed out`
- `curl --max-time 8 -fsS http://192.168.3.43:8080/api/health`
  - 结果：`Connection timed out`

因此本轮仍不能继续 `B1a` 实际上传，按执行规划继续切到 `C1`。

### 14.2 本轮收口范围

这轮继续按专题批次处理，不散改主服务。

本轮只收一类：

- aggressive 10cm 研究 agent / execution 研究脚本
- combined risk stack 研究脚本

共同目标：

- 默认跟随 `RESEARCH_CURRENT_ROOT`
- atomic 默认支持：
  - `ATOMIC_COMPACT_DB_PATH`
  - `ATOMIC_MAINBOARD_DB_PATH`
- selection 默认支持：
  - `SELECTION_DB_PATH`
- heat 默认支持：
  - `FINE_THEME_HEAT_DB`
  - `FINE_THEME_HEAT_V2_DB`

### 14.3 本轮已处理文件

- `backend/scripts/research_aggressive_10cm_low_position_agent.py`
- `backend/scripts/research_aggressive_10cm_hot_theme_agent.py`
- `backend/scripts/research_combined_risk_stack.py`
- `backend/scripts/research_aggressive_10cm_execution_agent.py`

### 14.4 本轮具体收口内容

#### 1. low position agent

`research_aggressive_10cm_low_position_agent.py` 现在默认改成：

- `RESEARCH_CURRENT_ROOT/atomic_facts/market_atomic_mainboard_compact_current.db`
- `RESEARCH_CURRENT_ROOT/selection/selection_research.db`
- `RESEARCH_CURRENT_ROOT/market_heat/fine_theme_heat_daily.db`

同时保留显式环境变量覆盖：

- `ATOMIC_COMPACT_DB_PATH`
- `ATOMIC_MAINBOARD_DB_PATH`
- `SELECTION_DB_PATH`
- `FINE_THEME_HEAT_DB`

另外：

- repo 内 `docs/` / `data/` 输出目录不再写死绝对路径
- 统一改成基于 `Path(__file__).resolve().parents[2]`

#### 2. hot theme agent

`research_aggressive_10cm_hot_theme_agent.py` 现在默认改成：

- `RESEARCH_CURRENT_ROOT/market_heat/fine_theme_heat_daily.db`
- `RESEARCH_CURRENT_ROOT/atomic_facts/market_atomic_mainboard_compact_current.db`

同时保留显式环境变量覆盖：

- `FINE_THEME_HEAT_DB`
- `ATOMIC_COMPACT_DB_PATH`
- `ATOMIC_MAINBOARD_DB_PATH`

#### 3. combined risk stack

`research_combined_risk_stack.py` 现在默认 atomic 改成：

- `RESEARCH_CURRENT_ROOT/atomic_facts/market_atomic_mainboard_compact_current.db`

同时保留显式环境变量覆盖：

- `ATOMIC_COMPACT_DB_PATH`
- `ATOMIC_MAINBOARD_DB_PATH`

#### 4. execution agent

`research_aggressive_10cm_execution_agent.py` 现在默认改成：

- atomic：
  - `RESEARCH_CURRENT_ROOT/atomic_facts/market_atomic_mainboard_compact_current.db`
- selection：
  - `RESEARCH_CURRENT_ROOT/selection/selection_research.db`
- heat v2：
  - `RESEARCH_CURRENT_ROOT/market_heat/fine_theme_heat_daily_v2.db`

同时保留显式环境变量覆盖：

- `ATOMIC_COMPACT_DB_PATH`
- `ATOMIC_MAINBOARD_DB_PATH`
- `SELECTION_DB_PATH`
- `FINE_THEME_HEAT_DB`
- `FINE_THEME_HEAT_V2_DB`

并且：

- `summary_payload["data_sources"]` 也不再写死 Mac 绝对路径

### 14.5 本轮验证证据

已执行并通过：

```text
pytest -q backend/tests/test_research_script_path_defaults.py
```

结果：

- `6 passed`

新增覆盖点：

- `research_aggressive_10cm_low_position_agent.py`
- `research_aggressive_10cm_hot_theme_agent.py`
- `research_combined_risk_stack.py`
- `research_aggressive_10cm_execution_agent.py`

已执行并通过：

```text
python3 -m py_compile \
  backend/scripts/research_aggressive_10cm_low_position_agent.py \
  backend/scripts/research_aggressive_10cm_hot_theme_agent.py \
  backend/scripts/research_combined_risk_stack.py \
  backend/scripts/research_aggressive_10cm_execution_agent.py
```

已追加执行并通过：

```text
pytest -q \
  backend/tests/test_market_data_path_config.py \
  backend/tests/test_spark_opportunity_exit_paths.py \
  backend/tests/test_research_script_path_defaults.py
```

结果：

- `9 passed`

已确认：

- 上述 4 个脚本内已不存在 `/Users/dong/Desktop/AIGC/market-data` 的硬编码默认路径

### 14.6 当前结论

这轮 `C1` 的新增结果是：

- 研究脚本又收了一批高命中旧路径
- `B1a` 继续被 NAS 网络不可达阻塞
- 但等 NAS 恢复后，当前下一目标仍然是：
  - `SSH_CONNECT_TIMEOUT=20 bash ops/upload_nas_research_release.sh nas_release_20260602_online`

## 15. 2026-06-03 阶段 C1 第四批收口

### 15.1 本轮前置判断

在继续离线收口前，本轮再次复测了 NAS 可达性：

- `ssh -o BatchMode=yes -o ConnectTimeout=8 zhangdong@192.168.3.43 'echo ok'`
  - 结果：`Operation timed out`
- `ssh -o BatchMode=yes -o ConnectTimeout=20 zhangdong@192.168.3.43 'echo ok'`
  - 结果：`Operation timed out`
- `curl --max-time 8 -fsS http://192.168.3.43:8080/api/health`
  - 结果：`Connection timed out`

因此本轮仍按执行规划继续 `C1`，不空等 `B1a`。

### 15.2 本轮收口范围

这轮继续按同一专题批次处理：

- `market_heat` 研究 / 分析 / 回测脚本

共同目标：

- 输出目录不再写死仓库绝对路径
- heat 默认跟随 `RESEARCH_CURRENT_ROOT/market_heat/...`
- atomic 默认跟随 `RESEARCH_CURRENT_ROOT/atomic_facts/...`
- theme map 默认跟随 `RESEARCH_CURRENT_ROOT/market_heat/tradable_theme_map.db`

### 15.3 本轮已处理文件

- `backend/scripts/analyze_theme_lead_stock_lag_strategy.py`
- `backend/scripts/analyze_hot_theme_big_mover_l2_precondition.py`
- `backend/scripts/backtest_hot_theme_monthly_samples.py`
- `backend/scripts/backtest_hot_theme_rule_pack_portfolio_2025.py`
- `backend/scripts/research_combined_risk_stack_robustness.py`

### 15.4 本轮具体收口内容

#### 1. lead-lag 主题滞后股分析

`analyze_theme_lead_stock_lag_strategy.py` 现在默认改成：

- `FINE_THEME_HEAT_DB`
- `TRADABLE_THEME_MAP_DB`
- `ATOMIC_COMPACT_DB_PATH`
- `ATOMIC_MAINBOARD_DB_PATH`

否则统一回退到：

- `RESEARCH_CURRENT_ROOT/market_heat/fine_theme_heat_daily.db`
- `RESEARCH_CURRENT_ROOT/market_heat/tradable_theme_map.db`
- `RESEARCH_CURRENT_ROOT/atomic_facts/market_atomic_mainboard_compact_current.db`

并且：

- 项目根不再写死 `/Users/dong/Desktop/AIGC/market-live-terminal`

#### 2. big mover L2 前置条件分析

`analyze_hot_theme_big_mover_l2_precondition.py` 现在默认改成：

- `FINE_THEME_HEAT_DB`
- `ATOMIC_COMPACT_DB_PATH`
- `ATOMIC_MAINBOARD_DB_PATH`

否则回退到：

- `RESEARCH_CURRENT_ROOT/market_heat/fine_theme_heat_daily.db`
- `RESEARCH_CURRENT_ROOT/atomic_facts/market_atomic_mainboard_compact_current.db`

#### 3. 月度样本回测

`backtest_hot_theme_monthly_samples.py` 现在默认改成：

- `FINE_THEME_HEAT_DB`
- `ATOMIC_COMPACT_DB_PATH`
- `ATOMIC_MAINBOARD_DB_PATH`

否则回退到：

- `RESEARCH_CURRENT_ROOT/market_heat/fine_theme_heat_daily.db`
- `RESEARCH_CURRENT_ROOT/atomic_facts/market_atomic_mainboard_compact_current.db`

#### 4. 规则包组合回测

`backtest_hot_theme_rule_pack_portfolio_2025.py` 现在默认 atomic 改成：

- `ATOMIC_COMPACT_DB_PATH`
- `ATOMIC_MAINBOARD_DB_PATH`

否则回退到：

- `RESEARCH_CURRENT_ROOT/atomic_facts/market_atomic_mainboard_compact_current.db`

并且：

- 项目根不再写死 Mac 仓库绝对路径

#### 5. combined risk stack robustness

`research_combined_risk_stack_robustness.py` 现在默认 atomic 改成：

- `ATOMIC_COMPACT_DB_PATH`
- `ATOMIC_MAINBOARD_DB_PATH`

否则回退到：

- `RESEARCH_CURRENT_ROOT/atomic_facts/market_atomic_mainboard_compact_current.db`

### 15.5 本轮验证证据

已执行并通过：

```text
pytest -q backend/tests/test_research_script_path_defaults.py
```

结果：

- `7 passed`

新增覆盖点：

- `analyze_theme_lead_stock_lag_strategy.py`
- `analyze_hot_theme_big_mover_l2_precondition.py`
- `backtest_hot_theme_monthly_samples.py`
- `backtest_hot_theme_rule_pack_portfolio_2025.py`
- `research_combined_risk_stack_robustness.py`

已执行并通过：

```text
python3 -m py_compile \
  backend/scripts/analyze_theme_lead_stock_lag_strategy.py \
  backend/scripts/analyze_hot_theme_big_mover_l2_precondition.py \
  backend/scripts/backtest_hot_theme_monthly_samples.py \
  backend/scripts/backtest_hot_theme_rule_pack_portfolio_2025.py \
  backend/scripts/research_combined_risk_stack_robustness.py
```

已追加执行并通过：

```text
pytest -q \
  backend/tests/test_market_data_path_config.py \
  backend/tests/test_spark_opportunity_exit_paths.py \
  backend/tests/test_research_script_path_defaults.py
```

结果：

- `10 passed`

已确认：

- 上述 5 个脚本内已不存在 `/Users/dong/Desktop/AIGC/market-data` 的硬编码默认路径

### 15.6 当前结论

这轮 `C1` 又收了一批 `market_heat` 研究/回测脚本。

但当前总基线已经变化，不能再把阶段 C 理解成“等 NAS 可达后再说”。

截至 `2026-06-04` 当前成立的结论是：

- NAS 查询主链已经切到 `research/current`
- 当前 `research/current` 是 bootstrap current，不是最终治理完成态
- NAS 上的正式研究数据仍落后于本地正式库
- 阶段 C 现在既服务 Mac 本地目录治理，也服务 NAS 运行态目录治理
- 后续 `C1` 要重点回答的不只是“哪些脚本还有硬编码”，还包括：
  - NAS 上哪些目录是正式库
  - 哪些目录是缓存
  - 哪些目录是研究产物
  - Windows 跑数后的同步入口最终要落在哪一层

因此阶段 C 下一批建议顺序更新为：

1. 继续清理剩余高命中硬编码路径
2. 明确 NAS `live / research/current / cache / artifacts / incoming` 的最终落位边界
3. 配合 `B1-补` 和 `B2`，把“缺失数据补齐”和“未来每日同步”纳入同一套目录口径
