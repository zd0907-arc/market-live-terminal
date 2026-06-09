# 三端存储与备份策略

## 1. 结论

当前最合理的备份口径是：

1. `Mac` 负责开发真相和 Git 提交。
2. `Windows` 负责原始包与正式跑数，不负责长期主备份。
3. `NAS` 负责在线服务、正式数据库快照和结构化备份。

不要再把 Windows 当主备份机。

## 2. 代码怎么备份

代码仓库不做“拷一份目录当备份”这套。

正式做法：

1. Mac 本地开发仓是主工作副本。
2. 每次关键变更至少执行：
   - `git push origin main`
   - `git push nas main`

解释：

1. `origin` = 外部 Git 备份
2. `nas` = NAS Gitea 私有备份

这已经是代码层的双备份。

## 3. 数据怎么备份

### 3.1 原始包

原始 `.7z` 包当前仍以 Windows 为主真相：

- `D:\MarketData`

建议：

1. 路径保持不变。
2. 不把原始包和正式数据库混放。
3. 后续如果要加第二份 raw 备份，优先增量同步到 NAS 的独立 raw 目录，不进正式 `data/`。

### 3.2 正式数据库

正式数据库备份以 NAS 为中心。

正式口径：

1. Mac 是研究消费与开发现场。
2. NAS 是正式 snapshot / archive / 公网服务节点。
3. Windows 不再承担“最终备份仓”角色。

当前建议路径：

- 正式运行/研究库：
  - `/volume1/docker/market-live-terminal/data/live`
  - `/volume1/docker/market-live-terminal/data/research/current`
- 正式备份快照：
  - `/volume1/docker/market-live-terminal/backups/db_snapshots`
- 人工冷备：
  - `/volume1/docker/market-live-terminal/backups/manual`
- 退休旧结构：
  - `/volume1/docker/market-live-terminal/backups/legacy_flat_root_20260608`
- 导入/迁移历史包：
  - `/volume1/docker/market-live-terminal/backups/imports`

## 4. 当前可执行的备份机制

已补脚本：

- [nas_backup_runtime_db_snapshot.sh](/Users/dong/Desktop/AIGC/market-live-terminal/ops/nas/nas_backup_runtime_db_snapshot.sh:1)

作用：

1. 从 NAS 当前正式 runtime 根读取 sqlite 主库。
2. 用 sqlite `.backup` 生成一致性快照。
3. 输出到：
   - `/volume1/docker/market-live-terminal/backups/db_snapshots/<timestamp>/`

覆盖对象：

1. `live/market_data.db`
2. `live/user_data.db`
3. `research/current/atomic_facts/market_atomic_mainboard_compact_current.db`
4. `research/current/selection/selection_research.db`
5. `research/current/selection/model_feature_store.db`
6. `research/current/selection/model_market_index_daily.db`
7. `research/current/market_heat/*.db`
8. `research/current/market_heat/*_latest.json`

## 5. 频率建议

当前建议不要一上来搞复杂。

最小可用机制：

1. **代码**：每次关键改动都 `push origin` + `push nas`
2. **数据库**：每日盘后或每周固定跑一次 `nas_backup_runtime_db_snapshot.sh`
3. **重大改造前**：额外做一次人工冷备，放到 `backups/manual/`

## 6. 现在不建议做的事

1. 不建议让 Windows 承担唯一长期备份角色。
2. 不建议继续把大备份直接堆在项目根目录。
3. 不建议现在做“云上唯一单盘备份”并把它当灾备完成态。

## 7. 后续增强

如果后面你补齐第二块云盘或对象存储，再做下一层：

1. NAS `db_snapshots` 定期同步到云端
2. 关键 raw 包按月份增量同步到云端
3. 形成 `本机 + NAS + 云端` 三份数据链
