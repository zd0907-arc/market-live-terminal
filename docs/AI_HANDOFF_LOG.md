# AI_HANDOFF_LOG（短日志）

## 2026-04-28 16:55 | Codex
- Task ID: `REQ-20260427-03-selection-news-event-research-context`
- CAP: `CAP-SELECTION-RESEARCH`, `CAP-STOCK-EVENTS`
- 结论: 已发布 v5.0.19 到 main：候选票研究上下文包、公司概况/决策解释持久化、研究依据包、查询触发预热、选股页加载稳定和波段复盘日涨跌口径均已收口。
- 风险: 公共新闻仍偏标题级；严格历史公司档案版本化未做；LLM 不可用时摘要会退化为规则解释。
- 验证: `npm run build`、`npm run check:version` 通过；浏览器验证 `localhost:5173/selection-research` 可看到 2026-04-24 申通快递的公司概况、决策解释和研究依据。
- 链接: `docs/changes/REQ-20260427-03-selection-news-event-research-context.md`, `docs/domain/selection-research.md`, `docs/contracts/review-selection.md`


## 2026-04-27 21:10 | Codex
- Task ID: `REL-20260427-selection-strategy-research-v5.0.9`
- CAP: `CAP-SELECTION-RESEARCH`, `CAP-STOCK-EVENTS`
- 结论: 已将选股策略研究阶段收口为 `v5.0.9`：每日复盘决策、资金流回调稳健、趋势中继高质量回踩已接入；消息事件重估补齐为“候选票事件解释卡 + 消息触发快速研判卡”两条入口。
- 风险: 消息事件理解层尚未开发；资金撤退/风险规避与市场环境过滤仍是后续模块，不作为当前主线发布内容。
- 链接: `docs/strategy-rework/project-status-20260427.md`, `docs/strategy-rework/strategies/S03-news-event-revaluation/README.md`, `docs/strategy-rework/current-inventory.md`


> 当前新日志的 `Task ID` 优先填写当前变更卡 ID（`MOD/REQ/INV/CFG/STG-*`）；历史 `CHG-*` 保留为旧阶段记录，不强行重写。
> 当前文件只保留最近 `1~2` 个版本窗口的短日志；更早阶段摘要见：
> - `docs/archive/ARC-LEG-20260425-ai-handoff-log-pre-v5-summary.md`
> - `docs/archive/AI_HANDOFF_LOG_LEGACY_2026-03-09.md`

## 2026-04-25 11:30 | Codex
- Task ID: `REQ-20260425-01-selection-ui-density-rework`
- CAP: `CAP-SELECTION-RESEARCH`, `CAP-HISTORY-30M`, `CAP-STOCK-EVENTS`
- 结论: 已在独立 worktree/分支完成选股研究工作台 UI 密度改造并升版本到 v5.0.8：顶部一行吸顶操作栏含版本号、策略仅保留启动确认/吸筹前置、股票横卡上移复用、左侧候选卡去标签化；右侧取消当前判断与复盘决策外框，覆盖长度合并到波段复盘标题栏；加入入场/出场交易计划标记、交易日禁点日期弹层、点外关闭、锚点累计净流入 L2/L1 紧贴K线展示，并默认从入场日开启；Top10 语义改为每日按策略分排序取前10；波段复盘顶栏重新压缩为单行，移除锚点说明框与冗余标签。
- 风险: 真实出场策略仍可继续细化；锚点累计本轮迁移为选股页波段复盘内置能力，未改复盘页原入口；日期可选性依赖 TradeCalendar 与 selection_signal_daily 是否有评分数据。
- 验证: `npm run check:version` 通过；`npm run build` 通过；`npm run check:baseline` 通过；3001 与 8000 已从当前 worktree 重启；API 已验证 2026-03-02/sz002733 返回入场 2026-03-03 与模拟出场 2026-03-31。
- 链接: `docs/changes/REQ-20260425-01-selection-ui-density-rework.md`, `src/components/selection/SelectionResearchPage.tsx`, `src/components/selection/SelectionDecisionPanel.tsx`, `src/components/dashboard/HistoryMultiframeFusionView.tsx`

