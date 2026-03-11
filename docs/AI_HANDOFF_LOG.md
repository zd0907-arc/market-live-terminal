# AI_HANDOFF_LOG（短日志）
> 规则：每条日志必须包含 Task ID、CAP ID、结论、阻塞/风险、链接；每条不超过 8 行要点。
>
> 历史长日志归档：`docs/archive/AI_HANDOFF_LOG_LEGACY_2026-03-09.md`

---

## 2026-03-11 17:10 | 后端 AI
- Task ID: `CHG-20260311-08`
- CAP: `CAP-SANDBOX-REVIEW`
- 结论: 完成复盘模块文档收口（变更卡 + `02/03/07` 回填），并按 `NO-PROD` 策略创建非生产分支 `codex/sandbox-review-mvp` 供 Draft PR 评审联调。
- 风险: 沙盒真实数据准备仍受阻塞项 `T-005` 约束，当前不进入生产发布与归档关闭。
- 链接: `docs/changes/REQ-20260310-01-sandbox-l2-review-mvp.md`, `docs/02_BUSINESS_DOMAIN.md`, `docs/03_DATA_CONTRACTS.md`, `docs/07_PENDING_TODO.md`

## 2026-03-11 15:25 | 后端 AI
- Task ID: `CHG-20260311-07`
- CAP: `CAP-SANDBOX-REVIEW`
- 结论: 已实现复盘页“锚点累计模式”V1：开启后点选 K 线设锚点，新增主力/超大累计净流两图（面积），并随同一 dataZoom 时间轴联动；锚点未设置时累计图区显示中文空态提示。
- 风险: 当前 V1 不做自动“离场点”判定，仅提供可视化参考；若需量化离场时刻需在 V2 增加规则引擎。
- 链接: `src/components/sandbox/SandboxReviewPage.tsx`, `docs/changes/REQ-20260310-01-sandbox-l2-review-mvp.md`, `docs/02_BUSINESS_DOMAIN.md`, `docs/03_DATA_CONTRACTS.md`

## 2026-03-11 14:10 | 后端 AI
- Task ID: `CHG-20260311-06`
- CAP: `CAP-SANDBOX-REVIEW`
- 结论: 复盘页完成 V4 前端增强：主图区升级为 6 图同屏；主力/超大柱图新增 L1/L2 活跃度线；净流入拆分为主力/超大两张面积图；新增 L1/L2 净流比图，保持统一时间轴联动。
- 风险: 六图同屏下图例较多，小屏设备首屏信息密度高；后续可考虑“图例分组折叠”进一步优化可读性。
- 链接: `src/components/sandbox/SandboxReviewPage.tsx`, `docs/changes/REQ-20260310-01-sandbox-l2-review-mvp.md`, `docs/02_BUSINESS_DOMAIN.md`, `docs/03_DATA_CONTRACTS.md`

## 2026-03-11 12:40 | 后端 AI
- Task ID: `CHG-20260311-05`
- CAP: `CAP-SANDBOX-REVIEW`
- 结论: 已实现并完成真实数据验证闭环：Windows `D:\\MarketData` 已重跑 2026年1-2月 ETL（1701条，含 `total_amount`），并回传本地库；相关性脚本与页面散点图均可展示有效统计结果。
- 风险: 结果显示“同期解释力”L2显著高于L1，但“下一根预测力”在当前样本上不显著；需后续扩展更多标的/周期验证稳健性。
- 链接: `backend/scripts/sandbox_review_etl.py`, `backend/scripts/sandbox_correlation_validation.py`, `src/components/sandbox/SandboxReviewPage.tsx`, `docs/changes/REQ-20260310-01-sandbox-l2-review-mvp.md`

## 2026-03-11 11:20 | 后端 AI
- Task ID: `CHG-20260311-04`
- CAP: `CAP-SANDBOX-REVIEW`
- 结论: 修复复盘页 HTTP 404 诊断能力（前端增加 sandbox 路由兼容探测）；后端新增“整日重复分时”自动剔除，已定位并标记问题日 `2026-02-23≈2026-02-11`。
- 风险: 若源数据本身重复，当前策略为“保留先出现交易日、剔除后出现交易日”，需后续在源目录侧复核原始CSV。
- 链接: `src/services/stockService.ts`, `backend/app/routers/sandbox_review.py`, `backend/tests/test_sandbox_review.py`, `docs/changes/REQ-20260310-01-sandbox-l2-review-mvp.md`

