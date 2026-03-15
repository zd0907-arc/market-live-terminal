# AI_HANDOFF_LOG（短日志）
> 规则：每条日志必须包含 Task ID、CAP ID、结论、阻塞/风险、链接；每条不超过 8 行要点。
>
> 历史长日志归档：`docs/archive/AI_HANDOFF_LOG_LEGACY_2026-03-09.md`

---

## 2026-03-15 18:40 | Codex
- Task ID: `CHG-20260315-03`
- CAP: `CAP-HISTORY-30M`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已按 STRICT 文档先行流程完成新版历史多维“轻量质量提示”第一版：正式 `5m / 1d` 表新增 `quality_info`，`/api/history/multiframe` 返回 `quality_info + is_placeholder`，缺失 `5m / 日` 在查询层补 placeholder，前端统一用黄色 `!` 标记异常点且 tooltip 直接展示质量说明。
- 风险: 当前质量体系仍是单文本轻量方案；若后续要做更精细问题分类，应另开卡，而不是在本方案上继续叠复杂状态机。
- 链接: `backend/app/db/l2_history_db.py`, `backend/app/routers/analysis.py`, `backend/scripts/l2_daily_backfill.py`, `src/components/dashboard/HistoryMultiframeFusionView.tsx`, `docs/changes/REQ-20260315-03-monitor-multiframe-quality-info-lightweight.md`

## 2026-03-15 13:20 | Codex
- Task ID: `CHG-20260315-02`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 结论: 已完成 `2026-03` 首批正式回补复盘：确认 `2026-03-02 ~ 2026-03-13` 共 10 个交易日的正式结果可作为当前基线使用，但仍有 `43` 个显式 `OrderID` 对齐失败和 `105` 个“无有效 bar”空结果样本需要进入 repair/review queue；同时已冻结未来每日盘后最佳执行方案为“Windows 数据面 + 常在线控制端 8 worker SSH 编排”。
- 风险: 现有缺口不会污染其他 symbol/day，但会让对应 symbol 在对应日期缺少正式 L2 结果；当前 Windows 父进程 `Popen` 分片方案仍不稳定，不宜直接做正式定时任务主路径。
- 链接: `backend/scripts/l2_daily_backfill.py`, `backend/tests/test_l2_daily_backfill.py`, `docs/changes/MOD-20260315-02-l2-march-backfill-review-and-postclose-runbook.md`, `docs/04_OPS_AND_DEV.md`, `docs/07_PENDING_TODO.md`

## 2026-03-15 14:18 | Codex
- Task ID: `CHG-20260315-02`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 结论: 已完成 `43` 个历史 `OrderID` 显式失败样本的脚本修复与 Windows 定向回补：`l2_daily_backfill.py` 现允许“单边 0 overlap、另一边可对齐”时回退到 `trade-side parent total`，仅在买卖两侧都完全无法对齐时才继续失败；同时新增 `l2_repair_failed_samples.py`，并已在 Windows 生成 `run_id=84~93` 的 repair run，`43/43` 全部恢复为正式成功。当前 `2026-03-02 ~ 2026-03-13` 正式累计已更新为 `history_daily_l2=74657`、`history_5m_l2=3361224`。
- 风险: 旧失败记录仍保留在 `l2_daily_ingest_failures` 作为历史 run 审计；当前剩余待处理的核心缺口收敛为 `105` 个空结果样本，需要继续区分停牌/无成交与源包异常。
- 链接: `backend/scripts/l2_daily_backfill.py`, `backend/scripts/l2_repair_failed_samples.py`, `backend/tests/test_l2_daily_backfill.py`, `docs/changes/MOD-20260315-02-l2-march-backfill-review-and-postclose-runbook.md`

## 2026-03-14 23:55 | Codex
- Task ID: `CHG-20260314-08`
- CAP: `CAP-REALTIME-FLOW`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已完成新版多维历史方案的 Step 1 数据层：新增 `realtime_5m_preview / realtime_daily_preview` 两张 preview 表，并在实时聚合/当日日线 overlay 链路中做写透；当前“今天”的 L1-only 预览值已具备独立存储层，不再只靠接口现场临算。
- 风险: 当前只是数据层与写入链路，统一查询接口与新版前端 IA 尚未接入；preview 层仍只存 L1，不伪造 L2。`2026-03` 正式 L2 日包全月入库仍待 Windows 下载与清洗完成。
- 链接: `backend/app/db/realtime_preview_db.py`, `backend/app/services/analysis.py`, `backend/app/routers/analysis.py`, `backend/tests/test_realtime_preview_db.py`, `docs/03_DATA_CONTRACTS.md`

