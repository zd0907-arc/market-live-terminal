# AI_HANDOFF_LOG（短日志）

## 2026-06-12 每日主链补齐市场水位刷新 | Codex
- Task ID: `REQ-20260612-01-market-water-daily-refresh`
- CAP: `CAP-SELECTION-RESEARCH`, `CAP-NAS-OPS`
- 结论: 已确认 2026-06-11 选股页看不到“近期市场趋势”的根因不是前端丢失，而是每日主链没有刷新市场水位研究产物；当日数据已经进入 atomic、selection、model feature 和候选库，但市场水位目录只到 2026-06-10。已把 `run_daily_new_framework.py` 补成在本地核心数据完整后自动刷新运行态市场水位目录，并把水位可用性纳入完整性校验；`--sync-nas` 会同步该小目录到 NAS 数据卷。后端读取逻辑改为优先读运行态目录，docs 仅兜底，且文件更新后无需重启进程即可读取新 CSV。
- 风险: `research_market_environment_gate.py` 当前仍是全量重算，不是日增算法；本轮先保证每日可用，后续再评估是否需要增量化。生产仍需部署服务读取路径改造并同步运行态水位目录。
- 验证: 已补算本地 2026-06-11 水位，结果为 `防守-弱势承压`、水位 `17.1262`、默认 `暂停新开仓`、`recent.length=90`；`python3 -m py_compile backend/scripts/run_daily_new_framework.py backend/app/services/selection_market_environment_gate.py` 通过；`pytest backend/tests/test_run_daily_new_framework_auto.py backend/tests/test_selection_market_environment_gate.py -q` 通过。
- 链接: `docs/changes/REQ-20260612-01-market-water-daily-refresh.md`, `backend/scripts/run_daily_new_framework.py`, `backend/app/services/selection_market_environment_gate.py`, `backend/tests/test_selection_market_environment_gate.py`, `docs/04_OPS_AND_DEV.md`

## 2026-06-11 选股页近期市场趋势 UI 发布准备 | Codex
- Task ID: `REQ-20260611-01-selection-market-trend-ui`
- CAP: `CAP-SELECTION-RESEARCH`
- 结论: 已把选股页左侧市场水位从数字堆叠改成“近期市场趋势”90 日水位图，并压缩候选导航：日期、策略状态和候选分类整合为单行；删除独立“股票导航”标题、说明句和无用的候选处理图。趋势图支持鼠标悬停查看选中日期、水位分数和市场状态，弱势证据收进标题后的感叹号 hover。
- 风险: 该能力是实盘前的市场环境辅助判断，不改变模型/策略本身的候选生成逻辑；生产 NAS 是否能完整显示取决于线上 selection 数据和市场环境研究数据是否齐备。
- 验证: 本地 `3001` 已验证 `2026-06-10` 候选页可显示“近期市场趋势”，不再出现旧标题/说明句，hover 示例为 `2026-04-10 / 水位 63.8 / 攻击`；`/api/selection/daily-candidates` 经 `3001` 代理返回 `market_environment.recent.length=90`；`bash scripts/check_baseline.sh` 通过。2026-06-11 已发布 NAS 生产，`main=edfbd577831fd934e0940e1efe59c12fa2c41534`；公开入口 `/api/health`、`/api/selection/market-environment?date=2026-06-08`、`/api/selection/daily-candidates?date=2026-06-08&include_exit_watchlist=true`、`/selection-research` 均返回 200，其中市场水位 `available=true`、`recent.length=90`。
- 链接: `docs/changes/REQ-20260611-01-selection-market-trend-ui.md`, `docs/domain/selection-research.md`, `src/components/selection/SelectionResearchPage.tsx`, `src/version.ts`

## 2026-06-09 每日主链收口到 NAS 生产库 | Codex
- Task ID: `MOD-20260609-07-daily-live-nas-sync-closeout`
- CAP: `CAP-NAS-OPS`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已把每日主链真正收口到你关心的业务动作上。第一，修掉了 `run_postclose_l2_daily.py` 的本地-only 判定 bug，避免“Mac 本地 live 已经补成功，但脚本仍误报失败”。第二，把 `run_daily_new_framework.py` 的 `--sync-nas` 改成收盘后先同步 NAS 生产 `live/market_data.db`，再后台触发一轮 NAS 数据库快照，不再把大体量 `research/current` 整包发布绑进每天主链。第三，已做了一次真实补跑：`2026-06-09` 的 `history_daily_l2=7739`、`history_5m_l2=349019`、`stock_universe_meta=5532` 现已在 Mac 本地和 NAS 生产库两端对齐，用户最核心的“当天数据为什么没进生产”问题已经收口。
- 风险: 这不等于 NAS 一切都彻底自动化。当前快照是“每日主链成功后后台触发”，还不是 NAS 自治的计划任务；另外 `research/current` 若以后仍要每天发布，需要单独设计适合 70G 级 atomic 主库的增量或高效发布方式，不能继续沿用整包上传。
- 验证: 已实测 `2026-06-09` 本地 `postclose_l2` 补跑成功；Mac 本地 `live/market_data.db` 已见 `7739 / 349019 / 5532`；NAS 生产 `live/market_data.db` 也已见同样结果；NAS 新快照目录 `20260609_225608` 已启动后台生成；并已清理本轮超时留下的半成品 staging 目录 `research/staging/nas_daily_new_20260609`。
- 链接: `backend/scripts/run_postclose_l2_daily.py`, `backend/scripts/run_daily_new_framework.py`, `backend/tests/test_run_postclose_l2_daily.py`, `backend/tests/test_run_daily_new_framework_auto.py`, `docs/ops/three-end-sync.md`, `docs/04_OPS_AND_DEV.md`, `docs/AI_QUICK_START.md`, `docs/07_PENDING_TODO.md`

## 2026-06-09 AI / skill 路由与治理口径收口 | Codex
- Task ID: `MOD-20260609-06-ai-skill-routing-and-governance-alignment`
- CAP: `CAP-DOCS-GOVERNANCE`
- 结论: 已把这轮项目管理层的关键分工写清：新增了 `docs/ops/ai-skill-routing.md`，明确全局 `AGENTS.md`、项目 `AGENTS.md`、核心文档、`AI_QUICK_START.md`、project skills 之间各自负责什么；同时把它接回 `AGENTS.md`、`04_OPS_AND_DEV.md`、`AI_QUICK_START.md`，不再靠口头解释。顺手修了 3 处容易误导后续 AI 的 skill 冲突：`version/release` 由 `origin/main` 主线改回 `nas/main` 主线、`dev-workflow-coordinator` 补进 Windows / UI 两类高频 specialist、`mac-windows-ops-bridge` 不再把旧 sandbox / worker 口径混成当前正式 L2 规则。
- 风险: 这轮又暴露出一个真实治理阻塞：高曝光文档原来一直写 `npm run check:baseline`，但仓库真实入口是 `bash scripts/check_baseline.sh`。入口已统一改正，但脚本执行后发现当前 `package.json=1.16.0`，而 `README.md`、`src/version.ts`、`backend/app/main.py` 都是 `5.2.2`，基线 gate 目前仍会因此失败；该问题已单独挂到 `07_PENDING_TODO.md`。
- 链接: `docs/ops/ai-skill-routing.md`, `AGENTS.md`, `docs/04_OPS_AND_DEV.md`, `docs/AI_QUICK_START.md`, `docs/07_PENDING_TODO.md`, `docs/changes/MOD-20260609-06-ai-skill-routing-and-governance-alignment.md`

## 2026-06-09 三端目录与命名同步核查 | Codex
- Task ID: `MOD-20260609-05-three-end-sync-audit`
- CAP: `CAP-DOCS-GOVERNANCE`, `CAP-NAS-OPS`
- 结论: 已按业务目标重新做了一次只看“三端文件管理”的现场核查，并顺手修了三处低风险收口。第一，Mac 与 NAS 现在确实已经共享同一套正式目录层级：`live / research/current / cache / artifacts / incoming`；Windows 现场原来仍是扁平 `data/*`，本轮已补出同名入口层，所以三端之后可以统一按同一套路径说话。第二，Mac 端 `cache/market_heat` 与 `cache/eastmoney_sector_cache` 原来是断软链，已修回有效入口。第三，NAS 作为代码备份和数据库快照落点已经成立，但“自动定时备份”还没完成，因为当前 SSH 用户写 crontab 会报权限错误。最关键的业务结论是：你的“三端同步目标”还没有完全达成，因为 NAS 生产 `live/market_data.db` 还没有和 Mac 本地 `live/market_data.db` 完全收成同一份状态。
- 验证: 已现场核查 Mac、Windows、NAS 三端路径；Windows 新增可见入口 `data/live`、`data/research/current`、`data/cache`、`data/artifacts`、`data/incoming`；NAS 确认存在 Gitea 仓库 `/volume1/docker/gitea/git/repositories/zhangdong/market-live-terminal.git` 与数据库快照目录 `/volume1/docker/market-live-terminal/backups/db_snapshots/20260609_100757`。同时对比生产库状态：Mac `history_daily_l2` 最新日 `2026-06-08` 为 `7745` 行、`stock_universe_meta=5532`；NAS 同日为 `3193` 行、`stock_universe_meta=5230`，说明生产 `live` 还没真正跟上 Mac 本地正式库。
- 链接: `docs/ops/three-end-sync.md`, `docs/07_PENDING_TODO.md`, `docs/04_OPS_AND_DEV.md`

