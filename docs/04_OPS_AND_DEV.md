# 04_OPS_AND_DEV（开发与运维入口）

> 目标：只回答“当前正式怎么运行、怎么发布、怎么验真、详细步骤去哪看”。
> 详细操作不再堆在本页；本页是运维/开发长记忆入口。
> 正式操作先从本页列出的 runbook 和少数正式脚本进入，不要默认从 `ops/` 目录里的历史 `bench / full_reverse / atomic` 族脚本开始。

## 1. 当前正式运行拓扑
- **Cloud**：轻量盯盘 / 手机应急查看
- **Windows**：原始包、正式跑数、实时 crawler、研究结果产出
- **Mac**：本地研究站、复盘、选股、文档与开发

## 2. 当前总原则
1. Windows 是数据主站；Mac 不直接跨网络读 Windows sqlite 主库。
2. Mac 保留一份同步后的正式库，作为本地研究主消费。
3. Cloud 不承载 `atomic_compact_main`、`selection_research_main`、`model_feature_store_main` 主链，只保留轻量盯盘链路。
4. `snapshot` 只作验证/应急，不是正式主方案。
5. 所有跨机器动作，先过连通性 gate，再执行同步/发布。
6. Windows -> Mac 正式同步只允许“局域网 HTTP relay / Cloud relay”，禁止再走 SSH/scp 直拉。
7. 实时盯盘 crawler 与每日盘后跑数是两条不同链路：前者是 `ZhangDataLiveCrawler`，后者当前正式主链是 `ops/run_daily_new_framework.sh`；`ops/run_postclose_l2.sh` 仅保留为旧盘后 L2 / cloud 同步兼容链路。

## 3. 先看哪个操作文档
| 场景 | 文档 |
|---|---|
| Mac 本地研究站启动 / 同步 / smoke | `docs/ops/mac-local-research.md` |
| Windows 数据主站 / crawler / 远控 | `docs/ops/windows-data-station.md` |
| Cloud 发版 / 冒烟 / 回滚 | `docs/ops/cloud-release.md` |
| 盘后正式主链 / 兼容旧链路 | `docs/ops/postclose-l2-runbook.md` |
| 标准开发流程 / 分支收口 / 文档收尾 | `docs/ops/development-workflow.md` |
| 历史脚本族边界 | `docs/ops/atomic-script-families-boundary.md` |

## 4. 正式脚本白名单
> 只有下列脚本属于当前正式默认入口；正式操作、runbook、交接说明默认只引用这些脚本。
> 未列入本表的 `ops/` / `scripts/` 脚本，默认都不是正式入口。

| 用途 | 脚本 |
|---|---|
| Mac 首次全量同步 | `ops/bootstrap_mac_full_processed_sync.sh` |
| Mac 本地后端启动 | `ops/start_local_research_station.sh` |
| Mac 本地前端启动 | `ops/start_local_research_frontend.sh` |
| 每日盘后正式主链 | `ops/run_daily_new_framework.sh` |
| 兼容旧盘后链路 | `ops/run_postclose_l2.sh` |
| 旧盘后链路状态查看 | `ops/check_postclose_l2_status.sh` |
| 新框架月批 / 阶段状态查看 | `ops/check_windows_new_framework_months_status.sh` |
| Windows 脚本同步 | `sync_to_windows.sh` |
| 云端发布 | `deploy_to_cloud.sh` |
| 基线检查 | `scripts/check_baseline.sh` |

> `bench / full_reverse / atomic backfill` 一类脚本族属于历史遗留、验证排查或二线运行工具；
> 它们可以在专项排查或人工授权场景下使用，但不是当前正式日常入口，也不应在默认 runbook 中替代上述白名单脚本。
> 具体边界见：`docs/ops/atomic-script-families-boundary.md`

> 实时盯盘 Windows 任务：
```bash
ssh laqiyuan@192.168.3.108 'cmd /c schtasks /Query /TN ZhangDataLiveCrawler /V /FO LIST'
```

> 当前盘后正式日常指令：
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
bash ops/run_daily_new_framework.sh --json
```

> 这条指令默认不需要指定日期：脚本会自动扫描 Windows `D:\MarketData` 日包，选择“最新完整日之后”Mac 尚未完整的日期补跑；完整性同时检查 atomic、selection、model_feature_store 落表，以及选股工作台活跃模型/策略是否已有 success 运行记录。

> 兼容旧盘后链路指令（仅历史 L2 / cloud 同步参考）：
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
bash ops/run_postclose_l2.sh
```

> 本地研究站后端不要手工 `python -m backend.app.main` 直跑；必须走 `ops/start_local_research_station.sh`，否则会绕过外置库路径注入，读错本地数据库。

## 5. 强制 gate
1. **跨机前**：先检查 Tailscale / SSH 连通。
2. **改 repo 后**：先在临时分支完成，再合回 `main`。
3. **提交前**：跑 `npm run check:baseline`。
4. **涉及长期事实变化**：同步回填 `README / 02 / 03 / 04 / AI_QUICK_START` 的受影响项。
5. **需求收尾**：同步更新 `AI_HANDOFF_LOG` 与 `07_PENDING_TODO`。

## 6. 当前工作目录与主线
- 主目录：`/Users/dong/Desktop/AIGC/market-live-terminal`
- 主线分支：`main`
- 当前工作版本：`v5.2.0`
- 当前项目真相入口：`docs/changes/MOD-20260421-01-project-current-state-and-doc-governance-normalization.md`
- 临时需求分支可使用 `codex/*`，但默认不把额外 worktree 作为主开发入口。

## 7. 相关规则
- 变更流程：`docs/06_CHANGE_MANAGEMENT.md`
- 文档治理：`docs/08_DOCS_GOVERNANCE.md`
- AI 协作：`docs/00_AI_HANDOFF_PROTOCOL.md`
- 开发流程标准：`docs/ops/development-workflow.md`