## 2026-03-15 00:18 | Codex
- Task ID: `CHG-20260314-08`
- CAP: `CAP-REALTIME-FLOW`, `CAP-L2-HISTORY-FOUNDATION`, `CAP-HISTORY-30M`
- 结论: 已完成新版“历史多维”Step 2 统一接口层：新增 `/api/history/multiframe`，统一返回 `5m/15m/30m/1h/1d` 的 finalized 历史 + today preview；别名 `day/daily/60m` 已归一，today preview 明确只返回 L1 并带 `preview_level=l1_only`。
- 风险: 当前仅接口层完成，新版前端还未切到该统一接口；正式 `2026-03` 全月 L2 数据仍待 Windows 下载、清洗并入 `history_5m_l2/history_daily_l2`，否则历史覆盖范围有限。
- 链接: `backend/app/routers/analysis.py`, `backend/tests/test_history_multiframe_router.py`, `docs/03_DATA_CONTRACTS.md`, `docs/changes/REQ-20260314-08-monitor-history-multiframe-fusion.md`

## 2026-03-15 00:42 | Codex
- Task ID: `CHG-20260314-08`
- CAP: `CAP-REALTIME-FLOW`, `CAP-HISTORY-30M`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已完成新版前端 IA 第一版接入：页面顶层保持“旧版 / 新版”，新版内部收敛为“当日分时 + 历史多维”，并在历史多维中支持 `5m / 30m / 1h / 日` 切换；历史多维已直接消费 `/api/history/multiframe`，沿用“上 K 下双柱、L2 包 L1”的融合视觉基线。
- 风险: 当前前端已能构建通过，但尚未等到 Windows `2026-03` 正式 L2 全月数据入库做大样本校正；新版 5m/30m/1h 仍属于第一版交互，后续需继续根据真实数据微调 tooltip、默认视窗与空态策略。
- 链接: `src/App.tsx`, `src/components/dashboard/HistoryMultiframeFusionView.tsx`, `src/services/stockService.ts`, `src/types.ts`, `docs/changes/REQ-20260314-08-monitor-history-multiframe-fusion.md`

## 2026-03-15 01:12 | Codex
- Task ID: `CHG-20260315-01`
- CAP: `CAP-HISTORY-30M`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已按“先做文档管理”的要求，把 `2026-03` 正式 L2 数据未下载完成回填到待办阻塞，并新增历史多维副图需求卡：冻结“净流入对比 + 买卖力度分离”两张副图的统一设计，明确继续采用 `L1 vs L2`、`主力 vs 超大单` 视角，且首期复用 `/api/history/multiframe` 前端派生，不新增后端接口。
- 风险: 当前仅完成文档冻结，未进入实现；由于 `2026-03` 全月正式数据尚未入库，副图默认视窗、tooltip 密度与空态策略都还不能做真实样本校正。
- 链接: `docs/changes/REQ-20260315-01-monitor-multiframe-secondary-panels.md`, `docs/07_PENDING_TODO.md`, `docs/02_BUSINESS_DOMAIN.md`

## 2026-03-15 01:28 | Codex
- Task ID: `CHG-20260315-01`
- CAP: `CAP-HISTORY-30M`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已完成历史多维副图第一版实现：在现有“价格 + 绝对买卖对比”主图下新增“净流入对比 + 买卖力度分离”两张副图，且四个粒度 `5m/30m/1h/日` 统一复用 `/api/history/multiframe` 前端派生；构建已通过。
- 风险: 当前实现仍缺 `2026-03` 全月正式 L2 数据做大样本校正，后续需继续微调默认视窗、tooltip 信息密度与空值/未结算提示，避免在高密度样本下可读性下降。
- 链接: `src/components/dashboard/HistoryMultiframeFusionView.tsx`, `docs/changes/REQ-20260315-01-monitor-multiframe-secondary-panels.md`, `docs/07_PENDING_TODO.md`

## 2026-03-15 02:20 | Codex
- Task ID: `CHG-20260314-04`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 结论: 已复查 Windows `2026-03` 日包下载状态，并验证稳定并发回补路径：`D:\\MarketData\\202603` 已具备 `20260302 ~ 20260313` 共 10 个日包；其中 `2026-03-12` 已通过“本地直连多 SSH 会话并发 6 shard”方式完成正式回补，累计落库 `history_daily_l2=7630`、`history_5m_l2=344317`。`2026-03-11` 整日回补结果维持 `history_daily_l2=7648`、`history_5m_l2=344439`。
- 风险: Windows 本机父进程拉起子进程的 shard 并发编排仍不稳定，当前可靠方案是“Mac 端直接并发多条 SSH worker”；`2026-03-12` 仍留有 `5` 个 `OrderID` 对齐失败 symbol 与 `20` 个无有效 bar symbol，后续批量跑 `20260313/10/09/06/05/04/03/02` 时需继续沿用该稳定路径并保留失败清单。
- 链接: `backend/scripts/l2_daily_backfill.py`, `backend/scripts/l2_day_sharded_backfill.py`, `docs/changes/REQ-20260314-04-l2-daily-package-adapter-and-backfill.md`, `docs/07_PENDING_TODO.md`