## 2026-06-09 本地 live backlog 实推 20260608 | Codex
- Task ID: `MOD-20260609-04-live-history-backlog-repair-sample`
- CAP: `CAP-DOCS-GOVERNANCE`, `CAP-SELECTION-RESEARCH`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已继续把 T-022 从“只修代码”往前推到一次真实补库。先补了 `run_postclose_l2_daily.py` 的 Windows bat 路径兼容，让它能同时识别新 `ops/windows/*` 和现场仍在用的旧 `ops/*`；随后复用已经跑出的 `20260608` `worker_*.db`，手工完成 Windows merge、导出 `l2_day_delta_20260608.db`、回传并 merge 到 Mac 本地正式 `live/market_data.db`。结果是本地 `history_daily_l2 / history_5m_l2` 最大日期都已推进到 `2026-06-08`，不再停在 `2026-05-21`。当前 backlog 已收缩到 `2026-05-22 ~ 2026-06-05` 共 `11` 个交易日。
- 风险: `20260608` 这次 merge 状态是 `partial_done`，共有 `16` 个 symbol failure，但主表已落入 `7745` 条 `history_daily_l2` 与 `351136` 条 `history_5m_l2`；这更像数据日包局部质量问题，不是主链路径问题。整条 `run_postclose_l2_daily.py --date 20260608` 仍会超时，因此本轮真实推进采用“复用 worker 产物，直接继续 merge/export”的方式完成。
- 验证: Windows 正式库 `history_daily_l2` 在 `2026-06-08` 新增 `7745` 行，Mac 本地正式库 `history_daily_l2` 在 `2026-06-08` 为 `7745` 行、`history_5m_l2` 在 `2026-06-08` 为 `351136` 行；随后再次执行 `python3 backend/scripts/refresh_stock_universe_meta.py --json`，`stock_universe_meta=5532`。剩余缺口日期复核为：`2026-05-22, 2026-05-25, 2026-05-26, 2026-05-27, 2026-05-28, 2026-05-29, 2026-06-01, 2026-06-02, 2026-06-03, 2026-06-04, 2026-06-05`。
- 链接: `backend/scripts/run_postclose_l2_daily.py`, `.run/postclose_l2/20260608/processed/l2_day_delta_20260608.db`, `docs/07_PENDING_TODO.md`

## 2026-06-09 日常主链补上本地 live 后处理 | Codex
- Task ID: `MOD-20260609-03-daily-mainline-live-postprocess`
- CAP: `CAP-DOCS-GOVERNANCE`, `CAP-SELECTION-RESEARCH`
- 结论: 已把 `backend/scripts/run_daily_new_framework.py` 补成“研究主链本地校验通过后，默认继续触发一次本地 `postclose_l2` L2 历史补齐，并刷新 `stock_universe_meta`”的后处理闭环。这样未来新交易日的 Mac 本地 `live/market_data.db` 不该再继续停在 `2026-05-21` 这类断更状态；同时保留 `--skip-live-sync` 作为排障开关，避免把旧 `live` 链路重新抬成不可绕过的黑盒。边界没有变：`--sync-nas` 仍只负责 `research/current`，不自动同步 NAS `live/market_data.db`。
- 验证: 新增 `backend/tests/test_run_daily_new_framework_auto.py` 两条用例，覆盖“默认会先做本地 live 后处理再 NAS 发布”和“显式 `skip` 时不会触发 live 后处理”；连同既有自动补跑检测用例一起执行 `pytest -q backend/tests/test_run_daily_new_framework_auto.py backend/tests/test_refresh_stock_universe_meta.py` 通过。`python3 -m py_compile backend/scripts/run_daily_new_framework.py backend/scripts/refresh_stock_universe_meta.py` 通过。
- 链接: `backend/scripts/run_daily_new_framework.py`, `backend/tests/test_run_daily_new_framework_auto.py`, `backend/scripts/refresh_stock_universe_meta.py`, `docs/07_PENDING_TODO.md`, `docs/changes/MOD-20260606-10-repo-and-market-data-structure-governance-plan.md`

## 2026-06-09 stock_universe_meta 无依赖刷新修复 | Codex
- Task ID: `MOD-20260609-02-stock-universe-meta-refresh-hardening`
- CAP: `CAP-DOCS-GOVERNANCE`, `CAP-SELECTION-RESEARCH`
- 结论: 已把 `backend/scripts/refresh_stock_universe_meta.py` 从“硬依赖 akshare + pandas”改成“优先东方财富全市场快照接口、无第三方依赖也能跑；akshare 退为次级 fallback；最后才用本地 selection/live 库兜底”。这样当前这台 Mac 就算只有系统 `python3`，也能直接把正式 `live/market_data.db` 里的 `stock_universe_meta` 刷起来，不再卡在依赖缺失。顺手复核出 `07_PENDING_TODO` 里旧说法已过期：当前真实历史缺口不再是 `2026-04-01 ~ 2026-04-10`，而是 `history_daily_l2 / history_5m_l2` 实际只覆盖到 `2026-05-21`；根因也已经钉住，当前 `run_daily_new_framework.py` 正式主链没有继续触发 `postclose_l2 / l2_daily_backfill`。
- 验证: 新增 `backend/tests/test_refresh_stock_universe_meta.py` 覆盖东方财富分页抓取和本地兜底逻辑，`pytest -q backend/tests/test_refresh_stock_universe_meta.py` 通过（`2 passed`）；实际执行 `python3 backend/scripts/refresh_stock_universe_meta.py --json` 后，Mac 本地正式库 `stock_universe_meta=5532`，其中 `market_cap > 0` 为 `5208`，`query_review_pool(limit=10)` 已能返回带名称/市值的正式池，`as_of_date=2026-06-09`、`latest_date=2026-06-08`。

## 2026-06-09 本地端口规范收口 | Codex
- Task ID: `MOD-20260609-01-local-port-governance`
- CAP: `CAP-DOCS-GOVERNANCE`
- 结论: 已把本地与 NAS 的正式端口口径重新收口。当前正式规则固定为：Mac 本地前端 `3001`、Mac 本地后端 `8001`、NAS 项目 Web `8080`、NAS Gitea Web `3000`；`8000` 只按 Docker 内部 backend 端口理解，`5173/5174` 只按历史临时调试端口理解，不再写入正式 runbook。顺手修复了 `ops/start_local_research_frontend.sh`：它不再依赖仓库根错误的 `npm run dev`，改为直接拉起本仓库 `vite`，并强制 `--strictPort`，防止前端端口静默漂移。
- 验证: 已确认 `vite.config.ts`、`src/config.ts`、`README.md`、`docs/AI_QUICK_START.md`、`docs/04_OPS_AND_DEV.md`、`docs/ops/mac-local-research.md` 当前都对齐到 `3001 / 8001`；`npm run dev` 现状会报 `Missing script: dev`；直接执行 `node_modules/.bin/vite --host 127.0.0.1 --port 3001 --strictPort` 可正常监听 `127.0.0.1:3001`。

## 2026-06-08 Windows/NAS 实机盘点 | Codex
- Task ID: `MOD-20260608-01-windows-nas-runtime-storage-and-public-entry-audit`
- CAP: `CAP-DOCS-GOVERNANCE`, `CAP-NAS-OPS`
- 结论: 已完成一轮不靠猜的 Windows / NAS 实机盘点，并顺手做了第一批低风险现场调整。Windows 侧已经确认不是开发仓，而是运行数据站：`D:\MarketData` 保存原始 `.7z` 包，`D:\market-live-terminal` 保存裁剪后的运行代码、正式产出 `data/` 和运行产物 `.run/`；`Z:\atomic_stage` 是 staging，`Z:\atomic_legacy_backup` 是冷备。本轮又已把 `selection_research.db`、`market_atomic_mainboard_compact_current.db` 两个 canonical 名补到 Windows 磁盘上，并保留旧名兼容。NAS 侧已经确认“服务在线，但目录和公网都还没到最终版”；同时已把 `full-import/` 和 `data-backup-*` 下沉到 `backups/`，并补了正式数据库快照脚本与备份策略文档。
- 风险: 当前真正剩余的不是 Mac 端，而是两端现场收口：Windows 的旧兼容名何时退休，以及 NAS 上 old flat-data root 实体的最终下线策略。正式公网入口还受制于域名和 `CLOUDFLARE_TUNNEL_TOKEN` 这两个外部条件。
- 验证: 已通过 SSH 实测两端目录与服务；Windows 侧确认 `.git / src / docs / package.json` 均不存在、`D:\MarketData` 约 `178.79 GB`、`D:\market-live-terminal\data\atomic_facts` 约 `108.82 GB`、`Z:\atomic_stage` 约 `99.37 GB`、`Z:\atomic_legacy_backup` 约 `40.21 GB`；同时已确认 `selection_research.db` 与 `selection_research_windows.db`、`market_atomic_mainboard_compact_current.db` 与 `compact_smoke_*` 当前长度一致并兼容共存。NAS 侧确认 `market-backend-nas / market-frontend-nas / gitea / tailscale-nas` 在线，且 `tailscale-nas` 仍报 `443` 冲突。
- 链接: `docs/changes/MOD-20260608-01-windows-nas-runtime-storage-and-public-entry-audit.md`, `docs/ops/windows-data-station.md`, `docs/ops/mac-nas-collaboration.md`, `docs/ops/storage-backup-policy.md`, `ops/nas/nas_backup_runtime_db_snapshot.sh`, `docs/07_PENDING_TODO.md`

