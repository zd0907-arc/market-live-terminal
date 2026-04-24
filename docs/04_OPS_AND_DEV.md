# 04_OPS_AND_DEV（开发与运维入口）

> 目标：只回答“当前正式怎么运行、怎么发布、怎么验真、详细步骤去哪看”。
> 详细操作不再堆在本页；本页是运维/开发长记忆入口。

## 1. 当前正式运行拓扑
- **Cloud**：轻量盯盘 / 手机应急查看
- **Windows**：原始包、正式跑数、实时 crawler、研究结果产出
- **Mac**：本地研究站、复盘、选股、文档与开发

## 2. 当前总原则
1. Windows 是数据主站；Mac 不直接跨网络读 Windows sqlite 主库。
2. Mac 保留一份同步后的正式库，作为本地研究主消费。
3. Cloud 不承载 full atomic 主库，只保留轻量盯盘链路。
4. `snapshot` 只作验证/应急，不是正式主方案。
5. 所有跨机器动作，先过连通性 gate，再执行同步/发布。

## 3. 先看哪个操作文档
| 场景 | 文档 |
|---|---|
| Mac 本地研究站启动 / 同步 / smoke | `docs/ops/mac-local-research.md` |
| Windows 数据主站 / crawler / 远控 | `docs/ops/windows-data-station.md` |
| Cloud 发版 / 冒烟 / 回滚 | `docs/ops/cloud-release.md` |
| 盘后 L2 / 原子层 / 日跑总控 | `docs/ops/postclose-l2-runbook.md` |
| 标准开发流程 / 分支收口 / 文档收尾 | `docs/ops/development-workflow.md` |

## 4. 当前常用脚本
| 用途 | 脚本 |
|---|---|
| Mac 首次全量同步 | `ops/bootstrap_mac_full_processed_sync.sh` |
| Mac 本地后端启动 | `ops/start_local_research_station.sh` |
| Mac 本地前端启动 | `ops/start_local_research_frontend.sh` |
| 每日盘后总控 | `ops/run_postclose_l2.sh` |
| 盘后状态查看 | `ops/check_postclose_l2_status.sh` |
| Windows 脚本同步 | `sync_to_windows.sh` |
| 云端发布 | `deploy_to_cloud.sh` |
| 基线检查 | `scripts/check_baseline.sh` |

## 5. 强制 gate
1. **跨机前**：先检查 Tailscale / SSH 连通。
2. **改 repo 后**：先在临时分支完成，再合回 `main`。
3. **提交前**：跑 `npm run check:baseline`。
4. **涉及长期事实变化**：同步回填 `README / 02 / 03 / 04 / AI_QUICK_START` 的受影响项。
5. **需求收尾**：同步更新 `AI_HANDOFF_LOG` 与 `07_PENDING_TODO`。

## 6. 当前工作目录与主线
- 主目录：`/Users/dong/Desktop/AIGC/market-live-terminal`
- 主线分支：`main`
- 当前版本：`v5.0.0`
- 当前项目真相入口：`docs/changes/MOD-20260421-01-project-current-state-and-doc-governance-normalization.md`

## 7. 相关规则
- 变更流程：`docs/06_CHANGE_MANAGEMENT.md`
- 文档治理：`docs/08_DOCS_GOVERNANCE.md`
- AI 协作：`docs/00_AI_HANDOFF_PROTOCOL.md`
- 开发流程标准：`docs/ops/development-workflow.md`
