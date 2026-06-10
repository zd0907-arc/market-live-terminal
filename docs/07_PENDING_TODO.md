# 07_PENDING_TODO（当前活跃待办 / 阻塞）

> 只保留**当前真实仍在 pending** 的事项；已过期、已降级为历史上下文、或已转入过程卡的旧事项，统一移出本文件。
> 当前项目真相总入口：`docs/changes/MOD-20260421-01-project-current-state-and-doc-governance-normalization.md`
> 已移出的旧待办摘要：`docs/archive/ARC-LEG-20260425-pending-todo-pre-v5-summary.md`

## T-014 每日盘后 L2 正式回补自动编排固化
- 状态：`ACTIVE`
- 当前事实：当前每日盘后正式主链是 `ops/run_daily_new_framework.sh --json`，已把 atomic、selection、市场环境指数、热点结果、热点页面缓存、model feature store 和选股工作台候选输出纳入一次日跑；`2026-05-26` 真实日跑已验证通过。剩余问题不再是“能不能跑通”，而是是否继续推进更强的无人值守编排与长期稳定性观察。
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
- 当前事实：Mac / Windows / NAS 三端职责已冻结；本地研究站已补齐“必须通过正式脚本启动，否则会读错库”的启动红线，并修复周末默认上一交易日盯盘缺票自动补拉。`2026-05-26` 又定位并修复了一次“重复拉起多个本地后端导致业务接口超时”的事故：`ops/start_local_research_station.sh` 已新增同仓库重复实例保护，核心 runbook 也已回写。当前待观察项主要剩“自然日运行几天后是否再出现错库/错进程”。
- 下一步：
  1. 继续观察几天自然盘后链路；
  2. 继续确认本地启动入口统一收敛到 `ops/start_local_research_station.sh`；
  3. 若无新故障，把本项关闭，并把“已稳定”回写长期文档。
- 关联任务：`CHG-20260417-01`, `MOD-20260425-04`

## T-022 选股工作台数据对齐与本地补齐
- 状态：`ACTIVE`
- 当前事实：选股工作台能力已可用，已接入每日复盘决策、资金流回调稳健、趋势中继高质量回踩；但当前仍只能视为研究/观察工作台，不能当稳定自动买入信号。`2026-06-09` 已把本地 `stock_universe_meta` 刷新脚本改成“优先东方财富全市场快照、无依赖可跑”的口径，并已把 Mac 本地正式库刷到 `5532` 行，`/api/review/pool` 现可返回带名称/市值的正式池。同日又把 `run_daily_new_framework.py` 补上“主链本地校验通过后，默认继续触发本地 `postclose_l2` L2 历史补齐 + `stock_universe_meta` 刷新”的后处理，所以未来新交易日不该再继续漏写这两张正式历史表。实际补跑上，本轮还利用已跑完的 `worker_*.db` 手工把 `2026-06-08` 合并回 Windows / Mac 本地正式 `market_data.db`，当前本地 `history_daily_l2` 与 `history_5m_l2` 的最大日期已推进到 `2026-06-08`。剩余 backlog 已收缩为 `2026-05-22 ~ 2026-06-05` 这 `11` 个交易日；同时 NAS / 线上 `live` 口径是否要跟随这条主链，仍需单独决定。
- 下一步：
  1. 用一次真实日跑验证 `run_daily_new_framework.sh` 新增的本地 `postclose_l2 + stock_universe_meta` 后处理闭环；
  2. 恢复剩余 `2026-05-22 ~ 2026-06-05` 的 `history_daily_l2 / history_5m_l2` 存量 backlog，并决定是否显式暴露 atomic fallback/source；
  3. 确认 NAS / 线上 `live/market_data.db` 是否也要跟随这条主链自动补齐；
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

## T-034 正式别名与 shadow/sample 迁移规划
- 状态：`DONE`
- 当前事实：`2026-06-08` 已完成 Windows 正式命名收口：正式主链只保留 `selection_research.db`、`market_atomic_mainboard_compact_current.db`、`model_feature_store.db`；旧 `selection_research_windows.db` 与 `compact_smoke_*` 正式别名已退休，`model_feature_store_smoke_*` 与 atomic 历史测试/备份库已下沉到 `Z:\atomic_legacy_backup\windows_retired_20260608\`。
- 收口结果：
  1. 活跃脚本默认值已统一到 canonical 名；
  2. Windows 现场不再保留旧正式别名；
  3. 历史对象进入冷备退休区，不再和正式运行目录并列。
- 关联任务：`MOD-20260524-12-formal-alias-and-shadow-sample-migration-plan`, `MOD-20260606-10-repo-and-market-data-structure-governance-plan`

## T-037 Windows / NAS 终态对齐与正式公网入口
- 状态：`ACTIVE`
- 当前事实：按 `2026-06-09` 晚间的现场核查，三端“文件名口径”已经基本统一，Windows 也已补出和 Mac / NAS 一致的入口层。更关键的是，Mac 本地正式 `live` 库与 NAS 生产 `live` 库现在都已经补到 `2026-06-09`，当天 `history_daily_l2=7739`、`history_5m_l2=349019`、`stock_universe_meta=5532` 已对齐。当前没有做成的，不再是“当天数据进生产”，而是 NAS 侧的长期自动化与大体量 `research/current` 发布策略。
- 下一步：
  1. 决定 NAS 快照是否继续采用“每日 Mac 跑数后后台触发”这条方式，还是以后再补更高权限的 NAS 定时任务；
  2. 决定 `research/current` 是否还需要每天整包发布到 NAS；如果需要，要单独设计适合大库的发布方式，而不是继续绑在每日收盘主链里；
  3. 决定 Windows 后续是停在“别名层对齐”还是继续做物理目录终态整理；
  4. 如果不购买域名，就把当前 `*.ts.net` 免费地址作为长期公网入口；如果以后要品牌域名，再启用 `Cloudflare Tunnel + 自定义域名`。
- 关联任务：`MOD-20260608-01-windows-nas-runtime-storage-and-public-entry-audit`

## T-038 基线版本面一致性收口
- 状态：`DONE`
- 当前事实：`2026-06-11` 发布准备已把 `README.md`、`package.json`、`package-lock.json`、`src/version.ts`、`backend/app/main.py` 统一到 `v5.2.17`，并通过 `python3 scripts/check_version_consistency.py`。基线入口继续以 `bash scripts/check_baseline.sh` 为准。
- 下一步：
  1. 维持 `package.json` 属于正式版本面；
  2. 后续发布继续先跑版本一致性，再跑 governance、后端测试和前端 build；
  3. 若未来拆分前后端版本，再另立版本策略变更卡，不在发布中临时改口径。
- 关联任务：`MOD-20260609-06-ai-skill-routing-and-governance-alignment`
