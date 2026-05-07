# AI_HANDOFF_LOG v5 窗口旧日志摘要

Archive-Meta:
- Archive-ID: `ARC-LEG-20260429-ai-handoff-log-v5-window-summary`
- Type: `LEG`
- Created: `2026-04-29`
- Source: `docs/AI_HANDOFF_LOG.md`

## 摘要

本归档承接 `AI_HANDOFF_LOG.md` 中 2026-04-04 到 2026-04-25 的旧窗口日志。主日志继续只保留最近窗口，避免短记忆文件继续膨胀。

## 旧窗口重点

- 选股研究工作台从早期候选页推进到 `v5.0.8` UI 密度改造，右侧复盘图、锚点累计、交易计划标记和日期可选性逐步收口。
- 生产实时盯盘、Mac 本地研究站、每日盘后跑数三条链路被重新固化；Windows `ZhangDataLiveCrawler` 清理重复进程，并补交易日判断与单实例锁。
- 盘后 L2 日跑固化为 `bash ops/run_postclose_l2.sh`，Windows -> Mac 同步收敛到局域网 HTTP relay / Cloud relay，不再走 SSH/scp 直拉。
- 核心长记忆文档完成拆分：`02/03/04` 只保留入口与边界，细节下沉到 `docs/domain/`、`docs/contracts/`、`docs/ops/`。
- 项目治理完成第一轮瘦身：`docs/` 根目录保留集固定为 `00~08 + AI_QUICK_START + AI_HANDOFF_LOG`。
- 官方事件层补齐公告、资讯、问答公共 fallback；事件理解层仍未完成。
- 原子事实层性能剖析与优化进入 30 分钟目标线，但仍需真实整日 wall time 验证。
- 选股页右侧历史图通过专用 `/api/selection/history/multiframe` fallback 解决本地正式 L2 未补齐时的可视化缺口。

## 仍需看原卡的主题

- 文档治理：`docs/changes/MOD-20260425-01-long-memory-docset-refactor-phase1.md`、`docs/changes/MOD-20260425-02-split-core-long-memory-docs.md`
- 开发流程：`docs/changes/MOD-20260425-03-development-workflow-standardization.md`
- 盘后日跑：`docs/changes/MOD-20260425-04-postclose-l2-command-solidification.md`
- 实时链路：`docs/changes/MOD-20260425-05-realtime-and-postclose-runtime-contract.md`、`docs/changes/MOD-20260425-06-local-monitor-data-source-fix.md`
- 选股 UI：`docs/changes/REQ-20260425-01-selection-ui-density-rework.md`