## 2026-03-15 05:10 | Codex
- Task ID: `CHG-20260314-04`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 结论: 已把稳定并发路径扩大到 `8 worker` 并继续批量处理 `2026-03-13 / 2026-03-10 / 2026-03-09`：当前正式结果分别为 `7610/343162`、`7348/331198`、`5893/260777`（格式：`history_daily_l2/history_5m_l2`）。剩余失败清单已收敛到少量 `OrderID` 对齐异常：`2026-03-13=4`、`2026-03-10=2`、`2026-03-09=1`。
- 风险: 现在真正未完成的只剩 `20260306/05/04/03/02`，且 Windows staging 已同时挂着多天解压目录；若继续连跑，建议优先补一个“清理已完成 staging + 按日生成 shard + 多 SSH worker 执行”的稳定脚本，避免后续纯手工编排出错。
- 链接: `backend/scripts/l2_daily_backfill.py`, `docs/changes/REQ-20260314-04-l2-daily-package-adapter-and-backfill.md`, `docs/07_PENDING_TODO.md`

## 2026-03-15 10:42 | Codex
- Task ID: `CHG-20260314-04`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 结论: 已把 `2026-03-06 / 05 / 04 / 03 / 02` 也全部按 `8 worker` 并发路径补完；至此，Windows 当前已下载的 `2026-03-02 ~ 2026-03-13` 共 10 个交易日已全部完成正式回补。10 日累计正式结果为：`history_daily_l2=74614`、`history_5m_l2=3360187`。显式 `OrderID` 对齐失败累计 `43` 个 `symbol-day`，另有 `105` 个 `symbol-day` 因无有效 bar 未形成正式 `5m+daily`。
- 风险: 失败样本不会污染其他 symbol/day 的正式数据，但会导致对应 symbol 在对应日期缺少正式 L2 行；下一步应对这 `43` 个失败样本按“ETF/基金类优先、上证样本次之”做专项容错评估，并尽快把当前手工并发流程脚本化，避免后续增量日包继续人工编排。
- 链接: `backend/scripts/l2_daily_backfill.py`, `docs/changes/REQ-20260314-04-l2-daily-package-adapter-and-backfill.md`, `docs/07_PENDING_TODO.md`

## 2026-03-14 23:20 | Codex
- Task ID: `CHG-20260314-08`
- CAP: `CAP-REALTIME-FLOW`, `CAP-HISTORY-30M`, `CAP-L2-HISTORY-FOUNDATION`, `CAP-SANDBOX-REVIEW`
- 结论: 已按“先做文档管理再开发”的要求完成本轮范围收口：把前序基础阶段标记为完成，未完成项迁移到 `07_PENDING_TODO`，并新建范围卡冻结新版 IA 为“当日分时 + 历史多维（5m/30m/1h/日）”；同时明确 `2026-03` L2 数据下载完成后的推进顺序为“清洗入库 → 接口 → 盯盘页 → 复盘页并库”。
- 风险: 当前仅完成文档治理与范围冻结，`2026-03` 日包仍在 Windows 下载中；正式 `realtime_5m_preview / realtime_daily_preview` 与新版历史多维统一接口尚未落代码，复盘页正式并库仍后置。
- 链接: `docs/changes/REQ-20260314-08-monitor-history-multiframe-fusion.md`, `docs/07_PENDING_TODO.md`, `docs/changes/STG-20260314-01-l2-postclose-history-foundation.md`, `docs/02_BUSINESS_DOMAIN.md`

## 2026-03-14 21:35 | 前端 AI
- Task ID: `CHG-20260314-07`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-REALTIME-FLOW`
- 结论: 已完成盯盘页“旧版 / 新版”整页切换，并新增新版日线融合视图 V1：上方价格区，下方左超大/右主力双柱；正式历史按 L2 包裹 L1 展示，当日未结算仅保留 L1 浅色芯柱。
- 风险: 新版日线当前仍依赖现有正式日线/日聚合接口；若股票尚无正式 `history_daily_l2` 覆盖，只会显示新版专属空态而不会伪造 L2。新版下的“当日分时 / 30分钟线”本轮仍复用旧组件。
- 链接: `src/App.tsx`, `src/components/dashboard/HistoryDailyFusionView.tsx`, `src/types.ts`, `docs/changes/REQ-20260314-07-monitor-fusion-daily-v1.md`

## 2026-03-14 20:40 | 后端 AI
- Task ID: `CHG-20260314-05`
- CAP: `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已按当前时点完成文档治理回填：总方案改为 ACTIVE，Phase 1/2/3/3.5 的已完成项、验证结果和后置项已统一写回变更卡与 core docs；当前对外口径可明确表述为“盘后 L2 历史底座已进入可用状态，复盘页并库为后续阶段”。
- 风险: 文档已收口到当前状态，但 `docs/changes/` 相关文件尚未做正式归档；待本期整体稳定、并确认是否要继续紧接着做下一阶段功能时再决定归档时点。
- 链接: `docs/changes/STG-20260314-01-l2-postclose-history-foundation.md`, `docs/changes/REQ-20260314-04-l2-daily-package-adapter-and-backfill.md`, `docs/changes/REQ-20260314-05-l2-history-query-switch.md`, `docs/02_BUSINESS_DOMAIN.md`

