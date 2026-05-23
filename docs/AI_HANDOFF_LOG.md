# AI_HANDOFF_LOG（短日志）

## 2026-05-20 12:30 | Codex
- Task ID: `MOD-20260520-04-code-governance-plan`
- CAP: `CAP-REALTIME-FLOW`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`
- 结论: 代码治理规划已单独起卡，当前优先级固定为研究页共享壳统一 → 情绪模块双轨清理 → 带股票上下文页面骨架统一 → 首页/复盘页共用逻辑评估。
- 风险: 这只是规划卡，后续真正动代码前还要逐项确认最小治理范围。
- 链接: `docs/changes/MOD-20260520-04-code-governance-plan.md`

## 2026-05-20 12:05 | Codex
- Task ID: `MOD-20260520-02-stage-summaries-for-selection-and-market-heat`
- CAP: `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`
- 结论: 已把选股和热点阶段压成更短的摘要：选股只保留三条主线，热点只保留“解释市场主线 / 辅助候选验证 / 追强候选池”三种用途，并明确不能直接当买点。
- 风险: 这仍是草稿，还要继续压缩成真正的承接文档，而不是阶段说明页。
- 链接: `docs/changes/MOD-20260520-02-stage-summaries-for-selection-and-market-heat.md`

## 2026-05-20 12:10 | Codex
- Task ID: `MOD-20260520-03-stage-summary-for-atomic-and-compact`
- CAP: `CAP-WIN-PIPELINE`, `CAP-HISTORY-30M`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: `atomic / compact` 阶段摘要已并入 `MOD-20260520-01-system-map-and-governance-stage-summary`，不再单独保留；主结论仍是 compact 已成为主链底座，`atomic_limit_state_daily` 作为日级主表，`atomic_limit_state_5m` 不再是默认长期表。
- 风险: 历史补齐和旧依赖剥离仍未完全收尾。
- 链接: `docs/changes/MOD-20260520-01-system-map-and-governance-stage-summary.md`

## 2026-05-20 11:20 | Codex
- Task ID: `MOD-20260520-01-system-map-and-governance-stage-summary`
- CAP: `CAP-REALTIME-FLOW`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`, `CAP-HISTORY-30M`, `CAP-WIN-PIPELINE`
- 结论: 已补系统地图与治理阶段摘要草稿，当前把系统稳定划成三端职责 + 主链/研究主线/专题层，并把 `snapshot`、`full_reverse / atomic backfill / bench`、Cloud 研究主站这几类旧叙事明确降级为非真相入口。
- 风险: 这仍是治理草稿；阶段总结还需要继续压缩 v2/v3、v4、v5 以及数据 / 策略 / 热点几个大主题。
- 链接: `docs/changes/MOD-20260520-01-system-map-and-governance-stage-summary.md`, `docs/ops/atomic-script-families-boundary.md`, `docs/07_PENDING_TODO.md`

## 2026-05-20 11:45 | Codex
- Task ID: `MOD-20260520-01-system-map-and-governance-stage-summary`
- CAP: `CAP-REALTIME-FLOW`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`, `CAP-HISTORY-30M`, `CAP-WIN-PIPELINE`
- 结论: 已把 `v2 / v4 / v5` 三段历史压成一张简表，明确 `v2` 只留研究/兼容语义，`v4` 是底座但过程卡不能再当运行步骤，`v5` 是当前研究/观察工作台而不是稳定自动买入系统。
- 风险: 这仍是阶段摘要草稿，后续还要继续补数据 / 策略 / 热点的主题级总结。
- 链接: `docs/changes/MOD-20260520-01-system-map-and-governance-stage-summary.md`, `docs/strategy-rework/current-research-operating-summary.md`

## 2026-05-19 15:40 | Codex
- Task ID: `MOD-20260519-02-process-material-risk-grading-batch1`
- CAP: `CAP-REALTIME-FLOW`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`
- 结论: 本轮把 `ops` 的历史脚本族边界单独收成 `docs/ops/atomic-script-families-boundary.md`，明确区分了正式白名单入口与 `full_reverse / atomic backfill / bench / snapshot` 这几类历史工具。同时复核 `strategy-rework` 已迁 archive 的 3 份旧顶层文件后，没再发现活入口指向它们的原路径。
- 风险: 历史脚本还在仓库里，当前只是文档收口，不是脚本改名或物理迁移。
- 链接: `docs/ops/atomic-script-families-boundary.md`, `docs/04_OPS_AND_DEV.md`, `docs/07_PENDING_TODO.md`