## 2026-03-11 10:30 | 后端 AI
- Task ID: `CHG-20260311-03`
- CAP: `CAP-SANDBOX-REVIEW`
- 结论: 复盘页完成可信度修正（Fail-Closed）：移除“接口失败回退预置数据”逻辑；接口异常与空数据分态展示。聚合升级为自动+手动粒度切换，新增 `60m/1d`，自动规则为 `1日=5m,3/5日=15m,20日=60m,60日/全部=1d`。
- 风险: `presetReviewData.ts` 仍保留在仓库未删除（已不再被页面引用），建议后续归档以减小维护噪音。
- 链接: `src/components/sandbox/SandboxReviewPage.tsx`, `src/services/stockService.ts`, `src/types.ts`, `docs/changes/REQ-20260310-01-sandbox-l2-review-mvp.md`

## 2026-03-11 01:10 | 后端 AI
- Task ID: `CHG-20260311-02`
- CAP: `CAP-SANDBOX-REVIEW`
- 结论: 已定位并修复 2月3/4 资金量级异常；根因是成交量单位判定阈值过严导致 `2026-02-04` 被误判成 `x100`。修复后已在 Windows 真数据源重跑并回传 `sandbox_review.db`。
- 风险: 预置数据文件较大导致 `SandboxReviewPage` chunk 体积 >500KB（功能正常，后续可做按需加载优化）。
- 链接: `backend/scripts/sandbox_review_etl.py`, `data/sandbox_review.db`, `src/components/sandbox/presetReviewData.ts`, `docs/changes/REQ-20260310-01-sandbox-l2-review-mvp.md`

## 2026-03-11 00:35 | 后端 AI
- Task ID: `CHG-20260311-01`
- CAP: `CAP-SANDBOX-REVIEW`
- 结论: 已完成 `sh603629` 在 `2026-01-01~2026-02-28` 的真实全量刷数（严格 L2，1701 条 5m bars），页面改为双端滑块拖动 + 动态聚合（5m/15m/30m）+ 20日/60日窗口。
- 风险: `2026-02-04` 单日量纲检测触发 `x100`，建议后续对该日原始文件做人工复核。
- 链接: `backend/scripts/sandbox_review_etl.py`, `data/sandbox_review.db`, `src/components/sandbox/SandboxReviewPage.tsx`, `docs/changes/REQ-20260310-01-sandbox-l2-review-mvp.md`

## 2026-03-10 18:25 | 后端 AI
- Task ID: `CHG-20260310-02`
- CAP: `CAP-SANDBOX-REVIEW`, `CAP-HISTORY-30M`
- 结论: 已完成沙盒 L2 复盘 MVP（独立 ETL+独立 DB+`/api/sandbox/review_data`+一键 ETL 接口+`/sandbox-review` 页面+首页“复盘”入口）。
- 风险: 真实 `D:\MarketData` 全量刷数尚未执行；当前验证为本地合成样本与自动化测试。
- 链接: `backend/scripts/sandbox_review_etl.py`, `backend/app/routers/sandbox_review.py`, `src/components/sandbox/SandboxReviewPage.tsx`, `docs/changes/REQ-20260310-01-sandbox-l2-review-mvp.md`

## 2026-03-10 14:10 | 后端 AI
- Task ID: `CHG-20260310-01`
- CAP: `CAP-REALTIME-FLOW`, `CAP-WIN-PIPELINE`
- 结论: 完成生产断链修复并发布 `v4.2.10`（Windows 依赖补齐 + ingest 地址修正 + 启动链路加固），当日分时恢复。
- 风险: 生产冒烟按流程需由你手动执行；若任一失败需立即回滚并登记阻塞。
- 链接: `backend/scripts/live_crawler_win.py`, `start_live_crawler.bat`, `docs/changes/INV-20260310-01-prod-intraday-no-data.md`, `src/version.ts`

## 2026-03-09 23:40 | 后端 AI
- Task ID: `CHG-20260309-09`
- CAP: `CAP-REALTIME-FLOW`
- 结论: 修复当日分时仅股价线问题；统一成交方向枚举后，主力资金曲线恢复非零展示。
- 风险: 上游若新增未知 `type`，当前会降级为 `neutral`，需继续观察采样日志。
- 链接: `backend/app/core/trade_side.py`, `backend/app/services/analysis.py`, `backend/app/routers/analysis.py`, `docs/archive/changes/ARC-CHG-20260309-intraday-flow-side-normalization.md`

