# MOD-20260619-03 NAS 存储清理与备份策略收口

日期：2026-06-19
状态：`PENDING_USER_DELETE`
主机：`NAS 192.168.3.43`

## 结论

本轮完成两件事：

1. 机制止血：每日盘后 `--sync-nas` 不再默认触发 NAS 数据库快照，避免继续每天复制 `68G+` atomic 大库。
2. 现场收口：历史备份、旧发布归档和传输残留已集中移动到一个待删除目录，由用户自行最终删除。

当前 NAS 大空间问题不是线上服务本身变成了 `1T`，而是历史备份和历史发布归档堆积：

```text
/volume1/docker/market-live-terminal/app       79M
/volume1/docker/market-live-terminal/data      226G
/volume1/docker/market-live-terminal/backups   820G  清理前
```

其中真正当前线上查询主数据主要在：

```text
data/research/current                          76G
data/live                                     1.2G
data/selection                                 99M
```

当前整理后：

```text
/volume1/docker/market-live-terminal/data                    77G
/volume1/docker/market-live-terminal/backups                  0
/volume1/docker/market-live-terminal/_pending_delete_20260619 314G
```

说明：

1. `_pending_delete_20260619` 只是集中待删桶，不是运行路径。
2. 同卷移动不会释放空间；用户删除该目录后才会真正释放空间。
3. 当前线上服务继续读取 `data/live`、`data/research/current`、`data/selection`。

## 业务来源解释

### 1. 每日同步

每日同步是“Windows / Mac 已经算出当天结果后，把当天增量写到 NAS 线上库”。

业务目的：

1. 让 NAS 页面能看到最新复盘、盯盘、选股、市场水位。
2. 保持线上服务可用。

处理策略：

1. 继续保留。
2. 只同步增量和小型运行态目录。
3. 不再默认触发数据库快照。

### 2. 运行态轻量备份

运行态轻量备份是“复制线上正在服务的 SQLite 小库和中等库”，用于误操作后的短期回滚。

业务目的：

1. 防止当天同步或小改造把线上库写坏。
2. 不追求长期全量灾备。

新策略：

```bash
bash ops/nas/nas_backup_runtime_db_snapshot.sh
```

默认落点：

```text
/volume1/docker/market-live-terminal/backups/runtime_snapshots/<timestamp>/
```

默认保留：

```text
最近 4 份
```

默认不备份：

```text
research/current/atomic_facts/market_atomic_mainboard_compact_current.db
```

### 3. 全量 atomic 备份

全量 atomic 备份是“复制训练 / 全量研究底座那张 68G+ 大库”。

业务目的：

1. 只用于重大改造前的人工保险。
2. 不适合每天跑。

新策略：

```bash
SNAPSHOT_PROFILE=full bash ops/nas/nas_backup_runtime_db_snapshot.sh
```

默认落点：

```text
/volume1/docker/market-live-terminal/backups/full_snapshots/<timestamp>/
```

默认保留：

```text
最近 1 份
```

## 已修改的机制

代码入口：

1. `backend/scripts/run_daily_new_framework.py`
2. `ops/nas/nas_backup_runtime_db_snapshot.sh`

调整结果：

1. `DAILY_NAS_SNAPSHOT_POLICY` 默认值为 `off`。
2. 每日 `--sync-nas` 默认只做 NAS 生产增量同步和市场水位目录同步。
3. 快照脚本默认 `SNAPSHOT_PROFILE=runtime`，不复制 atomic 大库。
4. `SNAPSHOT_PROFILE=full` 才复制 atomic 大库。
5. 新快照带保留数量：
   - runtime：默认保留 `4` 份
   - full：默认保留 `1` 份

## 已集中移动的可删对象

下面对象已移动到：

```text
/volume1/docker/market-live-terminal/_pending_delete_20260619
```

用户可在 NAS 文件管理器中删除这个目录来释放空间。

### A. 旧全量日快照

路径：

```text
/volume1/docker/market-live-terminal/backups/db_snapshots
```

大小：

```text
656G
```

来源：

早期每日主链成功后自动触发的“全量运行库快照”。每份都复制了 atomic 大库，所以一份约 `68G-76G`。

