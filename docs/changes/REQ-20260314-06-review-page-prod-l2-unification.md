# REQ-20260314-06-review-page-prod-l2-unification

## 1. 基本信息
- 标题：Phase 4｜复盘页并库到生产 L2 正式底座
- 状态：DONE
- 负责人：Codex / 后端 AI
- 关联 Task ID：`CHG-20260314-06`
- 关联 CAP：`CAP-L2-HISTORY-FOUNDATION`, `CAP-SANDBOX-REVIEW`
- 关联 STG：`STG-20260314-01`

## 2. 背景与目标
- 当前复盘页原先主要依赖 sandbox 独立数据域，且前端写死 `2025-01-01 ~ 2026-02-28` 查询窗口；长期若继续双正式库并行，维护成本和口径漂移风险都过高。
- 本阶段目标是把复盘页正式主链路切到生产 `history_5m_l2 / history_daily_l2`，同时保留 sandbox 作为实验入口。

## 3. 方案与边界
- 做什么：
  - 新增正式元数据表 `stock_universe_meta`，承接 `symbol -> name + market_cap + as_of_date`；
  - 新增正式复盘接口 `/api/review/pool` 与 `/api/review/data`，返回当前复盘页可直接消费的兼容结构；
  - 复盘页前端切换到正式接口，并改为按当前股票真实 `min_date/max_date` 动态限制日期；
  - 新增单股票后台补历史脚本 `backend/scripts/promote_review_symbol_history.py`，支持 `auto/promote_existing/rebuild_from_raw` 三档；
  - 保留 sandbox `/api/sandbox/*` 与 `/sandbox-review` 路由，但正式主链路不再读 sandbox 接口。
- 不做什么：
  - 本阶段不新增前端“补历史”按钮；
  - 不强制删除现有 sandbox 代码、数据库与实验入口；
  - 不在本卡内实现 `stock_universe_meta` 的定时刷新调度，仅提供刷新脚本与表结构。

## 4. 执行步骤
1. 在生产正式库补 `stock_universe_meta` schema 与查询 helper。
2. 落地 `/api/review/pool`、`/api/review/data`，统一从正式 `history_5m_l2 / history_daily_l2` 出数。
3. 复盘页前端改读正式接口，移除写死日期窗口，改为动态 `min_date/max_date`。
4. 保留 sandbox 作为实验入口，不再承担正式复盘主链路。
5. 新增后台脚本能力：
   - `backend/scripts/refresh_stock_universe_meta.py`
   - `backend/scripts/promote_review_symbol_history.py`

## 5. 验收标准（Given/When/Then）
- Given `2026-03-21 10:00`，When 打开复盘页默认股票 `sh603629`，Then 页面应从 `/api/review/data` 读取正式历史，并允许查询至该股票正式库 `max_date`。
- Given `2026-03-21 10:05`，When 查询 `sz000833` 的 `2025-01-02 ~ 2026-03-20`，Then 前段可来自历史池提升、后段可来自正式日更库，页面时间轴连续。
- Given `2026-03-21 10:10`，When 当前股票真实覆盖范围为 `2026-03-02 ~ 2026-03-20`，Then 日期输入只允许该区间，不再伪造更早日期。
- Given sandbox V2 已存在 `symbols/{symbol}.db`，When 执行 `promote_review_symbol_history.py --mode auto`，Then 应优先走 `promote_existing` 快路径并写入正式库。

## 6. 风险与回滚
- 风险：若复盘页长期不并库，后续每次口径修复都要双写双验，代价持续放大。
- 回滚：sandbox 继续保留，必要时可作为迁移过渡期的兜底实验环境。

## 7. 结果回填
- 实际改动：
  - 已在 `history` 正式库补齐 `stock_universe_meta` schema；
  - 已新增 `/api/review/pool` 与 `/api/review/data`；
  - 复盘页已切到正式接口，股票池与日期边界改为动态真实覆盖范围；
  - 已新增正式元数据刷新脚本与单股票后台补历史脚本。
- 验证结果：
  - `python3 -m pytest -q backend/tests/test_review_router.py backend/tests/test_promote_review_symbol_history.py`
  - `python3 -m pytest -q backend/tests/test_sandbox_review_v2.py backend/tests/test_history_multiframe_router.py`
  - `npm run check:baseline`
- 遗留问题：
  - 首期只提供 `stock_universe_meta` 刷新脚本，尚未接定时调度；
  - 单股票补历史的 slow path 仍依赖本地原始历史包可访问；
  - sandbox 入口继续保留，用于实验/验真，不作为正式主链路。

## 8. 归档信息
- 归档时间：
- Archive ID：
- 归档路径：