## 2026-03-09 16:55 | 后端 AI
- Task ID: `CHG-20260309-08`
- CAP: `CAP-WIN-PIPELINE`
- 结论: 核心编号重构为 `00~08`，移除根目录临时编号文档；建立 `06_CHANGE_MANAGEMENT` 与 `docs/changes` 动态体系。
- 风险: 无代码变更；后续新增需求必须严格按 `06` 命名与流程执行。
- 链接: `docs/06_CHANGE_MANAGEMENT.md`, `docs/08_DOCS_GOVERNANCE.md`, `docs/changes/README.md`

## 2026-03-09 16:05 | 后端 AI
- Task ID: `CHG-20260309-07`
- CAP: `CAP-HISTORY-30M`, `CAP-WIN-PIPELINE`
- 结论: 30m 与审计事件正文已归档到 `docs/archive/incidents/`。
- 风险: 无代码变更；发布前仍需按 `04` 第七节执行一次 bug 修复验证流程。
- 链接: `docs/archive/incidents/06_TECH_AUDIT_2026-03-07.md`, `docs/archive/incidents/09_30M_DIAGNOSIS_PLAN_2026-03-07.md`, `docs/08_DOCS_GOVERNANCE.md`, `docs/04_OPS_AND_DEV.md`

## 2026-03-09 15:20 | 后端 AI
- Task ID: `CHG-20260309-06`
- CAP: `CAP-WIN-PIPELINE`
- 结论: 完成 `01/05` 一致性收口（架构边界说明、Windows 路径约定、安全文档本地启动步骤对齐）。
- 风险: 无代码改动；仅文档一致性修订。
- 链接: `docs/01_SYSTEM_ARCHITECTURE.md`, `docs/05_LLM_KEY_SECURITY.md`, `docs/08_DOCS_GOVERNANCE.md`

## 2026-03-09 14:40 | 后端 AI
- Task ID: `CHG-20260309-05`
- CAP: `CAP-MKT-TIME`, `CAP-HISTORY-30M`
- 结论: 完成文档边界补齐（README 阅读顺序、事件类文档标注、契约/SOP 边界提醒）。
- 风险: 无业务逻辑变更；仅文档治理层更新。
- 链接: `docs/03_DATA_CONTRACTS.md`, `docs/04_OPS_AND_DEV.md`, `docs/archive/incidents/06_TECH_AUDIT_2026-03-07.md`, `docs/archive/incidents/09_30M_DIAGNOSIS_PLAN_2026-03-07.md`

## 2026-03-09 12:10 | 后端 AI
- Task ID: `CHG-20260309-04`
- CAP: `CAP-MKT-TIME`, `CAP-REALTIME-FLOW`, `CAP-WIN-PIPELINE`
- 结论: 文档治理重构已落地（主册改为能力卡模式、协议改为任务卡+短日志）。
- 风险: Windows 回传/merge 仍受连接抖动影响。
- 阻塞: `T-002`, `T-003`
- 链接: `docs/02_BUSINESS_DOMAIN.md`, `docs/07_PENDING_TODO.md`

## 2026-03-09 11:45 | 后端 AI
- Task ID: `CHG-20260309-02`
- CAP: `CAP-REALTIME-FLOW`
- 结论: 本地 watchlist 11 只股票当日 ticks 已回填，主力动态恢复可用。
- 风险: 本地后端需重启后才能持续采集（`.env.local` 新增开关）。
- 链接: `docs/02_BUSINESS_DOMAIN.md#cap-realtime-flow`

## 2026-03-08 22:30 | 后端 AI
- Task ID: `CHG-20260308-01`
- CAP: `CAP-HISTORY-30M`, `CAP-WIN-PIPELINE`
- 结论: Windows 侧 202602 ETL 重建完成（15/15 DONE, 0 FAILED）。
- 风险: 95MB 产物回传中断导致 merge 未完成。
- 阻塞: `T-002`
- 链接: `docs/07_PENDING_TODO.md#t-002-windows-etl-产物待回传并云端-merge高优先级`

## 2026-03-07 17:05 | 后端 AI
- Task ID: `CHG-20260307-03`
- CAP: `CAP-HISTORY-30M`
- 结论: v4.2.8 上线，30m 统一 8 桶并过滤非标准桶。
- 风险: 历史污染窗口仍需 Windows 重建后 merge 才能最终闭环。
- 链接: `docs/02_BUSINESS_DOMAIN.md#cap-history-30m`
