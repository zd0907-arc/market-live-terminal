## 2026-04-04 23:25 | Codex
- Task ID: `CHG-20260404-02`
- CAP: `CAP-SELECTION-RESEARCH`, `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 结论: 已把选股工作台再收口一轮：候选默认范围限制为沪深A（先排除科创板/北交所），右侧复盘默认改为日线，并在日线下优先复用旧 `HistoryView(local_history)`，保证正式 L2 未补齐前也能先看到日级复盘；同时新增数据对齐卡，明确“选股信号能跑”和“正式复盘历史已补齐”是两层问题。
- 风险: 本地 `history_daily_l2/history_5m_l2` 仍只覆盖极少数 symbol，`stock_universe_meta` 仍为空；本轮尝试连接 Windows 原始数据机失败，且本机 `tailscale` 处于 stopped，后续补 `2026-03` 全量 L2 仍需先恢复远程链路。
- 链接: `src/components/selection/SelectionDecisionPanel.tsx`, `src/components/dashboard/HistoryView.tsx`, `backend/app/services/selection_research.py`, `docs/changes/REQ-20260404-05-selection-data-alignment-and-backfill.md`, `docs/07_PENDING_TODO.md`

## 2026-04-04 23:55 | Codex
- Task ID: `CHG-20260404-02`
- CAP: `CAP-SELECTION-RESEARCH`, `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 结论: 已继续按工作流收口选股页右侧：把顶部判断区压缩为横向摘要，放大主图区域；新增“信号后40天/90天/到现在 + 起止日期”窗口控制；主图改为优先直连 `HistoryMultiframeFusionView` 展示 L1/L2 资金图，没正式 L2 时再回退日级资金 fallback。同时已远程核验 Windows：`D:\MarketData\202603` 现有 `20260302~20260331` 共 22 个日包，`data/market_data.db` 已含 `2026-03-02~2026-03-13` 的 `8111` symbols 正式 L2。
- 风险: Windows 这批正式 L2 还没同步到本地，所以当前页面虽能按新窗口看，但不少股票仍会先走 fallback；下一步应优先做“只同步正式 L2 表，不覆盖本地其它表”的本地对齐。
- 链接: `src/components/selection/SelectionDecisionPanel.tsx`, `src/components/dashboard/HistoryMultiframeFusionView.tsx`, `docs/changes/REQ-20260404-05-selection-data-alignment-and-backfill.md`

## 2026-04-05 00:18 | Codex
- Task ID: `CHG-20260404-03`
- CAP: `CAP-SELECTION-RESEARCH`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已按“不要全量同步大库，先让右侧能看”落地选股专用云端只读 fallback：新增 `/api/selection/history/multiframe`，本地无有效多维数据时自动回退生产 `/api/history/multiframe`；前端选股右侧图表已改为只走这条专用通道，并在命中云端时显示来源提示。旧首页/旧复盘主链路未改。
- 风险: 当前只接了选股右侧的历史多维图；名称映射和本地正式库补齐仍要继续做。若云端临时不可达，右侧仍会退回本地现状，不会改坏旧模块。
- 链接: `backend/app/services/selection_history_proxy.py`, `backend/app/routers/selection.py`, `src/services/selectionService.ts`, `src/components/selection/SelectionDecisionPanel.tsx`, `src/components/dashboard/HistoryMultiframeFusionView.tsx`

## 2026-03-21 19:10 | Codex
- Task ID: `CHG-20260321-01`, `CHG-20260321-02`
- CAP: `CAP-REALTIME-FLOW`, `CAP-HISTORY-30M`, `CAP-L2-HISTORY-FOUNDATION`, `CAP-SANDBOX-REVIEW`
- 结论: 已完成 最后一个支持“旧版 / 新版切换”的生产基线（`v4.2.28`），逐页面写清首页旧版/新版并存、正式复盘并库后的真实链路与数据覆盖；同时已冻结下一阶段“去掉旧版、只保留新版”的 REQ，并准备从新分支推进。
- 风险: 首页去旧版首期应按“先下入口、后删代码”推进；`HistoryView` 与旧接口若立刻物理删除，会抬高回滚成本。正式复盘元数据 `stock_universe_meta` 仍需后续补自动刷新。
- 链接: `docs/archive/changes/ARC-CHG-20260321-v4-2-28-last-legacy-toggle-baseline.md`, `docs/archive/changes/ARC-CHG-20260321-fusion-only-remove-legacy-entry.md`, `docs/07_PENDING_TODO.md`, `docs/AI_QUICK_START.md`

# AI_HANDOFF_LOG（短日志）

## 2026-04-12 13:40 | Codex
- Task ID: `CHG-20260412-05`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 结论: 已完成原子事实层正式回补的细粒度性能剖析：`commit` 批量化只能减少写库/锁等待，不能解决主耗时；`2026-04-01` 样本显示单 symbol 平均约读 `15` 次 CSV，真正瓶颈在 `trade/order/book/auction` 的重复 raw 解析与聚合。当前 live 吞吐约 `15.46 symbol/min`，按沪深非科创 `7097` symbols 估算，单日约需 `7.6` 小时。
- 风险: 以当前结构直接连续回补 2026-04→2025-01 会过慢，不适合作为稳定日常工作流；下一步必须优先做 per-symbol raw cache + order/book 聚合向量化优化。
- 链接: `backend/scripts/benchmark_atomic_detailed_profile.py`, `backend/scripts/benchmark_atomic_stage_profile.py`, `docs/changes/STG-20260412-04-atomic-formal-backfill-runbook.md`

## 2026-04-12 14:05 | Codex
- Task ID: `CHG-20260412-05`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 结论: 已完成第一轮主链路提速并停掉旧全量任务：同一 symbol/day 改成 raw 只读一次，order 聚合改向量化，book 计算改向量化，auction/phase 改复用同一份 raw frame。复测 `2026-04-01` 8 symbol 样本后，单 symbol 平均耗时从 `~5.15s` 降到 `~1.90s`，CSV 读取次数从 `15` 次降到 `3` 次，单线程理论日耗时从 `~10.15h` 降到 `~3.74h`。
- 风险: 新的主要瓶颈已收敛到 `load_bundle + trade`，全量月批仍不该马上恢复；应继续优化 `ticks/order_events` 标准化与 trade 5m 聚合后再重开正式回补。
- 链接: `backend/scripts/backfill_atomic_order_from_raw.py`, `backend/scripts/build_book_state_from_raw.py`, `backend/scripts/build_open_auction_summaries.py`, `backend/scripts/run_atomic_backfill_windows.py`, `backend/scripts/benchmark_atomic_detailed_profile.py`

## 2026-04-12 14:20 | Codex
- Task ID: `CHG-20260412-05`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 结论: 已完成第二轮 trade 主链路去重：atomic trade 侧不再重复跑 `compute_5m_review_bars / _bucket_stats_from_ticks / _build_trade_feature_maps`，改成单次 bucket 聚合 + 单次 parent 聚合直接产出 rows 和 daily_feature。复测 `2026-04-01` 8 symbol 样本后，单 symbol 平均耗时进一步降到 `~1.47s`，单线程理论日耗时约 `2.89h`；按 `8 worker` 理想并行估算，首次进入 `~21.7min`，已进 30 分钟目标线。
- 风险: 当前仍是小样本推算，不是完整交易日实跑；下一步要补一轮真实 `8 worker wall time` 验证，并继续压 `load_bundle` 给大票/极端日留余量。
- 链接: `backend/scripts/run_symbol_atomic_validation.py`, `backend/scripts/benchmark_atomic_detailed_profile.py`, `docs/changes/STG-20260412-04-atomic-formal-backfill-runbook.md`

