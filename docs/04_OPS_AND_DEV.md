# 04_OPS_AND_DEV（开发与运维入口）

> 目标：只回答“当前正式怎么运行、怎么发布、怎么验真、详细步骤去哪看”。
> 详细操作不再堆在本页；本页是运维/开发长记忆入口。
> 正式操作先从本页列出的 runbook 和少数正式脚本进入，不要默认从 `ops/` 目录里的历史 `bench / full_reverse / atomic` 族脚本开始。

## 1. 当前正式运行拓扑
- **NAS**：当前线上前后端、`live/` 轻量盯盘、`research/current` 在线查询、发布/回滚节点
- **Windows**：原始包、正式跑数、实时 crawler、研究结果产出
- **Mac**：本地研究站、复盘、选股、文档与开发
- 正式数据根统一按 `live / research/current / cache / artifacts / incoming` 收口；repo 内 `data/` 只按兼容/fallback 理解

## 2. 当前总原则
1. Windows 是数据主站；Mac 不直接跨网络读 Windows sqlite 主库。
2. Mac 保留一份同步后的正式库，作为本地研究主消费。
3. NAS 不承担盘后重跑真相源，但承担当前线上轻量盯盘与 `research/current` 查询主链。
4. `snapshot` 只作验证/应急，不是正式主方案。
5. 所有跨机器动作，先过连通性 gate，再执行同步/发布。
6. Windows -> Mac 正式同步只允许“局域网 HTTP relay / Cloud relay”，禁止再走 SSH/scp 直拉。
7. 实时盯盘 crawler 与每日盘后跑数是两条不同链路：前者当前仍以 Windows `ZhangDataLiveCrawler` 为正式基线，NAS crawler 已跑通但仍在观察期；后者当前正式主链是 `ops/run_daily_new_framework.sh`；`ops/legacy/run_postclose_l2.sh` 仅保留为旧盘后 L2 / cloud 同步兼容链路。
8. Mac -> NAS 默认直连 Tailscale，不再把 Windows 当跳板机。

## 3. 先看哪个操作文档
| 场景 | 文档 |
|---|---|
| Mac 本地研究站启动 / 同步 / smoke | `docs/ops/mac-local-research.md` |
| 端口规范 / 本地端口红线 | `docs/ops/port-management.md` |
| Mac 直连 NAS / 远程查库 / 发布控制 / 公网域名规划 | `docs/ops/mac-nas-collaboration.md` |
| AI / skill 路由与协同 | `docs/ops/ai-skill-routing.md` |
| NAS 正式公网域名 / Cloudflare Tunnel 切换 | `docs/ops/nas-public-domain-cloudflare.md` |
| Windows 数据主站 / crawler / 远控 | `docs/ops/windows-data-station.md` |
| 旧 Cloud 发版 / 退役边界（legacy/emergency only） | `docs/ops/cloud-release.md` |
| NAS 盘中 crawler 切换 | `docs/ops/nas-crawler-cutover-runbook.md` |
| NAS `research/current` 发布 / 回滚 | `docs/ops/nas-research-release-runbook.md` |
| 盘后正式主链 / 兼容旧链路 | `docs/ops/postclose-l2-runbook.md` |
| 三端目录 / 命名 / 生产与备份同步核查 | `docs/ops/three-end-sync.md` |
| 标准开发流程 / 分支收口 / 文档收尾 | `docs/ops/development-workflow.md` |
| 历史脚本族边界 | `docs/ops/atomic-script-families-boundary.md` |
| `backend/scripts` 脚本族边界 | `docs/ops/backend-script-families-boundary.md` |
| report / artifact 落点边界 | `docs/ops/report-and-artifact-boundary.md` |

## 3.1 Mac -> NAS 最小入口

当前已经验证通过的最小入口：

```bash
ssh zhangdong@dxp4800pro
```

```text
http://dxp4800pro:8080
https://100.119.0.126:9443
https://dxp4800pro.tailfff556.ts.net/
```

补充事实：

- `dxp4800pro` 是当前可用的 Tailscale MagicDNS 名称
- 项目 Web 当前可通过 `http://dxp4800pro:8080` 访问
- NAS 管理后台当前可通过 `https://100.119.0.126:9443` 访问
- 项目公网当前可通过 `https://dxp4800pro.tailfff556.ts.net/` 访问
- 当前这台 UGOS 的 `scp / sftp / rsync` 绝对路径上传不稳定，项目文件默认不要用它们发版
- 当前稳定上传方式包括 `git push nas main`、`scp -O`、`tar | ssh`
- 这个公网入口当前基于 `Tailscale Funnel`，可用但不是最终自定义域名方案

## 3.2 当前正式端口

- Mac 本地前端：`3001`
- Mac 本地后端：`8001`
- NAS 项目 Web：`8080`
- NAS Gitea Web：`3000`
- Docker 内部 backend：`8000`（只在容器内部使用）

红线：

- `5173 / 5174` 只按历史临时调试端口理解，不写进正式 runbook。
- 本地端口冲突时先清理旧实例，不要默默漂移到别的前端端口。
- 详细规则统一看 `docs/ops/port-management.md`。