## 2026-05-19 15:10 | Codex
- Task ID: `MOD-20260519-02-process-material-risk-grading-batch1`
- CAP: `CAP-REALTIME-FLOW`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`
- 结论: `strategy-rework` 顶层入口和 `ops` 默认脚本入口已进一步收紧。`LONG_MEMORY / current-strategy-conclusion / current-research-operating-summary` 已被明确成新的默认三件套；`project-status-20260427.md`、`experiment-decision-log.md`、`archive-index.md` 都已降级为追溯型材料。`docs/04_OPS_AND_DEV.md` 与 `docs/ops/development-workflow.md` 也已写明正式脚本白名单，默认不再从 `bench / full_reverse / atomic backfill` 族脚本进。
- 风险: `ops` 历史脚本族还只是入口降级，还没做命名/迁移清理。
- 链接: `docs/strategy-rework/current-research-operating-summary.md`, `docs/04_OPS_AND_DEV.md`, `docs/07_PENDING_TODO.md`

## 2026-05-19 14:35 | Codex
- Task ID: `MOD-20260519-02-process-material-risk-grading-batch1`
- CAP: `CAP-REALTIME-FLOW`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`
- 结论: 第三批已开始落地到 `strategy-rework` 顶层。`current-inventory.md` 已迁入 `docs/archive/`，同时新增 `current-research-operating-summary.md` 作为“当前阶段状态 / 继续推进项 / 明确否决项”的压缩入口，`README / AI_QUICK_START / handoff` 也已开始改向新入口。当前 `strategy-rework` 顶层已经从“多份并列现状卡”收窄到更接近“三件套”：`LONG_MEMORY`、`current-strategy-conclusion`、`current-research-operating-summary`。
- 风险: `project-status-20260427.md` 与 `experiment-decision-log.md` 仍在当前入口链路上，不能直接硬迁；下一步需要先补链接收口，再决定是否继续归档。
- 链接: `docs/strategy-rework/current-research-operating-summary.md`, `docs/archive/ARC-LEG-20260519-strategy-research-current-inventory.md`, `docs/07_PENDING_TODO.md`

## 2026-05-19 14:05 | Codex
- Task ID: `MOD-20260519-02-process-material-risk-grading-batch1`
- CAP: `CAP-REALTIME-FLOW`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`
- 结论: 第二批真实归档已落地。`docs/selection` 顶层的 `selection_research_cleanup_plan / selection_cleanup_execution_todo / selection_cleanup_deleted_manifest / opportunity_discovery_archive_summary` 已迁入 `docs/archive/`，同时新增 `docs/selection/selection_research_archive_decision_summary.md` 承接压缩结论。当前 `docs/selection` 顶层已明显变薄，只保留现行说明书、现行接入方案和主题级入口。
- 风险: `docs/strategy-rework` 顶层仍存在多入口竞争；`ops/` 历史脚本族也还没有真正从默认阅读路径退出。下一批如果不继续做，未来 AI 还是会在这两块浪费上下文。
- 链接: `docs/selection/selection_research_archive_decision_summary.md`, `docs/archive/ARCHIVE_CATALOG.md`, `docs/07_PENDING_TODO.md`

## 2026-05-19 13:10 | Codex
- Task ID: `MOD-20260519-02-process-material-risk-grading-batch1`
- CAP: `CAP-REALTIME-FLOW`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`
- 结论: 第一批入口降噪已经落地。已给 `docs/changes` 中 5 张高风险现状型过程卡、`docs/strategy-rework/handoff-for-next-ai.md` 补上“先看当前母卡/当前真相”的顶部提示，同时收紧了 `docs/strategy-rework/README.md`、`docs/selection/selection_research_master.md`、`docs/04_OPS_AND_DEV.md` 的默认阅读路径。当前治理线可以从“先止血”切到“真实归档和阶段汇总”。
- 风险: 这一步只是减少误读，不是体量清理；`docs/selection/` 顶层 `final / plan / cleanup` 类文件、`strategy-rework` 顶层多入口、`ops` 历史脚本族仍会继续消耗上下文，第二批必须开始真实归档。
- 链接: `docs/changes/MOD-20260519-02-process-material-risk-grading-batch1.md`, `docs/07_PENDING_TODO.md`

