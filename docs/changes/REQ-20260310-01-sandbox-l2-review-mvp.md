# REQ-20260310-01-sandbox-l2-review-mvp

## 1. 基本信息
- 标题：沙盒 L2 资金复盘 MVP（全隔离 ETL + API + 前端）
- 状态：DONE（可用：DRAFT/RELEASE_READY/RELEASED_PENDING_SMOKE/DONE）
- 负责人：后端 AI
- 关联 Task ID：`CHG-20260310-02`
- 关联 CAP：`CAP-SANDBOX-REVIEW`, `CAP-HISTORY-30M`
- 关联 STG：`STG-20260310-01-sandbox-l2-review`

## 2. 背景与目标
- 在不污染生产 `market_data.db`、不干扰既有核心路由的前提下，验证 L1（单笔阈值）与 L2（母单还原）资金口径差异。
- 重点股票窗口：利通电子（`sh603629`）2026-01-01 至 2026-02-28。
- 图形目标：主图 5 分钟蜡烛图 + 多副图同轴复盘，覆盖主力/超大绝对买卖、净流入分层与净流比对比。

## 3. 方案与边界
- 做什么：
  - 新增独立 ETL 脚本 `backend/scripts/sandbox_review_etl.py`，写入 `data/sandbox_review.db`。
  - 新增独立 API `GET /api/sandbox/review_data`，仅查询沙盒 DB。
  - 新增前端页面 `/sandbox-review` 与首页入口“复盘”。
  - 先单日试跑验证，后全量刷数。
- 不做什么：
  - 不修改生产 `market_data.db` 表结构与数据。
  - 不变更现有 `/api/realtime/*`、`/api/history/*` 的行为与口径。
  - 不做生产发布与归档收口（本卡完成后再进入归档流程）。

## 4. 执行步骤（按顺序）
1. 文档先行：建卡并在 `02/03` 登记拟变更点与契约。
2. 实施沙盒 ETL 与独立 DB 查询模块。
3. 实施 `/api/sandbox/review_data` 路由并接入主应用。
4. 实施前端 `/sandbox-review` 页面与首页入口。
5. 单日试跑（自动探测首个可用交易日）并验证。
6. 通过后执行全量刷数并回填结果与风险。

## 5. 验收标准（Given/When/Then，绝对时间）
- Given `2026-03-11 11:00`，When 请求 `GET /api/sandbox/review_data?symbol=sh603629&start_date=2026-01-01&end_date=2026-02-28`，Then 返回 `code=200` 且不再出现 `HTTP 404`。
- Given `2026-03-11 11:05`，When 沙盒接口命中 1-2月真实数据，Then 返回区间覆盖 `2026-01-05~2026-02-27`，且数据升序、无 3 月记录。
- Given `2026-03-11 11:10`，When 检测到“整日重复分时”异常，Then 接口自动剔除重复日并在 `message` 标注异常日期对（当前为 `2026-02-23≈2026-02-11`）。
- Given `2026-03-11 11:15`，When 打开 `/sandbox-review`，Then 页面仅展示 API 真实结果；接口异常时只显示错误态，不回退本地预置数据。

## 6. 风险与回滚
- 风险：
  - L2 CSV 字段命名不统一（中英文字段差异）导致部分文件识别失败。
  - 成交量单位“手/股”混用导致金额误判。
  - 历史 ZIP 体量大导致全量刷数耗时较长。
- 回滚：
  - 移除 `/api/sandbox/*` 路由挂载；
  - 下线 `/sandbox-review` 入口与页面；
  - 删除 `data/sandbox_review.db`（仅 sandbox 文件，不影响生产库）。