## 2026-03-14 20:25 | 后端 AI
- Task ID: `CHG-20260314-05`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-MKT-TIME`
- 结论: 已完成盯盘页历史分时补链与本地验证：`/api/realtime/dashboard` 历史日期现优先读取 `history_5m_l2`；同时将前端来源文案改为动态显示接口真实 `source`。已从 Windows `D:\\MarketData\\20260311\\20260311` 抽取 `000833.SZ/600519.SH` 样本回补到本地，验证 `sz000833` 返回 `49` 条 5m、`sh600519` 返回 `48` 条 5m，且两者历史 30m/历史分时接口均返回 `source=l2_history`。
- 风险: `sh600519` 存在部分母单号无法在委托文件对齐（buy 缺 `6375` / sell 缺 `6034`），当前已改成“可对齐部分优先用委托母单金额，不可对齐部分回退到成交侧订单号聚合”，能稳定出数，但后续仍建议继续观察上证样本是否需要更细的订单口径兼容。
- 链接: `backend/scripts/l2_daily_backfill.py`, `backend/app/routers/market.py`, `backend/app/services/analysis.py`, `src/components/dashboard/RealtimeView.tsx`, `src/components/dashboard/HistoryView.tsx`

## 2026-03-14 19:45 | 后端 AI
- Task ID: `CHG-20260314-05`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-MKT-TIME`
- 结论: 已把历史分时日期回溯接入正式 L2 历史：`/api/realtime/dashboard` 在历史日期下现按 `history_1m -> history_5m_l2 -> trade_ticks fallback` 的优先级取数，因此像 `2026-03-11` 这类已完成盘后回补的日期，也能在盯盘页分时模式直接看到 5m 的 L2 派生曲线。
- 风险: 若某只股票（如 `sh600519`）当天没有执行过盘后日包回补，历史 30m/历史分时仍不会凭空出现；这属于“该 symbol 当天正式 L2 数据未入库”，不是查询链路 bug。复盘页并库已按产品优先级延后。
- 链接: `backend/app/routers/market.py`, `backend/app/services/analysis.py`, `backend/tests/test_realtime_dashboard_router.py`, `docs/changes/REQ-20260314-06-review-page-prod-l2-unification.md`

## 2026-03-14 19:20 | 后端 AI
- Task ID: `CHG-20260314-05`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-REALTIME-FLOW`
- 结论: 已完成 Phase 3 后端查询切换：`/api/history/trend` 现优先读取 `history_5m_l2` 并支持 `5m|15m|30m|1h|1d` 聚合，`/api/history_analysis` 历史日期优先读取 `history_daily_l2`；两接口均补充 `source/is_finalized/fallback_used`，当天仍保留实时 ticks 覆盖能力。
- 风险: 当前只是后端与契约层切换完成，历史页数据源选择器文案仍沿用旧 `Sina/Local` 语义；复盘页也还未并库到生产 L2 底座，仍属于下一阶段任务。
- 链接: `backend/app/routers/analysis.py`, `backend/app/db/l2_history_db.py`, `backend/tests/test_l2_history_query_switch.py`, `docs/changes/REQ-20260314-05-l2-history-query-switch.md`

## 2026-03-14 18:25 | 后端 AI
- Task ID: `CHG-20260314-04`
- CAP: `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已完成 Phase 2 单日回补链路：新增 `l2_daily_backfill.py`，可从 Windows 盘后 L2 日包直接生成 L1/L2 的 `5m + daily` 正式派生，并写入 `history_5m_l2/history_daily_l2` 与回补状态表；对 `2026-03-11 / 000833.SZ` 样本手动冒烟，成功落库 `49` 条 5m + `1` 条 daily，run 状态为 `done`。
- 风险: 当前回补脚本已兼容旧 `20260311/20260311` 与新 `202603/20260311` 输入，但还没实现“整个月目录自动发现待回补日”与“裸日目录自动迁移”；生产查询接口和页面也还没切到新正式历史表。
- 链接: `backend/scripts/l2_daily_backfill.py`, `backend/tests/test_l2_daily_backfill.py`, `backend/app/db/l2_history_db.py`, `docs/changes/REQ-20260314-04-l2-daily-package-adapter-and-backfill.md`