## 2026-04-25 09:55 | Codex
- Task ID: `MOD-20260425-05`
- CAP: `CAP-WIN-PIPELINE`, `CAP-REALTIME-FLOW`
- 结论: 已复核并固化生产实时盯盘 / Mac 本地研究站 / 每日盘后跑数三条链路；Windows `ZhangDataLiveCrawler` 已清掉重复进程，`live_crawler_win.py` 增加交易日判断与单实例锁，周末不再做 full sweep / final sweep。
- 风险: Mac 本地默认仍不是生产级连续 crawler，只是读取本地同步库并支持单票按需 hydrate；如要本地完全等同线上连续盯盘，需要另开明确需求。
- 链接: `docs/changes/MOD-20260425-05-realtime-and-postclose-runtime-contract.md`, `docs/domain/realtime-monitor.md`, `docs/ops/windows-data-station.md`, `backend/scripts/live_crawler_win.py`

## 2026-04-25 10:55 | Codex
- Task ID: `MOD-20260425-06`
- CAP: `CAP-REALTIME-FLOW`, `CAP-WIN-PIPELINE`
- 结论: 已修复 Mac 本地盯盘两处收口问题：周末默认上一交易日视图在本地缺票时会自动补拉最近交易日；同时确认并纠正本地后端必须通过 `ops/start_local_research_station.sh` 启动，否则会误读项目内旧库，造成“历史多维停在旧日期 / 分时页空白”。
- 风险: 当前自动补拉只覆盖“默认上一交易日”场景，不覆盖用户手动回溯任意历史日期；若后续要支持更广泛历史补拉，需要单独设计上限与缓存策略。
- 链接: `docs/changes/MOD-20260425-06-local-monitor-data-source-fix.md`, `docs/ops/mac-local-research.md`, `docs/04_OPS_AND_DEV.md`, `backend/app/routers/market.py`

## 2026-04-25 00:10 | Codex
- Task ID: `MOD-20260424-03`
- CAP: `CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`
- 结论: 已完成一轮仓库瘦身与文档集收敛：`docs/REMOTE_CONTROL_GUIDE.md` 已删除，`docs/` 根目录保留集明确为 `00~08 + AI_QUICK_START + AI_HANDOFF_LOG`；同时删除一批无当前引用的历史脚本/样本产物（`.trae` 计划文档、`push_db_to_cloud.sh`、`etl_autorun.bat`、`test_env.py`、`market.db`、`metadata.json`、`mined_comments.txt`、3 个旧 sentiment helper 脚本），并清理本地嵌套旧副本目录。
- 风险: 归档文档里仍会引用已删除历史文件，这是历史事实保留，不代表当前入口；另外顶层仍有少量活跃运维脚本，后续若继续做目录收敛，可再单独把它们迁入 `ops/`。
- 链接: `docs/changes/MOD-20260424-03-repo-prune-and-docset-slimming.md`, `docs/08_DOCS_GOVERNANCE.md`, `README.md`, `docs/04_OPS_AND_DEV.md`, `docs/AI_QUICK_START.md`

## 2026-04-25 01:10 | Codex
- Task ID: `MOD-20260425-02`
- CAP: `CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`, `CAP-STOCK-EVENTS`
- 结论: 已完成核心长记忆文档第二阶段拆分：`04 / 03 / 02` 已分别压缩到 `54 / 49 / 40` 行，只保留入口与边界；细节下沉到 `docs/ops/*`、`docs/contracts/*`、`docs/domain/*`。`README / AI_QUICK_START / 08` 也已切到新阅读路径。
- 风险: 当前只是文档结构重构，不代表每个子主题都已经被细化到最终版本；后续若能力边界变化，仍要先回写入口页，再更新子文档。
- 链接: `docs/changes/MOD-20260425-02-split-core-long-memory-docs.md`, `docs/04_OPS_AND_DEV.md`, `docs/03_DATA_CONTRACTS.md`, `docs/02_BUSINESS_DOMAIN.md`, `docs/ops/`, `docs/contracts/`, `docs/domain/`