## 7. 结果回填
- 实际改动：
  - 新增 ETL：`backend/scripts/sandbox_review_etl.py`（支持 `pilot/full`，默认独立写入 `sandbox_review.db`，金额单位自动判定）。
  - ETL 增加 L2 严格模式：缺失 `BuyOrderID/SaleOrderID` 直接失败（不降级近似），并在日志输出缺失文件来源。
  - ETL 增加 symbol 级清理与工作日过滤：每次运行先清理 `review_5m_bars.symbol` 历史数据，避免混入 3 月旧数据与周末镜像。
  - 新增沙盒 DB 模块：`backend/app/db/sandbox_review_db.py`（独立连接与 schema）。
  - 新增接口：`backend/app/routers/sandbox_review.py`，路径 `GET /api/sandbox/review_data`、`POST /api/sandbox/run_etl`、`GET /api/sandbox/etl_status`。
  - 后端挂载：`backend/app/main.py` 新增 `/api/sandbox/*` 路由注册。
  - 前端页面改版：`src/components/sandbox/SandboxReviewPage.tsx` 改为 Fail-Closed（接口失败/空数据不再回退预置数据）；保留双端滑块横向拖动 + 窗口快捷（1/3/5/20/60日/全部）。
  - 前端动态聚合升级：支持 `5m/15m/30m/60m/1d`；自动规则调整为 `1日=5m, 3/5日=15m, 20日=60m, 60日/全部=1d`，并新增手动粒度切换（自动 | 5m | 15m | 30m | 60m | 1d）。
  - 服务层改造：`src/services/stockService.ts` 的 `fetchSandboxReviewData` 不再吞异常为空数组，改为区分“接口异常”与“空数据”。
  - 服务层容错：`fetchSandboxReviewData` 新增路由兼容探测（`/api/sandbox/review_data` → `/api/review_data` → `/sandbox/review_data`），用于定位后端版本/路由前缀不一致导致的 404。
  - 数据质量修复：`GET /api/sandbox/review_data` 在返回前执行“整日重复分时”去重；若发现重复日（如 `2026-02-23` 与 `2026-02-11` 完全一致）会自动剔除后者并在 `message` 标注。
  - 指标扩展：沙盒表 `review_5m_bars` 增加 `total_amount`（5分钟总成交额）；ETL 同步写入并支持旧库自动补列迁移。
  - 新增统计脚本：`backend/scripts/sandbox_correlation_validation.py`，输出 L1/L2 与当期/下一根涨跌幅 Pearson 相关系数，以及 `l2_activity_ratio>30%` 条件相关系数。
  - 前端新增相关性区：在复盘页底部新增两张散点图（L1 vs price_return、L2 vs price_return）及统计结论卡片，活跃度映射点大小/颜色。
  - 复盘页 V4 升级为 6 图同屏（单 ECharts）：K线、主力绝对、超大绝对、主力净流、超大净流、净流比，统一 `dataZoom` 与十字光标联动。
  - 主力/超大绝对图新增活跃度双线：`L1/L2 activity = (buy+sell)/total_amount*100`，右侧副轴显示 `%`（允许 >100%）。
  - 净流入拆分为两张面积图：主力净流与超大净流分别独立，正负方向分色（L2 正紫负深黄，L1 正红负绿）。
  - 新增净流比图：`l1/l2 net ratio = (main_net + super_net)/total_amount*100`，与资金图同时间轴。
  - 可读性增强：各资金子图左侧 y 轴加入中文名称，tooltip 自动区分金额 `w` 与百分比 `%`。
  - 新增“锚点累计模式”V1：点击 K 线设置锚点时间，累计终点随当前滑块右边界变化。
  - 累计区改为四张独立图：`主力L2`、`主力L1`、`超大L2`、`超大L1`，避免同图重叠导致可读性下降。
  - 四张累计图统一改为“单累计曲线 + 正负面积分色”语义：每图只保留一条累计净流曲线，正负用面积颜色区分（不再双曲线对比）。
  - 累计面积层去除边缘线，仅保留面积填充；主曲线用于表达累计路径。
  - 复盘主图高度提升为可滚动长画布（超过一屏），以提升多副图场景下的人眼辨识度。
  - 累计模式交互：工具区新增“锚点累计模式开关 / 清除锚点 / 当前锚点时间”，未设置锚点时累计图区显示中文空态提示。
  - 累计模式可视增强：在主图与各子图加入锚点竖线（markLine）对齐参考，支持粒度切换后按时间戳重新对齐。
  - 数值展示修正：百分比坐标轴统一显示整数百分号（无小数）。
  - 文档治理收口：完成变更卡回填、`02/03/07` 同步更新，并新增 `CHG-20260311-08` 非生产发布治理记录。
  - 非生产分支策略：采用 `codex/sandbox-review-mvp` + Draft PR 评审联调；明确排除 `data/*.db`、`data/sandbox_exports/*.csv`、`dist/`、`.venv/` 与临时异常文件。
