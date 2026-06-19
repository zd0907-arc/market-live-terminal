# MOD-20260619-03 NAS 存储清理与备份策略收口

日期：2026-06-19
状态：`IN_PROGRESS`
主机：`NAS 192.168.3.43`

## 结论

本轮先完成“止血”：每日盘后 `--sync-nas` 不再默认触发 NAS 数据库快照，避免继续每天复制 `68G+` atomic 大库。

当前 NAS 大空间问题不是线上服务本身变成了 `1T`，而是历史备份和历史发布归档堆积：

```text
/volume1/docker/market-live-terminal/app       79M
/volume1/docker/market-live-terminal/data      226G
/volume1/docker/market-live-terminal/backups   820G
```

其中真正当前线上查询主数据主要在：

```text
data/research/current                          76G
data/live                                     1.2G
data/selection                                 99M
```

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

## 当前可删候选

下面是“按业务判断可以清理”的候选。清理前仍建议先确认当天没有正在跑日跑或发布。

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

1. 保守：只保留最新一份 `20260618_031041`，删除其余。
2. 激进：整个 `db_snapshots` 删除。

预计释放：

```text
保守约 580G
激进约 656G
```

### B. 旧导入包

路径：

```text
/volume1/docker/market-live-terminal/backups/imports/full-import_20260608
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

建议：

公司 Mac 迁移完成并验证后删除；如果急需释放空间，也可以现在删除。

### C. 旧扁平结构备份

路径：

```text
/volume1/docker/market-live-terminal/backups/legacy_flat_root_20260608
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

建议：

公司 Mac 迁移完成并验证后删除；如果急需释放空间，也可以现在删除。

### D. 旧 research 发布归档

路径：

```text
/volume1/docker/market-live-terminal/data/research/archive/20260605_220145_nas_daily_new_20260605
/volume1/docker/market-live-terminal/data/research/archive/20260608_235037_nas_daily_new_20260608
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

建议：

公司 Mac 迁移完成并验证后删除；若要立刻清空间，至少保留最近一份。

### E. 本轮三端同步前备份

路径：

```text
/volume1/docker/market-live-terminal/backups/pre_three_end_sync_20260619_183932
```

大小：

```text
8.4G
```

来源：

2026-06-19 三端同步前，为 selection、market_heat、模型小目录做的局部回滚备份。

建议：

先保留到公司 Mac 迁移完成；之后可以删除。

### F. incoming 历史传输残留

路径：

```text
/volume1/docker/market-live-terminal/data/incoming
```

大小：

```text
749M
```

来源：

历史日跑、验证、传输测试和日志。

建议：

可后续清理，但不是当前空间主因。

## 推荐清理顺序

先不碰当前线上目录：

```text
/volume1/docker/market-live-terminal/data/live
/volume1/docker/market-live-terminal/data/research/current
/volume1/docker/market-live-terminal/data/selection
```

优先释放空间：

1. 清理 `backups/db_snapshots`：释放 `580G-656G`
2. 清理 `backups/imports/full-import_20260608`：释放 `78G`
3. 清理 `backups/legacy_flat_root_20260608`：释放 `78G`
4. 清理 `data/research/archive` 旧发布归档：释放最多 `149G`

## 给用户的删除方式

如果用户自己在 NAS 文件管理器删除，优先删这些整目录：

```text
/volume1/docker/market-live-terminal/backups/db_snapshots
/volume1/docker/market-live-terminal/backups/imports/full-import_20260608
/volume1/docker/market-live-terminal/backups/legacy_flat_root_20260608
```

如果需要由 Codex 代删，建议先执行“隔离移动”，把候选目录移动到同一目录：

```text
/volume1/docker/market-live-terminal/backups/_pending_delete_20260619/
```

确认线上服务和公司 Mac 迁移都正常后，再删除该目录。

## 未执行删除

本轮到当前为止没有删除 NAS 上任何历史备份或当前运行数据。
