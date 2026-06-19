# 三端存储与备份策略

## 1. 结论

当前最合理的备份口径是：

1. `Mac` 负责开发真相和 Git 提交。
2. `Windows` 负责原始包与正式跑数，不负责长期主备份。
3. `NAS` 负责在线服务、短期运行态快照和结构化备份入口。
4. 每日盘后 `--sync-nas` 只做生产增量同步，不默认做数据库快照。

不要再把 Windows 当主备份机。

也不要把 NAS Docker 项目目录当长期文件保险柜。Docker 目录只保留运行服务需要的内容和少量短期回滚点；长期文件级备份应放到 NAS 个人数据盘或独立共享目录，由用户手动或 DSM 任务管理。

## 2. 代码怎么备份

代码仓库不做“拷一份目录当备份”这套。

正式做法：

1. Mac 本地开发仓是主工作副本。
2. 每次关键变更至少执行：
   - `git push nas main`
   - `git push origin main`

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

正式数据库备份以 NAS 为中心，但分为“运行目录”和“保险柜目录”两类。

正式口径：

1. Mac 是研究消费与开发现场。
2. NAS Docker 目录是在线服务节点和短期运行态快照节点。
3. Windows 不再承担“最终备份仓”角色。
4. NAS 个人数据盘或独立共享目录才是长期文件级备份位置。

当前 Docker 内建议路径：

- 正式运行/研究库：
  - `/volume1/docker/market-live-terminal/data/live`
  - `/volume1/docker/market-live-terminal/data/research/current`
  - `/volume1/docker/market-live-terminal/data/selection`
- 运行态轻量备份快照：
  - `/volume1/docker/market-live-terminal/backups/runtime_snapshots`
- 手工全量备份快照：
  - `/volume1/docker/market-live-terminal/backups/full_snapshots`
- 人工冷备：
  - `/volume1/docker/market-live-terminal/backups/manual`

当前不再保留在 Docker 运行路径里的对象：

- 旧的全量日快照历史包
- 旧导入包
- 旧扁平结构备份
- 旧 `research/current` 发布归档
- 历史 `incoming` 传输残留

这些对象已集中到：

```text
/volume1/docker/market-live-terminal/_pending_delete_20260619
```

由用户在 NAS 文件管理器中手动删除。

## 4. 当前可执行的备份机制

已补脚本：

- [nas_backup_runtime_db_snapshot.sh](/Users/dong/ZhangData/market-live-terminal/ops/nas/nas_backup_runtime_db_snapshot.sh:1)

作用：

1. 从 NAS 当前正式 runtime 根读取 sqlite 主库。
2. 用 sqlite `.backup` 生成一致性快照。
3. 默认输出到：
   - `/volume1/docker/market-live-terminal/backups/runtime_snapshots/<timestamp>/`

默认覆盖对象：

1. `live/market_data.db`
2. `live/user_data.db`
3. `research/current/selection/selection_research.db`
4. `research/current/selection/model_feature_store.db`
5. `research/current/selection/model_market_index_daily.db`
6. `research/current/market_heat/*.db`
7. `research/current/market_heat/*_latest.json`

默认不覆盖：

1. `research/current/atomic_facts/market_atomic_mainboard_compact_current.db`

原因：

1. 这张 atomic 大库当前约 `68G+`，是训练 / 全量研究底座，不是每天线上查询都要新复制的对象。
2. 每天复制它会把 NAS `backups` 快速堆到数百 GB，已经实测发生过。
3. 需要全量保险时，必须人工显式执行：

```bash
SNAPSHOT_PROFILE=full bash ops/nas/nas_backup_runtime_db_snapshot.sh
```

这个命令会输出到：

```text
/volume1/docker/market-live-terminal/backups/full_snapshots/<timestamp>/
```

## 5. 频率建议

当前建议不要一上来搞复杂。

最小可用机制：

1. **代码**：每次关键改动都 `push origin` + `push nas`
2. **每日数据同步**：每日盘后只同步增量到 NAS 生产库，不默认做快照
3. **数据库轻量快照**：最多每周固定跑一次 `nas_backup_runtime_db_snapshot.sh`，保留最近 `4` 份
4. **全量 atomic 快照**：只在重大改造前人工执行 `SNAPSHOT_PROFILE=full`，保留最近 `1` 份
5. **人工冷备**：真正要长期保存时，放到 NAS 个人数据盘或独立共享目录，不放在 Docker 项目运行目录里

## 6. 现在不建议做的事

1. 不建议让 Windows 承担唯一长期备份角色。
2. 不建议继续把大备份直接堆在 Docker 项目根目录。
3. 不建议把 Docker `data/` 或 `backups/` 当长期文件保险柜。
4. 不建议现在做“云上唯一单盘备份”并把它当灾备完成态。
5. 不建议把 `backups/db_snapshots` 继续作为新快照落点；这里已经降级为历史待清理目录。

## 7. 后续增强

如果后面你补齐第二块云盘或对象存储，再做下一层：

1. NAS `runtime_snapshots` 定期同步到云端
2. 关键 raw 包按月份增量同步到云端
3. 形成 `本机 + NAS + 云端` 三份数据链
