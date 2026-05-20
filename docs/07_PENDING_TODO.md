# 07_PENDING_TODO（当前活跃待办 / 阻塞）

> 只保留**当前真实仍在 pending** 的事项；已过期、已降级为历史上下文、或已转入过程卡的旧事项，统一移出本文件。
> 当前项目真相总入口：`docs/changes/MOD-20260421-01-project-current-state-and-doc-governance-normalization.md`
> 已移出的旧待办摘要：`docs/archive/ARC-LEG-20260425-pending-todo-pre-v5-summary.md`

## T-014 每日盘后 L2 正式回补自动编排固化
- 状态：`ACTIVE`
- 当前事实：Mac 一条命令总控 `ops/run_postclose_l2.sh` 已固化；同步铁律已收敛为“局域网 HTTP relay / Cloud relay”，`2026-04-24` 已完成收口验证。剩余问题不再是“能不能跑通”，而是是否继续推进更强的无人值守编排与长期稳定性观察。
- 下一步：
  1. 评估是否继续做 OS 级定时控制器；
  2. 固化 repair queue 导出与失败清单；
  3. 若当前人工一条命令已满足日用，则把“全自动”降为次优先级。
- 关联任务：`CHG-20260315-02`, `MOD-20260425-04`

## T-016 Windows 实时采集计划任务稳态化
- 状态：`ACTIVE`
- 当前事实：`ZhangDataLiveCrawler` 已清掉重复进程并重建任务；`live_crawler_win.py` 已增加交易日判断与单实例锁。当前验证到 5 分钟重复触发后仍只有一个 Python crawler 进程。
- 下一步：
  1. 补一次 Windows 重启或注销后的自动恢复演练；
  2. 视需要增加 heartbeat / 健康日志；
  3. 把 tick 单源风险与 fallback 收口为下一张明确变更卡。
- 关联任务：`CHG-20260316-06`, `CHG-20260318-01`

## T-019 原子事实层全链路 30 分钟目标
- 状态：`ACTIVE`
- 当前事实：计算链路样本估算已进入 `~30m` 目标线，剩余未完成的是“真实整日 prepare + run”总 wall time 验证。
- 下一步：
  1. 对真实交易日做一次整条链路计时；
  2. 如果仍超时，继续优化 prepare 与 runner 衔接；
  3. 达标后再决定是否恢复更大范围正式回补。
- 关联任务：`CHG-20260411-14`

## T-020 本地研究站稳定性观察
- 状态：`ACTIVE`
- 当前事实：Windows / Mac / Cloud 三端职责已冻结；本地研究站已补齐“必须通过正式脚本启动，否则会读错库”的启动红线，并修复周末默认上一交易日盯盘缺票自动补拉。当前待观察项主要剩“自然日运行几天后是否再出现错库/错进程”。
- 下一步：
  1. 继续观察几天自然盘后链路；
  2. 继续确认本地启动入口统一收敛到 `ops/start_local_research_station.sh`；
  3. 若无新故障，把本项关闭，并把“已稳定”回写长期文档。
- 关联任务：`CHG-20260417-01`, `MOD-20260425-04`

## T-022 选股工作台数据对齐与本地补齐
- 状态：`ACTIVE`
- 当前事实：选股工作台能力已可用，已接入每日复盘决策、资金流回调稳健、趋势中继高质量回踩；但当前仍只能视为研究/观察工作台，不能当稳定自动买入信号。最新复核结果是：主链能跑，但还不能叫“完美支持”，当前最实的缺口是 `stock_universe_meta` 为空、`2026-04-01 ~ 2026-04-10` 的 `history_*_l2` 缺口、以及 `market_heat` 仍可能读到空的 old full_reverse / 旧 snapshot cache。
- 下一步：
  1. 补 `stock_universe_meta`；
  2. 恢复 `2026-04-01 ~ 2026-04-10` 的 `history_daily_l2 / history_5m_l2` 正式覆盖，并决定是否显式暴露 atomic fallback/source；
  3. 清理 `market_heat` 旧 snapshot/cache，并让 atomic source 明确收敛到 compact；
  4. 跟踪资金流回调稳健与趋势中继最近信号的真实后续表现；
  5. 明确哪些策略结果只做解释/观察，哪些可以进入模拟盘优先级。