## 2026-04-25 01:25 | Codex
- Task ID: `MOD-20260425-03`
- CAP: `CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`
- 结论: 已把“需求开启→分支/worktree 决策→开发→验证→合并→文档收尾→归档”固化成正式流程文档 `docs/ops/development-workflow.md`，并同步接入 `README / AI_QUICK_START / 04 / 06 / 08 / 00`。以后默认按这条流程收口，不再只加不减。
- 风险: 当前流程已经成型，但能否长期保持，需要后续每次需求都严格执行；如果再次出现“做完不清理”，应先修流程执行，再谈补文档。
- 链接: `docs/changes/MOD-20260425-03-development-workflow-standardization.md`, `docs/ops/development-workflow.md`, `docs/06_CHANGE_MANAGEMENT.md`, `docs/08_DOCS_GOVERNANCE.md`

## 2026-04-25 00:35 | Codex
- Task ID: `MOD-20260425-01`
- CAP: `CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`, `CAP-STOCK-EVENTS`
- 结论: 已启动长记忆文档重构 Phase 1：`AI_HANDOFF_LOG` 压缩为近期窗口、`07_PENDING_TODO` 收敛为当前活跃项，并新增两份 archive summary 承接旧日志与旧待办；同时把“需求完成后必须做文档回流 / 待办收口 / 日志归档”的动作写入 `06 / 08`。
- 风险: 当前只完成第一阶段，`04 / 03 / 02` 还未拆细；后续若继续重构，需要再按同样规则把细节下沉到 `docs/ops / docs/contracts / docs/domain`。
- 链接: `docs/changes/MOD-20260425-01-long-memory-docset-refactor-phase1.md`, `docs/07_PENDING_TODO.md`, `docs/06_CHANGE_MANAGEMENT.md`, `docs/08_DOCS_GOVERNANCE.md`, `docs/archive/ARC-LEG-20260425-ai-handoff-log-pre-v5-summary.md`, `docs/archive/ARC-LEG-20260425-pending-todo-pre-v5-summary.md`

## 2026-04-24 23:40 | Codex
- Task ID: `MOD-20260424-02`
- CAP: `CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`, `CAP-STOCK-EVENTS`
- 结论: 已继续完成第二轮历史过程卡入口压缩：为 `STG-20260411-05~13` 和 `INV-20260410-01 ~ INV-20260411-15` 这一批高频数据治理执行/审计卡补上“先看 `MOD-20260421-01` + `MOD-20260411-14`”提示，避免后续直接把旧施工文档当成当前真相。
- 风险: 当前完成的是“入口治理”，不是重写全部历史卡；若后续主题继续扩张，仍应优先新增/维护母卡，而不是把过程卡重新变成真相入口。
- 链接: `docs/changes/MOD-20260424-02-project-governance-cleanup-program.md`, `docs/changes/MOD-20260421-01-project-current-state-and-doc-governance-normalization.md`, `docs/changes/MOD-20260411-14-market-data-governance-current-state.md`

## 2026-04-24 23:10 | Codex
- Task ID: `MOD-20260424-02`
- CAP: `CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`, `CAP-STOCK-EVENTS`
- 结论: 已完成项目治理收口的前三批首轮落地：`README / 01 / 04 / AI_QUICK_START / MOD-20260421-01` 已统一到 `main / v5.0.0` 与“Windows 数据主站 / Mac 本地研究站 / Cloud 轻量盯盘”口径；`00 / 02 / 06 / 08 / AI_HANDOFF_LOG` 已改为“新卡统一用 `MOD/REQ/INV/CFG/STG-*`，历史 `CHG-*` 只兼容保留”；`03` 已补当前选股接口契约，`07` 已修重复编号与多处过期状态。
- 风险: 历史过程卡仍然很多，后续还要继续做入口压缩；当前只完成了“当前真相 + 规则口径 + 关键入口脚本”的第一轮治理，不等于所有历史文档都已重写。
- 链接: `docs/changes/MOD-20260424-02-project-governance-cleanup-program.md`, `README.md`, `docs/01_SYSTEM_ARCHITECTURE.md`, `docs/04_OPS_AND_DEV.md`, `docs/07_PENDING_TODO.md`, `scripts/check_baseline.sh`