## 2026-03-21 21:05 | Codex
- Task ID: `CHG-20260321-03`
- CAP: `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已完成正式复盘页顶部操作栏重构：股票选择改为首页同款搜索体验，日期改为范围选择器，切股默认回到最近 `90` 天，顶部标签改为两行极简摘要；同时保留平台 logo，删去重复 symbol 与“锚点未设置”等无效信息。
- 风险: 本地若看到 `HTTP 404` 并非“无数据”，而是当前后端未提供 `/api/review/*` 路由或代理未连通；正式“无数据”应表现为 `HTTP 200 + 空数组`。本轮最初曾误在 `main` 本地工作树改动，现已转移到 `codex/review-toolbar-refactor`。
- 链接: `src/components/sandbox/SandboxReviewPage.tsx`, `docs/changes/MOD-20260321-03-review-toolbar-refactor.md`

## 2026-03-21 22:15 | Codex
- Task ID: `CHG-20260321-03`
- CAP: `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已继续收口复盘页操作栏：移除整个第二行说明文字、去掉日期按钮固定“最近90天”提示、删除粒度区“自动”按钮，并在日期快捷区间中补 `10天`；当前改为“选定日期范围后自动落到推荐粒度，用户如有需要再手动切换”。
- 风险: 当前“推荐粒度”是按日期跨度静态落档，不再随图表 dataZoom 动态切换；若后续需要恢复“拖动窗口自动变档”，需再单独冻结交互规则。
- 链接: `src/components/sandbox/SandboxReviewPage.tsx`, `docs/changes/MOD-20260321-03-review-toolbar-refactor.md`

## 2026-03-21 22:45 | Codex
- Task ID: `CHG-20260321-03`
- CAP: `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已继续优化复盘页视觉与交互：新增横向股票信息卡显示所选股票最新一日基础信息；日期快捷按钮外置；`60/90天` 默认落 `1d`；股价主图高度压缩；两个净流入对比图改为柱状图；tooltip 改为顶部固定且精简，避免随鼠标漂出画面。
- 风险: 最新一日信息卡当前基于复盘返回的最新日线数据派生，不额外请求实时 quote；若后续要完全复刻首页实时价卡，需要再单独决定是否引入 quote 口径差异。
- 链接: `src/components/sandbox/SandboxReviewPage.tsx`, `docs/changes/MOD-20260321-03-review-toolbar-refactor.md`

## 2026-03-21 23:05 | Codex
- Task ID: `CHG-20260321-03`
- CAP: `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已把首页与复盘页股票信息卡收口为共享组件 `StockQuoteHeroCard`，并让复盘页改用实时 quote 补齐真实股票名称与最新行情日；同时复盘页搜索框在选股后只显示名称，不再把 `symbol` 回填到输入框，快捷区间/粒度按钮也已缩小并改成可换行全量可见。
- 风险: 首页卡片已切到共享组件，但首页搜索候选列表仍保留代码信息，当前“代码尽量降噪”的调整主要落实在复盘页选股态；若后续要把首页搜索候选也改成纯名称，需要单独再收一轮搜索体验。
- 链接: `src/components/common/StockQuoteHeroCard.tsx`, `src/App.tsx`, `src/components/sandbox/SandboxReviewPage.tsx`, `docs/changes/MOD-20260321-03-review-toolbar-refactor.md`

## 2026-03-21 20:05 | Codex
- Task ID: `CHG-20260321-02`
- CAP: `CAP-REALTIME-FLOW`, `CAP-HISTORY-30M`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已完成首页“只保留新版”发布准备：版本提升到 `v4.2.29`，首页已去掉 `旧版 / 新版` 切换与旧版 `30分钟线 / 日线` 入口，并完成基线检查。
- 风险: 当前仍保留 `HistoryView` 与旧接口作为一版暗桩回滚缓冲；本轮属于“下入口，不删代码”的安全收敛。
- 链接: `src/App.tsx`, `docs/archive/changes/ARC-CHG-20260321-fusion-only-remove-legacy-entry.md`, `docs/archive/changes/ARC-CHG-20260321-v4-2-28-last-legacy-toggle-baseline.md`


## 2026-03-21 19:40 | Codex
- Task ID: `CHG-20260321-02`
- CAP: `CAP-REALTIME-FLOW`, `CAP-HISTORY-30M`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已在分支 `codex/fusion-only-remove-legacy` 完成首页“只保留新版”第一步实现：去掉 `旧版 / 新版` 顶部切换与旧版 `30分钟线 / 日线` 首页入口，首页现只保留 `当日分时 + 历史多维 + 散户情绪监测`。
- 风险: 当前仅移除入口，尚未物理删除 `HistoryView` 与旧接口；这符合“先下入口、后删代码”的回滚缓冲策略，但正式线上尚未发版。
- 链接: `src/App.tsx`, `docs/archive/changes/ARC-CHG-20260321-fusion-only-remove-legacy-entry.md`, `docs/archive/changes/ARC-CHG-20260321-v4-2-28-last-legacy-toggle-baseline.md`

> 规则：每条日志必须包含 Task ID、CAP ID、结论、阻塞/风险、链接；每条不超过 8 行要点。
>
> 历史长日志归档：`docs/archive/AI_HANDOFF_LOG_LEGACY_2026-03-09.md`

---

## 2026-03-19 02:40 | Codex
- Task ID: `CHG-20260319-01`
- CAP: `CAP-REALTIME-FLOW`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已把资金博弈调参从“当前页面临时态”升级为“按股票 `symbol` 写入浏览器本地持久化”：同一只股票刷新后继续沿用上次参数，切换到其他股票则自动载入各自保存值；点击“恢复默认”会清除当前股票的本地覆盖值。
- 风险: 当前持久化仅限浏览器本地 `localStorage`，不做跨设备同步；若未来需要把调参结果共享给别的终端或用户，仍需单独冻结后端配置口径。
- 链接: `src/components/dashboard/FundsBattleSection.tsx`, `docs/changes/REQ-20260318-06-funds-battle-dual-track-and-signal-engine.md`, `docs/07_PENDING_TODO.md`

## 2026-03-19 02:32 | Codex
- Task ID: `CHG-20260319-01`
- CAP: `CAP-REALTIME-FLOW`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已继续补强资金博弈调参体验：5 个参数控件旁均新增 `!` 浮窗解释，并在面板内加入“老 finalized 样本缺 `total_volume` 时，VWAP 会退化为 close”的专项提示；对 `粤桂股份(sz000833) 2026-03-18` 本地样本已验证，若想先看到信号，优先把 `VWAP 偏离阈值` 调到 `0`，必要时再把 `吃/出 差值阈值` 下调到 `100万`。
- 风险: 当前这类旧 finalized 样本缺少 `total_volume/cancel_*` 时，仍不适合拿来验证完整的 `诱空/诱多` 逻辑；页面只做了显式提示，没有伪造缺失因子。
- 链接: `src/components/dashboard/FundsBattleSection.tsx`, `src/components/dashboard/fundsBattleUtils.ts`

## 2026-03-19 02:18 | Codex
- Task ID: `CHG-20260319-01`
- CAP: `CAP-REALTIME-FLOW`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已为资金博弈模块落地首期前端调参 UI：页面内新增折叠式“高级设置”，开放 `diff/cancel/VWAP偏离/通道/共振` 五项参数，默认使用放宽后的联调值，并即时重算 L1/L2 的 `吃/出/诱空/诱多` 标签与计数；调参仅作用于当前页面会话，不写后端也不持久化。
- 风险: 当前本地 `2026-03-18` 旧 finalized 样本仍缺完整 order-event 扩展因子，因此调参主要先改善差值类信号可见性；若要让 `诱空/诱多` 在老样本上完整恢复，仍需补历史字段级重算。
- 链接: `src/components/dashboard/FundsBattleSection.tsx`, `src/components/dashboard/FundsBattleL1Panel.tsx`, `src/components/dashboard/FundsBattleL2Panel.tsx`, `src/components/dashboard/fundsBattleUtils.ts`, `docs/changes/REQ-20260318-06-funds-battle-dual-track-and-signal-engine.md`

## 2026-03-19 01:35 | Codex
- Task ID: `CHG-20260319-01`
- CAP: `CAP-REALTIME-FLOW`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已把 `粤桂股份(sz000833)` 与 `利通电子(sh603629)` 的 `2026-03-18` finalized L2 样本从 production 同步到本地库用于联调；同时按你的反馈把当日分时页主力动态恢复为原 L1 上下双图样式，并将资金博弈恢复原 L1 模块后，在其下新增一块上下结构的 `L2 真实资金博弈` 面板。
- 风险: 当前这两只票同步到本地的 `2026-03-18` finalized L2 仍属于旧版存量结果，只含 L2 买卖事实，不含 `add/cancel/l2_cvd_delta/l2_oib_delta` 扩展因子；因此 L2 面板可用于看对比曲线，但新信号引擎暂不能在这天完整发挥。
- 链接: `src/components/dashboard/RealtimeView.tsx`, `src/components/dashboard/FundsBattleL2Panel.tsx`, `docs/07_PENDING_TODO.md`

## 2026-03-19 01:52 | Codex
- Task ID: `CHG-20260319-01`
- CAP: `CAP-REALTIME-FLOW`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已继续按 UI 反馈收口资金博弈：L1 不再复用旧分钟级 `SentimentTrend`，改为使用统一 `intraday_fusion` 的 5m L1 数据重绘原风格 CVD/OIB，并把原火球/盾牌替换为 L2 推导出的 `吃/出/诱空/诱多` 文字标签；L2 面板也补了同宽右侧摘要条，修正了 Y 轴负号可见性与高度压缩。
- 风险: 盘后/复盘态已停止 30s 轮询，但当前停轮询判断仍基于前端交易时段推断；若后续要精确覆盖跨时段长开页场景，可再补“状态切换时自动重建轮询”的细化逻辑。
- 链接: `src/components/dashboard/FundsBattleL1Panel.tsx`, `src/components/dashboard/FundsBattleL2Panel.tsx`, `src/components/dashboard/fundsBattleUtils.ts`, `src/components/dashboard/RealtimeView.tsx`

## 2026-03-19 00:58 | Codex
- Task ID: `CHG-20260319-02`
- CAP: `CAP-MKT-TIME`
- 结论: 已把交易日北京时间 `00:00 ~ 09:15` 的本地展示语义从“盘前未开盘”调整为“隔夜复盘”：后端 `MarketClock.get_market_context()` 现在返回 `market_status=post_close` 且默认展示上一交易日；前端本地 provisional 状态也同步改为复盘态，避免页面在 `2026-03-19 00:xx` 这类时点错误显示盘前心智。
- 风险: 当前只是状态机与本地展示语义修正，不改变默认仍查看上一交易日这一事实；若后续要把凌晨也展示为“今天占位态”，需另开需求卡。
- 链接: `backend/app/core/http_client.py`, `src/components/dashboard/RealtimeView.tsx`, `backend/tests/test_market_clock.py`, `docs/02_BUSINESS_DOMAIN.md`

## 2026-03-19 01:05 | Codex
- Task ID: `CHG-20260319-01`
- CAP: `CAP-REALTIME-FLOW`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已完成当日分时页 L1/L2 双轨首轮实现：后端为 `history_5m_l2/realtime_5m_preview` 补齐 `total_volume + add/cancel + l2_cvd_delta + l2_oib_delta`，新增统一接口 `/api/realtime/intraday_fusion`；前端当日分时页已把 `主力动态 + 资金博弈分析` 改为 5m 单轨/双轨自适应，并用前端 VWAP + 极简文字标签替换旧 `SentimentTrend` 主链路。
- 风险: 当前 `委托类型=U` 仍按 cancel-like v1 假设处理；信号阈值虽已预留常量但尚未开放 UI，复盘页也尚未复用统一双轨接口。
- 链接: `backend/app/db/l2_history_db.py`, `backend/app/db/realtime_preview_db.py`, `backend/scripts/l2_daily_backfill.py`, `backend/app/routers/market.py`, `src/components/dashboard/IntradayDualTrackPanels.tsx`, `src/components/dashboard/RealtimeView.tsx`, `backend/tests/test_l2_daily_backfill.py`, `backend/tests/test_realtime_dashboard_router.py`

## 2026-03-19 00:07 | Codex
- Task ID: `CHG-20260319-01`
- CAP: `CAP-REALTIME-FLOW`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已按 STRICT 文档先行流程冻结“当日分时页 L1/L2 双轨重构”需求：新增 `STG-20260318-03` 母卡与 `REQ-20260318-03~06` 四张分期卡，并同步 core docs，明确范围覆盖 `主力动态 + 资金博弈分析`、统一 `5m`、盘后自动切双轨、`逐笔委托 0/1/U` 的 v1 事件解释，以及新正式主路径 `/api/realtime/intraday_fusion`。
- 风险: 当前仍停留在文档阶段；`委托类型=U` 仍是 v1 假设，且调参 UI / 复盘页并库均后置到实现后续阶段。
- 链接: `docs/changes/STG-20260318-03-intraday-l1-l2-dual-track-rebuild.md`, `docs/changes/REQ-20260318-03-order-event-factors-and-5m-contract.md`, `docs/changes/REQ-20260318-04-intraday-dual-track-api-and-mode-switch.md`, `docs/changes/REQ-20260318-05-monitor-mainflow-dual-track-ui.md`, `docs/changes/REQ-20260318-06-funds-battle-dual-track-and-signal-engine.md`, `docs/02_BUSINESS_DOMAIN.md`, `docs/03_DATA_CONTRACTS.md`

## 2026-03-18 22:15 | Codex
- Task ID: `CHG-20260318-02`
- CAP: `CAP-MKT-TIME`, `CAP-REALTIME-FLOW`
- 结论: 已完成当日分时市场状态机收口：后端新增 `盘前 / 盘中 / 午间休市 / 盘后 / 休盘日` 五态，`/api/realtime/dashboard` 明确返回 `market_status / default_display_scope / view_mode`；前端状态不再等数据返回才判定，改为先显示临时状态、后用后端权威状态覆盖。盘后查看“今天”的新股票时，若本地无分时，后端会按需补抓当天 full-day ticks 并聚合展示。
- 风险: 盘后按需补抓仍依赖外部源可用性；若外部源短时失败，页面状态语义仍会正确，但图表可能暂时无数据。
- 链接: `backend/app/core/http_client.py`, `backend/app/routers/market.py`, `src/components/dashboard/RealtimeView.tsx`, `backend/tests/test_market_clock.py`, `backend/tests/test_realtime_dashboard_router.py`, `docs/changes/MOD-20260318-02-market-session-states-and-intraday-defaults.md`

## 2026-03-18 13:00 | Codex
- Task ID: `CHG-20260318-01`
- CAP: `CAP-REALTIME-FLOW`, `CAP-WIN-PIPELINE`
- 结论: 已完成 Windows 实时采集第二阶段稳态化：`ZhangDataLiveCrawler` 收口为单正式任务（`SYSTEM + Boot + 每5分钟 + IgnoreNew`），同步时自动清理旧 crawler 多实例；Windows 进程数已从 `11` 个收敛为 `1` 个，并跨下一个 5 分钟周期复检未再膨胀。生产 `/api/realtime/dashboard?symbol=sz000833` 与云端 `trade_ticks/sentiment_snapshots` 已恢复 `2026-03-18` 当天真实数据。
- 风险: 当前已验证“非交互单实例稳态 + 生产恢复”，但尚未补做“Windows 重启/注销后自动恢复”正式演练；`T-016` 继续保留为 ACTIVE。
- 链接: `backend/scripts/live_crawler_win.py`, `ops/win_register_live_crawler_tasks.ps1`, `start_live_crawler.bat`, `sync_to_windows.sh`, `docs/changes/MOD-20260318-01-windows-realtime-task-stabilization.md`, `docs/07_PENDING_TODO.md`

## 2026-03-18 00:20 | Codex
- Task ID: `CFG-20260318-01`
- CAP: `CAP-REALTIME-FLOW`, `CAP-WIN-PIPELINE`
- 结论: 已完成第一阶段“先存档 → 再做最小治理”基线落地：创建 `snapshot-20260318-pre-governance` / `codex/archive-pre-governance-20260318` / `codex/baseline-governance-20260318`，导出 bundle 与仓库外 DB/.env 快照；同时移除前端 `VITE_WRITE_API_TOKEN` 注入，改为 Vite/Nginx 代理在服务端侧注入写请求头，并补齐版本一致性检查与统一 `check:baseline` 自检入口。
- 风险: 官方前端写请求现依赖 dev proxy / Nginx proxy 正确注入 `X-Write-Token`；若本地 `.env.local` 或生产 frontend 容器未配置 `WRITE_API_TOKEN`，写接口会返回 401/503。另：`.venv` 已从 Git 索引移除，后续环境需按本地重新安装维护，不再依赖仓库内虚拟环境副本。
- 链接: `scripts/check_version_consistency.py`, `scripts/check_baseline.sh`, `deploy/nginx.conf`, `deploy/docker-compose.yml`, `docs/AI_QUICK_START.md`, `docs/changes/CFG-20260318-01-baseline-governance-hardening.md`

## 2026-03-18 01:40 | Codex
- Task ID: `CFG-20260318-01`
- CAP: `CAP-WIN-PIPELINE`
- 结论: 已完成分支治理收口：`codex/baseline-governance-20260318` 已 fast-forward 合入 `main` 并推送 GitHub；本地与远端现仅保留 `main` + `codex/archive-pre-governance-20260318` 两个长期分支。历史分支 `codex/daily-postclose-l2-fusion`、`codex/sandbox-review-mvp`、`release/v4.1.0` 已删除；历史中文命名远端分支先转存为 tag `archive-legacy-v2.8-local-final-20260318` 后删除。
- 风险: 后续日常开发不要再保留长期工作分支；建议所有新需求都从 `main` 临时拉 `codex/<topic>`，完成即删，避免再次堆积历史分支。
- 链接: `docs/changes/CFG-20260318-01-baseline-governance-hardening.md`, `docs/AI_QUICK_START.md`

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

## 2026-03-16 09:02 | 发布 AI
- Task ID: `CHG-20260316-06`
- CAP: `CAP-HISTORY-30M`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: `v4.2.15` 已发布生产；修复历史多维将 `quality_info=None/null` 误判为黄色异常点的问题，后端与前端已双重归一化，生产接口抽样确认不再返回字符串 `"None"`，前端静态产物版本已切到 `4.2.15`。
- 风险: 历史月份 rollout runner 仍在后台执行中，本次前端修复不影响其写库流程；建议你刷新生产历史多维并抽看此前有大量黄标的股票确认视觉收敛。
- 链接: `backend/app/routers/analysis.py`, `src/components/dashboard/HistoryMultiframeFusionView.tsx`, `src/version.ts`

## 2026-03-16 10:05 | 文档 AI
- Task ID: `CHG-20260316-06`
- CAP: `CAP-REALTIME-FLOW`, `CAP-WIN-PIPELINE`
- 结论: 已回填生产实时 K 线缺失事故文档，明确根因是 Windows 计划任务 `ZhangDataLiveCrawler` 未自动拉起；手动恢复后，已将“计划任务稳态化”登记为显式待办 `T-016`。
- 风险: 当前 Windows 实时采集仍存在“登录触发 / 交互方式”脆弱点；若未完成稳态化，后续盘中仍可能再次出现实时 K 线空白。
- 链接: `docs/changes/INV-20260316-06-prod-realtime-kline-scheduler-gap.md`, `docs/04_OPS_AND_DEV.md`, `docs/07_PENDING_TODO.md`

## 2026-03-16 11:10 | 后端 AI
- Task ID: `CHG-20260316-07`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 结论: 已落地“Mac 一条命令盘后 L2 日增量总控”第一版：新增 Windows prepare、云端 artifact merge、Mac 总控与 shell/bat 入口；同时冻结后续范围为“自 `2025-01-02` 起向后增量”，不再回补 `2025-01` 之前更老月份。
- 风险: 当前尚未做真实跨机实跑，需先把新脚本同步到 Windows 后再做一次真实 `--dry-run` / 单日演练；完全无人值守定时执行仍需后续把这套语义迁到 OS 级调度器。
- 链接: `docs/changes/REQ-20260316-07-postclose-l2-one-command-runner.md`, `backend/scripts/run_postclose_l2_daily.py`, `backend/scripts/l2_postclose_prepare_day.py`, `backend/scripts/merge_l2_day_delta.py`, `docs/04_OPS_AND_DEV.md`

## 2026-03-16 23:40 | 后端 AI
- Task ID: `CHG-20260316-07`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 结论: 已完成 `20260316` 的首个真实“一条命令盘后 L2”演练：dry-run 正常识别 pending day，8 worker Windows artifact 产出成功，云端 merge 经修正后已写入生产；最终 `history_daily_l2=7663`、`history_5m_l2=345461`，latest merge run `id=102`，`status=partial_done`，失败样本 `15`。
- 风险: 当前总控链路虽然已打通，但仍依赖 Mac 发起与云端 `sudo` merge；若要完全无人值守，还需继续推进 `T-014` 的 OS 级定时控制器固化。
- 链接: `backend/scripts/run_postclose_l2_daily.py`, `backend/scripts/merge_l2_day_delta.py`, `docs/04_OPS_AND_DEV.md`, `docs/07_PENDING_TODO.md`

## 2026-03-16 23:58 | 前端 AI
- Task ID: `CHG-20260316-08`
- CAP: `CAP-HISTORY-30M`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已完成新版历史多维 UI 瘦身与专业级交互重构第一版：`[旧版 / 新版]` 切换上移到全局头部，历史多维头部改为单行控制区，并新增 `15m` 粒度、步进缩放、主图时间轴标签、表格化 tooltip 与移动端长按 tooltip。
- 风险: 当前仅完成构建级验证，`Shift + 滚轮` / 触控板横向平移与真机移动端长按手感仍需用户侧体验确认；本次未包含发版动作。
- 链接: `docs/archive/changes/ARC-CHG-20260317-monitor-multiframe-ui-slim-pro-interaction.md`, `src/App.tsx`, `src/components/dashboard/HistoryMultiframeFusionView.tsx`

## 2026-03-17 00:16 | 发布 AI
- Task ID: `CHG-20260316-08`
- CAP: `CAP-HISTORY-30M`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已完成 `v4.2.16` 生产发布；新版历史多维 UI / 交互重构与盘后 L2 一条命令链路一并进入 `main`，GitHub tag=`v4.2.16`，发布锚点 commit=`d640146`。
- 风险: 本次按发布 SOP 只执行部署，不代跑生产冒烟；建议你重点手测“顶部版本切换 / 历史多维 15m / 图表头部单行控制区 / v4.2.16 可见性”。
- 链接: `src/version.ts`, `README.md`, `docs/archive/changes/ARC-CHG-20260317-monitor-multiframe-ui-slim-pro-interaction.md`, `docs/changes/REQ-20260316-07-postclose-l2-one-command-runner.md`

## 2026-03-17 00:38 | 发布 AI
- Task ID: `CHG-20260317-09`
- CAP: `CAP-HISTORY-30M`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已完成 `v4.2.17` 生产发布；新版历史多维读数条改为外置顶栏，y 轴修正为“左轴 + 轴右侧内嵌标签”，并把普通滚轮优先级还给页面滚动，发布锚点 commit=`9e13fd3`，tag=`v4.2.17`。
- 风险: 本次仍未代跑生产冒烟；`Shift + 滚轮` / 触控板横向平移手感与浏览器差异仍需用户侧持续观察。
- 链接: `src/components/dashboard/HistoryMultiframeFusionView.tsx`, `src/version.ts`, `README.md`, `docs/archive/changes/ARC-CHG-20260317-monitor-multiframe-info-strip-polish.md`

## 2026-03-17 22:10 | 运维 AI
- Task ID: `CHG-20260317-10`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 结论: 已将盘后 L2 一条命令总控收口为 `PASS / PASS_WITH_WARNINGS / FAIL` 三档结论；其中“仅无有效 bar 空样本”归类为 `PASS_WITH_WARNINGS`，视为生产前端可用。`20260317` 现有报告重算结果为 `PASS_WITH_WARNINGS`。
- 风险: 当前仍未把“最终状态”反写进云端 merge 表本身；数据库 run 记录仍保持 `done / partial_done / failed` 原始技术状态。
- 链接: `backend/scripts/run_postclose_l2_daily.py`, `ops/run_postclose_l2.sh`, `docs/04_OPS_AND_DEV.md`, `docs/archive/changes/ARC-CHG-20260317-postclose-l2-one-command-final-status.md`

## 2026-03-17 22:45 | 发布 AI
- Task ID: `CHG-20260317-11`
- CAP: `CAP-HISTORY-30M`, `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 结论: 准备发布 `v4.2.18`；新版历史多维已补齐“本周期涨跌”、默认约 40 点窗口与 20/40/80/160 步进缩放、横轴真实时间刻度、无 L2 假底柱隐藏、L1 配色增强，并在第四图叠加 L2 超大单/主力活跃度细实线；同时纳入盘后 L2 一条命令最终态三档结论。
- 风险: 本次仍为发布后人工验收模式，未代跑生产冒烟；重点关注白天 preview 场景是否只剩真实 L1 芯柱、以及第四图双实线在移动端的可读性。
- 链接: `src/components/dashboard/HistoryMultiframeFusionView.tsx`, `backend/scripts/run_postclose_l2_daily.py`, `src/version.ts`, `docs/04_OPS_AND_DEV.md`

## 2026-03-17 23:18 | 发布 AI
- Task ID: `CHG-20260317-12`
- CAP: `CAP-HISTORY-30M`, `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 结论: 已将当前线上真实状态重新收口为 `v4.2.19`，用于覆盖“`v4.2.18` tag 后仍继续上线小修”的漂移；同时已把项目版本纪律写入 `04_OPS_AND_DEV.md`，后续要求“每次生产变更必须 bump 版本、一个 tag 只对应一个线上状态、本地 main 必须跟上 origin/main`。
- 风险: 当前 Git 工作流仍以长生命周期 `codex/*` 分支推进，后续若不按新纪律执行，仍可能再次出现 tag / 线上状态漂移。
- 链接: `docs/04_OPS_AND_DEV.md`, `src/version.ts`, `README.md`, `docs/archive/changes/ARC-CHG-20260317-version-discipline-and-v4-2-19-normalization.md`

## 2026-03-19 11:40 | 后端 AI
- Task ID: `CHG-20260319-02`
- CAP: `CAP-REALTIME-FLOW`, `CAP-WIN-PIPELINE`
- 结论: 已修复“当日分时今日已有部分数据但已陈旧时，页面继续复用旧数据而不补拉”的链路缺口：`/api/realtime/dashboard` 与 `/api/realtime/intraday_fusion` 现在会在盘中/午休/盘后对今日陈旧 payload 做节流补拉，避免个别股票因为 Windows 逐笔超时而长期停在 `09:31` 之类旧时间点。
- 风险: 当前 Windows `live_crawler_win.py` 仍可能出现 AkShare 逐笔超时，热修只能保证“页面打开时尝试自救”，不能替代 Windows 采集稳态化本身。
- 链接: `backend/app/routers/market.py`, `backend/tests/test_realtime_dashboard_router.py`

## 2026-03-19 14:55 | 前后端 AI
- Task ID: `CHG-20260319-03`
- CAP: `CAP-REALTIME-FLOW`, `CAP-WIN-PIPELINE`
- 结论: 已继续收口当日分时稳定性与资金博弈 UI：资金博弈调参入口已收回标题栏右侧，盘中无 finalized L2 时不再留空白 L2 面板；同时对“盘后仍陈旧”的 today payload 增补了强制二次补拉与重算，避免盘中失败冷却直接延续到收盘后。
- 风险: 云端盘后自愈虽已增强，但根因仍是 Windows / AkShare 个股逐笔超时；若上游持续不可用，最终仍可能需要云端或 Windows 侧再做抓取源 fallback。
- 链接: `src/components/dashboard/FundsBattleSection.tsx`, `src/components/dashboard/RealtimeView.tsx`, `src/App.tsx`, `src/index.tsx`, `backend/app/routers/market.py`

## 2026-03-20 09:10 | 发布 AI
- Task ID: `CHG-20260320-01`
- CAP: `CAP-REALTIME-FLOW`, `CAP-WIN-PIPELINE`
- 结论: 已完成 `v4.2.27` 发布准备与归档；针对个别股票当日分时停在 `14:45/14:50` 的问题，新增云端盘后主动自愈扫盘，固定在交易日 `15:02 / 15:07 / 15:12 / 15:17` 自动扫描自选股，若 today ticks 最新时间 `< 14:55:00` 则补抓、覆盖写回并刷新 `history_1m + realtime_5m_preview`，不再只依赖“打开页面时才自救”。
- 风险: 当前主动自愈仍调用 AkShare 单源 `fetch_live_ticks`；若上游源持续超时，盘后扫盘仍可能失败，后续需考虑多源 fallback 与更强告警。
- 链接: `backend/app/scheduler.py`, `backend/app/db/crud.py`, `backend/tests/test_scheduler_postclose_self_heal.py`, `docs/archive/changes/ARC-CHG-20260320-postclose-stale-self-heal-release.md`

## 2026-03-21 11:35 | 前后端 AI
- Task ID: `CHG-20260314-06`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-SANDBOX-REVIEW`
- 结论: 已完成复盘页正式并库首轮实现：新增正式元数据表 `stock_universe_meta`、`/api/review/pool`、`/api/review/data`，前端复盘页已切到生产正式库并改为按股票真实 `min_date/max_date` 动态限界；同时新增 `refresh_stock_universe_meta.py` 与 `promote_review_symbol_history.py`，支持正式池元数据刷新与单股票后台补历史。
- 风险: 当前 `stock_universe_meta` 仍需脚本手动刷新，尚未接定时调度；单股票补历史 slow path 仍依赖本地原始历史包可访问。
- 链接: `backend/app/routers/review.py`, `backend/app/db/l2_history_db.py`, `backend/scripts/refresh_stock_universe_meta.py`, `backend/scripts/promote_review_symbol_history.py`, `src/components/sandbox/SandboxReviewPage.tsx`, `docs/changes/REQ-20260314-06-review-page-prod-l2-unification.md`

## 2026-03-21 16:20 | 前端 AI
- Task ID: `MOD-20260321-03`
- CAP: `CAP-SANDBOX-REVIEW`
- 结论: 已继续收口复盘页操作栏/信息卡/锚点图体验：股票信息卡上移到搜索栏下方并与首页共享 `StockQuoteHeroCard`，恢复名称后股票代码且固定展示市值；复盘页卡片最新日期改跟随首页同源 quote；锚点累计图从 4 张收敛为 2 张且仅在锚点开关打开时显示，同时压缩主图高度并把底部 dataZoom 拉近图区。
- 风险: 复盘页信息卡最新日期依赖腾讯 quote 返回，若外部 quote 拉取失败则会回退到正式历史表最后一日；当前改动仍在功能分支 `codex/review-toolbar-refactor`，尚未发布。
- 链接: `src/components/sandbox/SandboxReviewPage.tsx`, `src/components/common/StockQuoteHeroCard.tsx`, `src/App.tsx`, `docs/changes/MOD-20260321-03-review-toolbar-refactor.md`

## 2026-03-21 16:48 | 前端 AI
- Task ID: `MOD-20260321-03`
- CAP: `CAP-SANDBOX-REVIEW`
- 结论: 已继续修正复盘页图表联调细节：锚点开关前后主图高度改为固定，不再出现“开锚点后整体突然拉高”；净流入柱图与锚点累计图已向历史多维配色对齐；tooltip 从固定右上角改为跟随当前点位，并在最右侧自动翻到左边。
- 风险: 当前 tooltip 仍采用 ECharts 单浮层，极窄窗口下若内容过长仍可能触发二次夹紧；如后续继续精修，可再按移动端单独降简内容。
- 链接: `src/components/sandbox/SandboxReviewPage.tsx`, `docs/changes/MOD-20260321-03-review-toolbar-refactor.md`

## 2026-03-21 17:05 | 前端 AI
- Task ID: `MOD-20260321-03`
- CAP: `CAP-SANDBOX-REVIEW`
- 结论: 已把首页与复盘页的顶栏结构进一步对齐：首页整体宽度扩到宽屏版式；复盘页搜索移入顶栏并放到 logo 后方，页面顺序调整为“搜索 → 股票信息卡 → 日期功能区 → 图表”；首页顶栏按钮继续显示 `复盘`，复盘页同位置切换为 `首页`。
- 风险: 当前“首页/复盘页顶栏统一”仍是样式级对齐，尚未抽成共享 header 组件；若后续继续频繁改顶栏，可考虑再抽共用壳层避免双处维护。
- 链接: `src/App.tsx`, `src/components/sandbox/SandboxReviewPage.tsx`, `docs/changes/MOD-20260321-03-review-toolbar-refactor.md`

## 2026-03-21 17:26 | 前端 AI
- Task ID: `MOD-20260321-03`
- CAP: `CAP-SANDBOX-REVIEW`
- 结论: 已继续按“首页/复盘页完全对齐”收口：首页按钮文案改为 `去复盘`，复盘页对应改为 `回到首页`；复盘页顶栏补回首页同款搜索历史下拉与右侧配置按钮区域；复盘页股票信息卡补齐首页同款 meta 行（自选、盯盘态、时钟、核心服务状态）。
- 风险: 复盘页当前保留了首页同款“盯盘”视觉按钮，但该按钮在复盘页仅作为界面状态，不驱动额外轮询策略；若后续需要严格语义一致，应考虑抽共享卡片同时做页面级行为适配。
- 链接: `src/App.tsx`, `src/components/sandbox/SandboxReviewPage.tsx`, `docs/changes/MOD-20260321-03-review-toolbar-refactor.md`

## 2026-03-21 17:48 | 前端 AI
- Task ID: `MOD-20260321-03`
- CAP: `CAP-SANDBOX-REVIEW`
- 结论: 已进一步落到真正共享实现：抽出 `MarketTopHeader` 与 `QuoteMetaRow`，首页/复盘页共用同一顶栏和股票信息 meta 行；同时把首页 `盯盘` 按钮从信息卡移到“当日分时 / 历史多维”小按钮操作栏，复盘页卡片不再带盯盘按钮。
- 风险: 目前仅顶栏与信息卡 meta 行实现了共享，页面主体内容区仍分别维护；若后续还要统一页头以下的操作区，建议继续抽第二层共用 shell。
- 链接: `src/components/common/MarketTopHeader.tsx`, `src/components/common/QuoteMetaRow.tsx`, `src/App.tsx`, `src/components/sandbox/SandboxReviewPage.tsx`, `docs/changes/MOD-20260321-03-review-toolbar-refactor.md`

## 2026-03-22 00:12 | 前端 AI
- Task ID: `MOD-20260321-03`
- CAP: `CAP-SANDBOX-REVIEW`
- 结论: 已按新确认版式把共享股票信息卡改成紧凑左中右结构：左侧保留名称/代码/星标/当前时间/服务状态，中间改成价格两行合并 + 交易两行合并 + 公司信息列，右侧大号价格区保持不动；同时接入 `turnover_rate`，并把“最新日期”限制为仅非交易时段展示。
- 风险: 换手率当前来自 `/api/sentiment` 腾讯快照链路，若该链路短时失败会回落显示 `--`；公司信息首期仍只有总市值，PE/PB/行业等尚未接入。
- 链接: `src/components/common/StockQuoteHeroCard.tsx`, `src/components/common/QuoteMetaRow.tsx`, `src/utils/marketTime.ts`, `src/App.tsx`, `src/components/sandbox/SandboxReviewPage.tsx`, `docs/changes/MOD-20260321-03-review-toolbar-refactor.md`

## 2026-03-22 00:26 | 前端 AI
- Task ID: `MOD-20260321-03`
- CAP: `CAP-SANDBOX-REVIEW`
- 结论: 已补齐首页/复盘页切换时的当前股票透传：两页都会把当前股票写入 URL `?symbol=`，互相跳转时自动带过去，刷新页面也能回到同一只股票。
- 风险: 首页初次用 URL symbol 引导时会优先尝试拉一次 quote 反查名称；若外部行情源瞬时失败，仍会回退到 symbol 占位后再由后续 quote 刷新纠正。
- 链接: `src/App.tsx`, `src/components/sandbox/SandboxReviewPage.tsx`, `docs/changes/MOD-20260321-03-review-toolbar-refactor.md`

## 2026-03-22 00:30 | 发布 AI
- Task ID: `MOD-20260321-03`
- CAP: `CAP-SANDBOX-REVIEW`
- 结论: 本轮“复盘页操作栏/共享壳层/股票透传”改动已随 `v4.2.30` 发版，`main` 发布提交为 `a281275`，生产部署完成；云端健康检查 `GET /api/health` 返回 `ok`。
- 风险: 当前发布只完成本轮已冻结范围；如后续还需继续统一首页与复盘页的非头部操作区，建议另起新卡继续收口，避免把后续视觉微调继续叠加到本卡。
- 链接: `docs/changes/MOD-20260321-03-review-toolbar-refactor.md`, `package.json`, `src/version.ts`, `backend/app/main.py`

## 2026-03-22 00:40 | 前端 AI
- Task ID: `MOD-20260321-03`
- CAP: `CAP-SANDBOX-REVIEW`
- 结论: 已修复首页/复盘页来回切换时搜索历史丢失：首页在 URL `?symbol=` 初始化选股时，改为使用函数式历史更新，避免先于 `localStorage` 回填时用空历史覆盖已有最近记录。
- 风险: 当前最近搜索仍为首页与复盘页共用同一个 `localStorage` key；这是符合预期的统一体验，但若未来要做页面级隔离历史，需要再拆 key 并补迁移逻辑。
- 链接: `src/App.tsx`, `docs/changes/MOD-20260321-03-review-toolbar-refactor.md`

## 2026-03-22 00:39 | 发布 AI
- Task ID: `MOD-20260321-03`
- CAP: `CAP-SANDBOX-REVIEW`
- 结论: 搜索历史覆盖修复已随 `v4.2.31` 发版；发布提交 `c18cd2c`，tag `v4.2.31`，生产部署完成。
- 风险: 本次为前端状态修复，不涉及后端契约；如用户仍反馈历史记录异常，应优先检查浏览器是否处于隐私模式或是否有扩展拦截 `localStorage`。
- 链接: `src/App.tsx`, `package.json`, `src/version.ts`, `backend/app/main.py`, `docs/changes/MOD-20260321-03-review-toolbar-refactor.md`

## 2026-03-22 01:10 | 文档 AI
- Task ID: `CHG-20260322-01`
- CAP: `CAP-RETAIL-SENTIMENT`
- 结论: 已按“文档先行”冻结散户情绪模块重构总方案与四张分期 REQ，并同步 core docs：模块定位正式改为“散户一致性观察”；明确 dashboard 读接口禁止同步 LLM、trend 必须区分 gap/0、首页后续按 freshness -> metric -> price-linked -> coverage 四期推进。
- 风险: 当前仅完成文档冻结，尚未落代码；`latest_crawl_time` 来源、`keywords.topics` 是否首期落地、`focus/hot pool` 规则仍保留为后续实施决策点。
- 链接: `docs/changes/STG-20260322-01-retail-sentiment-rebuild.md`, `docs/changes/REQ-20260322-02-sentiment-positioning-and-freshness-v1.md`, `docs/02_BUSINESS_DOMAIN.md`, `docs/03_DATA_CONTRACTS.md`, `docs/07_PENDING_TODO.md`

## 2026-03-22 02:05 | 前后端 AI
- Task ID: `CHG-20260322-01`
- CAP: `CAP-RETAIL-SENTIMENT`
- 结论: 已完成 Phase 1 首轮实现：dashboard 读接口改为只读缓存摘要、不再同步调 LLM；trend 增加 `has_data/is_gap`；首页模块改名为“散户一致性观察”，顶部切到 `热度 / 一致性 / 风险 / 最新样本`，并移除“页面刷新时间伪装成数据更新时间”的旧表达；scheduler 同步补了盘前/盘后摘要缓存刷新任务。
- 风险: Phase 1 的 `heat_score / risk_tag` 仍属过渡口径，Phase 2 需要继续冻结正式指标定义与关键词区；评论覆盖仍然主要受单源股吧样本质量约束。
- 链接: `backend/app/services/retail_sentiment.py`, `backend/app/routers/sentiment.py`, `backend/app/scheduler.py`, `src/components/sentiment/SentimentDashboard.tsx`, `docs/changes/REQ-20260322-02-sentiment-positioning-and-freshness-v1.md`

## 2026-03-22 03:20 | 前后端 AI
- Task ID: `CHG-20260322-01`
- CAP: `CAP-RETAIL-SENTIMENT`
- 结论: 已完成 Phase 2：新增 `GET /api/sentiment/keywords`，首页模块重排为 `热度/一致性/偏向/风险 + 缓存摘要/关键词主题词/代表帖子 + 趋势图` 三段式结构；代表帖子支持 `最新/最热/分歧` 排序，并新增 `高热中性/噪音` 展示层分类。
- 风险: 关键词/主题聚合仍属规则统计法，存在少量泛词混入；真正的“情绪-价格背离”标签与价格联动图仍待 Phase 3 落地。
- 链接: `backend/app/services/retail_sentiment.py`, `backend/app/routers/sentiment.py`, `src/services/sentimentService.ts`, `src/components/sentiment/SentimentDashboard.tsx`, `src/components/sentiment/CommentList.tsx`, `docs/changes/REQ-20260322-03-sentiment-metric-engine-and-dashboard-v2.md`

## 2026-03-22 04:05 | 前后端 AI
- Task ID: `CHG-20260322-01`
- CAP: `CAP-RETAIL-SENTIMENT`
- 结论: 已完成 Phase 3：`/api/sentiment/trend` 新增 `neutral_vol + price_close + price_change_pct + volume_proxy + has_price_data`；首页趋势图升级为“偏多/偏空/中性柱 + 热度线 + 价格线”，并新增前端联动观察标签。非交易时段默认优先展示 `14D`。
- 风险: `volume_proxy` 仍是成交活跃度代理，不是严格统一量；72H 价格桶当前按自然小时对齐舆情小时桶，后续若要改为交易所标准小时桶需重新冻结口径。
- 链接: `backend/app/services/retail_sentiment.py`, `backend/app/routers/sentiment.py`, `src/components/sentiment/SentimentTrendChart.tsx`, `src/components/sentiment/SentimentDashboard.tsx`, `docs/changes/REQ-20260322-04-sentiment-price-linked-visualization-v3.md`

## 2026-03-23 11:40 | 前后端 AI
- Task ID: `CHG-20260323-01`
- CAP: `CAP-RETAIL-SENTIMENT`
- 结论: 已完成散户一致性观察 V2 首轮落地：新增 `sentiment_events` 正式事件流模型与旧 `sentiment_comments` 懒回填；首页正式主链路切到 `GET /api/sentiment/overview|heat_trend|feed`；首页模块重构为 `单信息卡 + 热度主图（价格 / 事件数 / 相对热度） + AI 预留窄区 + 右侧来源 Tab 原文流`，窗口统一为 `5D / 20D`。
- 风险: 当前正式可见数据仍以 `股吧主帖 + 旧评论兼容回填` 为主；股吧回复正文与雪球适配器尚未实装，因此 `reply`/`xueqiu` 仍主要停留在 schema/API 预留层。
- 链接: `backend/app/db/database.py`, `backend/app/services/retail_sentiment.py`, `backend/app/services/sentiment_crawler.py`, `backend/app/routers/sentiment.py`, `src/services/sentimentService.ts`, `src/components/sentiment/SentimentDashboard.tsx`, `docs/changes/STG-20260323-01-retail-sentiment-v2-heat-event-stream.md`

## 2026-03-23 19:20 | 数据接入 AI
- Task ID: `CHG-20260323-01`
- CAP: `CAP-RETAIL-SENTIMENT`
- 结论: 已继续推进事件流接入层：股吧 crawler 新增线程详情解析，主帖可从详情页提取正文与互动字段；回复链路改为调用东方财富 `gbapi` reply 接口做 best-effort 抓取；雪球新增 cookie-gated 适配器骨架（`statuses/search.json + statuses/comments.json`）。同时已在本地对 `000833 / 603629` 执行 live crawl，V2 模块本地样本已刷新到 `2026-03-23`。
- 风险: 东方财富 reply API 当前大量返回 `系统繁忙[00003]`，因此 reply 正文仍不稳定；雪球在未配置 `XUEQIU_COOKIE` 或被 WAF 挑战时会软失败，当前环境下默认仍可能无数据。
- 链接: `backend/app/services/sentiment_crawler.py`, `backend/app/services/retail_sentiment.py`, `docs/changes/REQ-20260323-02-sentiment-events-and-two-source-contract.md`

## 2026-03-24 18:40 | 文档治理 AI
- Task ID: `CHG-20260324-01`
- CAP: `CAP-RETAIL-SENTIMENT`
- 结论: 已完成散户一致性观察本轮文档治理收口：新增总收口卡 `MOD-20260324-01-retail-sentiment-v2-current-state.md`，把 `2026-03-22 ~ 2026-03-24` 多轮 STG/REQ 的过程文档收敛为“当前真实状态”母卡；同步把 `02/03/07` 回填为实际已落地口径（股吧单源、`5D/20D/60D`、星标股日级 AI 评分、前端可改 `llm_model`、未完成项改写为后置项）。
- 风险: 旧的 `20260322/20260323` 规划卡仍保留作为过程记录，其中关于“多源 / AI仅占位 / 来源Tab”的说法已不再代表当前真实状态；后续查现状时应优先看 `MOD-20260324-01`。
- 链接: `docs/changes/MOD-20260324-01-retail-sentiment-v2-current-state.md`, `docs/02_BUSINESS_DOMAIN.md`, `docs/03_DATA_CONTRACTS.md`, `docs/07_PENDING_TODO.md`

## 2026-03-24 20:20 | 生产补跑 / 归档 AI
- Task ID: `CHG-20260324-01`
- CAP: `CAP-RETAIL-SENTIMENT`
- 结论: 已在生产对 7 只星标股完成散户一致性观察补跑：执行星标抓取补跑 `new_count=444`、当日日评分补跑 `generated=7`，并继续补齐近 20 个交易日 AI 日评分；补跑后 `20D` 可见评分点分别为 `7/11/11/10/9/7/11` 天（贵州茅台/天下秀/有研新材/利通电子/中百集团/贝因美/粤桂股份）。同时已将本轮母卡归档为 `ARC-CHG-20260324-retail-sentiment-v2-release-and-backfill`，作为 `v4.2.32 / 9bbdd3d` 的冻结基线。
- 风险: 历史 AI 评分仍按“样本数足够才生成”的规则执行，个别交易日会因 `insufficient_samples` 留空；这属于真实数据稀疏，不是图表缺失。
- 链接: `docs/archive/changes/ARC-CHG-20260324-retail-sentiment-v2-release-and-backfill.md`, `docs/archive/ARCHIVE_CATALOG.md`, `docs/02_BUSINESS_DOMAIN.md`


## 2026-04-04 21:20 | 选股研究 AI
- Task ID: `CHG-20260404-01`
- CAP: `CAP-SELECTION-RESEARCH`
- 结论: 已完成选股研究一期强解耦实现：新增独立库 `data/selection/selection_research.db`、独立服务层 `selection_research.py`、独立接口 `/api/selection/*`、独立研究页 `/selection-research`，并补齐总册 + 四张需求卡。当前策略固定为 `stealth / breakout / distribution`，回测固定支持 `5/10/20/40` 交易日。
- 风险: 主正式库里的 L2 订单事件新因子是否完整 merge，仍会影响 `2026-03+` 的增强确认质量；当前模块已做弱化兜底，但这属于后续增强项。
- 链接: `docs/selection/selection_research_master.md`, `docs/changes/REQ-20260404-01-selection-data-foundation.md`, `backend/app/services/selection_research.py`, `backend/app/routers/selection.py`, `src/components/selection/SelectionResearchPage.tsx`

## 2026-04-04 21:45 | 选股研究 AI
- Task ID: `CHG-20260404-01`
- CAP: `CAP-SELECTION-RESEARCH`
- 结论: 已补齐首轮真实数据样例：独立选股库当前已有 `603,675` 条 feature、`413,204` 条 signal，最新信号日为 `2026-02-27`；已跑出 breakout 回测 `run_id=1`（区间 `2026-02-03 ~ 2026-02-27`），`5D` 胜率 `58.43%`、平均收益 `2.02%`，`10D` 胜率 `52.50%`、平均收益 `2.46%`。同时已修正 refresh 过程中的 `FutureWarning` 噪音，方便后续继续补跑。
- 风险: 当前 `stock_universe_meta` 为空，页面暂时只能稳定显示 `symbol`；另外本地主库 `2026-03+` 全市场连续覆盖不完整，因此现阶段最适合先用 `2026-02-27` 前的数据做研究验证。
- 链接: `docs/changes/MOD-20260404-01-selection-research-current-state.md`, `docs/selection/selection_research_master.md`, `docs/changes/REQ-20260404-02-selection-features-and-signals.md`, `docs/changes/REQ-20260404-03-selection-backtest-engine.md`, `docs/changes/REQ-20260404-04-selection-api-and-research-page.md`

## 2026-04-04 22:35 | 选股研究 AI
- Task ID: `CHG-20260404-01`
- CAP: `CAP-SELECTION-RESEARCH`
- 结论: 已完成 V2 重构：工作台从“研究数表页”收敛为“左侧 Top10 breakout 候选池 + 右侧复盘决策视图”。`distribution` 不再做全市场榜单，而是变成当前票风险判断；右侧详情新增“当前综合判断 / 为什么选中它 / 出货风险 / 事件时间线”；回测新增窗口最高机会口径，开始同时输出固定持有与窗口机会结果。
- 风险: 股票正式名称映射仍优先依赖 `stock_universe_meta`，当前库为空时页面通过前端 fallback 尽量补名称；动态出货退出回测仍未实现，现阶段只完成双口径静态统计。
- 链接: `src/components/selection/SelectionResearchPage.tsx`, `src/components/selection/SelectionDecisionPanel.tsx`, `backend/app/services/selection_research.py`, `backend/app/db/selection_db.py`, `docs/selection/selection_research_master.md`

## 2026-04-10 23:35 | 数据审计 / 选股研究 AI
- Task ID: `CHG-20260410-01`
- CAP: `CAP-SELECTION-RESEARCH`, `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 结论: 已完成利通电子 `sh603629` 原始包审计，确认 `2025-01 ~ 2026-02` 属于成交级源、`2026-03+` 原始包真实包含挂单事件；当前事件层大量缺失的关键原因不是 raw 无数据，而是旧 `l2_daily_backfill.py` 未兼容 Wind `A/D` 挂单事件码，且 Windows 正式跑数机 schema 仍偏旧。已在本地修复解析脚本并补单测，同时把利通关键日 `2026-03-09 / 03-11 / 03-16 ~ 03-18` 回补到本地，事件层字段现已可读。
- 风险: 当前只完成利通关键日单票修复，Windows 正式跑数机与全市场历史库仍未整体升级；若不继续同步 Windows 最新脚本与 schema，后续新增日仍会继续丢事件层。
- 链接: `backend/scripts/l2_daily_backfill.py`, `backend/tests/test_l2_daily_backfill.py`, `docs/changes/INV-20260410-01-litong-data-audit-and-parser-gap.md`, `docs/changes/REQ-20260404-05-selection-data-alignment-and-backfill.md`, `docs/07_PENDING_TODO.md`

## 2026-04-10 23:55 | 数据审计 / Windows 链路 AI
- Task ID: `CHG-20260410-02`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`
- 结论: 已完成 Windows 正式 L2 链路范围审计，确认当前跑数机代码并非只差一个补丁，而是整体停留在“基础 5m+daily + quality_info”阶段，尚未进入事件因子阶段；Windows 正式库现有 `2026-03-02 ~ 2026-03-13` 的 `76,749` 条 daily / `3,461,334` 条 5m 结果因此整体缺 `total_volume + add/cancel + l2_cvd_delta + l2_oib_delta`。同时已确认原始挂单事件码存在多套体系：`sz000833=0/1/U`，`sh603629=A/D/S`，后续修复必须做多映射兼容，不能只修单一编码。
- 风险: 若直接全量重跑而不先做编码分布审计与单日演练，容易再次踩大规模跑数坑；但若不升级 Windows 正式链路，后续选股研究与复盘都会继续受限于事件层缺失。
- 链接: `docs/changes/INV-20260410-02-windows-l2-version-drift-scope.md`, `docs/changes/INV-20260410-01-litong-data-audit-and-parser-gap.md`, `docs/07_PENDING_TODO.md`, `docs/04_OPS_AND_DEV.md`

## 2026-04-11 00:20 | 数据治理 / 文档与脚本 AI
- Task ID: `CHG-20260410-03`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`
- 结论: 已新增本轮数据治理的完整母文档，系统梳理 `2025-01~2026-02` 成交级历史、`2026-03+` 成交+挂单历史、当前问题、修复路线、正式库目标结构、Windows staging/8-worker 清理策略，以及 `2025` 原始数据“榨干后再删”的判断边界；同时新增事件码审计脚本 `backend/scripts/audit_l2_order_event_codes.py`，已用本地样本验证 `sh603629=alpha_ads`、`sz000833=numeric_01u`。
- 风险: 审计脚本目前已适合做小样本/单日抽查，但全市场大样本统计仍需配合 Windows staging 或 prepare 流程使用；`2025` raw 删除仍不建议立即执行，需先完成正式 `5m+daily` 与必要研究派生沉淀。
- 链接: `docs/changes/STG-20260410-03-l2-data-remediation-full-guide.md`, `backend/scripts/audit_l2_order_event_codes.py`, `docs/07_PENDING_TODO.md`

## 2026-04-11 00:45 | 数据审计 / 利通补数 AI
- Task ID: `CHG-20260410-01`
- CAP: `CAP-SELECTION-RESEARCH`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已继续补利通 `sh603629` 的后续关键日到本地：新增回补 `2026-03-19` 与 `2026-04-01`，5m 事件层均已成功落库；其中 `2026-03-19` 的 `Σl2_add_buy≈48.78亿 / Σcancel_buy≈33.82亿 / Σcvd≈-5.37亿 / Σoib≈+7.08亿`，`2026-04-01` 的 `Σl2_add_buy≈24.87亿 / Σcancel_buy≈10.65亿 / Σcvd≈+1.44亿 / Σoib≈-1.47亿`。同时补充样本确认 `sh600519` 也使用 `A/D/S`，进一步支持“事件码至少分两套体系”的判断。
- 风险: 当前只是单票/少量样本验证，尚未把 `2026-03+` 全市场正式库整体升级；若不尽快推进 Windows 单日演练，最近窗口的正式全市场研究仍会受限。
- 链接: `docs/changes/INV-20260410-01-litong-data-audit-and-parser-gap.md`, `docs/changes/INV-20260410-02-windows-l2-version-drift-scope.md`, `backend/scripts/audit_l2_order_event_codes.py`

## 2026-04-11 01:35 | 数据治理 / 利通全窗口补齐 AI
- Task ID: `CHG-20260410-01`
- CAP: `CAP-SELECTION-RESEARCH`, `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 结论: 已继续通过 Tailscale + SSH + 单票 raw 抽取，把利通 `sh603629` 此前仍是旧版存量的 `2026-03-02 / 03 / 04 / 05 / 06 / 10 / 12 / 13` 共 `8` 个交易日补回本地；至此，本地 `2026-03-02 ~ 2026-04-10` 共 `29` 个交易日的 `l2_add_* / l2_cancel_* / l2_cvd_delta / l2_oib_delta` 已全部可读，不再存在整天全空的旧版存量。新补样本中，`2026-03-02` 的 `Σl2_add_buy≈34.52亿 / Σcancel_buy≈20.18亿 / Σcvd≈-0.09亿 / Σoib≈+0.80亿`，`2026-03-03` 的 `Σl2_add_buy≈21.43亿 / Σcancel_buy≈8.01亿 / Σcvd≈-2.01亿 / Σoib≈+2.27亿`。
- 风险: 当前改善仍限于利通本地单票窗口；Windows 正式库与全市场 `2026-03+` 事件层缺口仍在，下一步要做的是 Windows 单日演练 + 利通分阶段深复盘，而不是误以为全局已修完。
- 链接: `docs/changes/INV-20260410-01-litong-data-audit-and-parser-gap.md`, `docs/changes/STG-20260410-03-l2-data-remediation-full-guide.md`, `docs/changes/REQ-20260404-05-selection-data-alignment-and-backfill.md`, `docs/07_PENDING_TODO.md`

## 2026-04-11 15:10 | 选股工作台 / 利通复盘 AI
- Task ID: `CHG-20260411-01`
- CAP: `CAP-SELECTION-RESEARCH`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已定位右侧“画像卡死/空白”的一个关键根因：当请求画像日期超过当前 `selection_feature_daily` 最新日时，旧逻辑会强行重算到越界日期，导致本地接口长时间卡住。现已改为自动回落到最近可用画像日，并在前端加明确提示；同时已新增《利通四阶段深复盘骨架》，把行情拆成“启动前吸筹 / 主升浪前半 / 主升浪后半 / 高位稳住”四段。第一版结论是：利通后半段更像“高位强换手 + 深承接”，关键不只是主动买入，而是 `超大单净额 + 正向 oib + 没有失衡的撤单结构` 一起支撑它高位没立刻崩。
- 风险: 这次修的是“画像日期越界卡顿”，不是把全市场历史都补齐；此外利通高位阶段的结论虽已具备数据骨架，但仍需补图形证据卡和失败样本对照，才能沉淀成可复用选股规则。
- 链接: `backend/app/services/selection_research.py`, `backend/app/db/selection_db.py`, `src/components/selection/SelectionDecisionPanel.tsx`, `docs/changes/INV-20260411-01-litong-phase-review-skeleton.md`, `docs/changes/REQ-20260404-05-selection-data-alignment-and-backfill.md`

## 2026-04-11 15:25 | 文档治理 / 数据与利通双线 AI
- Task ID: `CHG-20260411-02`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`, `CAP-WIN-PIPELINE`
- 结论: 已按后续分会话推进的需要，新增两份独立母文档：一份是《市场数据处理总方案》，专门冻结老数据榨干、新数据事件层、正式库结构、Windows 处理方式与 2025 raw 删除前条件；另一份是《利通电子复盘专项当前状态》，专门收口“已经做了什么、发现了哪些问题、下一步准备做什么”。后续可以分别围绕“数据治理”与“利通复盘”两条线继续推进。
- 风险: 这两份文档解决的是“真实状态与执行边界”，不是已经完成对应工程；尤其 2025 raw 仍未达到可删线，利通复盘也还没完成图形证据卡和失败样本对照。
- 链接: `docs/changes/STG-20260411-02-market-data-processing-master.md`, `docs/changes/MOD-20260411-03-litong-review-current-state.md`

## 2026-04-11 15:45 | 数据治理 / 利通样板票 AI
- Task ID: `CHG-20260411-04`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 结论: 数据治理线已把利通 `sh603629` 正式沉淀成样板票：新增《利通电子数据治理验收卡》，确认本地 `2026-03-02 ~ 2026-04-10` 共 `29` 个交易日事件层窗口已打通；同时新增《单票补数 SOP》，冻结“Windows raw -> 单票抽取 -> 本地回填 -> SQL 验证”的标准路径，后续别的票可以复用这条样板流程。
- 风险: 这次收口的是“单票样板”和“局部治理路径”，不代表 Windows 正式全市场链路已经修完；下一步仍要做页面验收和 Windows 单日正式演练。
- 链接: `docs/changes/INV-20260411-04-litong-data-governance-acceptance.md`, `docs/changes/STG-20260411-05-single-symbol-backfill-sop.md`, `docs/07_PENDING_TODO.md`

## 2026-04-11 16:05 | 数据治理 / 原子特征设计 AI
- Task ID: `CHG-20260411-06`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`
- 结论: 已新增《资金流向研究的一次性数据沉淀清单》，把这轮数据治理的目标从“先想死一套策略”收敛为“先把原子事实层做厚”。文档明确区分了老数据（成交级原子特征）与新数据（挂单事件原子特征）应一次性沉淀哪些字段，并冻结原则：未来多数新研究应只重算 snapshot / signal / backtest，而不反复重跑 raw。
- 风险: 这份文档现在定义的是“目标字段层”，还不是字段差异表；下一步必须继续做当前表结构 vs 目标字段的差异梳理，否则仍容易停留在原则层。
- 链接: `docs/changes/STG-20260411-06-fund-flow-atomic-data-catalog.md`, `docs/07_PENDING_TODO.md`

## 2026-04-11 16:20 | 数据治理 / 原子事实层设计 AI
- Task ID: `CHG-20260411-07`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`
- 结论: 已新增《原子事实层表设计与字段对应总表》，把原子事实层进一步收口成可执行的表设计：`atomic_trade_5m / atomic_trade_daily / atomic_order_5m / atomic_order_daily / atomic_data_manifest`，并逐字段标明“字段名、字段含义、当前来源、老数据是否支持、新数据是否支持、处理方式”。这张表现在已经可以直接作为后续字段差异执行表的上游输入。
- 风险: 当前这张文档解决的是“设计和对应关系”，还没有把字段分成“已有 / 可由现表直接算 / 必须补清洗”的最终执行表；下一步仍需要继续做差异执行表。
- 链接: `docs/changes/STG-20260411-07-atomic-fact-layer-schema-map.md`, `docs/changes/STG-20260411-06-fund-flow-atomic-data-catalog.md`, `docs/07_PENDING_TODO.md`

## 2026-04-11 16:40 | 数据治理 / 原子事实差异执行 AI
- Task ID: `CHG-20260411-08`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`, `CAP-WIN-PIPELINE`
- 结论: 已新增《原子事实层字段差异执行表》，把目标原子层字段正式拆成“已有 / 可算 / 必补”三类，并按 `atomic_trade_5m / atomic_trade_daily / atomic_order_5m / atomic_order_daily / atomic_data_manifest` 五个对象逐字段标明来源、说明、支持范围与优先级。当前已经可以明确首批 P0 顺序应为：先做成交原子层，再做 `2026-03+` 的挂单原子层，最后补 manifest 验收清单。
- 风险: 当前完成的是“施工清单”而不是落库实现；如果下一步不尽快把 P0 字段转成真实表与脚本，文档仍会停留在设计层。另：老数据区间仍不支持真实挂单事件层，这个边界不能被后续实现误突破。
- 链接: `docs/changes/STG-20260411-08-atomic-fact-gap-execution-table.md`, `docs/changes/STG-20260411-07-atomic-fact-layer-schema-map.md`, `docs/07_PENDING_TODO.md`

## 2026-04-11 16:55 | 数据治理 / 原子事实 P0 落库 AI
- Task ID: `CHG-20260411-09`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`, `CAP-WIN-PIPELINE`
- 结论: 已新增《原子事实层 P0 落库方案与跑批顺序》，把下一步真正要落的最小可用范围冻结为 `atomic_trade_5m / atomic_trade_daily / atomic_order_5m / atomic_order_daily / atomic_data_manifest` 五张表，并同步新增可执行 DDL 文件 `backend/scripts/sql/atomic_fact_p0_schema.sql`。该 SQL 已做一次 SQLite 建表冒烟，表结构可成功创建。
- 风险: 当前仍是“DDL + 跑批拆分方案”阶段，真正的 `init/build/backfill` Python 脚本骨架还没补；另外 `2025-01 ~ 2026-02` 的 `trade_count/total_volume` 缺口仍需要 raw 回填，`2026-03+` 的 `add/cancel count/volume` 也仍需要正式清洗脚本支撑。
- 链接: `docs/changes/STG-20260411-09-atomic-fact-p0-ddl-and-runbook.md`, `backend/scripts/sql/atomic_fact_p0_schema.sql`, `docs/07_PENDING_TODO.md`

## 2026-04-11 17:10 | 数据治理 / 原子事实脚本骨架 AI
- Task ID: `CHG-20260411-09`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`
- 结论: 在 P0 DDL 之外，已继续补上两个可执行脚本：`init_atomic_fact_db.py` 用于初始化 `market_atomic.db`，`build_atomic_trade_from_history.py` 用于把现有 `history_5m_l2 / history_daily_l2` 映射进 `atomic_trade_5m / atomic_trade_daily`。已做一次小范围冒烟：以 `sh603629`、`2026-03-02 ~ 2026-03-05` 为样本，成功写入 `195` 条 `atomic_trade_5m` 与 `4` 条 `atomic_trade_daily`。
- 风险: 当前脚本只覆盖“现表可直映/可算”的 trade 层，尚未补 raw 回填脚本；因此 `trade_count` 仍为空，`2026-03+` 的 `add/cancel count/volume` 也还未进入原子库。
- 链接: `backend/scripts/init_atomic_fact_db.py`, `backend/scripts/build_atomic_trade_from_history.py`, `backend/scripts/sql/atomic_fact_p0_schema.sql`, `docs/changes/STG-20260411-09-atomic-fact-p0-ddl-and-runbook.md`

## 2026-04-11 17:30 | 数据治理 / 评审意见吸收 AI
- Task ID: `CHG-20260411-09`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`
- 结论: 已把新一轮评审意见回填到数据治理文档：明确 raw price/复权因子分层、5m 前闭后开约定、集合竞价必须与连续竞价隔离、涨跌停状态作为 P1 增强、以及截面读取索引优化；同时已把时间维度的二级索引直接补进 `atomic_fact_p0_schema.sql`。其中“集合竞价如何具体落库”已被明确记录为**待下一轮专题讨论**，当前只冻结“必须隔离”，不冻结最终字段形态。
- 风险: 集合竞价设计仍未完全拍板，因此当前任何新脚本都不应自行把 `09:25` 并入 `09:30` 连续竞价 bar；此外复权因子与涨跌停状态目前仍停留在文档层，尚未进入实际表结构与脚本实现。
- 链接: `docs/03_DATA_CONTRACTS.md`, `docs/changes/STG-20260411-07-atomic-fact-layer-schema-map.md`, `docs/changes/STG-20260411-08-atomic-fact-gap-execution-table.md`, `docs/changes/STG-20260411-09-atomic-fact-p0-ddl-and-runbook.md`, `backend/scripts/sql/atomic_fact_p0_schema.sql`

## 2026-04-11 17:45 | 数据治理 / 集合竞价审计 AI
- Task ID: `CHG-20260411-10`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`, `CAP-WIN-PIPELINE`
- 结论: 已新增《集合竞价原始数据审计方案》与脚本 `audit_l2_auction_window.py`，用于在 raw 日包层面确认 `trade/order/quote` 三类文件在 `09:15~09:25` 的真实覆盖、是否存在 `09:25:00`、以及样本属于 `trade+order+quote / quote_only / no_pre_0930_data` 哪种形态。脚本已用本地伪造日包做过一次冒烟，输出结构正常。
- 风险: 当前拿到的是“审计工具”和“审计方案”，不是最终集合竞价 schema；在 Windows 样本实际跑出来之前，仍不能拍板 `09:25` 是否单独成 bar、`session_phase` 如何设计，也不能让新脚本默认把竞价并入连续竞价桶。
- 链接: `docs/changes/STG-20260411-10-auction-window-audit-plan.md`, `backend/scripts/audit_l2_auction_window.py`, `docs/07_PENDING_TODO.md`

## 2026-04-11 18:05 | 数据治理 / 集合竞价样本证据 AI
- Task ID: `CHG-20260411-10`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`, `CAP-WIN-PIPELINE`
- 结论: 已把新脚本同步到 Windows，并对真实 raw 样本完成第一轮集合竞价审计：`sh603629@20260302/20260311/20260408/20260410` 与 `sz000833@20260311`。结论已足够明确：raw 里确实存在竞价数据；`order/quote` 对 `09:15~09:24:59` 的覆盖比 `trade` 更稳定；`09:25` 是明显边界点；集合竞价至少包含“过程窗口 + 最终边界点”两层结构，不能简单并入 `09:30` 连续竞价 bar。
- 风险: 目前仍是第一轮样本，不代表已覆盖所有股票/月份；同时 `trade` 层在不同股票上的竞价表现并不完全一致（如 `sh603629` 多数只见 `09:25`，`sz000833` 则在 `09:15~09:19` 也有记录），因此仍不宜马上拍板最终 schema。
- 链接: `docs/changes/STG-20260411-10-auction-window-audit-plan.md`, `docs/changes/INV-20260411-11-auction-window-sample-findings.md`, `backend/scripts/audit_l2_auction_window.py`, `docs/07_PENDING_TODO.md`

## 2026-04-11 18:20 | 数据治理 / 集合竞价落库草案 AI
- Task ID: `CHG-20260411-12`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`
- 结论: 基于第一轮 Windows 真实样本，已新增《集合竞价落库方案草案 V1》。当前推荐方向已经明确：不要把集合竞价硬塞进 `atomic_trade_5m / atomic_order_5m`，而是先独立成 `atomic_open_auction_trade_daily / atomic_open_auction_order_daily` 两张日级竞价摘要表，与连续竞价 5m 原子层并行。这样既保留竞价独立语义，也不污染主 5m 表。
- 风险: 当前仍然是 V1 草案，不是已冻结正式 schema；尤其 `09:25` 是否要再单独建 event 子对象、`09:20~09:25` 是否要单独强调不可撤单语义、收盘竞价是否复用同一设计，这些还没最后拍板。
- 链接: `docs/changes/STG-20260411-12-open-auction-storage-v1.md`, `docs/changes/INV-20260411-11-auction-window-sample-findings.md`, `docs/07_PENDING_TODO.md`

## 2026-04-11 18:35 | 数据治理 / 集合竞价 L1L2 草案 AI
- Task ID: `CHG-20260411-13`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`
- 结论: 已按“先只做数据层、不碰决策层”的要求，新增《集合竞价 L1/L2 摘要表与 DDL 草案》。当前建议集合竞价先独立成三表：`atomic_open_auction_l1_daily`、`atomic_open_auction_l2_daily`、`atomic_open_auction_manifest`；其中 L1 表记录白天真实可见竞价结果，L2 表记录盘后增强结果，manifest 负责覆盖与质量对齐。同时已新增对应 SQL 草案 `open_auction_summary_schema_draft.sql`。
- 风险: 当前仍是草案，不代表正式 schema 已冻结；字段还没有接入正式跑批，也还没经过更大样本的跨股票/跨月份校正。
- 链接: `docs/changes/STG-20260411-13-open-auction-l1-l2-ddl-draft.md`, `backend/scripts/sql/open_auction_summary_schema_draft.sql`, `docs/07_PENDING_TODO.md`

## 2026-04-11 18:55 | 数据治理 / 集合竞价构建脚本 AI
- Task ID: `CHG-20260411-13`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`, `CAP-WIN-PIPELINE`
- 结论: 在竞价 L1/L2 表草案之外，已继续进入真正治理阶段：新增 `build_open_auction_summaries.py`，用于从 raw 日包直接构建 `atomic_open_auction_l1_daily / atomic_open_auction_l2_daily / atomic_open_auction_manifest` 三张竞价摘要表。脚本已本地伪样本冒烟通过，并已同步到 Windows，在真实样本 `sh603629 @ 20260311` 上成功写入 `D:\market-live-terminal\data\atomic_facts\auction_test.db`。
- 风险: 当前写入的仍是 draft schema，对字段定义和窗口切法还需更大样本继续校正；同时它还没正式并入统一 `market_atomic.db` 主跑批，只能算竞价子模块的首轮试跑。
- 链接: `docs/changes/MOD-20260411-14-market-data-governance-current-state.md`, `docs/changes/STG-20260411-13-open-auction-l1-l2-ddl-draft.md`, `backend/scripts/build_open_auction_summaries.py`, `backend/scripts/sql/open_auction_summary_schema_draft.sql`

## 2026-04-11 19:10 | 数据治理 / 新库承接原则冻结 AI
- Task ID: `CHG-20260411-14`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`
- 结论: 已把本轮数据治理迁移原则正式收口到母卡：**旧库只读，不做原地高风险改造；新库独立承接治理结果；待新链路校验通过后，再评估是否把功能平移过去。** 这意味着接下来的 `atomic_trade / atomic_order / auction / manifest` 主线，都应以独立治理库为落点，而不是在旧主库上来回修改。
- 风险: 会暂时形成“旧库继续供现网、新库承接治理”的双轨状态，因此后续必须补 manifest、覆盖校验和功能切换验收，否则容易长期双轨失管。
- 链接: `docs/changes/MOD-20260411-14-market-data-governance-current-state.md`, `docs/07_PENDING_TODO.md`

## 2026-04-11 19:25 | 数据治理 / atomic order raw 回填脚本 AI
- Task ID: `CHG-20260411-14`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`
- 结论: 已新增 `backend/scripts/backfill_atomic_order_from_raw.py`，把连续竞价挂单原子层也推进到真正可执行阶段：脚本可直接读取 raw 日包中的 `逐笔委托.csv + 逐笔成交.csv`，构建 `atomic_order_5m / atomic_order_daily`，并回填 `add/cancel amount + count + volume + cvd/oib`。同时已新增单测 `backend/tests/test_atomic_order_backfill.py`，样本验证通过；随后又已在 Windows 独立测试库 `D:\market-live-terminal\data\atomic_facts\order_test.db` 上对真实样本 `sh603629 @ 2026-03-11` 跑通，结果为 `48` 条 `atomic_order_5m` + `1` 条 `atomic_order_daily`，且不再是空壳数据。
- 风险: 当前已完成单样本真机验证，但还没扩到多股票 / 多日期批跑；另外 `buy_support_ratio / sell_pressure_ratio` 依赖 `atomic_trade_daily.total_amount`，若 trade 原子层未先建好，会退化为 `NULL`。
- 链接: `backend/scripts/backfill_atomic_order_from_raw.py`, `backend/tests/test_atomic_order_backfill.py`, `docs/changes/MOD-20260411-14-market-data-governance-current-state.md`

## 2026-04-11 19:45 | 数据治理 / 利通验证窗口并行跑数 AI
- Task ID: `CHG-20260411-14`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`
- 结论: 已新增 `backend/scripts/run_symbol_atomic_validation.py`，并在 Windows 上以 `6` 个 worker 对利通验证窗口执行首轮并行跑数：老数据 `2026-02-01 ~ 2026-02-28`、新数据 `2026-03-01 ~ 2026-04-10`，临时解压盘改为 `G:\tmp_litong_validation`。实测证明：老 zip 可只定向抽 `603629.csv`，新 7z 可只定向抽 `YYYYMMDD\\603629.SH\\*`，不必整包全量展开。结果上，新数据窗口的 `atomic_order_daily` 和 `atomic_open_auction_*` 已成功覆盖 `29` 个交易日；但 `atomic_trade_daily` 只覆盖到 `2026-03-02 ~ 2026-03-13` 共 `10` 天，根因已确认是 Windows 主库 `history_daily_l2 / history_5m_l2` 自身只存在这 10 天底表，不是并行回补失败。
- 风险: 当前已经证明“单票定向解压 + 新数据 order/auction 子层”是可行的，但 trade 主原子层仍缺少 `raw-direct build` 能力；如果不补这一层，老数据 2 月和新数据 3 月后半 / 4 月的 trade 行仍无法完整落到新治理库。
- 链接: `backend/scripts/run_symbol_atomic_validation.py`, `docs/changes/MOD-20260411-14-market-data-governance-current-state.md`

## 2026-04-11 20:10 | 数据治理 / 利通验证窗口第二轮全量跑通 AI
- Task ID: `CHG-20260411-14`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`
- 结论: 已修复 `run_symbol_atomic_validation.py` 对旧版 `l2_daily_backfill.compute_5m_bars` 的依赖，把新数据 trade 5m 聚合逻辑直接内置到脚本中，并重新同步到 Windows。随后按同一命令、`6` 个 worker 对利通验证窗口重跑，结果 `44/44` 全部成功、`0` 失败。验证库 `D:\\market-live-terminal\\data\\atomic_facts\\litong_validation.db` 当前覆盖为：`atomic_trade_daily=44`、`atomic_trade_5m=2148`、`atomic_order_daily=29`、`atomic_order_5m=1416`、`atomic_open_auction_l1_daily=29`、`atomic_open_auction_l2_daily=29`、`atomic_open_auction_manifest=29`。这说明老数据 trade raw-direct build、新数据 trade/order/auction raw-direct build 都已真实跑通。
- 风险: 利通样板票已跑通，但这还不是全量治理完成；下一阶段风险已收敛为“批量回补策略怎么设计更稳、更省盘、更容易续跑”，而不是“表设计能不能落”。
- 链接: `backend/scripts/run_symbol_atomic_validation.py`, `docs/changes/MOD-20260411-14-market-data-governance-current-state.md`, `docs/07_PENDING_TODO.md`

## 2026-04-11 20:20 | 数据治理 / 单票获取过程收口 AI
- Task ID: `CHG-20260411-14`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 结论: 已把“利通单票从 Windows raw 定向解压 -> 新库原子层落库 -> SQL 验收”的完整闭环补回 `STG-20260411-05-single-symbol-backfill-sop.md`，并明确记录了这次样板票的真实覆盖范围与产物行数，作为后续多股票小样本验证和批量回补规划的基线。
- 风险: 单票 SOP 已经够做样板验证，但不能直接替代后续批量治理方案；后续仍要决定按股票批还是按日期批更合适。
- 链接: `docs/changes/STG-20260411-05-single-symbol-backfill-sop.md`, `docs/changes/MOD-20260411-14-market-data-governance-current-state.md`

## 2026-04-11 20:35 | 利通 / 原子层结构化复盘首版 AI
- Task ID: `CHG-20260411-14`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`
- 结论: 已基于 `litong_validation.db` 落下的 `atomic_trade_daily / atomic_order_daily / atomic_open_auction_l2_daily` 做出首版结构化复盘，并沉淀到 `INV-20260411-15-litong-atomic-structured-review.md`。当前最重要的发现是：利通更像“整理期承接未断 -> 3/11 与 3/19 成交+挂单共振确认 -> 4/7/4/8 高位二次承接 -> 4/9/4/10 分歧抬头”，而不是简单一波拉高。同时已记录 `2026-02-23` 与 `2026-02-11` 结果重复这一老数据置信度问题。
- 风险: 这还是验证窗口版，不是最终深复盘完结版；2 月旧数据段仍要谨慎使用，后续更高置信度的规则提炼应优先依赖 `2026-03+`。
- 链接: `docs/changes/INV-20260411-15-litong-atomic-structured-review.md`, `docs/changes/STG-20260411-05-single-symbol-backfill-sop.md`

## 2026-04-11 20:50 | 数据治理 / 利通 legacy 重复包定位 AI
- Task ID: `CHG-20260411-14`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 结论: 已进一步定位利通 `2026-02-11 / 2026-02-23` 重复问题。当前证据显示：`2026-02-11.zip` 与 `2026-02-23.zip` 整包哈希不同，但其中抽样的 `603629.csv` 与 `600000.csv` 哈希完全相同，说明问题更像 legacy raw 源包异常，而不是当前原子层脚本算错。已对利通验证库这两天打上 `legacy_raw_duplicate_suspect` 质量标记，并把该问题回填到总方案与利通复盘文档。
- 风险: 目前只是样板票级定位，不代表 legacy 全量范围已审计完成；后续 `2025-01 ~ 2026-02` 若要全量治理，必须补 `legacy raw duplicate audit`。
- 链接: `docs/changes/INV-20260411-15-litong-atomic-structured-review.md`, `docs/changes/STG-20260411-02-market-data-processing-master.md`

## 2026-04-11 21:05 | 利通 / 原子层是否足够支撑未来复盘 AI
- Task ID: `CHG-20260411-14`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`
- 结论: 已继续深挖利通关键日期 `2026-03-11 / 03-19 / 03-20 / 04-07 / 04-08 / 04-09 / 04-10` 的 5m 成交层与挂单层细节，并把“原子层是否足够支撑未来任意股票复盘”这一视角回填到利通复盘文档。当前结论是：这套原子层已经足够支撑复盘主骨架（启动确认、盘中成交/挂单共振、高位承接、风险日识别），但要把“为什么走成这样”解释完整，仍必须补事件层（新闻/财报/公告/题材）。
- 风险: 若没有事件层，复盘只能做到“结构解释”，还做不到“驱动解释”；另外 legacy 老数据段仍受源包质量问题影响。
- 链接: `docs/changes/INV-20260411-15-litong-atomic-structured-review.md`

## 2026-04-11 21:20 | 数据治理 / 原子层设计够不够 AI
- Task ID: `CHG-20260411-14`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`
- 结论: 已基于利通样板票回看当前原子层设计的充分性，并把结论回填到母卡。当前判断是：`atomic_trade_* + atomic_order_* + auction_*` 这套主骨架已经够支撑未来股票复盘主流程，但若要把“偷偷吃货 / 提前埋伏 / 驱动解释”做稳，还必须补一批 P1 增强字段（母单数量、集中度、最大母单、OIB 集中度等）以及独立事件层。
- 风险: 如果现在就直接全量回补而不留这些 P1 扩展位，后面仍可能为了更细的吸筹识别再回 raw。
- 链接: `docs/changes/MOD-20260411-14-market-data-governance-current-state.md`, `docs/changes/INV-20260411-15-litong-atomic-structured-review.md`

## 2026-04-11 22:45 | 数据治理 / 母卡收口与 P1 设计冻结 AI
- Task ID: `CHG-20260411-14`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`
- 结论: 已按当前真实主线把数据治理母卡与总方案继续收口，并新增 `STG-20260411-16-atomic-p1-enhancement-design.md` 作为 P1 增强单独设计卡。当前正式冻结为：P1-A 立即进入利通重跑（母单数量、集中度、最大母单、单笔强度、OIB 连续性/集中度），P1-B 先记录设计不阻塞主线（涨跌停状态、复权因子、事件层、竞价 phase 细分）。
- 风险: 文档已收口，但 P1-B 里关于竞价 phase 细拆和涨跌停口径仍需后续再讨论，不宜现在直接写死到批量回补脚本。
- 链接: `docs/changes/MOD-20260411-14-market-data-governance-current-state.md`, `docs/changes/STG-20260411-02-market-data-processing-master.md`, `docs/changes/STG-20260411-16-atomic-p1-enhancement-design.md`

## 2026-04-11 23:35 | 数据治理 / 利通 P1-A 字段实跑验证 AI
- Task ID: `CHG-20260411-14`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`
- 结论: 已把 `run_symbol_atomic_validation.py`、`backfill_atomic_order_from_raw.py` 与 `atomic_fact_p0_schema.sql` 同步到 Windows，并按 `2026-02-01~2026-02-28 + 2026-03-01~2026-04-10` 对利通执行第三轮 P1-A 重跑，结果仍为 `44/44` 成功、`0` 失败。验证库中新增字段已落值，说明这批 P1-A 增强可以进入后续样板解释与批量回补规划。
- 风险: 当前只验证了利通样板票，尚未说明所有股票、所有事件码风格都完全无坑；正式批量回补前仍需要再做横向小样本验证。
- 链接: `backend/scripts/run_symbol_atomic_validation.py`, `backend/scripts/backfill_atomic_order_from_raw.py`, `docs/changes/STG-20260411-16-atomic-p1-enhancement-design.md`, `docs/changes/MOD-20260411-14-market-data-governance-current-state.md`

## 2026-04-12 00:20 | 数据治理 / 涨跌停状态层专项设计 AI
- Task ID: `CHG-20260411-14`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`
- 结论: 已把涨跌停状态层从 P1-B 待补项提升为专项设计，新增 `STG-20260412-01-limit-state-layer-design.md`，并同步回填到数据治理母卡、总方案与 P1 设计卡。当前建议在独立治理库新增 `atomic_limit_state_daily` 与 `atomic_limit_state_5m`，并通过 `cfg_limit_rule_map` 做板块/风险标识/生效日期配置，不把涨跌停比例硬编码到脚本里。
- 风险: 涨跌停比例属于交易规则口径，未来可能调整；因此当前冻结的是“配置驱动设计”，不是永久写死比例。
- 链接: `docs/changes/STG-20260412-01-limit-state-layer-design.md`, `docs/changes/MOD-20260411-14-market-data-governance-current-state.md`, `docs/changes/STG-20260411-02-market-data-processing-master.md`, `docs/changes/STG-20260411-16-atomic-p1-enhancement-design.md`

## 2026-04-12 00:35 | 数据治理 / 集合竞价 phase 过程层专项设计 AI
- Task ID: `CHG-20260411-14`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`
- 结论: 已把‘更细的竞价层’收口为 phase 过程层，而不是逐笔竞价明细库；新增 `STG-20260412-02-open-auction-phase-layer-design.md`，建议在现有 `atomic_open_auction_l1/l2_daily` 摘要层之上，新增 `atomic_open_auction_phase_l1_daily` 与 `atomic_open_auction_phase_l2_daily` 两张日级过程表，用于记录 `09:15~09:20 / 09:20~09:25 / 09:25撮合` 三段演化。
- 风险: 这层目前还是设计冻结，是否能大规模批量回补，仍要先抽 raw 样本确认 `行情/成交/委托` 对竞价 phase 覆盖是否稳定。
- 链接: `docs/changes/STG-20260412-02-open-auction-phase-layer-design.md`, `docs/changes/MOD-20260411-14-market-data-governance-current-state.md`, `docs/changes/STG-20260411-02-market-data-processing-master.md`

## 2026-04-12 00:50 | 数据治理 / 盘口存量快照层专项设计 AI
- Task ID: `CHG-20260411-14`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`
- 结论: 已把盘口存量快照层写入正式总设计，新增 `STG-20260412-03-order-book-state-layer-design.md`，建议后续若 raw 的 `行情.csv` 能稳定提供盘口快照，再新增 `atomic_book_state_5m` 与 `atomic_book_state_daily`。当前这层先定位为‘待 raw 可行性确认后再实现’，不直接插队主线开发。
- 风险: 若原始文件没有稳定的盘口快照，只靠逐笔委托/成交反推留存挂单，会有较大失真风险；因此这层不能先拍脑袋落地。
- 链接: `docs/changes/STG-20260412-03-order-book-state-layer-design.md`, `docs/changes/MOD-20260411-14-market-data-governance-current-state.md`, `docs/changes/STG-20260411-02-market-data-processing-master.md`

## 2026-04-12 01:20 | 数据治理 / 盘口存量快照层基础版落地 AI
- Task ID: `CHG-20260411-14`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`
- 结论: 已新增 `book_state_schema.sql` 与 `build_book_state_from_raw.py`，并接入 `run_symbol_atomic_validation.py`。当前基础版已能从 `行情.csv` 生成 `atomic_book_state_5m / atomic_book_state_daily`，口径为“每个 5m bucket 取最后一个盘口快照”，并处理 `15:00 -> 14:55` 归并。单测已通过。
- 风险: 当前 `resting_amount` 仍按十档金额和落值，不代表绝对全盘口总额；下一步必须在 Windows 4 只样板库核字段值与单位，再决定是否进入批量回补。
- 链接: `backend/scripts/build_book_state_from_raw.py`, `backend/scripts/sql/book_state_schema.sql`, `backend/scripts/run_symbol_atomic_validation.py`, `backend/tests/test_book_state_from_raw.py`, `docs/changes/STG-20260412-03-order-book-state-layer-design.md`

## 2026-04-12 01:45 | 数据治理 / 4只样板票补齐 book+limit 状态层 AI
- Task ID: `CHG-20260411-14`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`, `CAP-WIN-PIPELINE`
- 结论: 已把最新脚本同步到 Windows，并完成 4 只样板票重跑。结果：利通 `44/44` 成功，其余 3 只各 `29/29` 成功；4 个标准验证库现均包含 `15` 张表，其中 `atomic_book_state_daily` 已落 `29` 天新数据，`atomic_limit_state_daily` 也已同步重建。
- 风险: 当前发现 Windows 命令行直接传反斜杠路径会生成一份“错路径 DB”副本；本次已回拷到标准目录，但后续批量跑必须统一改成更稳的路径传参方式，避免脏文件继续堆积。
- 链接: `backend/scripts/run_symbol_atomic_validation.py`, `backend/scripts/build_book_state_from_raw.py`, `backend/scripts/build_limit_state_from_atomic.py`, `docs/changes/MOD-20260411-14-market-data-governance-current-state.md`, `docs/changes/STG-20260412-03-order-book-state-layer-design.md`

## 2026-04-12 02:15 | 数据治理 / Windows 正式批量回补口径落地 AI
- Task ID: `CHG-20260411-14`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 结论: 已新增 Windows 本地正式回补入口 `run_atomic_backfill_windows.py`，并配套 `win_run_atomic_backfill.bat + sample/pilot config`。核心改动是：不再从 Mac 侧用 SSH 拼超长反斜杠路径，而是改成 Windows 本地读 JSON 配置执行，按天解压、按天清理、批次末统一重建 `limit_state`。同时已用 pilot config 在 Windows 跑通 `2026-02-27 + 2026-03-11` 两天、4 只样板票，结果成功。
- 风险: 当前 full-market 正式批次还没真正开跑；另外 `limit_state` 还是批次末统一重建，后续若全量规模明显变大，可以再改为按日增量。
- 链接: `backend/scripts/run_atomic_backfill_windows.py`, `ops/win_run_atomic_backfill.bat`, `backend/scripts/configs/atomic_backfill_windows.sample.json`, `backend/scripts/configs/atomic_backfill_windows.pilot.sample.json`, `docs/changes/STG-20260412-04-atomic-formal-backfill-runbook.md`

## 2026-04-12 02:35 | 数据治理 / 4只样板票三项核验收口 AI
- Task ID: `CHG-20260411-14`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`
- 结论: 已对 4 只样板票完成三项收口：1) 涨跌停状态层已落表并验证；2) `2026-03-11` 竞价 phase raw 审核显示 4 只票全部为 `trade+order+quote`；3) `2026-03-11` 盘口快照 raw 审核显示 4 只票全部达到 `sufficient_for_book_state_basic`。这意味着：limit/phase/book 三层都已具备进入全量回补的前提。
- 风险: 当前盘口 `resting_amount` 仍是十档金额和，后续若要做更强盘口解释，还需继续观察是否要引入更完整总额口径。
- 链接: `backend/scripts/build_limit_state_from_atomic.py`, `backend/scripts/audit_l2_auction_window.py`, `backend/scripts/audit_book_snapshot_raw.py`, `docs/changes/STG-20260412-01-limit-state-layer-design.md`, `docs/changes/STG-20260412-02-open-auction-phase-layer-design.md`, `docs/changes/STG-20260412-03-order-book-state-layer-design.md`

## 2026-04-12 12:05 | 数据治理 / 全市场 L2 解压链路纠偏 AI
- 卡片: `STG-20260412-04`, `MOD-20260411-14`
- 结论: 已确认本轮全市场原子层回补变慢的根因不是包本身，而是**误把旧稳定的 `Z:` + `tar -xf` 主链路改成了 `G:` + `7z.exe`**。复核旧方案后，`2026-04-01` 真实包（约 `5.30GB`）已用旧 prepare 路径在约 `255.5` 秒完成解压+切 `7702` 个 symbol / `8` 个 shard；同时复测得到 `8 worker ≈ 14.33 symbol/min`、`10 worker ≈ 14 symbol/min`、`12 worker` 更差。因此当前重新冻结：**全市场整日 L2 必须走 `Z:` staging + `tar -xf` + 8 worker；`G:` 只保留给单票定向验证或实验。**
- 风险: 若后续再次切换 staging 盘位或解压器，必须先做短 bench 并更新 runbook，否则会重犯同类问题。
- 链接: `docs/changes/STG-20260412-04-atomic-formal-backfill-runbook.md`, `docs/changes/STG-20260411-02-market-data-processing-master.md`, `docs/changes/MOD-20260411-14-market-data-governance-current-state.md`, `docs/04_OPS_AND_DEV.md`

## 2026-04-12 12:20 | 数据治理 / G盘依赖切断与连续月批入口补齐 AI
- 卡片: `STG-20260412-04`, `04_OPS_AND_DEV`
- 结论: 已再次确认 4只样板票最终产物全部落在 `D:\market-live-terminal\data\atomic_facts\*_validation.db`，不依赖 `G:` 挂载；`G:` 当前仅剩单票验证、bench、解压实验遗留目录，可在无占用进程时清理。与此同时，已补齐连续按月倒序回补入口：`atomic_backfill_windows.full_reverse_202604_to_202501.json`，以及 Mac 侧启动/人话状态查询脚本，后续正式跑数将按 `2026-04 -> 2026-03 -> 2026-02 -> 2026-01 -> 2025-12..2025-01` 连续推进，不再每月停一次。
- 风险: 正式连续月批启动前，仍需先清理 G 盘实验遗留目录，避免后续误判为正式依赖。
- 链接: `backend/scripts/configs/atomic_backfill_windows.full_reverse_202604_to_202501.json`, `ops/start_atomic_backfill_full_reverse.sh`, `ops/check_atomic_backfill_full_reverse.sh`, `docs/changes/STG-20260412-04-atomic-formal-backfill-runbook.md`, `docs/04_OPS_AND_DEV.md`

## 2026-04-12 12:35 | 数据治理 / Windows 盘位规则最终收口 AI
- 卡片: `STG-20260412-04`, `04_OPS_AND_DEV`
- 结论: 用户已明确要求彻底移除 `G:`。现已把未来所有 Windows 数据治理执行口径统一冻结为：**`Z:` + `tar -xf` + `8 worker`**，不再区分“单票验证可用 G”这类例外规则；同时已把该约束回填到总方案、runbook、当前状态卡，以及 `mac-windows-ops-bridge` 的项目参考中。
- 风险: 历史 `AI_HANDOFF_LOG` 中仍会保留曾经用过 `G:` 的事实记录，但那只是历史，不再代表当前可执行规则。
- 链接: `docs/changes/STG-20260412-04-atomic-formal-backfill-runbook.md`, `docs/changes/STG-20260411-02-market-data-processing-master.md`, `docs/04_OPS_AND_DEV.md`, `/Users/dong/Desktop/AIGC/skills/mac-windows-ops-bridge/references/market-live-terminal.md`

## 2026-04-12 20:45 | 数据治理 / 原子事实层计算链路压到 30 分钟内 AI
- 卡片: `STG-20260412-04`, `07_PENDING_TODO`
- 结论: 已完成第三轮提速并切换正式 runner 到“多进程分片库 + merge 回主库”。新增优化包括：`load_bundle` 先按时段过滤再转 datetime、`to_datetime(format=...)`、OrderID 对齐改 `Index.intersection`、trade parent 聚合改 `parent_bucket + parent_daily`。Windows 实测：`8 process / 160 symbols -> 39.20s`，吞吐 `244.91 symbol/min`，推全市场 `7097` symbols ≈ `28.98` 分钟；正式 runner 在已解压 day root 下 `160 symbols` 也已跑到 `40.19s`。同时复测确认 `10/12 process` 都比 `8` 慢，当前仍冻结 `8 worker`。
- 风险: 目前达标的是**已解压目录下的计算链路**；“整日 tar 解压 + 正式 runner”全链路总 wall time 还未最终压测收口，所以连续倒序月批暂不恢复。
- 链接: `backend/scripts/backfill_atomic_order_from_raw.py`, `backend/scripts/run_symbol_atomic_validation.py`, `backend/scripts/run_atomic_backfill_windows.py`, `backend/scripts/benchmark_atomic_process_shards.py`, `docs/changes/STG-20260412-04-atomic-formal-backfill-runbook.md`, `docs/07_PENDING_TODO.md`

## 2026-04-12 22:30 | 数据治理 / 主板3天连续预演通过 AI
- 卡片: `STG-20260412-04`, `04_OPS_AND_DEV`
- 结论: 已完成主板口径 `2026-04-01 ~ 2026-04-03` 连续 3 天真实预演，DB 为 `D:\market-live-terminal\data\atomic_facts\preflight_mainboard_3d_20260401_20260403.db`。3 天全部成功、0 失败，总耗时 `2365.61s`（约 `39.43` 分钟），平均约 `13.14` 分钟/天。并已抽查 `trade_daily/order_daily/book_state_daily/open_auction_l1_daily/limit_state_daily` 多表样本，确认数据真实落库。
- 风险: 这次 first preflight 已证明主板连续跑数可行，但也暴露出“`prefetch_next_day_extract` 若不同时配 `reuse_extracted_day_if_exists=true` 则不会真正复用”的配置要求；正式批次必须把这两个开关一起写死。
- 链接: `backend/scripts/run_atomic_backfill_windows.py`, `docs/changes/STG-20260412-04-atomic-formal-backfill-runbook.md`, `docs/04_OPS_AND_DEV.md`

## 2026-04-12 21:50 | 数据治理 / 正式主板批量回补已启动 AI
- 卡片: `STG-20260412-04`
- 结论: 已正式启动主板口径连续批量回补，config=`atomic_backfill_windows.mainboard_full_reverse_202604_to_202501.json`，DB=`market_atomic_mainboard_full_reverse.db`。当前固定口径为主板 only + 8 worker + 预解压 + reuse。Mac 侧统一通过 `ops/check_atomic_backfill_status_brief.sh <config>` 查进度。
- 风险: 当前真正长期运行的进程是通过直跑验证后留在 Windows 上的正式进程；后续若需重启，仍优先用独立 config + 状态脚本验真，不只看 tasklist。
- 链接: `backend/scripts/configs/atomic_backfill_windows.mainboard_full_reverse_202604_to_202501.json`, `ops/start_atomic_backfill_mainboard_full_reverse.sh`, `docs/changes/STG-20260412-04-atomic-formal-backfill-runbook.md`
- 时间: 2026-04-12 23:20
- 摘要: 原子事实层正式长跑性能优化完成，并重新冻结正式执行口径
- 结论: 已修复最近一轮优化引入的 shard 回归（`build_book_rows` 调用口径、shard 错误可见化、shard 内复用单连接写库），并完成真实 wall time 复测：主板 only `2026-04-01` 全日完整链路 `8 worker = 743.23s`、`12 worker = 696.06s`。同时确认 `12 worker + overlap/prefetch` 会触发 `database or disk is full`，因此当前正式配置改为 **主板 only + `Z:` + `tar -xf` + `12 worker` + no-overlap**。
- 风险: overlap 能力不是逻辑错误，而是当前 `Z:` staging 容量不够；若后续要恢复 overlap，需先调整 staging 容量或落盘策略，再重做 3 天连续复测。
- 后续: 直接按更新后的正式 config 启动 `atomic_backfill_windows.mainboard_full_reverse_202604_to_202501.json` 长跑，并继续通过 `ops/check_atomic_backfill_status_brief.sh atomic_backfill_windows.mainboard_full_reverse_202604_to_202501.json` 查进度。
- 链接: `backend/scripts/run_atomic_backfill_windows.py`, `backend/scripts/benchmark_atomic_process_shards.py`, `backend/scripts/configs/atomic_backfill_windows.mainboard_full_reverse_202604_to_202501.json`, `docs/changes/STG-20260412-04-atomic-formal-backfill-runbook.md`
- 时间: 2026-04-12 23:55
- 摘要: 已收口本轮“选股数据治理 + 全量历史回补”的单文档总说明
- 结论: 已新增总入口文档，统一说明本轮业务背景、原子事实层方案、单票验证、多票验证、全市场正式回补、关键踩坑、性能提速路径、正式冻结口径，以及“当前数据尚未切到旧功能”的边界。后续如果只看一份文档，优先看这份总说明。
- 风险: 当前长跑仍在继续推进，文档描述的是“截至 2026-04-12 晚间的冻结状态”；如果后续正式口径再变化，需要继续回填这份总说明而不是再分裂出新的平行真相文档。
- 后续: 持续观察 `mainboard_full_reverse` 长跑，阶段完成后回填进度，并在后续功能对接时明确哪些页面切新数据源。
- 链接: `docs/changes/MOD-20260412-05-selection-atomic-backfill-retrospective.md`

## 2026-04-14 01:20 | Codex
- Task ID: `CHG-20260414-01`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`
- 结论: 已把本轮原子事实层正式回补的真实收尾状态回填到总文档与 runbook：确认主板 `2026-04 -> 2025-01` 主数据已全部落库，当前唯一集中缺口是最后统一回填 `limit_state` 时因磁盘空间不足失败；同时已盘点 `D:\MarketData\202501~202503` 与 `Z:` 上 bench/stage/l2_stage 临时目录的人工可删清单，并把 P0 收尾顺序改成“先清空间，再单独补 limit_state，再做全量校验”。
- 风险: 当前 `state.json` 仍是假 `running`，且新原子层尚未正式接入旧复盘/盯盘/选股链路；若不先做状态收尾和 limit_state 补跑，就还不能进入功能迁移。
- 链接: `docs/changes/MOD-20260412-05-selection-atomic-backfill-retrospective.md`, `docs/changes/STG-20260412-04-atomic-formal-backfill-runbook.md`, `docs/07_PENDING_TODO.md`

## 2026-04-14 23:05 | Codex
- Task ID: `CHG-20260414-01`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`
- 结论: 已完成本轮正式回补的 P0 收尾：新增 `finalize_atomic_backfill_run.py / validate_atomic_backfill_run.py`，在 Windows 上单独补完 `atomic_limit_state_5m / daily`，并生成最终 `state/report/validation` 三份产物。当前正式库状态已收口为 `done`，`limit_state_daily=974571`、`limit_state_5m=47545635`，可进入“新原子层 -> 复盘/选股功能对接”阶段。
- 风险: `report/validation` 中的 `expected_day_count` 反映的是**当前 raw 存量快照**，会因为旧 raw 月包已删除而小于历史 `completed_days=307`；验收时应优先看最终表行数、月度覆盖和抽样结果，而不是把该字段当成历史完成天数。
- 链接: `backend/scripts/finalize_atomic_backfill_run.py`, `backend/scripts/validate_atomic_backfill_run.py`, `docs/changes/MOD-20260412-05-selection-atomic-backfill-retrospective.md`, `docs/changes/STG-20260412-04-atomic-formal-backfill-runbook.md`

## 2026-04-14 23:40 | Codex
- Task ID: `CHG-20260414-02`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-HISTORY-30M`, `CAP-SELECTION-RESEARCH`
- 结论: 已完成“新原子层 -> 旧功能兼容迁移”的第一层：`l2_history_db` 新增 atomic fallback，旧 `history_daily_l2/history_5m_l2` 有数据时仍优先旧表，缺数据时自动读 `atomic_trade_* / atomic_order_*`；`query_review_pool` 也已能从 `atomic_trade_daily` 补 bounds。与此同时，`selection_research` 的 `_load_l2_daily/_load_l2_5m_daily` 也已接 atomic fallback，因此复盘旧接口和选股研究输入都开始具备读新原子表的能力。
- 风险: 当前这仍是“兼容层”，不是全量硬切；要真正让本地页面稳定看到新数据，还需要下一步继续处理本地/Windows/生产的 atomic DB 路径与部署口径。
- 链接: `backend/app/db/l2_history_db.py`, `backend/app/services/selection_research.py`, `backend/tests/test_atomic_review_fallback.py`, `docs/changes/MOD-20260412-05-selection-atomic-backfill-retrospective.md`

## 2026-04-14 23:58 | Codex
- Task ID: `CHG-20260414-02`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-HISTORY-30M`, `CAP-SELECTION-RESEARCH`
- 结论: 已完成兼容迁移第二层收口：把 `ATOMIC_DB_PATH / ATOMIC_MAINBOARD_DB_PATH` 上收为统一配置入口，Docker 默认也能显式挂接 `market_atomic_mainboard_full_reverse.db`；同时新增 `test_atomic_history_multiframe_fallback.py`，覆盖“旧历史表为空、仅 atomic 有数据”时 `/api/history/multiframe` 的 `1d/30m` 返回，确保复盘多维链路在 atomic-only 场景下也有测试兜底。
- 风险: 当前还是“兼容迁移”而非真实页面硬切；本地若未挂到真实 atomic DB 文件，页面仍看不到新原子层数据。
- 链接: `backend/app/core/config.py`, `deploy/docker-compose.yml`, `backend/tests/test_atomic_history_multiframe_fallback.py`, `docs/changes/MOD-20260412-05-selection-atomic-backfill-retrospective.md`

## 2026-04-15 00:20 | Codex
- Task ID: `CHG-20260414-02`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`
- 结论: 已继续把选股链路补到可落地验收：`selection_research` 现在在 `local_history` 为空/覆盖不足时，可直接用 `atomic_trade_daily` 兜底映射日级行情与主力净额，完成 feature/signal/profile 计算；同时新增 `ops/start_local_backend_with_atomic.sh` 作为本地挂正式 atomic 库的统一启动入口，并补了 atomic-only 的选股路由测试。
- 风险: 这一步解决的是“本地挂 atomic 后选股页能跑起来”的底座问题；真实页面是否直接出候选，还取决于本地是否实际挂到了正式 `market_atomic_mainboard_full_reverse.db`。
- 链接: `backend/app/services/selection_research.py`, `backend/tests/test_selection_research.py`, `ops/start_local_backend_with_atomic.sh`, `src/version.ts`

## 2026-04-15 01:05 | Codex
- Task ID: `CHG-20260415-01`
- CAP: `CAP-L2-HISTORY-FOUNDATION`, `CAP-HISTORY-30M`, `CAP-SELECTION-RESEARCH`, `CAP-WIN-PIPELINE`
- 结论: 已完成“数据治理生产发布准备”的第一步收口：确认当前生产基线仍为已归档的 `v4.2.32 / 9bbdd3d`，新增发布准备母卡 `MOD-20260415-01-atomic-release-readiness.md`，并把当前 atomic 集成阶段明确归类为 `UNRELEASED_WORK + STAGE_READY_TO_NORMALIZE`。建议后续正式发布时不要沿用零散 patch，而是统一归一到 `v4.3.0` 再切生产。
- 风险: 当前仍处于工作分支，尚未合回 `main`；atomic 切换虽然本地已基本通，但生产挂库路径、selection DB 与页面最终冒烟仍需正式验证。
- 链接: `docs/changes/MOD-20260415-01-atomic-release-readiness.md`, `docs/archive/changes/ARC-CHG-20260324-retail-sentiment-v2-release-and-backfill.md`, `backend/app/main.py`

## 2026-04-15 01:20 | Codex
- Task ID: `CHG-20260415-02`
- CAP: `CAP-WIN-PIPELINE`, `CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`
- 结论: 已把本轮数据治理后的真实运行架构收口为“云端只保留轻量盯盘 / Windows 做数据主站 / Mac 做本地研究工作台”，并新增母卡 `MOD-20260415-02-local-research-station-architecture.md` 作为当前真相入口；同时回填 `02/04/07/AI_QUICK_START`，停止把“full atomic 切生产”作为当前主线目标；当前主开发分支：`codex/local-research-station-20260415`，主开发 worktree：`/Users/dong/Desktop/AIGC/market-live-terminal-local-research`。
- 风险: Windows -> Mac 研究快照同步链路与 Mac 本地复盘裁剪库尚未正式落地，当前只是完成了架构收口与待办冻结。
- 链接: `docs/changes/MOD-20260415-02-local-research-station-architecture.md`, `docs/02_BUSINESS_DOMAIN.md`, `docs/04_OPS_AND_DEV.md`, `docs/07_PENDING_TODO.md`, `docs/AI_QUICK_START.md`

## 2026-04-15 22:05 | Codex
- Task ID: `CHG-20260415-02`
- CAP: `CAP-WIN-PIPELINE`, `CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`
- 结论: 已完成本地研究站 Phase B/P2 的第一轮落地：新增 `build_local_research_snapshot.py + sync_windows_research_snapshot.sh + start_local_research_station.sh`，并完成一次真实 Windows -> Mac 快照同步验证；随后用 `PORT=8001` 启动本地研究站，已验证 `/api/selection/health`、`/api/selection/candidates`、`/api/review/pool`、`/api/review/data` 都能直接读本地快照工作。
- 风险: Windows 端正式 `selection_research.db` 仍未稳定产出，当前同步脚本还保留本地 bootstrap selection DB 兜底；后续需单独补齐 Windows selection 产出链路。
- 链接: `backend/scripts/build_local_research_snapshot.py`, `ops/sync_windows_research_snapshot.sh`, `ops/start_local_research_station.sh`, `docs/changes/STG-20260415-03-local-research-station-rollout-plan.md`

## 2026-04-15 23:10 | Codex
- Task ID: `CHG-20260415-02`
- CAP: `CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`
- 结论: 已继续推进本地研究站可用性：确认 Windows 正式选股库实际文件名为 `selection_research_windows.db`，并把 `build_local_research_snapshot.py + sync_windows_research_snapshot.sh` 改为自动识别 `selection_research.db / selection_research_windows.db`；同时补了 `ops/start_local_research_frontend.sh` 与 `VITE_API_PROXY_TARGET` 代理开关，Mac 本地前后端启动链路已收口。
- 风险: 还需再做一轮完整 smoke，确认最新同步确实不再依赖本地 bootstrap，且页面层使用体验稳定。
- 链接: `backend/scripts/build_local_research_snapshot.py`, `ops/sync_windows_research_snapshot.sh`, `ops/start_local_research_frontend.sh`, `vite.config.ts`

## 2026-04-15 23:45 | Codex
- Task ID: `CHG-20260415-03`
- CAP: `CAP-WIN-PIPELINE`, `CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`
- 结论: 已根据最新确认把架构真相再次收口：旧的“Windows -> Mac 裁剪快照”不再作为最终目标，改为“raw 只留 Windows；处理后全量库 Windows / Mac 各保留一份；Cloud 只保留轻量盯盘”；同时明确旧 `./ops/run_postclose_l2.sh` 只覆盖数据治理前的盘后结果，不包含 atomic / selection 等新增表，后续需要升级成“首次整库同步 + 每日增量同步”的统一入口。
- 风险: 这一步目前先完成文档收口，新的日常总控命令还未真正实现。
- 链接: `docs/changes/MOD-20260415-02-local-research-station-architecture.md`, `docs/changes/STG-20260415-03-local-research-station-rollout-plan.md`, `docs/04_OPS_AND_DEV.md`

## 2026-04-16 00:20 | Codex
- Task ID: `CHG-20260415-03`
- CAP: `CAP-WIN-PIPELINE`, `CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`
- 结论: 已实现新版日常总控第一版：`run_postclose_l2_daily.py` 现在除旧的 Cloud L2 merge 外，还新增了 Windows 本地 `market_data.db` merge、Mac 本地 `market_data.db` merge、Windows 单日 `atomic` 更新、Windows 单日 `selection` 刷新，以及 `atomic_day_delta / selection_day_delta` 导出回流 Mac；并支持 `--bootstrap-mac-full-sync` 做首次整库同步。
- 风险: 目前已完成本地脚本级验证与 dry-run；还未对整条远程真实链路做一轮完整实跑。
- 链接: `backend/scripts/run_postclose_l2_daily.py`, `backend/scripts/export_atomic_day_delta.py`, `backend/scripts/merge_atomic_day_delta.py`, `backend/scripts/export_selection_day_delta.py`, `backend/scripts/merge_selection_day_delta.py`