## 4. 正式脚本白名单
> 只有下列脚本属于当前正式默认入口；正式操作、runbook、交接说明默认只引用这些脚本。
> 未列入本表的 `ops/` / `scripts/` 脚本，默认都不是正式入口。

| 用途 | 脚本 |
|---|---|
| Mac 首次全量同步 | `ops/bootstrap_mac_full_processed_sync.sh` |
| Mac 本地后端启动 | `ops/start_local_research_station.sh` |
| Mac 本地前端启动 | `ops/start_local_research_frontend.sh` |
| 每日盘后正式主链 | `ops/run_daily_new_framework.sh` |
| 兼容旧盘后链路 | `ops/legacy/run_postclose_l2.sh` |
| 旧盘后链路状态查看 | `ops/legacy/check_postclose_l2_status.sh` |
| 新框架月批 / 阶段状态查看 | `ops/check_windows_new_framework_months_status.sh` |
| Windows 脚本同步 | `sync_to_windows.sh` |
| 旧 Cloud 发布（legacy/emergency only） | `deploy_to_cloud.sh` |
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
cd /Users/dong/ZhangData/market-live-terminal
bash ops/run_daily_new_framework.sh --json --sync-nas
```

> 这条指令默认不需要指定日期：脚本会自动扫描 Windows `D:\MarketData` 日包，选择“最新完整日之后”Mac 尚未完整的日期补跑；完整性同时检查 atomic、selection、model_feature_store 落表、市场环境指数、热点结果、热点页面缓存、选股工作台活跃模型/策略 success 运行记录，以及选股页近期市场水位是否已覆盖当天。
> 
> 每日主链内置顺序：Windows atomic 与指数刷新并行；atomic 完成后并行跑 selection refresh 与热点计算；随后构建模型特征、导出增量、同步回 Mac，并在 Mac 本地生成选股工作台候选。自 `2026-06-09` 起，主链本地校验通过后还会继续补一次本地 `postclose_l2` L2 历史并刷新 `stock_universe_meta`，用于收口 Mac 本地 `live/market_data.db`。自 `2026-06-12` 起，主链还会刷新运行态市场水位目录 `research/current/selection/market_environment_gate_2026-06-10`；若带 `--sync-nas`，则在这些本地步骤通过后，把正式 `live` 结果和市场水位目录同步到 NAS 生产数据卷，并后台启动一轮 NAS 数据库快照。
>
> 额外边界：`--sync-nas` 现在聚焦“生产库 + 小型运行态产物 + 备份”这条日常链路，不再默认把整套 `research/current` 做成每天整包发布。`research/current` 的大体量发布仍保留为单独动作。

> 兼容旧盘后链路指令（仅历史 L2 / cloud 同步参考）：
```bash
cd /Users/dong/ZhangData/market-live-terminal
bash ops/legacy/run_postclose_l2.sh
```

> 本地研究站后端不要手工 `python -m backend.app.main` 直跑；必须走 `ops/start_local_research_station.sh`，否则会绕过外置库路径注入，读错本地数据库。
> 同时不要并行拉起多个本地后端；当前正式脚本已内置“同仓库重复实例保护”，重复执行会先停止旧实例再启动新实例。
> 页面侧也不要把远端抓数挂到初始化或轮询上。尤其 `散户一致性观察` 这类链路，页面默认只能读本地库；补抓必须是显式手动动作或盘后任务，否则很容易把本地单实例后端拖到业务接口超时。
> 选股/研究页同样遵守这个原则：读接口只负责展示当前本地已有结果；不能在初始化时默默重跑，也不要默认走云端兜底。未跑、无结果、失败必须直接给出明确空态，重跑只允许通过显式按钮或每日任务。


## 5. 强制 gate
1. **跨机前**：先检查 Tailscale / SSH 连通。
2. **改 repo 后**：先在临时分支完成，再合回 `main`。
3. **提交前**：跑 `bash scripts/check_baseline.sh`。
4. **涉及长期事实变化**：同步回填 `README / 02 / 03 / 04 / AI_QUICK_START` 的受影响项。
5. **需求收尾**：同步更新 `AI_HANDOFF_LOG` 与 `07_PENDING_TODO`。

## 6. 当前工作目录与主线
- 主目录：`/Users/dong/ZhangData/market-live-terminal`
- 主线分支：`main`
- 当前工作版本：`v5.2.20`
- 当前项目真相入口：`docs/changes/MOD-20260421-01-project-current-state-and-doc-governance-normalization.md`
- 临时需求分支可使用 `codex/*`，但默认不把额外 worktree 作为主开发入口。

## 7. 相关规则
- 变更流程：`docs/06_CHANGE_MANAGEMENT.md`
- 文档治理：`docs/08_DOCS_GOVERNANCE.md`
- AI 协作：`docs/00_AI_HANDOFF_PROTOCOL.md`
- 开发流程标准：`docs/ops/development-workflow.md`