## 2026-04-24 00:10 | Codex
- Task ID: `CHG-20260423-01`
- CAP: `CAP-STOCK-EVENTS`
- 结论: 已补一张新闻事件层当前真相母卡，明确写清“现在实际能拿到哪些数据、哪些是 token 主源、哪些是公共 fallback、还缺什么”，避免继续靠多张过程卡拼现状。
- 风险: 当前母卡只收“事件采集现状”，不包含后续事件理解层；那部分还没开始实现。
- 链接: `docs/changes/MOD-20260424-01-stock-events-current-state.md`, `docs/02_BUSINESS_DOMAIN.md`, `docs/03_DATA_CONTRACTS.md`

## 2026-04-23 20:20 | Codex
- Task ID: `CHG-20260423-01`
- CAP: `CAP-STOCK-EVENTS`, `CAP-SELECTION-RESEARCH`
- 结论: 已把 `qa` 无 token 模式接到 `public_sina_dongmiqa`：`sync_shenzhen_qa / sync_shanghai_qa / backfill_symbol_qa` 现可自动走新浪董秘问答公共页 fallback，并增加公开页面 charset 识别，避免新浪 UTF-8 问答详情页乱码。
- 风险: 当前公共问答 fallback 依赖新浪转写页，稳定性仍低于交易所/Tushare 原始源；但已足够支撑盘后候选票研究。
- 链接: `backend/app/services/stock_events.py`, `backend/tests/test_stock_events.py`, `docs/03_DATA_CONTRACTS.md`, `docs/changes/REQ-20260423-01-stock-event-refine-and-selection-fusion.md`

## 2026-04-23 19:55 | Codex
- Task ID: `CHG-20260423-01`
- CAP: `CAP-STOCK-EVENTS`, `CAP-SELECTION-RESEARCH`
- 结论: 已继续把 `news` 无 token 模式接到 `public_sina_stock_news`：`sync_short_news / sync_major_news / backfill_symbol_news` 现可自动走新浪个股资讯公共页 fallback，支持分页、时间窗过滤、单票匹配和 related symbol 映射。
- 风险: 当前公共 fallback 仍是标题级抓取，不是正文级抓取；问答公共 fallback 仍未接入，下一步优先补这块。
- 链接: `backend/app/services/stock_events.py`, `backend/tests/test_stock_events.py`, `docs/changes/REQ-20260423-01-stock-event-refine-and-selection-fusion.md`, `docs/03_DATA_CONTRACTS.md`

## 2026-04-23 19:30 | Codex
- Task ID: `CHG-20260423-01`
- CAP: `CAP-STOCK-EVENTS`, `CAP-SELECTION-RESEARCH`
- 结论: 已按 STRICT 流程冻结单票事件层二期需求卡，并落地第一阶段后端底座：新增 `GET /api/stock_events/capabilities` 与 `POST /api/stock_events/hydrate/{symbol}`，同时把 coverage/audit 补成“能区分无数据 vs 当前源不可用”。
- 风险: 当前无 token 模式下，问答/新闻公共源仍未真正接入，只是先把能力缺口透明化并打通候选票触发入口；下一步仍要补公共新闻源与问答 fallback。
- 链接: `docs/changes/REQ-20260423-01-stock-event-refine-and-selection-fusion.md`, `backend/app/services/stock_events.py`, `backend/app/routers/stock_events.py`, `backend/tests/test_stock_events.py`, `docs/03_DATA_CONTRACTS.md`