现状：

1. 已不再作为新备份落点。
2. 已被新策略替代。
3. 不是线上服务读取路径。

建议：

已由用户先行删除主要内容；剩余旧快照不再保留。

预计释放：

```text
约 656G
```

### B. 旧导入包

路径：

```text
/volume1/docker/market-live-terminal/_pending_delete_20260619/backups/imports
```

大小：

```text
78G
```

来源：

6 月 8 日做 NAS 数据恢复/导入时保留的一份全量导入现场。

现状：

1. 当前线上主数据已在 `data/research/current`。
2. 这份不是服务读取路径。
3. 它与当前线上数据有大量重复。

处理结果：

已移动到待删除桶，可直接删除。

### C. 旧扁平结构备份

路径：

```text
/volume1/docker/market-live-terminal/_pending_delete_20260619/backups/legacy_flat_root_20260608
```

大小：

```text
78G
```

来源：

6 月 8 日把 NAS 旧扁平数据结构迁到新 `data/live`、`data/research/current` 结构时，下沉保存的旧结构保险。

现状：

1. 当前线上结构已经改用新路径。
2. 这份不是服务读取路径。
3. 它主要用于“旧结构误迁移时回滚”。

处理结果：

已移动到待删除桶，可直接删除。

### D. 旧 research 发布归档

路径：

```text
/volume1/docker/market-live-terminal/_pending_delete_20260619/data/research/archive
```

大小：

```text
约 149G
```

来源：

旧的 `research/current` 发布回滚点。每份也带一份 atomic 大库。

现状：

1. 当前线上读取 `data/research/current`。
2. 这两份只用于旧发布回滚。
3. 当前已完成三端同步后，它们的回滚价值下降。

处理结果：

已移动到待删除桶，可直接删除。

### E. 本轮三端同步前备份

路径：

```text
/volume1/docker/market-live-terminal/_pending_delete_20260619/backups/pre_three_end_sync_20260619_183932
```

大小：

```text
8.4G
```

来源：

2026-06-19 三端同步前，为 selection、market_heat、模型小目录做的局部回滚备份。

处理结果：

已移动到待删除桶，可直接删除。

### F. incoming 历史传输残留

路径：

```text
/volume1/docker/market-live-terminal/_pending_delete_20260619/data/incoming
```

大小：

```text
749M
```

来源：

历史日跑、验证、传输测试和日志。

处理结果：

已移动到待删除桶，可直接删除。正式 `data/incoming` 已重建为空目录。

### G. 旧手工备份

路径：

```text
/volume1/docker/market-live-terminal/_pending_delete_20260619/backups/manual
```

大小：

```text
1.9G
```

来源：

早期人工保存的旧 `market_data.db` / 小型 selection 备份。

处理结果：

已移动到待删除桶。正式 `backups/manual` 已重建为空目录。

## 推荐清理顺序

先不碰当前线上目录：

```text
/volume1/docker/market-live-terminal/data/live
/volume1/docker/market-live-terminal/data/research/current
/volume1/docker/market-live-terminal/data/selection
```

用户现在只需要删除一个目录：

```text
/volume1/docker/market-live-terminal/_pending_delete_20260619
```

预计释放：

```text
约 314G
```

加上用户已经删除的 `db_snapshots`，本轮合计移出/可释放空间约 `900G+`。

## 验证结果

移动后已验证：

1. `/api/health` 返回 `ok`。
2. `/api/selection/daily-candidates?date=2026-06-17&limit=1` 返回 200。
3. `/api/market_heat/fine_dates?days=20` 返回 200，最新日期 `2026-06-17`。
4. `/api/market_temperature/snapshot?days=5` 返回 200，最新日期 `2026-06-17`。

## Docker 数据边界

NAS Docker 项目目录只保留三类东西：

1. 正在运行的 app。
2. 正在被线上服务读取的 data。
3. 新机制下的短期运行态快照。

长期“文件保险柜”不放在 Docker 目录里。若用户需要整份文件级备份，应放到 NAS 个人数据盘或独立共享目录，由用户手动或 DSM 任务管理。