## 2026-05-19 12:05 | Codex
- Task ID: `MOD-20260519-02-process-material-risk-grading-batch1`
- CAP: `CAP-REALTIME-FLOW`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`
- 结论: 已完成第一批过程材料风险分级。当前最高风险区已明确集中在 `docs/changes` 的“现状型过程卡”、`docs/strategy-rework` 的旧交接与未归档实验入口、`docs/selection` 顶层的 `final/plan/cleanup` 类文件，以及 `ops` 中仍高频暴露 `full_reverse / bench` 的脚本族。当前建议仍然是不删文件，先做入口提示补齐和默认阅读路径收缩。
- 风险: 如果现在直接删文件，误删仍有追溯价值资料的风险较高；当前更稳的做法是先降低它们作为“默认真相入口”的可见性。
- 链接: `docs/changes/MOD-20260519-02-process-material-risk-grading-batch1.md`, `docs/07_PENDING_TODO.md`

## 2026-05-19 12:20 | Codex
- Task ID: `MOD-20260519-01-system-surface-audit-and-doc-prune-plan`
- CAP: `CAP-REALTIME-FLOW`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`
- 结论: 治理线目标已更新为“先降噪，再归档，再阶段汇总”。用户明确不接受“旧文件全留着只加提示”的终局，因此后续应在第一批入口降噪之后，继续推进真实 archive 迁移和少数阶段总结文档落地，用摘要替代大量零散过程卡。
- 风险: 如果只停在提示层，未来 AI 仍会反复读大量过时材料，虽然不一定做错，但会持续浪费上下文并增加误判概率。
- 链接: `docs/changes/MOD-20260519-01-system-surface-audit-and-doc-prune-plan.md`, `docs/changes/MOD-20260519-02-process-material-risk-grading-batch1.md`