## 2026-04-12 14:20 | Codex
- Task ID: `CHG-20260412-05`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 结论: 已完成第二轮 trade 主链路去重：atomic trade 侧不再重复跑 `compute_5m_review_bars / _bucket_stats_from_ticks / _build_trade_feature_maps`，改成单次 bucket 聚合 + 单次 parent 聚合直接产出 rows 和 daily_feature。复测 `2026-04-01` 8 symbol 样本后，单 symbol 平均耗时进一步降到 `~1.47s`，单线程理论日耗时约 `2.89h`；按 `8 worker` 理想并行估算，首次进入 `~21.7min`，已进 30 分钟目标线。
- 风险: 当前仍是小样本推算，不是完整交易日实跑；下一步要补一轮真实 `8 worker wall time` 验证，并继续压 `load_bundle` 给大票/极端日留余量。
- 链接: `backend/scripts/run_symbol_atomic_validation.py`, `backend/scripts/benchmark_atomic_detailed_profile.py`, `docs/changes/STG-20260412-04-atomic-formal-backfill-runbook.md`

## 2026-04-12 14:05 | Codex
- Task ID: `CHG-20260412-05`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 结论: 已完成第一轮主链路提速并停掉旧全量任务：同一 symbol/day 改成 raw 只读一次，order 聚合改向量化，book 计算改向量化，auction/phase 改复用同一份 raw frame。复测 `2026-04-01` 8 symbol 样本后，单 symbol 平均耗时从 `~5.15s` 降到 `~1.90s`，CSV 读取次数从 `15` 次降到 `3` 次，单线程理论日耗时从 `~10.15h` 降到 `~3.74h`。
- 风险: 新的主要瓶颈已收敛到 `load_bundle + trade`，全量月批仍不该马上恢复；应继续优化 `ticks/order_events` 标准化与 trade 5m 聚合后再重开正式回补。
- 链接: `backend/scripts/backfill_atomic_order_from_raw.py`, `backend/scripts/build_book_state_from_raw.py`, `backend/scripts/build_open_auction_summaries.py`, `backend/scripts/run_atomic_backfill_windows.py`, `backend/scripts/benchmark_atomic_detailed_profile.py`

## 2026-04-12 13:40 | Codex
- Task ID: `CHG-20260412-05`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 结论: 已完成原子事实层正式回补的细粒度性能剖析：`commit` 批量化只能减少写库/锁等待，不能解决主耗时；`2026-04-01` 样本显示单 symbol 平均约读 `15` 次 CSV，真正瓶颈在 `trade/order/book/auction` 的重复 raw 解析与聚合。当前 live 吞吐约 `15.46 symbol/min`，按沪深非科创 `7097` symbols 估算，单日约需 `7.6` 小时。
- 风险: 以当前结构直接连续回补 2026-04→2025-01 会过慢，不适合作为稳定日常工作流；下一步必须优先做 per-symbol raw cache + order/book 聚合向量化优化。
- 链接: `backend/scripts/benchmark_atomic_detailed_profile.py`, `backend/scripts/benchmark_atomic_stage_profile.py`, `docs/changes/STG-20260412-04-atomic-formal-backfill-runbook.md`

## 2026-04-05 00:18 | Codex
- Task ID: `CHG-20260404-03`
- CAP: `CAP-SELECTION-RESEARCH`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已按“不要全量同步大库，先让右侧能看”落地选股专用云端只读 fallback：新增 `/api/selection/history/multiframe`，本地无有效多维数据时自动回退生产 `/api/history/multiframe`；前端选股右侧图表已改为只走这条专用通道，并在命中云端时显示来源提示。旧首页/旧复盘主链路未改。
- 风险: 当前只接了选股右侧的历史多维图；名称映射和本地正式库补齐仍要继续做。若云端临时不可达，右侧仍会退回本地现状，不会改坏旧模块。
- 链接: `backend/app/services/selection_history_proxy.py`, `backend/app/routers/selection.py`, `src/services/selectionService.ts`, `src/components/selection/SelectionDecisionPanel.tsx`, `src/components/dashboard/HistoryMultiframeFusionView.tsx`