## 2026-06-08 单日主链执行 20260608 | Codex
- Task ID: `CHG-20260608-daily-run-20260608`
- CAP: `CAP-NAS-OPS`, `CAP-SELECTION-RESEARCH`
- 结论: 已执行正式单日主链 `bash ops/run_daily_new_framework.sh --date 20260608 --json --sync-nas`。Windows `D:\MarketData\202606\20260608.7z` 已被消费，Windows 跑数、Mac 合并、选股候选生成均完成；首次失败只发生在 NAS 发布尾步，根因是 NAS 在线代码目录仍是旧扁平 `ops/` 结构，而本地发布链已切到 `ops/nas/`。已补齐 NAS 端 `ops/nas/*`，并把本地发布脚本改成兼容远端 `ops/nas/` 与旧 `ops/` 两种布局后重试成功。
- 验证: `.run/daily_new_framework/latest.json` 当前为 `pass`；`20260608` 当日 `atomic_trade_daily=3193`、`selection_feature_daily=3193`、`model_feature_daily_v1=3193`、热点 `v2` 已到 `2026-06-08`；NAS 当前 release 为 `nas_daily_new_20260608`，`/api/health` 返回 `200 OK`。

## 2026-06-08 Windows/NAS 结构退休收口 | Codex
- Task ID: `MOD-20260608-01-windows-nas-runtime-storage-and-public-entry-audit`
- CAP: `CAP-DOCS-GOVERNANCE`, `CAP-NAS-OPS`
- 结论: 已把“只新增不退休”的结构问题收口。Mac 侧正式 `atomic_facts` 当前只保留一份 `market_atomic_mainboard_compact_current.db`；Windows 侧 `selection_research_windows.db` 与 `compact_smoke_*` 正式别名已退休，`model_feature_store_smoke_*` 与 atomic 历史测试/备份库已下沉到 `Z:\atomic_legacy_backup\windows_retired_20260608\`；NAS 侧 root old flat-data 实体已下沉到 `/volume1/docker/market-live-terminal/backups/legacy_flat_root_20260608/`，在线服务仍保持 `200 OK`。
- 风险: 当前剩余不是“正式目录还在并行双写”，而是 Windows 0 MB 空壳与公网入口是否继续沿用免费 `*.ts.net`，还是以后再补自定义域名。
- 验证: 已实测 Mac `market-data/research/current/atomic_facts` 当前只有一份 `66G` 正式库；Windows `selection_research.db` 与 `market_atomic_mainboard_compact_current.db` 当前都只剩 canonical 名；NAS `/api/health` 在 old flat-data 下沉后仍返回 `200 OK`。

## 2026-06-08 治理卡收尾 | Codex
- Task ID: `MOD-20260606-10-repo-and-market-data-structure-governance-plan`
- CAP: `CAP-DOCS-GOVERNANCE`, `CAP-NAS-OPS`, `CAP-SELECTION-RESEARCH`
- 结论: 已把这轮“仓库与 market-data 结构治理”的主目标收尾到可关闭状态。`T-036` 目录结构治理已从活跃待办移出：云端线、report 线、删库后的文档闭环都已完成，root 层孤儿 `market_data.db-wal / market_data.db-shm` 也已删除。当前仍保留的治理项只剩 `T-034`，但它已经不再是结构治理，而是是否继续改 Windows 侧历史物理文件名的命名治理问题。
- 风险: 当前剩余不再是“系统会不会继续读错库”，而是“要不要继续追求更直观的跨端物理名”。这属于下一张卡，不应再混在本轮结构治理里。
- 验证: 已确认 `/Users/dong/Desktop/AIGC/market-data/live/market_data.db-shm` 与 `/Users/dong/Desktop/AIGC/market-data/live/market_data.db-wal` 正常保留；root 层同名孤儿文件已不存在；`07_PENDING_TODO` 现已不再保留 `T-036`。
- 链接: `docs/07_PENDING_TODO.md`, `docs/changes/MOD-20260606-10-repo-and-market-data-structure-governance-plan.md`, `docs/contracts/storage.md`

## 2026-06-08 三线收口 | Codex
- Task ID: `MOD-20260606-10-repo-and-market-data-structure-governance-plan`
- CAP: `CAP-DOCS-GOVERNANCE`, `CAP-NAS-OPS`, `CAP-SELECTION-RESEARCH`
- 结论: 已把当前用户最关心的三条线收口。第一，云端线已定性为“NAS 正式线上 + old cloud 兼容应急”，并把 Windows crawler 默认 ingest 目标、高曝光运维文档、旧 cloud 脚本说明统一降权。第二，report 线已补出单点边界文档，正式研究真相、人读结论、仓外 artifacts、运行态副产物四层已明确。第三，删库后的现场和文档已重新对齐：repo 内三类兼容库当前默认不存在，`market-data` root 旧入口已删除，正式库实体继续稳定落在 `live/` 与 `research/current/`。
- 风险: 当前已不再是“默认路径走错”的风险；剩余只是低风险残留，例如 root 层孤儿 `market_data.db-wal / market_data.db-shm`，以及 report builder 家族后续若要继续整理时的物理分层问题。
- 验证: 已确认 `/Users/dong/Desktop/AIGC/market-data/{market_data.db,user_data.db,atomic_facts,selection,market_heat}` 当前不存在；`/Users/dong/Desktop/AIGC/market-data/live/{market_data.db,user_data.db}` 与 `/Users/dong/Desktop/AIGC/market-data/research/current/{atomic_facts,selection,market_heat}` 正常存在；市场热点删除旧入口后的缓存路径兼容修复已通过 `pytest backend/tests/test_market_heat_forecast.py -q`。
- 链接: `docs/ops/report-and-artifact-boundary.md`, `docs/05_LLM_KEY_SECURITY.md`, `docs/04_OPS_AND_DEV.md`, `docs/contracts/storage.md`, `/Users/dong/Desktop/AIGC/market-data/README.md`

## 2026-06-07 结构治理-1 | Codex
- Task ID: `MOD-20260606-10-repo-and-market-data-structure-governance-plan`
- CAP: `CAP-DOCS-GOVERNANCE`, `CAP-SELECTION-RESEARCH`
- 结论: 已继续把三块高价值治理落地。第一，repo 内三类兼容库角色已固定：`data/market_data.db`、`data/user_data.db`、`data/selection/selection_research.db` 统一降级为兼容副本，并通过 `data/README.md` / `data/selection/README.md` 写死边界。第二，外置 `market-data` 已完成最终物理搬迁：正式库实体已落到 `live/` 与 `research/current/`，root 旧路径改为兼容软链，`cache/` 与 `artifacts/market_heat/models` 仍保留结构别名。第三，`watchlist snapshot / cycle return` 之外，又补了一批活跃研究脚本默认跟随新正式根。第四，高曝光文档和旧 flat-data 兼容脚本都补上了“不是当前默认正式入口”的提醒，盘点脚本也新增了 symlink 与 runtime residue 清单导出。
- 风险: 当前最值得继续治理的，不再是默认入口解析，而是仍可能默认写 repo fallback 的研究脚本尾项，以及旧 `cloud / repo-data` 兼容链是否继续保留。
- 验证: 已确认 `/Users/dong/Desktop/AIGC/market-data/live/{market_data.db,user_data.db}`、`/Users/dong/Desktop/AIGC/market-data/research/current/{atomic_facts,selection,market_heat}` 当前是实体对象；`/Users/dong/Desktop/AIGC/market-data/{market_data.db,user_data.db,atomic_facts,selection,market_heat}` 当前已改为兼容软链；`ops/bench/export_market_data_inventory.sh` 已新增 symlink / wal-shm 导出。
- 链接: `data/README.md`, `data/selection/README.md`, `/Users/dong/Desktop/AIGC/market-data/README.md`, `/Users/dong/Desktop/AIGC/market-data/live/README.md`, `/Users/dong/Desktop/AIGC/market-data/research/current/README.md`, `ops/bench/export_market_data_inventory.sh`

## 2026-06-06 续接-3 | Codex
- Task ID: `MOD-20260606-10-repo-and-market-data-structure-governance-plan`
- CAP: `CAP-DOCS-GOVERNANCE`, `CAP-SELECTION-RESEARCH`
- 结论: 已继续按主卡完成两块收口：一是把最后 3 个 active residual fallback 清掉，分别是 `backend/scripts/run_postclose_l2_daily.py` 的本地 / cloud 默认路径解析、`ops/legacy/start_local_backend_with_atomic.sh` 的 legacy 启动默认值，以及 `backend/app/core/config.py` 的默认 resolver；二是通过子 Agent 把 `docs/archive/changes/MOD-20260606-02-project-governance-master-plan.md` 恢复成纯 archive 内容，使 `docs/archive/changes` 这组不再混入额外正文改动。
- 风险: 当前“默认入口 fallback”已不是主问题；下一步真正要决定的是 repo 内 `data/market_data.db`、`data/user_data.db`、`data/selection/selection_research.db` 的最终保留语义，以及 `report builder / watchlist snapshot / cycle return` 这类研究脚本族是否仍会默认写 repo fallback。
- 验证: `python3 -m py_compile backend/app/core/config.py backend/scripts/run_postclose_l2_daily.py` 通过；`bash -n ops/legacy/start_local_backend_with_atomic.sh` 通过；搜索 `file:data/market_data.db`、`DEFAULT_REPO_DATA_DIR`、`ATOMIC_REPO_DEFAULT` 已不再命中；archive 卡 `MOD-20260606-02` 中的 `11.5` 已移除。
- 链接: `backend/app/core/config.py`, `backend/scripts/run_postclose_l2_daily.py`, `ops/legacy/start_local_backend_with_atomic.sh`, `docs/archive/changes/MOD-20260606-02-project-governance-master-plan.md`, `docs/changes/MOD-20260606-10-repo-and-market-data-structure-governance-plan.md`

## 2026-06-06 续接-2 | Codex
- Task ID: `MOD-20260606-10-repo-and-market-data-structure-governance-plan`
- CAP: `CAP-DOCS-GOVERNANCE`, `CAP-SELECTION-RESEARCH`
- 结论: 已继续按主卡推进到“少数 residual fallback 收口”这一步。本轮完成两类动作：一是修掉 3 个活跃旧路径残留，分别是 `run_daily_new_framework.py` 中的 `ops/nas/nas_run_phase_b_release.sh` 调用、`run_postclose_l2_daily.py` 中的 `ops/windows/win_prepare_l2_day.bat` / `ops/windows/win_run_l2_shard.bat` 默认路径，以及 `AI_HANDOFF_LOG` 自身的旧入口描述；二是通过子 Agent 收紧了 `intraday_evolution_lab.py`、`start_local_research_station.sh`、`run_model_feature_store_batch.sh` 的默认 repo fallback 行为。
- 风险: 当前 residual fallback 已缩到 3 个重点对象：`backend/scripts/run_postclose_l2_daily.py` 的旧 postclose/cloud 兼容读取、`ops/legacy/start_local_backend_with_atomic.sh`、`backend/app/core/config.py` 的最终 fallback。它们都比本轮已处理的入口更敏感，不继续在这一步扩大改动面。
- 验证: `python3 -m py_compile backend/app/services/intraday_evolution_lab.py backend/scripts/run_daily_new_framework.py backend/scripts/run_postclose_l2_daily.py` 通过；`bash -n ops/start_local_research_station.sh ops/run_model_feature_store_batch.sh` 通过；对活跃面执行旧路径搜索后，未再命中 `ops/nas_run_phase_b_release.sh`、`ops/win_prepare_l2_day.bat`、`ops/win_run_l2_shard.bat`、`ops/nas_list_research_releases.sh`、`ops/nas_check_crawler_status.sh`、`ops/run_postclose_l2.sh` 这批已修对象。
- 链接: `backend/app/services/intraday_evolution_lab.py`, `backend/scripts/run_daily_new_framework.py`, `backend/scripts/run_postclose_l2_daily.py`, `ops/start_local_research_station.sh`, `ops/run_model_feature_store_batch.sh`, `docs/changes/MOD-20260606-10-repo-and-market-data-structure-governance-plan.md`

## 2026-06-06 续接 | Codex
- Task ID: `MOD-20260606-10-repo-and-market-data-structure-governance-plan`
- CAP: `CAP-DOCS-GOVERNANCE`, `CAP-SELECTION-RESEARCH`
- 结论: 已按用户要求以“总控 + 子 Agent”方式接手 repo / 文档 / 数据结构治理线。复核结论是：前序方向正确，运行真相和第一批低风险结构治理已完成；当前不应继续扩大搬迁面，先要把现有 `git status` 中的结构迁移形成可审计闭环。已把续接点评和下一轮 P0-P3 计划写回 `MOD-20260606-10`，把 `MOD-20260606-11` 补成最新接手交接文档，并从 `07_PENDING_TODO` 移除 `T-033`、`T-035` 两个已完成项。
- 新增: 已创建 `/Users/dong/Desktop/AIGC/market-data/README.md`，作为外置数据根的单点说明入口，明确正式库、非正式主库对象、目标结构和操作红线。
- 风险: repo fallback 仍未最终收口；当前少数仍需重点处理的入口包括 `intraday_evolution_lab.py`、`run_postclose_l2_daily.py`、`start_local_research_station.sh`、`run_model_feature_store_batch.sh`、`ops/legacy/start_local_backend_with_atomic.sh` 和 `backend/app/core/config.py` 的最终 fallback。
- 验证: 本次只改文档和数据根 README，未迁移数据库，未改运行代码；已执行只读盘点并确认 `docs/changes` 顶层为 6 个文件、`backend/scripts` 顶层为 185 个文件、外置 `market-data` 当前仍是兼容正式目录结构。
- 链接: `docs/changes/MOD-20260606-10-repo-and-market-data-structure-governance-plan.md`, `docs/changes/MOD-20260606-11-repo-and-market-data-governance-handoff.md`, `docs/07_PENDING_TODO.md`, `/Users/dong/Desktop/AIGC/market-data/README.md`

## 2026-06-06 23:35 | Codex
- Task ID: `MOD-20260606-10-repo-and-market-data-structure-governance-plan`
- CAP: `CAP-DOCS-GOVERNANCE`, `CAP-SELECTION-RESEARCH`
- 结论: 已继续按治理卡完成第二批真正落到目录结构上的收口，并同步把“已完成”写回主文档。当前新增完成四件事：一是 `backend/scripts` 再做一批低风险物理分层，已把 `l2_wait_then_backfill.py`、`l2_repair_failed_samples.py`、`l2_repair_missing_daily_symbols.py`、`l2_review_empty_samples.py` 下沉到 `backend/scripts/maintenance/l2_repair/`，把 `backfill_history.py`、`backfill_history_1m.py`、`backfill_local_history.py`、`backfill_local_symbol_from_windows_raw.py`、`build_atomic_trade_from_history.py` 下沉到 `backend/scripts/legacy/history_repair/`；二是修正了这批脚本迁目录后仓库根路径解析会跑错的问题；三是 `build_cycle_return_snapshot.py`、`build_cycle_return_sector_report.py` 已从默认读取 repo `data/selection/selection_research.db` 改成默认跟随 `RESEARCH_CURRENT_ROOT/selection/selection_research.db`，并把对应研究 README 口径回写；四是继续把结构治理现状回写到 `MOD-20260606-10`、`07_PENDING_TODO`、`backend-script-families-boundary`、`market-data-reclassification-plan`、`contracts/storage`。
- 验证: `python3 -m py_compile` 已覆盖 `build_cycle_return_*` 与第二批新迁的 9 个脚本并通过；`bash -n sync_to_windows.sh ops/nas/*.sh ops/legacy/*.sh` 通过；当前 `backend/scripts` 顶层文件数已进一步降到约 `185`。
- 风险: repo 内 `data/market_data.db`、`data/user_data.db`、`data/selection/selection_research.db` 的最终保留策略还没做完；`market-data` 下 `cache / latest 元数据 / models / wal-shm / atomic_facts/shadow` 这批对象也还没进入物理治理；`cycle return / watchlist snapshot / report builder` 这类仍有活跃研究入口引用的脚本族还没进入下一批迁移。
- 链接: `docs/changes/MOD-20260606-10-repo-and-market-data-structure-governance-plan.md`, `docs/07_PENDING_TODO.md`, `docs/ops/backend-script-families-boundary.md`, `docs/ops/market-data-reclassification-plan.md`, `docs/contracts/storage.md`

## 2026-06-06 22:20 | Codex
- Task ID: `MOD-20260606-10-repo-and-market-data-structure-governance-plan`
- CAP: `CAP-DOCS-GOVERNANCE`, `CAP-SELECTION-RESEARCH`
- 结论: 已继续按治理卡推进 `backend/scripts` 的第一批最小物理分层，并完成实际迁移与回写。当前已下沉：`benchmark_atomic_*` -> `backend/scripts/maintenance/bench/`，`audit_l2_order_event_codes.py` -> `backend/scripts/maintenance/audit/`，`build_local_research_snapshot.py` -> `backend/scripts/legacy/compat/`，`merge_historical_db.py` 与 `merge_historical_db_local.py` -> `backend/scripts/legacy/history_merge/`。同时已把 `ops/legacy/sync_windows_research_snapshot.sh`、`AI_QUICK_START`、`mac-local-research`、`atomic-script-families-boundary`、`backend-script-families-boundary` 等活跃入口回写到新路径。`backend/scripts` 顶层文件数已从约 `202` 降到 `194`。
- 验证: `python3 -m py_compile` 已覆盖上述 8 个新迁脚本并通过；`bash -n ops/legacy/sync_windows_research_snapshot.sh` 通过；活跃文档扫描后，除 `AI_HANDOFF_LOG` 历史日志保留旧路径外，已无非 archive 活跃引用继续指向这批旧路径。
- 风险: 这轮仍未处理 repo 内 `data/market_data.db`、`data/selection/selection_research.db` 的最终边界；`cycle return / watchlist snapshot / report builder` 这类仍有活跃研究入口引用的脚本，也还没进入下一批迁移。
- 链接: `docs/changes/MOD-20260606-10-repo-and-market-data-structure-governance-plan.md`, `docs/ops/backend-script-families-boundary.md`, `ops/legacy/sync_windows_research_snapshot.sh`

## 2026-06-06 21:35 | Codex
- Task ID: `MOD-20260606-10-repo-and-market-data-structure-governance-plan`
- CAP: `CAP-DOCS-GOVERNANCE`, `CAP-NAS-OPS`, `CAP-SELECTION-RESEARCH`
- 结论: 已继续按当前治理卡推进“仓库与 market-data 结构治理”并完成第一批真正会影响后续执行的收口：一是把 `ops/nas/*`、`ops/legacy/*` 迁目录后的脚本根路径、互调路径和默认主机口径修正到当前结构，避免 NAS 发布链和旧兼容链因为迁目录直接跑错；二是把 `04_OPS_AND_DEV / AI_QUICK_START / nas-research-release-runbook / nas-crawler-cutover-runbook / mac-local-research / windows-data-station / postclose-l2-runbook / atomic-script-families-boundary` 等高曝光文档回写到 `ops/nas/*`、`ops/legacy/*`、`ops/windows/*` 新路径；三是继续对外置 `market-data` 做低风险物理整理，把 `legacy_market_merge_report_20260425.json` 与 `model_market_index_daily_validation_20260523.json` 下沉到 `artifacts/`，并清掉根目录 / `atomic_facts` / `market_heat` 下的 `.DS_Store`。当前还没开始的是 repo 内 fallback 库最终边界和 `backend/scripts` 的物理分层。
- 验证: `bash -n sync_to_windows.sh ops/nas/*.sh ops/legacy/*.sh` 通过；`python3 -m py_compile backend/scripts/run_daily_new_framework.py` 通过；`bash ops/nas/check_nas_research_release.sh /Users/dong/Desktop/AIGC/market-data` 通过，确认当前本地正式库与 `market_heat/latest.json` 元数据仍一致。
- 风险: `backend/scripts` 仍有大量研究/专题/历史脚本混在顶层，这轮只完成认知与入口收口，没有开始物理迁移；`market-data` 里也仍保留 `market_heat/cache`、`market_heat/models`、`*_latest.json`、`atomic_facts/shadow`、`*.db-wal/*.db-shm` 这些下一批对象。
- 链接: `docs/changes/MOD-20260606-10-repo-and-market-data-structure-governance-plan.md`, `docs/07_PENDING_TODO.md`, `docs/ops/market-data-reclassification-plan.md`, `docs/04_OPS_AND_DEV.md`

## 2026-06-06 16:50 | Codex
- Task ID: `MOD-20260606-02-project-governance-master-plan`
- CAP: `CAP-DOCS-GOVERNANCE`, `CAP-NAS-OPS`, `CAP-SELECTION-RESEARCH`
- 结论: 这轮项目综合治理已经按总控卡完成到 `Phase 7` 收口。当前已完成三类闭环：一是仓库资产盘点与低风险文件治理，仓库体积约从 `7.8G` 压到 `6.2G`，并把根目录历史兼容库下沉到 `data/legacy/`；二是高曝光真相文档统一到 `Mac 开发控制台 / Windows 数据主站 / NAS 在线运行与 research/current 发布节点` 口径；三是 `Mac -> NAS` 控制面、Git、`research/current` 发布链与线上 API 当前都已有实证。当前 `research/current` 版本为 `nas_daily_new_20260605`，archive 已保留 `20260604 / 20260605` 两个回滚点。
- 验证: `pytest -q backend/tests/test_market_data_path_config.py backend/tests/test_research_script_path_defaults.py backend/tests/test_nas_release_scripts.py` 通过，共 `14 passed`；`bash ops/nas/nas_list_research_releases.sh` 已确认 current/staging/archive；`bash ops/nas/nas_check_crawler_status.sh` 已确认 `backend/frontend/crawler` 容器在线且 crawler 日志持续推送；`curl -fsS --max-time 10 http://dxp4800pro:8080/api/health` 与 `curl -i --max-time 20 http://dxp4800pro:8080/api/selection/health` 均返回 `200`。
- 风险: 当前剩余的大文件不再属于“误删候选”，而是显式保留对象：`data/market_data.db`、`data/selection/selection_research.db`、`data/legacy/root_market_data_history.db` 与最近两天 `.run/daily_new_framework/*processed*`。后续若继续做，应转到 `T-034` 那条“正式别名 / shadow sample 迁移规划”，不是继续把这轮治理重复打开。
- 链接: `docs/changes/MOD-20260606-02-project-governance-master-plan.md`, `docs/changes/MOD-20260606-09-phase7-governance-closeout-audit.md`, `docs/07_PENDING_TODO.md`, `docs/ops/mac-nas-collaboration.md`

## 2026-06-06 02:05 | Codex
- Task ID: `MOD-20260606-02-project-governance-master-plan`
- CAP: `CAP-NAS-OPS`, `CAP-DOCS-GOVERNANCE`
- 结论: 已按治理母卡开始执行 `Phase 1`，先复核 `NAS / research-current` 与三端真相文档线。当前基于代码、脚本和测试可确认：`LIVE_DATA_ROOT + RESEARCH_CURRENT_ROOT` 双口径、`--sync-nas` 日跑发布、`nas-research-release-runbook` 的 `staging -> current -> archive` 链路，以及 `docker-compose.nas-full.yml` 的运行时路径注入都已形成闭环；相关测试 `backend/tests/test_market_data_path_config.py`、`backend/tests/test_research_script_path_defaults.py`、`backend/tests/test_nas_release_scripts.py` 已全部通过。当前剩余工作不再是功能补齐，而是把高曝光入口文档和 pending 真相彻底对齐，再独立提交这条线。
- 验证: `pytest -q backend/tests/test_market_data_path_config.py backend/tests/test_research_script_path_defaults.py backend/tests/test_nas_release_scripts.py` 通过，共 `14 passed`。
- 风险: `T-035` 一类文档项里仍有旧说法，例如“NAS 上尚无 git”；这类错真相若不先修，会影响后续全仓治理判断。
- 链接: `backend/app/core/config.py`, `backend/scripts/run_daily_new_framework.py`, `deploy/docker-compose.nas-full.yml`, `docs/ops/nas-research-release-runbook.md`, `docs/changes/MOD-20260606-02-project-governance-master-plan.md`

## 2026-06-06 01:44 | Codex
- Task ID: `MOD-20260606-01-selection-probe-model-research-closure`
- CAP: `CAP-SELECTION-RESEARCH`, `CAP-MODEL-RESEARCH`
- 结论: 已完成一轮“按业务目标而不是按文件名”的收口复核，并把过时口径回写到核心文档。当前确认三条线都已达成原业务目标：`星火双轨持仓跟踪` 已形成 `exit_watchlist + dual_exit_tracks + 选股页展示` 的完整链路；`试盘识别` 已同时接入每日候选源和模型训练页独立研究页；`docs/model-research/*` 已形成模型研究总入口、方向索引、指标字典与 artifact 治理框架。本轮另修复了 `SelectionDecisionPanel` 的 hooks 顺序错误，解除选股页 `Rendered more hooks than during the previous render` 前端报错。
- 验证: 本地前后端已在 `3001 / 8001` 运行；`pytest -q backend/tests/test_selection_daily_workbench.py backend/tests/test_spark_opportunity_exit_paths.py` 通过；另确认 `ModelTrainingPage -> 试盘事件研究页` 入口、`selection_daily_workbench` 活跃来源和 `SelectionDecisionPanel` 双轨展示代码均已到位。
- 风险: 本轮不混入 `NAS / research-current` 路径迁移与发布链改动；那条线虽已有较完整实现，但仍作为后续独立治理主题处理。仓库里仍有大量未提交脏改，提交时必须按 `星火双轨`、`probe 研究资料包`、`model-research 文档包` 分组切开。
- 链接: `docs/selection/daily_candidate_source_contract.md`, `docs/selection/model_development_sop.md`, `docs/model-research/research-directions-index.md`, `src/components/selection/SelectionDecisionPanel.tsx`, `backend/app/services/selection_daily_workbench.py`

## 2026-06-05 00:55 | Codex
- Task ID: `MOD-20260605-02-spark-pattern-research-ui-closure`
- CAP: `CAP-SELECTION-RESEARCH`
- 结论: 已完成 `spark-ui` worktree 收口确认。这条线的实际产物不是训练模型，而是选股研究工作台里的“研究入口 + 星火形态研究页”前端。当前已确认：`/selection-research` 顶部 `研究入口` 下拉菜单可展开 3 个独立研究页入口；`/selection-spark-pattern-research/1-0` 可正常打开，`Top1 / Top3` 切换、按股票完整图卡、信号日 / 次日买入日 / 22 日硬退出日标记均可见。对应静态 payload 与 `backend/scripts/export_spark_pattern_research_payloads.py` 也已纳入正式保留范围。
- 验证: `npm run build` 通过；浏览器实开验收通过 `/selection-research` 与 `/selection-spark-pattern-research/1-0`。
- 风险: 这次收口只代表研究页前端完成，不代表新增训练链路或模型结论更新。`selection-spark-pattern-prototype` 仍保留为历史样式参考页，不是主入口。
- 链接: `docs/selection/spark_pattern_research_ui_closure_2026-06-05.md`, `src/components/selection/SelectionResearchPage.tsx`, `src/components/selection/SparkPatternResearchPage.tsx`, `backend/scripts/export_spark_pattern_research_payloads.py`

## 2026-06-04 11:50 | Codex
- Task ID: `MOD-20260604-01-nas-b1-bootstrap-current-switch`
- CAP: `CAP-NAS-OPS`, `CAP-DEPLOYMENT`
- 结论: 已按“先跑通迁移、后补缺失日期”的目标完成 `B1` 的现场收口。由于当前从 Mac 向 NAS 直传完整正式库接近 `79GB`，而现场 SSH 长连接间歇超时，本轮没有强行先做大上传，而是直接复用 NAS 现有 flat 研究库，在 NAS 本机引导出 `research/current`：`atomic_facts / selection / market_heat` 均以符号链接方式挂到 current，下发 `.release_name=nas_release_bootstrap_from_flat_20260604`，并重写 `market_heat/latest.json` 的 `meta.atomic_db` 指针。随后已执行 `docker compose --env-file .env.nas-full -f deploy/docker-compose.nas-full.yml up -d --build backend frontend`，确认线上前后端已经切到新版 compose 和 `research/current` 新口径。当前已验证通过：`/api/health`、`/api/selection/health`、`/api/selection/daily-candidates`、`/api/market_heat/latest`、`/api/trend-research/ideas`、`/selection-research`。因此“迁移结构已跑通”这一目标已达成。
- 风险: 当前 `research/current` 仍是基于 NAS 旧 flat 研究库引导出来的 bootstrap 版本，不是从本地最新正式库完整上传得到的 staged release；其研究数据日期大致停在 `2026-05-27`，后续仍需补一轮“缺失日期同步到 NAS”。这不阻塞下一阶段 `A1`（NAS 接管盘中 crawler），但仍是后续必须收口的数据更新事项。
- 链接: `docs/ops/nas-research-release-runbook.md`, `docs/ops/nas-migration-execution-plan.md`

## 2026-06-03 15:42 | Codex
- Task ID: `MOD-20260603-01-mac-nas-collaboration-and-domain-plan`
- CAP: `CAP-NAS-OPS`, `CAP-DEPLOYMENT`
- 结论: 已完成一轮 `Mac -> NAS` 长期协作面验证，并把结果回写到核心文档。当前已验证通过：Tailscale 节点 `dxp4800pro / 100.119.0.126` 在线；`ssh zhangdong@dxp4800pro` 可直连；`http://dxp4800pro:8080` 与 `https://100.119.0.126:9443` 可访问；NAS 上可执行 `docker compose ps`、`python3`、`sqlite3`，可直接做远程查库和容器管理。文件提交层面，`tar | ssh` 与 `ssh 'cat > file'` 已验证可用；`scp / sftp / rsync` 绝对路径上传当前不稳定，不再写成默认发布路径。另确认 NAS 上尚无 `git`，因此“自定义 Git 仓库”还不是已就绪能力。已新增 `docs/ops/mac-nas-collaboration.md`，并同步更新 `README / 04_OPS_AND_DEV / AI_QUICK_START`。
- 风险: 当前公网自定义域名仍未落地；如果后续要长期给外部用户访问，建议在服务链稳定后再接 `Cloudflare Tunnel + 自定义域名`，不要把 Tailscale 本身当最终公网品牌入口。
- 链接: `docs/ops/mac-nas-collaboration.md`, `README.md`, `docs/04_OPS_AND_DEV.md`, `docs/AI_QUICK_START.md`

## 2026-06-03 21:42 | Codex
- Task ID: `MOD-20260603-02-gitea-nas-git-link`
- CAP: `CAP-NAS-OPS`, `CAP-GIT`
- 结论: 已完成 `Mac -> NAS Gitea` Git 链路接通。当前实际 owner 是 `zhangdong`，不是先前假设的 `dong`；已把本机现有 `id_ed25519.pub` 注册到 Gitea 用户 `zhangdong`，并验证 `ssh -p 2222 -T git@192.168.3.43` 与 `ssh -p 2222 -T git@dxp4800pro` 均返回认证成功。已为本地仓库添加 `nas` remote 并收口为统一入口 `nas-git:zhangdong/market-live-terminal.git`，同时保留 `nas-local` 作为局域网备用。`main` 已成功首次推送到 NAS Gitea。另已确认 `scp` 问题的真实原因是 macOS 15+ 默认走 SFTP 子系统，当前对这台 NAS 使用 `scp -O` 已实测可用。后续代码推送默认优先 `git push nas main`。
- 风险: 这轮只打通了私网 / Tailscale Git 链路，公网自定义域名和公网 Git 服务入口仍未配置；如需外部任何网络直接访问项目网页，仍应走 `Cloudflare Tunnel + 自定义域名`。
- 链接: `docs/ops/mac-nas-collaboration.md`, `README.md`, `docs/04_OPS_AND_DEV.md`, `docs/AI_QUICK_START.md`

## 2026-05-28 01:45 | Codex
- Task ID: `MOD-20260527-01-selection-v522-spark-priority-and-may-exit-backfill`
- CAP: `CAP-SELECTION-RESEARCH`
- 结论: 已完成 `v5.2.2` 选股工作台收口。`每日综合候选` 现按“动作优先级 -> 来源优先级 -> 综合分”排序，星火模型排在策略前；`stable_capital_callback` 单日上限从 `10` 收紧到 `3`；右侧 `持仓跟踪 / 次日卖出` 已补名称拉取；并新增 `backend/scripts/backfill_spark_exit_watchlist_month.py`，已将 `2026-05` 星火持仓/卖出回补到 15 个实际交易日。额外查明 `2026-05-25` 之前不是前端漏显，而是库里当时真被写成 `spark=0`；按当前正式数据重跑后，这一天已修正为 `spark=3`。
- 风险: 当前仓库还存在并行开发中的 Spark pattern prototype 改动与未跟踪 `docs/portfolio-ops/` 目录，本次提交不混入这些内容。
- 链接: `backend/app/services/selection_candidate_store.py`, `backend/app/services/selection_daily_workbench.py`, `src/components/selection/SelectionResearchPage.tsx`, `backend/scripts/backfill_spark_exit_watchlist_month.py`, `docs/changes/MOD-20260527-01-selection-v522-spark-priority-and-may-exit-backfill.md`

## 2026-05-26 22:35 | Codex
- Task ID: `MOD-20260526-04-daily-postclose-index-and-heat-mainline`
- CAP: `CAP-WIN-PIPELINE`, `CAP-MARKET-HEAT`, `CAP-SELECTION-RESEARCH`
- 结论: 已把每日正式跑数主链升级为“指数 + 热点 + 页面缓存 + 选股输出”一体化日跑，并完成 `2026-05-26` 真实验证通过。当前 `ops/run_daily_new_framework.sh --json` 会在 Windows 侧并行刷新市场环境指数与 atomic，随后并行跑选股基础刷新与热点重算，再构建模型特征、同步回 Mac、生成选股工作台候选。真实验收结果：`2026-05-26` 当天市场环境指数 5/5 到位，热点结果 633 条到位，热点页面缓存覆盖到 `2026-05-26`，选股工作台三类来源均有 success 记录；此前 `index_daily_missing` 与 `heat_feature_missing` 两个降级告警已消失。
- 风险: 当前 Windows 正式链仍在使用带 `smoke` 字样的物理库名；另外自动检测仍会把 `2025-12` 那批历史缺口记为 `historical_missing_dates`，但不会自动补跑。它们属于后续治理项，不影响当前日常主链成功。
- 链接: `backend/scripts/run_daily_new_framework.py`, `backend/scripts/refresh_market_heat_cache.py`, `backend/scripts/sync_model_market_index_daily.py`, `docs/ops/postclose-l2-runbook.md`, `docs/04_OPS_AND_DEV.md`, `.run/daily_new_framework/20260526/report.json`

## 2026-05-26 02:40 | Codex
- Task ID: `MOD-20260526-03-homepage-postclose-previous-trade-day-fallback`
- CAP: `CAP-MKT-TIME`, `CAP-REALTIME-FLOW`
- 结论: 已补回首页分时默认日期链路的缺口。此前 `MarketClock` 在交易日盘后会默认把首页主力动态请求打到“今天”，但当某只股票当天分时尚未入库时，`/api/realtime/dashboard` 不会自动回退到上一交易日，导致首次打开或刷新首页时直接空白。当前已改为：用户未手动选日期时，盘后先尝试今天；如果今天没有可展示分时，再自动回退上一交易日，并把 `default_display_scope/default_display_date/view_mode` 一并回写给前端。
- 链接: `backend/app/routers/market.py`, `backend/tests/test_realtime_dashboard_router.py`, `docs/contracts/market-realtime.md`

## 2026-05-26 02:05 | Codex
- Task ID: `MOD-20260526-02-retail-sentiment-page-no-auto-crawl`
- CAP: `CAP-RETAIL-SENTIMENT`
- 结论: 已收掉首页 `散户一致性观察` 的自动补抓触发。此前页面打开后会自动调用 `POST /api/sentiment/crawl/{symbol}`，这条链路会同步执行股吧翻页、详情抓取、回复抓取与落库，导致本地后端出现“健康检查正常，但 history / sentiment 业务接口持续转圈或超时”的卡死现象。当前已改为页面默认只读本地库缓存，补抓仅保留手动按钮触发，并已将该红线回写核心文档。
- 链接: `src/components/sentiment/SentimentDashboard.tsx`, `docs/domain/retail-sentiment.md`, `docs/04_OPS_AND_DEV.md`

## 2026-05-26 01:45 | Codex
- Task ID: `MOD-20260526-01-local-research-backend-singleton-guard`
- CAP: `CAP-REALTIME-FLOW`, `CAP-SELECTION-RESEARCH`
- 结论: 已定位并修复 Mac 本地研究站一次真实运行态事故：同仓库下同时存在多个 `backend.app.main` 高 CPU 进程，导致 `/api/health` 仍能响应，但 `history/multiframe`、`sentiment/*` 等业务接口超时，前端表现为历史多维 / 散户一致性观察长期转圈或动态模块加载失败。当前已为 `ops/start_local_research_station.sh` 增加重复实例保护，重复执行会先清理旧实例再启动新实例；并已把症状、排查与恢复动作回写 `README`、`docs/ops/mac-local-research.md`、`docs/04_OPS_AND_DEV.md`、`docs/AI_QUICK_START.md`。
- 风险: 本轮只收口 Mac 本地研究站后端重复实例，不等于所有历史脚本族都具备单实例治理；后续仍需继续观察几天自然运行，确认不再复发。
- 链接: `ops/start_local_research_station.sh`, `docs/ops/mac-local-research.md`, `docs/04_OPS_AND_DEV.md`, `docs/AI_QUICK_START.md`, `README.md`

## 2026-05-24 23:45 | Codex
- Task ID: `MOD-20260524-13-governance-phase-summaries-and-active-wip-map`
- CAP: `CAP-REALTIME-FLOW`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`, `CAP-WIN-PIPELINE`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已删除 `notebooklm-sync/` 整个目录，并把外部知识库同步源正式退役；同时新增治理阶段摘要入口 `docs/changes/README_STAGE_SUMMARY.md`、阶段摘要文档 `MOD-20260524-13` 和九项 ACTIVE 盘点 `MOD-20260524-14`，把当前治理主线压成短入口。
- 验证: `npm run build` 通过；`rg` 仅在两份旧 history 文件里还看到 NotebookLM 退役语义残留，不再有 `notebooklm-sync/` 目录本体。
- 风险: `docs/changes` 与 `docs/selection` 仍保留大量历史过程文档，后续应继续按阶段摘要和主入口缩减，而不是恢复 NotebookLM 同步区。
- 链接: `docs/changes/README_STAGE_SUMMARY.md`, `docs/changes/MOD-20260524-13-governance-phase-summaries-and-active-wip-map.md`, `docs/changes/MOD-20260524-14-active-pending-nine-item-audit.md`, `docs/selection/selection_research_history_summary.md`

## 2026-05-24 23:05 | Codex
- Task ID: `MOD-20260520-04-code-governance-plan`
- CAP: `CAP-REALTIME-FLOW`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`
- 结论: 代码治理第一批已经收尾到可交接状态。`src/components/selection/SelectionDecisionPanel.tsx` 的局部 `MetricCard` 已统一到共享 `ResearchCard.Metric`；`src/components/dashboard/SentimentDashboard.tsx` 与 `src/components/dashboard/SentimentTrend.tsx` 已删除，情绪模块只保留 `src/components/sentiment/*` 作为 canonical；`backend/app/services/market.py` 里与旧趋势页有关的注释也已改成中性表述，避免继续指向已退役实现。
- 验证: `npm run build` 通过。
- 风险: 当前仓库仍有大量已完成的治理改动未提交，`docs/changes/MOD-20260520-04-code-governance-plan.md` 还需要继续按后续批次回写；下一步若继续做，应先按文档里的“代码治理前置条件”推进，不要跨主题拼单。
- 链接: `src/components/selection/SelectionDecisionPanel.tsx`, `src/components/dashboard/SentimentDashboard.tsx`, `src/components/dashboard/SentimentTrend.tsx`, `backend/app/services/market.py`, `docs/changes/MOD-20260520-04-code-governance-plan.md`

## 2026-05-24 22:35 | Codex
- Task ID: `MOD-20260520-04-code-governance-plan`
- CAP: `CAP-REALTIME-FLOW`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`
- 结论: 已完成情绪模块单轨收口。`src/components/dashboard/SentimentDashboard.tsx` 与 `src/components/dashboard/SentimentTrend.tsx` 已删除，`src/components/sentiment/SentimentDashboard.tsx` 成为唯一 canonical 情绪面板；`src/App.tsx` 仍只指向 `components/sentiment/SentimentDashboard`。本轮没有改情绪业务逻辑，只是清掉了旧双轨实现。
- 验证: `npm run build` 通过；仓库内已无对 `src/components/dashboard/SentimentDashboard` / `SentimentTrend` 的代码引用。
- 风险: 下一步若要继续收口，优先看情绪页内部是否还存在局部可抽共享壳，而不是再恢复旧 dashboard 文件。
- 链接: `src/components/sentiment/SentimentDashboard.tsx`, `src/components/dashboard/SentimentDashboard.tsx`, `src/components/dashboard/SentimentTrend.tsx`, `docs/changes/MOD-20260520-04-code-governance-plan.md`

## 2026-05-24 22:10 | Codex
- Task ID: `MOD-20260520-04-code-governance-plan`
- CAP: `CAP-REALTIME-FLOW`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`
- 结论: 已把代码治理前置包补完整，并开始第一批代码治理。文档层已把 `backend/market.db` / `backend/app/market_data.db` / `backend/app/db/market_data.db` 明确成 shadow/sample/排障对象；`docs/04_OPS_AND_DEV.md` 与 `docs/ops/atomic-script-families-boundary.md` 统一成 `run_daily_new_framework.sh` 才是正式盘后主链，`run_postclose_l2.sh` 仅保留旧盘后兼容语义。代码层已完成一处最小收口：`src/components/selection/SelectionDecisionPanel.tsx` 的局部 `MetricCard` 改用共享 `ResearchCard.Metric`，减少了一个局部重复壳。
- 验证: `npm run build` 通过。
- 风险: 旧 `src/components/dashboard/SentimentDashboard.tsx` / `SentimentTrend.tsx` 仍保留为 legacy 兼容实现，下一步应优先确认是否还需要继续收口它们的入口引用，而不是直接删文件。
- 链接: `docs/changes/MOD-20260520-04-code-governance-plan.md`, `docs/ops/atomic-script-families-boundary.md`, `src/components/selection/SelectionDecisionPanel.tsx`

## 2026-05-24 21:05 | Codex
- Task ID: `MOD-20260524-12-formal-alias-and-shadow-sample-migration-plan`
- CAP: `CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已把“正式别名与 shadow/sample 目录迁移”单独立成新治理卡，并把它挂进 `07_PENDING_TODO`。当前只做规划收口，不做物理迁移；Windows 正式主链的 `compact_smoke_*` / `model_feature_store_smoke_*` 以及后端 `shadow/sample` 对象，后续会按别名、目录、回写三步继续收紧。
- 风险: 这轮还没有改任何物理文件名，也没有迁移动作；只是把下一步的顺序固定下来。
- 链接: `docs/changes/MOD-20260524-12-formal-alias-and-shadow-sample-migration-plan.md`, `docs/07_PENDING_TODO.md`, `docs/changes/MOD-20260524-11-shadow-db-and-mainchain-physical-name-governance.md`

## 2026-05-24 20:45 | Codex
- Task ID: `MOD-20260524-11-shadow-db-and-mainchain-physical-name-governance`
- CAP: `CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已完成一轮 `backend shadow / sample db` 与主链物理名治理。`backend/market.db`、`backend/app/db/market_data.db`、`backend/app/market_data.db` 已被明确区分为空壳或样本对象，不再按正式运行库理解；同时把 `selection_research_windows.db`、`compact_smoke_*`、`model_feature_store_smoke_*` 明确为“正式语义已固定，但物理名仍保留历史痕迹”的主链对象。同步新增治理卡，后续若继续做，会优先考虑 shadow/sample 目录迁移规划和主链正式别名规划，而不是直接删库或先做代码治理。
- 风险: 这轮仍没有做物理迁移，也没有改运行脚本里的实际文件名；只是把“谁是正式角色、谁只是 shadow/sample”先写死在文档里。
- 链接: `docs/changes/MOD-20260524-11-shadow-db-and-mainchain-physical-name-governance.md`, `docs/changes/MOD-20260524-05-business-view-governance-execution-checklist.md`, `docs/changes/MOD-20260524-03-canonical-data-artifacts-manifest.md`, `docs/01_SYSTEM_ARCHITECTURE.md`, `docs/03_DATA_CONTRACTS.md`, `docs/contracts/storage.md`

## 2026-05-24 20:15 | Codex
- Task ID: `MOD-20260524-10-high-value-entry-and-storage-naming-alignment`
- CAP: `CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已完成一轮“高收益入口与存储命名收口”。当前已统一 `README / AI_QUICK_START / 04_OPS_AND_DEV` 的版本口径到 `v5.2.0`，并继续把 Mac 外置正式数据根目录 `/Users/dong/Desktop/AIGC/market-data` 与 repo 内 `data/` 的回退/兼容角色写清。同步把 `postclose-l2`、Windows 主站、`strategy-rework` 旧交接入口再降一级，避免后续 AI 又把旧兼容链或旧阶段材料当成当前默认入口。治理总框架和 `07_PENDING_TODO` 也已按这轮重评结果改成“先补最后一批高收益入口/命名收口，再决定是否进入代码治理”。
- 风险: 这轮仍然没有物理迁移任何数据库或历史产物，也没有给 `selection_research_windows.db / compact_smoke_* / model_feature_store_smoke_* / backend shadow db` 做真正命名调整；只是把默认认知先固定住。
- 链接: `docs/changes/MOD-20260524-10-high-value-entry-and-storage-naming-alignment.md`, `README.md`, `docs/AI_QUICK_START.md`, `docs/03_DATA_CONTRACTS.md`, `docs/contracts/storage.md`, `docs/ops/postclose-l2-runbook.md`, `docs/ops/windows-data-station.md`, `docs/strategy-rework/README.md`, `docs/strategy-rework/handoff-for-next-ai.md`, `docs/07_PENDING_TODO.md`

## 2026-05-24 19:40 | Codex
- Task ID: `MOD-20260524-09-snapshot-sync-local-compatibility-boundary-governance`
- CAP: `CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`
- 结论: 已完成 `snapshot / sync / local compatibility` 第一批边界治理。当前已明确：Mac 正式本地研究入口仍然是 `bootstrap_mac_full_processed_sync -> start_local_research_station -> start_local_research_frontend`；`ops/sync_windows_research_snapshot.sh`、`backend/scripts/build_local_research_snapshot.py`、`ops/start_local_backend_with_atomic.sh` 都只是兼容/验证/排查链，不属于正式默认入口。同步把 `build_local_research_snapshot.py` 的默认 atomic 改成优先跟随全局 resolver 和 `compact_current`，不再把旧 `full_reverse` 当默认底座。
- 风险: 本轮没有删除 `snapshot` 相关运行产物，也没有改 Windows->Mac 正式同步实现；只是把边界和默认口径收紧。旧快照链仍然能用，但应该只在明确兼容任务里手工调用。
- 链接: `docs/changes/MOD-20260524-09-snapshot-sync-local-compatibility-boundary-governance.md`, `backend/scripts/build_local_research_snapshot.py`, `docs/ops/mac-local-research.md`, `docs/ops/atomic-script-families-boundary.md`, `docs/AI_QUICK_START.md`

## 2026-05-24 19:10 | Codex
- Task ID: `MOD-20260524-08-selection-watchlist-and-doubler-boundary-governance`
- CAP: `CAP-SELECTION-RESEARCH`
- 结论: 已完成 `selection/watchlist/doubler` 第一批边界治理。当前已明确：`watchlist` 是“研究后持续盯盘”的独立产物链，正式入口是 `watchlist.json -> build_research_watchlist_snapshot.py -> snapshots/daily markdown`；`doubler` 是“案例库 / 样本研究”的独立产物链，正式入口是 `study.csv -> build_ytd_doubler_analysis.py -> manifest + top20 reports`。两者都不是当前 `/selection-research` 页面主流程，也不是每日选股工作台主链。同步把两个仍在用的维护脚本默认 atomic 改成跟随全局 resolver，不再私自兜底到旧 `full_reverse`。
- 风险: 这批没有去动 `top20/*.md`、每日盯盘日记、案例库正文；它们仍然会存在，但现在已经被明确成产物材料而不是系统入口。
- 链接: `docs/changes/MOD-20260524-08-selection-watchlist-and-doubler-boundary-governance.md`, `backend/scripts/build_research_watchlist_snapshot.py`, `backend/scripts/build_ytd_doubler_analysis.py`, `docs/selection/research_watchlist/README.md`, `docs/selection/doublers/2026-ytd/README.md`

## 2026-05-24 18:45 | Codex
- Task ID: `MOD-20260524-07-market-heat-module-boundary-governance`
- CAP: `CAP-MARKET-HEAT`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已完成 `market_heat` 模块第一批边界治理。当前已明确三层结构：页面正式消费链路是 `tradable_theme_map.db + fine_heat_snapshots_* + /api/market_heat/fine_dashboard`；`build_stock_sector_map.py / build_tradable_theme_map.py / build_fine_theme_heat_daily*.py` 属于研究/训练底座维护脚本；趋势 HTML、回测、案例和阶段卡都属于专题/历史材料。同步把 `docs/selection/market_heat/README.md`、`theme_taxonomy_management.md` 的入口口径收紧，并把 `build_stock_sector_map.py` 的 atomic 默认候选改成跟随全局 resolver，不再自己单独兜底到旧 `full_reverse`。
- 风险: `market_heat` 下仍有大量 `analyze_* / backtest_* / build_*trend*` 脚本没有继续分批治理；但这批大多不在正式页面链路里，当前优先级低于系统其他高混淆区域。
- 链接: `docs/changes/MOD-20260524-07-market-heat-module-boundary-governance.md`, `backend/scripts/build_stock_sector_map.py`, `docs/selection/market_heat/README.md`, `docs/selection/market_heat/theme_taxonomy_management.md`

## 2026-05-24 18:10 | Codex
- Task ID: `MOD-20260524-06-active-atomic-entry-classification-and-downgrade`
- CAP: `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已完成第三批“只修活跃入口，不全仓替换”的 atomic 治理。根据分类，本轮真正影响当前页面/工作台的剩余活跃命中只有 `backend/app/services/spark_opportunity_selector.py` 与 `backend/app/services/selection_strategy_v2.py`，两者默认 atomic 已从旧 `market_atomic_mainboard_full_reverse.db` 改到 `market_atomic_mainboard_compact_current.db`。同时把 `ops/start_local_backend_with_atomic.sh` 明确成兼容脚本：默认优先 compact，回落 legacy 时打印警告。另补了几份高风险研究/交接文档的顶部降级提示，避免后续 AI 把阶段快照误读成当前真相。
- 风险: 仓库里仍有大量研究脚本、专题页构建脚本和历史案例材料直接写死 `full_reverse`；当前是有意识地保留，不做全量替换。这些对象后续应按模块逐批处理，而不是做字符串级“大扫除”。
- 链接: `backend/app/services/spark_opportunity_selector.py`, `backend/app/services/selection_strategy_v2.py`, `ops/start_local_backend_with_atomic.sh`, `docs/changes/MOD-20260524-06-active-atomic-entry-classification-and-downgrade.md`

## 2026-05-24 17:05 | Codex
- Task ID: `MOD-20260524-05-business-view-governance-execution-checklist`
- CAP: `CAP-WIN-PIPELINE`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已完成第二批代码级入口治理，只改了 `ops/start_local_research_station.sh` 与 `backend/app/core/config.py`。当前默认 atomic 入口已切到 compact：`backend/app/core/config.py` 的 `DEFAULT_ATOMIC_MAINBOARD_DB_FILE` 改为 `market_atomic_mainboard_compact_current.db`，`candidate_atomic_db_paths()` 默认以 compact 为正式底座，同时保留 `full_reverse` 作为兼容回退；`ops/start_local_research_station.sh` 也改为默认注入 compact，只有在 compact 不存在且用户未显式指定 atomic 路径时，才自动回退到 legacy `full_reverse`。这一步没有改候选顺序、没有动 `DB_PATH` 隔离逻辑，也没有改其他业务脚本。
- 风险: 仓库里仍有不少研究脚本和专题脚本直接硬编码 `market_atomic_mainboard_full_reverse.db`；它们不走 `candidate_atomic_db_paths()`，所以还不算完成全仓治理。另一个现实限制是本机没有项目 pytest 环境，没法直接跑现成 pytest；本轮用静态编译 + Python 断言脚本 + 启动脚本双场景模拟完成了行为验证。
- 链接: `backend/app/core/config.py`, `ops/start_local_research_station.sh`, `backend/tests/test_atomic_history_multiframe_fallback.py`

## 2026-05-24 16:40 | Codex
- Task ID: `MOD-20260524-05-business-view-governance-execution-checklist`
- CAP: `CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`, `CAP-L2-HISTORY-FOUNDATION`
- 结论: 已完成第一批命名收口的文档回写。核心文档和直接入口文档已统一三条正式主链口径：`selection_research_main` 为每日选股研究主链，Windows 主写 `selection_research_windows.db`、Mac 主读 `selection_research.db`；`atomic_compact_main` 为盘后明细底座，不再把 `full_reverse` 讲成当前正式底座；`model_feature_store_main` 被明确为正式主链之一。运维入口同时改为：`ops/run_daily_new_framework.sh` 是当前盘后正式主链，`ops/legacy/run_postclose_l2.sh` 仅保留为兼容旧链路。
- 风险: 这一步只改文档口径，没有改脚本默认变量；像 `ops/start_local_research_station.sh`、`backend/app/core/config.py` 里仍保留 `full_reverse` 兼容路径，属于后续代码治理范围。
- 链接: `docs/01_SYSTEM_ARCHITECTURE.md`, `docs/03_DATA_CONTRACTS.md`, `docs/contracts/storage.md`, `docs/04_OPS_AND_DEV.md`, `docs/ops/mac-local-research.md`, `docs/ops/windows-data-station.md`, `docs/ops/postclose-l2-runbook.md`, `docs/AI_QUICK_START.md`

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

## 2026-05-26 00:35 | Codex
- Task ID: `MOD-20260526-01-postclose-auto-date-detection`
- CAP: `CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`
- 结论: 已把每日盘后正式入口收口为 `bash ops/run_daily_new_framework.sh --json`：默认自动检测 Windows 日包与 Mac 本地完整性，只补最新完整日之后的缺失日期；完成标准纳入 atomic、selection、model_feature_store 落表和选股工作台活跃模型/策略 success 记录。
- 验证: 自动模式 dry-run 与正式 no-op 验证通过；新增自动日期检测测试通过。
- 链接: `docs/ops/postclose-l2-runbook.md`, `docs/domain/data-pipeline.md`

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
- 验证: `npm run build`、`npm run check:version` 通过；浏览器验证 `localhost:5173/selection-research` 可看到 2026-04-24 申通快递的公司概况、决策解释和研究依据（当时是临时 Vite 验证端口，不是当前正式口径）。
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