## 2026-05-19 11:20 | Codex
- Task ID: `MOD-20260519-01-system-surface-audit-and-doc-prune-plan`
- CAP: `CAP-REALTIME-FLOW`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`
- 结论: 已完成系统产品面、组件复用面、文档/脚本噪音面的第一轮盘点。当前系统已经形成“盯盘 / 复盘 / 选股”主链，以及“市场热点、趋势研究、模型训练、专题复盘”研究层；现阶段最优先的治理动作不是直接重构代码，而是先清一轮过程材料堆积，避免过时信息继续误导实现。
- 风险: 当前风险主要不在“功能不存在”，而在“入口太多、过程卡太多、历史实验资料仍被误当成真相源”；若不先做文档入口降噪，后续代码与脚本治理容易失焦。
- 链接: `docs/changes/MOD-20260519-01-system-surface-audit-and-doc-prune-plan.md`, `docs/07_PENDING_TODO.md`

## 2026-05-18 19:20 | Codex
- Task ID: `MOD-20260518-01-compact-training-readiness-and-project-health`
- CAP: `CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`
- 结论: `2026-04` 到 `2026-05` 新重跑数据已经足以支撑现有系统主链和主要页面打开，但还不能叫“完美支持”。最关键的 3 个缺口是：`stock_universe_meta` 为空导致复盘池/选股画像元数据退化；`history_daily_l2 / history_5m_l2` 在 `2026-04-01 ~ 2026-04-10` 缺失，部分链路靠 atomic merge 才继续工作；`market_heat` 仍会读旧 snapshot/cache，且默认 source 候选可能落到空的 old full_reverse，已影响局部统计准确性。
- 风险: 若把“接口 200 / 页面能开”直接视为“数据已完全恢复”，会误判当前质量状态；当前更像是主链可用、质量未完全收口。
- 链接: `docs/changes/MOD-20260518-01-compact-training-readiness-and-project-health.md`, `docs/07_PENDING_TODO.md`

## 2026-05-18 18:10 | Codex
- Task ID: `MOD-20260518-01-compact-training-readiness-and-project-health`
- CAP: `CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`
- 结论: compact DB 基线已足够支撑当前主链；短期真正要盯的不是 `atomic_limit_state_5m`，而是历史 `order/book/auction`、`history_*_l2`、`stock_universe_meta`、`selection_feature_daily / selection_signal_daily` 的覆盖与重算。训练侧现状可支撑 P0 feature store / 最近窗口 smoke，但还不够作为未来本地模型训练的完整长期基线。
- 风险: “结果库覆盖到 2026-05-15” 不能等同于 “5 月 raw L2 每天都已零失败跑完”；`2026-04` 在 compact 结果库里已覆盖，但本地镜像不足以单独证明某条 4 月批次的原始执行进度。
- 链接: `docs/changes/MOD-20260518-01-compact-training-readiness-and-project-health.md`, `docs/07_PENDING_TODO.md`

## 2026-05-16 21:35 | Codex
- Task ID: `MOD-20260516-01-project-governance-phase1`
- CAP: `N/A`
- 结论: 已完成治理线第一阶段收口：只补治理规则、入口文档和只读巡检纪律；明确治理工作先在 `main` 只读排查，存在并行 worktree 时必须使用独立治理分支 / worktree；过程只进 change card，handoff 只保留短日志。
- 风险: 本轮不触碰业务代码、不调整 README、不改 `market_heat` 业务文档；`07_PENDING_TODO.md` 仅固化清理规则，未逐项执行清理。
- 链接: `docs/changes/MOD-20260516-01-project-governance-phase1.md`, `docs/selection/daily_candidate_source_contract.md`

## 2026-05-07 09:33 | Codex
- Task ID: `MOD-20260507-02-el-nino-trend-research-intake`
- CAP: `CAP-SELECTION-RESEARCH`
- 结论: 新增厄尔尼诺 / 气候异常长期趋势线索：官方口径是 2026 年中后段概率上升但非必然；已落研究卡、结构化跟踪数据，并接入趋势研究 API/页面。
- 补充: 已固化长期趋势话题 SOP，并按流程补齐厄尔尼诺深度计划；橡胶链纳入观察，海南橡胶为 A 类核心观察，轮胎股为 C 类成本压力旁路。
- 2026-05-09 补充: 完成橡胶长周期研究，World Bank RSS3 显示 2011-02 高点 6.2592 美元/kg，2026-04 为 2.5056 美元/kg，高点约为当前 2.5 倍；2011 式行情需要需求、天气、库存、油价和流动性共振。
- 2026-05-09 继续补充: 已解释并接入 RU/NR 主连、RU-NR价差、2024以来价格阶段；基于 NOAA ONI 和 World Bank 商品价格完成历史厄尔尼诺商品影响统计，优先研究顺序收敛为橡胶、棕榈油/油脂、粮食种业/水利抗旱。
- 风险: 当前仍是线索期，没有 A 股个股横评；需等待 2026-05-14 NOAA/CPC 更新和后续农产品/水利/电力传导验证。
- 验证: `npm run check:version`、`npm run build` 通过。
- 链接: `docs/changes/MOD-20260507-02-el-nino-trend-research-intake.md`, `docs/selection/long_term_trends/cases/el_nino_2026-05-07.md`

## 2026-05-07 00:30 | Codex
- Task ID: `MOD-20260507-01-repo-consolidation-cloud-lite-freeze`
- CAP: `CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`
- 结论: 仓库收口进入 `codex/repo-consolidation-20260506` 分支：合入 GitHub main 与本地 v5.1.0，保护 `docs/selection/long_term_trends/` 作为当前唯一持续更新研究目录，并把 Cloud 后续边界冻结为 Lite：盯盘 + 复盘优先。
- 风险: 本轮不发布云端、不删除云端数据；热点/选股/长期研究默认本地使用，Cloud 需后续通过 profile 隐藏或禁用。
- 链接: `docs/changes/MOD-20260507-01-repo-consolidation-cloud-lite-freeze.md`, `docs/selection/long_term_trends/README.md`

## 2026-05-06 00:45 | Codex
- Task ID: `MOD-20260506-01-market-heat-strong-momentum-exit-research`
- CAP: `CAP-SELECTION-RESEARCH`
- 结论: 小主题热点研究收口到“强者恒强追强候选池 + 卖点管理”：纯热点不能直接买；强者恒强规则能提高后20日冲高概率；2025 年 100万单账户回测里，分批止盈版 `+24.2%`，去掉半仓仅 `+1.9%`，固定持有20日 `-14.2%`。
- 风险: 当前仍是研究/候选机制，不是自动买入系统；样本以 2025 年主板 L1/L2 数据为主，后续需继续测多仓位和不同市场阶段。
- 链接: `docs/selection/market_heat/README.md`, `docs/selection/market_heat/backtests/strong_momentum_exit_compare_2025.md`

## 2026-04-29 23:01 | Codex
- Task ID: `MOD-20260429-07-core-doc-audit-and-external-sync`
- CAP: `CAP-REALTIME-FLOW`, `CAP-HISTORY-30M`, `CAP-SELECTION-RESEARCH`, `CAP-WIN-PIPELINE`
- 结论: 已完成核心文档审计与外部知识库同步准备：对齐 `v5.1.0` 版本口径，回写盯盘/复盘/选股三大已落地模块现状，并明确热点板块仍是 `EXPLORING`。
- 风险: 主工作区仍有热点板块相关未提交代码和过程卡；本次文档收口不代表热点模块正式投产。
- 链接: `docs/domain/selection-research.md`, `docs/strategy-rework/LONG_MEMORY.md`

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
- 链接: `docs/strategy-rework/current-research-operating-summary.md`, `docs/strategy-rework/strategies/S03-news-event-revaluation/README.md`, `docs/archive/ARC-LEG-20260519-strategy-research-current-inventory.md`


> 当前新日志的 `Task ID` 优先填写当前变更卡 ID（`MOD/REQ/INV/CFG/STG-*`）；历史 `CHG-*` 保留为旧阶段记录，不强行重写。
> 当前文件只保留最近 `1~2` 个版本窗口的短日志；更早阶段摘要见：
> - `docs/archive/ARC-LEG-20260429-ai-handoff-log-v5-window-summary.md`
> - `docs/archive/ARC-LEG-20260425-ai-handoff-log-pre-v5-summary.md`
> - `docs/archive/AI_HANDOFF_LOG_LEGACY_2026-03-09.md`