## 2026-04-04 23:55 | Codex
- Task ID: `CHG-20260404-02`
- CAP: `CAP-SELECTION-RESEARCH`, `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 结论: 已继续按工作流收口选股页右侧：把顶部判断区压缩为横向摘要，放大主图区域；新增“信号后40天/90天/到现在 + 起止日期”窗口控制；主图改为优先直连 `HistoryMultiframeFusionView` 展示 L1/L2 资金图，没正式 L2 时再回退日级资金 fallback。同时已远程核验 Windows：`D:\MarketData\202603` 现有 `20260302~20260331` 共 22 个日包，`data/market_data.db` 已含 `2026-03-02~2026-03-13` 的 `8111` symbols 正式 L2。
- 风险: Windows 这批正式 L2 还没同步到本地，所以当前页面虽能按新窗口看，但不少股票仍会先走 fallback；下一步应优先做“只同步正式 L2 表，不覆盖本地其它表”的本地对齐。
- 链接: `src/components/selection/SelectionDecisionPanel.tsx`, `src/components/dashboard/HistoryMultiframeFusionView.tsx`, `docs/changes/REQ-20260404-05-selection-data-alignment-and-backfill.md`

## 2026-04-04 23:25 | Codex
- Task ID: `CHG-20260404-02`
- CAP: `CAP-SELECTION-RESEARCH`, `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 结论: 已把选股工作台再收口一轮：候选默认范围限制为沪深A（先排除科创板/北交所），右侧复盘默认改为日线，并在日线下优先复用旧 `HistoryView(local_history)`，保证正式 L2 未补齐前也能先看到日级复盘；同时新增数据对齐卡，明确“选股信号能跑”和“正式复盘历史已补齐”是两层问题。
- 风险: 本地 `history_daily_l2/history_5m_l2` 仍只覆盖极少数 symbol，`stock_universe_meta` 仍为空；本轮尝试连接 Windows 原始数据机失败，且本机 `tailscale` 处于 stopped，后续补 `2026-03` 全量 L2 仍需先恢复远程链路。
- 链接: `src/components/selection/SelectionDecisionPanel.tsx`, `src/components/dashboard/HistoryView.tsx`, `backend/app/services/selection_research.py`, `docs/changes/REQ-20260404-05-selection-data-alignment-and-backfill.md`, `docs/07_PENDING_TODO.md`

> 规则：每条日志必须包含 Task ID、CAP ID、结论、阻塞/风险、链接；每条不超过 8 行要点。

## 2026-04-25 03:55 | Codex
- Task ID: `MOD-20260425-04`
- CAP: `CAP-WIN-PIPELINE`, `CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`
- 结论: 已把盘后正式日跑固化为 `cd /Users/dong/Desktop/AIGC/market-live-terminal && bash ops/run_postclose_l2.sh`；主线脚本已补齐“局域网 HTTP / Cloud relay”双通道同步，禁用 Windows->Mac SSH/scp 直拉，并增加“已完整成功则复用结果”恢复语义。`2026-04-24` 已收口验证：Mac `history_daily_l2=7644`、`history_5m_l2=346154`、`atomic_trade_daily=3184`、`selection_feature_daily=3184`，Cloud verify 通过，dry-run 返回“无待跑交易日”。
- 风险: Cloud merge wall time 仍需继续观察，但链路已从“易挂死”收敛为“可恢复 / 可复用”。
- 链接: `docs/changes/MOD-20260425-04-postclose-l2-command-solidification.md`, `docs/ops/postclose-l2-runbook.md`, `docs/AI_QUICK_START.md`, `backend/scripts/run_postclose_l2_daily.py`
