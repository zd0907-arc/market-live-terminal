# MOD-20260619-01 本地收口：三端同步前代码、文档与研究产物整理

日期：2026-06-19
状态：`LOCAL_CLOSED_PENDING_REMOTE_AND_THREE_END_SYNC`
主路径：`/Users/dong/ZhangData/market-live-terminal`

## 结论

本次只做 Mac 正式仓库的本地收口：把最近几天散落的开发、文档和 Agent 研究产物拆成独立 Git 提交包。未执行 GitHub/NAS Gitea 双推，未执行 Mac/NAS/Windows 三端数据同步，也未改 NAS 部署目录。

当前本地 `main` 相对 `origin/main` 与 `nas/main` 均领先 3 个业务提交；本文档提交后将领先 4 个提交。

## 已收口提交包

### 1. 日跑与 L2 同步链路加固

提交：`a4f9fe6 Harden daily run and L2 sync closeout`

业务目标：让每日跑数完成标准更明确，把 Windows 跑数、Mac live 补库、NAS 同步门禁、模型产物检查和 L2 增量回补串得更稳。

包含内容：

- 日跑 wrapper 默认进入 `--sync-nas` 口径，`--skip-nas` 仅允许显式排障。
- Windows atomic 侧增加流式解压处理、postclose seed L2 artifact、seed 后复用已解压目录。
- Mac live L2 本地补库增加恢复逻辑和完成判定。
- NAS 同步前增加 live 与市场水位同步门禁。
- 选股模型和双轨退出模型增加本地必需产物检查。
- 市场热点详情在 atomic 只覆盖最新日时，可回退读取 live L2 历史补齐成分股走势和涨停/炸板估算。
- 文档同步更新正式日跑入口、NAS 同步边界、恢复遗漏模型目录说明。

### 2. 市场温度雷达研究页

提交：`d0dfcf0 Add market temperature radar research page`

业务目标：新增一个盘后宏观行情感知页，用于观察市场温度、赛道强度、交易重心迁移和主题生命周期。

包含内容：

- 新增前端页面 `/market-temperature`。
- 首页增加市场温度入口。
- 新增后端只读接口 `GET /api/market_temperature/snapshot`。
- 接口读取 `model_market_state_daily_v1`，输出成交额、市场广度、涨跌停、指数表现和热点支撑字段。
- 正式吸收旧桌面实验目录中的产品定义文档：`docs/selection/market_temperature_product_definition.md`。
- 新增实现评估与需求文档：`docs/selection/market_temperature_research_and_requirements.md`。

未迁入内容：

- 旧桌面路径 `market-temperature-lab/index.html` 是一次性 HTML mock，不进入正式仓库；正式页面已由 React 实现承接。

### 3. 星标公司金融 Agent 候选研究产物归档

提交：`9ef3da4 Archive starred watchlist agent research runs`

业务目标：保留 2026-06-17 批量星标公司研究结果，作为后续公司卡片和详情页落库前的候选研究资料。

包含内容：

- 批次：`agentic_finance_agents/runs/20260617-0003-starred-watchlist-batch`
- 公司候选：
  - `sh603301` 振德医疗
  - `sz002600` 领益智造
  - `sh600693` 东百集团
  - `sz000833` 粤桂股份
  - `sh603629` 利通电子
  - `sz000759` 中百集团
  - `sz002137` 实益达

边界：

- 这些产物状态仍是 `candidate_only`。
- 未写入正式 `company_research.db`。
- 未改选股页公司卡片真实数据源。

## 验证结果

已执行：

```bash
git diff --check
python3 -m pytest backend/tests/test_export_l2_day_delta.py backend/tests/test_run_postclose_l2_daily.py backend/tests/test_run_daily_new_framework_auto.py backend/tests/test_market_heat_forecast.py -q
npm run build
```

结果：

- 补丁检查通过。
- 后端关键测试：`28 passed`。
- 前端生产构建通过。

## 数据层观察

Mac 本地正式数据目录 `/Users/dong/ZhangData/market-data` 已出现 2026-06-17 增量：

- `research/current/atomic_facts/market_atomic_mainboard_compact_current.db` 覆盖到 `2026-06-17`。
- `selection/model_feature_store.db` 中 `model_market_state_daily_v1` 覆盖到 `2026-06-17`。
- `market_heat/fine_theme_heat_daily_v2.db` 覆盖到 `2026-06-17`。
- `live/market_data.db` 的 `history_daily_l2` 与 `history_5m_l2` 覆盖到 `2026-06-17`。
- `selection_research.db` 中 2026-06-16、2026-06-17 活跃来源均有 success 运行记录；2026-06-15 有一次 spark 失败记录，但同日也有 success 记录。

这些数据不进入 Git。本次没有把这些数据库同步到 NAS 或 Windows。

## 三端同步前置状态

当前停在这里：

1. Mac 本地代码和文档已经拆包收口。
2. Mac 本地数据已有 2026-06-17 新增结果。
3. GitHub `origin/main` 与 NAS Gitea `nas/main` 尚未接收本次本地提交。
4. NAS app 部署目录未更新。
5. Windows 数据目录未改动。

后续用户确认后，建议按以下顺序执行：

1. 代码双推：`nas/main` 与 `origin/main` 都更新到本地 `HEAD` 并验真。
2. NAS 部署目录核对：确认 Gitea main、NAS app 工作目录、运行 compose 使用的代码一致。
3. 数据差异核对：比较 Mac `/Users/dong/ZhangData/market-data` 与 NAS `/volume1/docker/market-live-terminal/data` 的 `live`、`market_heat`、`selection`、`cache`、`research/current` 关键目录。
4. 数据同步：只同步线上功能需要的增量，继续保护 NAS/Windows 上的全量大库，不用 Mac 轻量 atomic 覆盖全量库。
5. 三端冒烟：Mac 本地、NAS 线上、Windows 跑数侧分别检查 2026-06-17 的复盘、盯盘、首页历史、选股候选、市场热点、市场温度接口。
