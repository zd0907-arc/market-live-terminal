# MOD-20260619-02 三端同步执行结果

日期：2026-06-19
状态：`DONE`
主路径：`/Users/dong/ZhangData/market-live-terminal`

## 结论

本轮已按三端同步方案完成代码、NAS app、NAS 数据、Windows 备份副本的同步收口。

当前结果：

1. GitHub `origin/main` 与 NAS Gitea `nas/main` 均已更新到 `4268dec46a029edbed23f6f888667550f1f044c0`。
2. NAS app 工作目录 `.deploy_commit` 已更新到同一 commit。
3. NAS full compose 已重建并重启 `backend / frontend / crawler`。
4. Mac、NAS、Windows 关键数据均已覆盖到 `2026-06-17`。
5. NAS 线上接口和页面冒烟通过。

## 代码同步

执行结果：

- 本地 `main` 推送到 NAS Gitea：成功。
- 本地 `main` 推送到 GitHub：成功。
- 验真：`origin/main` 与 `nas/main` 均等于本地 `HEAD`。

最新 commit：

```text
4268dec46a029edbed23f6f888667550f1f044c0
```

## NAS app 同步

NAS app 路径：

```text
/volume1/docker/market-live-terminal/app
```

处理结果：

- 使用 `git archive | ssh tar` 将 Mac 正式仓库内容发布到 NAS app 目录。
- 保留 NAS 侧 `.env.nas-full` / `.env.nas-lite`。
- 写入 `.deploy_commit=4268dec46a029edbed23f6f888667550f1f044c0`。
- 使用 full compose 重建并启动：
  - `market-backend-nas`
  - `market-frontend-nas`
  - `market-crawler-nas`

## NAS 数据同步

NAS data 路径：

```text
/volume1/docker/market-live-terminal/data
```

同步内容：

- `research/current/selection`
- `research/current/market_heat`
- `selection/opportunity_discovery`
- `research/current/atomic_facts/market_atomic_mainboard_compact_current.db` 中 `2026-06-16`、`2026-06-17` 两天 atomic 增量

保护边界：

- 未用 Mac 轻量 atomic 库覆盖 NAS 71G 全量 atomic 库。
- atomic 只按 `trade_date in ('2026-06-16', '2026-06-17')` 合并 12 张表的增量行。

NAS 回滚备份：

```text
/volume1/docker/market-live-terminal/backups/pre_three_end_sync_20260619_183932
```

NAS 数据复核：

```text
atomic_trade_daily: 2024-09-02 -> 2026-06-17
history_daily_l2: latest 2026-06-17
history_5m_l2: latest 2026-06-17
selection_candidate_daily: 2026-03-02 -> 2026-06-17
selection_strategy_runs: 2026-03-01 -> 2026-06-17
model_market_state_daily_v1: 2024-09-02 -> 2026-06-17
fine_theme_heat_daily_v2: 2026-02-13 -> 2026-06-17
```

## Windows 数据同步

Windows 角色仍保持为跑数工具和稳定备份副本，不作为开发或研究站。

只读核查结果：

- atomic full：已到 `2026-06-17`。
- model feature：已到 `2026-06-17`。
- market heat：已到 `2026-06-17`。
- live：已到 `2026-06-17`。
- selection 原先仍停在 2026-04-30，且 `selection_candidate_daily` 为空。

处理结果：

- 已把 Mac 当前 `selection_research.db` 同步到 Windows `D:\market-live-terminal\data\selection\selection_research.db`。
- 已同步 `market_environment_gate_2026-06-10`。
- 已同步 `selection/opportunity_discovery` 小模型目录，补齐 `postclose_exit_2025top5_heat_v0_1`。
- 未覆盖 Windows full atomic。

Windows 回滚备份：

```text
D:\market-live-terminal\data\backups\pre_three_end_sync_20260619_190144
```

Windows 数据复核：

```text
atomic_trade_daily: 2024-09-02 -> 2026-06-17
selection_candidate_daily: 2026-03-02 -> 2026-06-17
selection_strategy_runs: 2026-03-01 -> 2026-06-17
model_market_state_daily_v1: 2024-09-02 -> 2026-06-17
live history_daily_l2: latest 2026-06-17
live history_5m_l2: latest 2026-06-17
```

## NAS 冒烟结果

入口：

```text
http://192.168.3.43:8080
```

已通过：

- `/api/health`
- `/api/review/pool?date=2026-06-17&limit=3`
- `/api/realtime/dashboard?symbol=sh601939`
- `/api/market_heat/fine_dates?days=20`
- `/api/market_heat/fine_dashboard?days=20&pool_size=20`
- `/api/market_temperature/snapshot?days=5`
- `/api/selection/daily-candidates?date=2026-06-17&limit=5`
- `/api/selection/market-environment?date=2026-06-17`
- `/api/selection/health`
- `/api/trend-research/ideas?limit=3`
- `/market-temperature`
- `/selection-research`

说明：

- `/api/selection/health` 第一次在外部 HTTP 访问中超时；容器内直接调用只耗时约 2.7 秒，随后外部 HTTP 重试返回 200。当前判定为刚重启后的瞬时状态，不是数据缺失。

## 临时文件清理

已清理：

- Mac `/tmp/market-three-end-sync-20260619`
- NAS `/volume1/docker/market-live-terminal/data/incoming/three_end_sync_20260619`
- Windows `D:\market-live-terminal\data\incoming\three_end_sync_20260619`
- 本轮临时探针脚本

保留：

- NAS 回滚备份：`/volume1/docker/market-live-terminal/backups/pre_three_end_sync_20260619_183932`
- Windows 回滚备份：`D:\market-live-terminal\data\backups\pre_three_end_sync_20260619_190144`

## 后续注意

1. Windows 的 selection 旧结构已经通过本轮补齐，但 Windows 仍不作为开发端。
2. NAS full atomic 已通过增量合并到 2026-06-17；后续日跑应继续避免用 Mac 轻量库覆盖 NAS full atomic。
3. NAS `incoming` 里仍保留历史日跑临时包和日志，本轮只清理了本次同步 staging。