- 新增前端类型与服务变更：`src/types.ts`、`src/services/stockService.ts`。
- 新增测试：`backend/tests/test_sandbox_review.py`（含重复交易日剔除与 `total_amount` 返回字段验证）。
- 验证结果：
  - 自动化：`python3 -m pytest backend/tests/test_sandbox_review.py -q` 通过（8/8）。
  - 前端构建：`npm run build` 通过。
  - 前端构建（V4改版后）：`2026-03-11 14:05` 执行 `npm run build` 通过。
  - 前端构建（锚点累计V1）：`2026-03-11 15:20` 执行 `npm run build` 通过。
  - 前端构建（累计四图拆分 + 单曲线面积语义）：`2026-03-11 16:10` 执行 `npm run build` 通过。
  - 自动化回归：`2026-03-11 17:18` 执行 `python3 -m pytest backend/tests/test_sandbox_review.py -q` 通过（8/8）。
  - 前端构建回归：`2026-03-11 17:19` 执行 `npm run build` 通过。
  - 真实全量跑数：`2026-03-11 00:25` 在 Windows `D:\\MarketData` 执行 `2026-01-01~2026-02-28` 全量 ETL 成功，写入 `1701` 条 5m bars。
  - `2026-03-11 12:55` 在 Windows 重跑 `sandbox_review_etl.py`（新版含 `total_amount`）成功并回传本地；校验 `total_amount<=0` 行数为 `0`。
  - SQL 校验：`symbol=sh603629` 的 `source_date` 范围为 `2026-01-05~2026-02-27`，`2026-03-*` 行数为 `0`。
  - 本地接口校验：`/api/sandbox/review_data?symbol=sh603629&start_date=2026-01-01&end_date=2026-02-28` 返回 `code=200` 且 `1701` 条。
  - 统计脚本校验：`python3 -m backend.scripts.sandbox_correlation_validation` 可运行并输出三组相关性结果与样本统计。
  - 相关性实测（剔除重复日 `2026-02-23≈2026-02-11` 后）：
    - 同期解释力：`corr(l1_net, price_return)=0.250808`，`corr(l2_net, price_return)=0.379811`
    - 下一根预测力：`corr(l1_net, next_price_return)=0.061336`，`corr(l2_net, next_price_return)=-0.006075`
    - 条件过滤（`l2_activity_ratio>30%`）：`corr(l2_net, next_price_return)=-0.006440`，样本占比 `93.03%`
  - 异常修复：`2026-03-11 01:05` 针对 `2026-02-03/02-04` 数量级异常完成量纲判定修正（`ratio100` 阈值放宽 + 中位数兜底），重新全量刷数后 `2026-02-04` 金额量级恢复到同月可比区间。
- 遗留问题：
  - `src/components/sandbox/presetReviewData.ts` 仍保留在仓库作为离线留档，当前页面已解除引用；后续可按归档策略移至 `docs/archive` 或测试夹具目录。

## 8. 归档信息
- 归档时间：
- Archive ID：
- 归档路径：