- 关联任务：`CHG-20260404-02`, `REL-20260427-selection-strategy-research-v5.0.9`, `MOD-20260429-07`

## T-027 单票新闻 / 公告 / 互动问答事件层基础建设
- 状态：`ACTIVE`
- 当前事实：公告 / 问答 / 资讯三类事实源已接通，无 token 模式也具备 fallback；当前缺的是“事件理解层”与更稳的实体映射。
- 下一步：
  1. 补利好/利空/催化类型/持续性等事件理解层；
  2. 扩充 alias/简称词典；
  3. 用 audit 持续抽检真实单票覆盖质量。
- 关联任务：`CHG-20260412-01`

## T-031 存量表依赖剥离验证
- 状态：`ACTIVE`
- 当前事实：运行时代码仍存在旧表/旧 snapshot/旧 source 候选顺序残留，因此“主链能跑”不等于“旧路径已经退干净”。
- 下一步：
  1. 复制测试版 `market_data.db`；
  2. 按表组删除存量表；
  3. 让本地服务指向测试库做回归；
  4. 明确哪些依赖尚未切干净，尤其 `review/data`、`history/multiframe`、`market_heat latest/fine dashboard`；
  5. 记录哪些链路只是 atomic merge / cache 命中后勉强可用，哪些已经真正完成新基线切换。
- 关联任务：`CHG-20260417-01`

## T-033 过程材料分级清理与入口降噪
- 状态：`ACTIVE`
- 当前事实：系统页面/模块已经形成主链、研究主线、实验专题三层，但仓库里仍堆积大量过程卡、历史研究、专题实验文档和脚本族。当前最大的治理风险不是“代码还不够漂亮”，而是过时材料仍在持续误导后续实现。第一批风险分级已完成；`docs/changes` 的 5 张高风险现状型过程卡、`docs/strategy-rework/handoff-for-next-ai.md`，以及 `docs/strategy-rework/README.md`、`docs/selection/daily_candidate_source_contract.md`、`docs/selection/opportunity_discovery_model_final.md`、`docs/04_OPS_AND_DEV.md` 的入口提示已补齐。第二批已执行：`docs/selection` 顶层 4 份一次性清理过程文档已迁入 `docs/archive/`，并新增 `selection_research_archive_decision_summary.md` 承接压缩结论。第三批已完成：`docs/strategy-rework/current-inventory.md`、`project-status-20260427.md`、`experiment-decision-log.md` 已迁 archive；`LONG_MEMORY / current-strategy-conclusion / current-research-operating-summary` 已收成新的默认三件套。当前又补了 `docs/ops/atomic-script-families-boundary.md`，把 `full_reverse / atomic backfill / bench / snapshot` 的历史脚本族边界单独收口。现在又补了系统地图与阶段摘要草稿，开始把主链 / 研究主线 / 专题层 / 三端职责固定成更稳定的总图。
- 重新评估结果：继续压历史文档的收益已经不高，后续只保留能直接消除错误入口、重复承接或冲突语义的最小改动；治理重心转向代码层共享壳和双轨实现收口。
- 下一步：
  1. 按 `docs/changes/MOD-20260520-04-code-governance-plan.md` 的第一批范围推进代码治理评估；
  2. 文档侧只保留必要的入口澄清和追溯索引，不再追加大面积瘦身；
  3. 等代码治理落一轮结果后，再决定是否还需要做最后一轮归档压缩。
- 关联任务：`MOD-20260519-01`, `MOD-20260519-02`, `MOD-20260424-02`, `MOD-20260424-03`