## 2026-03-14 18:05 | 后端 AI
- Task ID: `CHG-20260314-03`
- CAP: `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已完成 Phase 1 本地代码落地：新增生产 L2 历史 schema/helper（`history_5m_l2/history_daily_l2/l2_daily_ingest_runs/l2_daily_ingest_failures`）、目录规范 helper（兼容旧双层日期目录与新 `YYYYMM/YYYYMMDD` 结构），并把 schema 挂入 `init_db()` 自动初始化。
- 风险: 当前只完成 schema/helper 与测试，尚未接入正式日包 ETL、正式回补任务和生产查询切换；Windows 现有裸日目录也还没真正迁移到月目录，只是 helper 已支持过渡兼容。
- 链接: `backend/app/db/l2_history_db.py`, `backend/app/core/l2_package_layout.py`, `backend/app/db/database.py`, `backend/tests/test_l2_history_foundation.py`, `docs/changes/REQ-20260314-03-l2-history-db-and-directory-spec.md`

## 2026-03-14 17:40 | 后端 AI
- Task ID: `CHG-20260314-03`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 结论: 已按“文档先行、数据库先行”要求冻结盘后 L2 历史底座总方案：生产正式层固定为 `history_5m_l2 + history_daily_l2 + 回补状态表`，历史最细粒度只保留 `5m`，`15m/30m/1h` 一律由 `5m` 聚合；同时明确同一份 L2 原始日包必须同步产出 L1 与 L2 双派生，供后续页面对比分析。
- 风险: 当前仍停留在文档冻结阶段，生产代码尚未实现；另外 Windows 现有 `20260311` 裸日目录仍需在实施阶段迁入 `D:\\MarketData\\202603\\20260311\\...` 规范结构，并完成强回补链路，才能真正切换历史查询。
- 链接: `docs/changes/STG-20260314-01-l2-postclose-history-foundation.md`, `docs/changes/REQ-20260314-03-l2-history-db-and-directory-spec.md`, `docs/changes/REQ-20260314-04-l2-daily-package-adapter-and-backfill.md`, `docs/03_DATA_CONTRACTS.md`, `docs/04_OPS_AND_DEV.md`

## 2026-03-14 16:12 | 后端 AI
- Task ID: `CHG-20260314-02`
- CAP: `CAP-WIN-PIPELINE`
- 结论: 已远程验证 Windows `2026-03-11` 每日盘后 L2 日包格式：目录为 `D:\\MarketData\\20260311\\20260311\\{symbol}`，样本 `000833.SZ` 含 `行情/逐笔成交/逐笔委托` 三类 CSV；`叫买序号/叫卖序号` 可完整对齐 `交易所委托号`，说明新数据具备真实 L2 母单聚合前提。
- 风险: 当前现有 ETL 对该格式不兼容——既无法从嵌套目录提取交易日，也未识别 `成交数量/叫买序号/叫卖序号` 等中文列名；若不先加适配层，直接接入会误判日期与字段。
- 链接: `backend/scripts/inspect_daily_l2_package.py`, `backend/scripts/sandbox_review_etl.py`, `docs/changes/REQ-20260314-02-daily-postclose-l2-fusion.md`, `docs/07_PENDING_TODO.md`

## 2026-03-14 14:05 | 后端 AI
- Task ID: `CHG-20260312-02`
- CAP: `CAP-REALTIME-FLOW`
- 结论: 已把新版 Windows crawler 同步到 `D:\market-live-terminal` 并重启 `ZhangDataLiveCrawler`；当前线上已形成 `focus=5秒 / warm=30秒 / watchlist=15分钟` 的端到端抓取闭环。
- 风险: 这一步解决的是“采集频率语义与前端按钮一致”，但“页面刷新是否足够丝滑”仍需要你在真实页面上做主观体验确认，因此 `T-008` 先保留为 ACTIVE。
- 链接: `backend/scripts/live_crawler_win.py`, `start_live_crawler.bat`, `docs/changes/MOD-20260312-01-realtime-focus-quiet-refresh.md`, `docs/07_PENDING_TODO.md`

## 2026-03-14 13:47 | 后端 AI
- Task ID: `CHG-20260314-01`
- CAP: `CAP-MKT-TIME`
- 结论: 已发布 `v4.2.12` 到云端生产；修复周末/非交易日“当日分时”回溯为空的问题，路径改为“优先 history_1m，缺失则回退到该日 trade_ticks 聚合”。线上冒烟：`/api/health` 正常，`/api/realtime/dashboard?symbol=sz000833` 返回 `display_date=2026-03-13` 且 `chart_data=241`。
- 风险: 当前仅云端前后端已发，Windows crawler 的 focus/warm 新逻辑尚未同步，`T-008` 继续保留为阻塞项。
- 链接: `backend/app/routers/market.py`, `backend/tests/test_realtime_dashboard_router.py`, `docs/changes/MOD-20260314-01-weekend-intraday-backfill-fix.md`, `src/version.ts`

## 2026-03-14 13:16 | 后端 AI
- Task ID: `CHG-20260314-01`
- CAP: `CAP-MKT-TIME`
- 结论: 已修复周末/非交易日“当日分时”空白问题；`/api/realtime/dashboard` 现仅在“自然日当天且为交易日”时走实时 ticks 聚合，回溯到上一交易日时优先走 `history_1m`，若缺失再回退到该日 `trade_ticks` 聚合。
- 风险: 若指定日期既无 `history_1m` 也无 `trade_ticks`，接口仍会按契约返回 404；这属于底座数据缺失，不再误判为日期路径问题。
- 链接: `backend/app/routers/market.py`, `backend/tests/test_realtime_dashboard_router.py`, `docs/changes/MOD-20260314-01-weekend-intraday-backfill-fix.md`

## 2026-03-14 13:08 | 后端 AI
- Task ID: `CHG-20260311-09`
- CAP: `CAP-SANDBOX-REVIEW`, `CAP-WIN-PIPELINE`
- 结论: Windows V2 全月份总控已完成，`data/sandbox/review_v2/` 已全量同步到云端；同时定位并修复云端容器仍使用旧版 1m `sandbox_review_v2_db.py` 的问题，重建前后端后 `/api/sandbox/pool` 与 `/api/sandbox/review_data` 已可返回真实 sandbox 数据。
- 风险: 少数日期与第三方终端仍可能存在集合竞价口径差异；当前沙盒验收以 `D:\\MarketData` 原始逐笔为准。另有一只人工补跑样本 `sz000759` 在云端可查，但不计入 2788 固定股票池。
- 链接: `backend/app/db/sandbox_review_v2_db.py`, `backend/app/routers/sandbox_review.py`, `src/components/sandbox/SandboxReviewPage.tsx`, `docs/changes/REQ-20260311-02-sandbox-review-v2-production-isolated.md`, `docs/07_PENDING_TODO.md`

## 2026-03-13 00:12 | 后端 AI
- Task ID: `CHG-20260312-04`
- CAP: `CAP-WIN-PIPELINE`
- 结论: 已新增 Mac 本地检查脚本 `check_windows_review_v2_progress.py`，可一条命令查看 Windows 全月份总控的任务状态、进程、状态文件与日志尾部。
- 风险: 该脚本依赖 Mac->Windows SSH/Tailscale 联通；若网络不通，会直接在输出中暴露失败信息。
- 链接: `check_windows_review_v2_progress.py`, `docs/04_OPS_AND_DEV.md`

## 2026-03-13 00:05 | 后端 AI
- Task ID: `CHG-20260312-04`
- CAP: `CAP-SANDBOX-REVIEW`, `CAP-WIN-PIPELINE`
- 结论: 已在 Windows 完成从 `SandboxBackfillMonth202602` 到 `SandboxBackfillAllMonths` 的无损切换：旧单月任务已停掉并禁用，新总控已启动，当前继续在 `2026-02` 上按 `--resume` 接管，后续会自动推进到 `2025-01`。
- 风险: 计划任务自身会迅速回到“就绪”态，但总控 Python 进程仍在服务会话中持续运行；后续验真应以 `run_all_months_latest.json`、`run_all_months.out.log` 和 Python PID 为准。
- 链接: `backend/scripts/sandbox_review_v2_run_all_months.py`, `docs/changes/MOD-20260312-02-sandbox-review-v2-all-months-runner.md`, `docs/07_PENDING_TODO.md`

## 2026-03-12 23:22 | 后端 AI
- Task ID: `CHG-20260312-04`
- CAP: `CAP-SANDBOX-REVIEW`, `CAP-WIN-PIPELINE`
- 结论: 已新增 V2 全月份总控脚本 `sandbox_review_v2_run_all_months.py`，支持一次启动后自动按 `2026-02 -> 2025-01` 串行回放；默认 `partial_done` 停机，全部完成后仅停在 `done` 态，不自动同步云端或发布。
- 风险: 当前 Windows 仍在运行 `2026-02` 单月任务；总控脚本已就绪，但应等待现任务结束后再切换，避免并发打架。
- 链接: `backend/scripts/sandbox_review_v2_run_all_months.py`, `backend/app/db/sandbox_review_v2_db.py`, `docs/changes/MOD-20260312-02-sandbox-review-v2-all-months-runner.md`, `docs/04_OPS_AND_DEV.md`

## 2026-03-12 23:05 | 后端 AI
- Task ID: `CHG-20260312-03`
- CAP: `CAP-WIN-PIPELINE`
- 结论: 已新增外部 Skill `mac-windows-ops-bridge`，并将 Mac 控 Windows 长任务执行/验真 SOP 回填到 `04_OPS_AND_DEV`。
- 风险: Skill 位于本地共享 skills 目录，不受 repo 版本控制；若本机 skill 根目录迁移，需要重新确认可发现性。
- 链接: `/Users/dong/Desktop/AIGC/skills/mac-windows-ops-bridge/SKILL.md`, `docs/changes/CFG-20260312-03-mac-windows-ops-bridge-skill.md`, `docs/04_OPS_AND_DEV.md`

## 2026-03-12 18:30 | 后端 AI
- Task ID: `CHG-20260312-02`
- CAP: `CAP-REALTIME-FLOW`
- 结论: 已完成生产实时页“盯盘二态 + 静默刷新”代码收口：前端改为 `盯盘开=5s / 关闭=30s`，`heartbeat` 升级为 `focus/warm` 分层，Windows crawler 同步升级为 focus/warm 双层 tick 策略。
- 风险: 当前仅完成本地代码与文档收口，按你的要求暂不单独发布；已登记 `T-008`，等待复盘模块一并进入同一发布窗口。
- 链接: `src/App.tsx`, `src/components/dashboard/RealtimeView.tsx`, `backend/app/routers/monitor.py`, `backend/app/services/monitor.py`, `backend/scripts/live_crawler_win.py`, `docs/changes/MOD-20260312-01-realtime-focus-quiet-refresh.md`

## 2026-03-12 13:20 | 后端 AI
- Task ID: `CHG-20260312-01`
- CAP: `CAP-SANDBOX-REVIEW`
- 结论: 已远程在 Windows 以计划任务 `SandboxBackfill5m` 启动全量5m长跑（`workers=8,min-workers=6,mem=75,shard=1000,resume`），任务持续运行中；最新日志进度为 `shard=1/3 2025-02-11`。
- 风险: 当前仍受 Windows→云端大文件同步超时影响，任务完成后需优先做断点续传/分片同步，否则云端仍可能“接口可用但数据不全”。
- 链接: `backend/scripts/sandbox_review_v2_backfill.py`, `docs/changes/REQ-20260311-02-sandbox-review-v2-production-isolated.md`, `docs/07_PENDING_TODO.md`

## 2026-03-12 00:15 | 后端 AI
- Task ID: `CHG-20260312-01`
- CAP: `CAP-SANDBOX-REVIEW`
- 结论: 按新决策将 V2 回放收敛为 5m 底层持久化（取消 1m 持久层），并升级回放脚本为“自动分片 + `--resume` 续跑 + Windows 内存阈值动态并发”，默认高压参数 `workers=8/min-workers=6`。
- 风险: 全量 2788 只长跑耗时仍较长；Windows→云端同步需改为断点续传/分片，否则大文件回传可能超时中断。
- 链接: `backend/scripts/sandbox_review_v2_backfill.py`, `backend/app/db/sandbox_review_v2_db.py`, `docs/changes/REQ-20260311-02-sandbox-review-v2-production-isolated.md`, `docs/07_PENDING_TODO.md`

## 2026-03-11 22:35 | 后端 AI
- Task ID: `CHG-20260311-09`
- CAP: `CAP-SANDBOX-REVIEW`
- 结论: 云端后端已补齐并生效 sandbox 模块（`main.py` 注册 + `sandbox_review` 路由 + V1/V2 db 模块）；外网验证 `/api/sandbox/pool` 与 `/api/sandbox/review_data` 均返回 `200`，404 已解除。
- 风险: 云端目前仅“接口可用”，但数据仍为空；Windows 样本包（约57MB）回传中出现超时，需改为分片/断点续传同步。
- 链接: `backend/app/main.py`, `backend/app/routers/sandbox_review.py`, `backend/app/db/sandbox_review_db.py`, `backend/app/db/sandbox_review_v2_db.py`, `docs/07_PENDING_TODO.md`

## 2026-03-11 22:05 | 后端 AI
- Task ID: `CHG-20260311-09`
- CAP: `CAP-SANDBOX-REVIEW`
- 结论: V2 数据链路已在 Windows 跑通：股票池首快照落地 **2788** 只（50-300亿、沪深A、排除ST），并完成 20 只样本 1m 回放（`run_id=1`，`total_rows=1317759`，`failed=0`）。
- 风险: 云端当前版本缺少 `sandbox_review` 路由文件，仍会触发 `/api/sandbox/*` 404；全量 2788 只回放尚未完成，仅完成样本批次。
- 链接: `backend/scripts/sandbox_review_v2_pool.py`, `backend/scripts/sandbox_review_v2_backfill.py`, `docs/changes/REQ-20260311-02-sandbox-review-v2-production-isolated.md`, `docs/07_PENDING_TODO.md`

## 2026-03-11 20:30 | 后端 AI
- Task ID: `CHG-20260311-09`
- CAP: `CAP-SANDBOX-REVIEW`
- 结论: 复盘模块 V2 首轮代码已落地：新增 V2 分库存储（`data/sandbox/review_v2`）、股票池接口 `/api/sandbox/pool`、`review_data` 粒度扩展、前端可选股/可选时间执行查询，以及池子构建/1m回放/容量审计脚本。
- 风险: 行情源短时断连会导致池子首次构建失败；当前脚本已加重试，但“首次数量”仍待在 Windows 节点成功跑通后回填。
- 链接: `backend/app/db/sandbox_review_v2_db.py`, `backend/app/routers/sandbox_review.py`, `src/components/sandbox/SandboxReviewPage.tsx`, `docs/changes/REQ-20260311-02-sandbox-review-v2-production-isolated.md`

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

## 2026-03-16 00:55 | 前端 AI
- Task ID: `CHG-20260315-01`
- CAP: `CAP-HISTORY-30M`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 本地已重构新版历史多维图表，三张副图改为 custom series 真双柱，恢复“左超大 / 右主力”，并重做 tooltip/图例交互。
- 风险: 仍需你在本地实际确认视觉是否符合样稿后再发生产。
- 链接: `docs/changes/REQ-20260315-01-monitor-multiframe-secondary-panels.md`

## 2026-03-16 01:02 | 前端 AI
- Task ID: `CHG-20260316-01`
- CAP: `CAP-HISTORY-30M`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: `v4.2.14` 已发布生产；历史多维三张副图恢复“左超大 / 右主力”真双柱，tooltip 收紧宽度并允许正常换行，生产健康检查与 `sz000833` 历史多维接口抽样通过，前端产物已确认包含版本号 `4.2.14`。
- 风险: 仍建议你在生产页面实际点开 `5m / 30m / 1h / 日` 各看一遍 tooltip 密度与 hover 手感。
- 链接: `docs/02_BUSINESS_DOMAIN.md#cap-history-30m`, `docs/changes/REQ-20260315-01-monitor-multiframe-secondary-panels.md`

## 2026-03-16 01:18 | 文档 AI
- Task ID: `CHG-20260316-03`
- CAP: `CAP-HISTORY-30M`, `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`, `CAP-REALTIME-FLOW`
- 结论: 已完成新版历史多维从需求、Windows 跑数、质量治理到生产发布的完整复盘，明确三次关键收敛、主要踩坑与后续建议。
- 风险: 复盘文档不改变线上行为；后续执行项仍需按 `07_PENDING_TODO` 与盘后 Runbook 继续推进。
- 链接: `docs/changes/MOD-20260316-03-monitor-history-multiframe-and-l2-rollout-retrospective.md`

## 2026-03-16 02:05 | 文档 AI
- Task ID: `CHG-20260316-04`
- CAP: `CAP-WIN-PIPELINE`, `CAP-L2-HISTORY-FOUNDATION`, `CAP-HISTORY-30M`
- 结论: 已补强文档/发布治理 Skill，并纠偏“Windows 本机不能跑正式回补”的表述；当前结论冻结为“不可接受的是 Python 父进程分片编排，Windows 本机 OS 级自动控制器仍可作为正式目标方案”。
- 风险: Windows 本机自动控制器尚未实现；当前正式稳定路径仍是“Windows 数据面 + 外部控制端 8 worker SSH 编排”。
- 链接: `docs/changes/CFG-20260316-04-skill-hardening-and-windows-l2-ops-decision.md`, `docs/changes/REQ-20260316-05-history-multiframe-monthly-pool-rollout.md`

## 2026-03-16 02:00 | 后端 AI
- Task ID: `CHG-20260316-05`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-HISTORY-30M`, `CAP-SANDBOX-REVIEW`
- 结论: 历史月份扩展路径已进一步收敛为“直接复用 sandbox V2 固定池 5m 产物，按月提升到生产 history L2”，并已新增月度提升脚本、在云端后台启动从 `2026-02 -> 2025-01` 的连续 rollout runner。
- 风险: 当前云端 runner 正在执行，首个月份 `2026-02` 的完整月报尚未产出；若中途需要停止，可创建 `/home/ubuntu/l2_month_rollout/STOP`。
- 链接: `backend/scripts/promote_sandbox_review_v2_month.py`, `backend/scripts/run_l2_history_monthly_rollout.py`, `docs/changes/REQ-20260316-05-history-multiframe-monthly-pool-rollout.md`
