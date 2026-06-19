# 三端目录与命名同步核查

更新时间：2026-06-09

## 1. 目标

这份文档只回答一件事：

Mac、Windows、NAS 三端的正式目录、正式文件名、生产职责和备份职责，是否已经收成同一套可协作口径。

## 2. 结论

截至 `2026-06-09`，你的目标只完成了前半段，还没有完全完成。

已经完成的部分：

1. **正式主文件名已经统一**。
   - 三端现在统一按下面这些名字沟通：
   - `market_data.db`
   - `user_data.db`
   - `market_atomic_mainboard_compact_current.db`
   - `selection_research.db`
   - `model_feature_store.db`
   - `model_market_index_daily.db`
2. **Mac 和 NAS 的正式目录层级已经基本一致**。
   - 都按 `live / research/current / cache / artifacts / incoming` 这套结构理解。
3. **Windows 现场原来还是扁平结构**，这次已补了一层**同名入口别名**。
   - 也就是：不搬活跃正式文件，但补出和 Mac/NAS 一样的可见路径，避免三端沟通时再出现“这个端这么叫、那个端那么叫”。
4. **Mac 端一个没收干净的现场问题已经修掉**。
   - `cache/market_heat` 和 `cache/eastmoney_sector_cache` 原来是断掉的软链，现在已经修回有效入口。
5. **NAS 作为代码备份和数据备份落点已经成立，但日跑不再默认触发数据库快照**。

没有完成的部分：

1. **Windows 还不是和 Mac/NAS 一样的真实物理目录结构**。
   - 现在是“活跃文件还在旧扁平位置，但已经补出同名别名入口”。
   - 这能解决协作命名问题，但还不等于 Windows 物理层也彻底整理完。
2. **NAS 生产库和 Mac 本地库还不是同一份状态**。
   - `2026-06-09` 现场核查结果：
   - 两边 `history_daily_l2` 的最大日期都已经到 `2026-06-08`
   - 但 Mac 当天记录数是 `7745`，NAS 是 `3193`
   - Mac 的 `stock_universe_meta` 是 `5532`，NAS 是 `5230`
   - 这说明“Mac 修完就自动同步到 NAS 生产库”这件事，当前并没有真正打通。
3. **NAS 数据库快照只有脚本和一份快照，自动调度没挂上**。
   - 当前看到的快照目录是 `20260609_100757`
   - 但当前 SSH 用户没有写 crontab 的权限，所以“定期自动备份”不能算完成态。

## 3. 当前统一口径

### 3.1 Mac

正式根目录：

```text
/Users/dong/ZhangData/market-data
```

当前正式入口：

```text
live/market_data.db
live/user_data.db
research/current/atomic_facts/market_atomic_mainboard_compact_current.db
research/current/selection/selection_research.db
research/current/selection/model_feature_store.db
research/current/selection/model_market_index_daily.db
research/current/market_heat/
cache/
artifacts/
incoming/
```

### 3.2 Windows

当前运行根目录：

```text
D:\market-live-terminal\data
```

当前应对外统一使用的可见路径：

```text
data\live\market_data.db
data\live\user_data.db
data\research\current\atomic_facts\
data\research\current\selection\
data\research\current\market_heat\
data\cache\
data\artifacts\
data\incoming\
```

补充说明：

1. Windows 的活跃正式文件当前仍主要落在旧扁平位置：
   - `data\market_data.db`
   - `data\user_data.db`
   - `data\atomic_facts\`
   - `data\selection\`
   - `data\market_heat\`
2. 本轮新增的是**同名入口层**，不是大搬家。
3. 这样做的目的，是先把三端协作口径统一，再决定以后要不要继续做 Windows 物理层整理。

### 3.3 NAS

正式根目录：

```text
/volume1/docker/market-live-terminal/data
```

当前正式入口：

```text
live/market_data.db
live/user_data.db
research/current/atomic_facts/market_atomic_mainboard_compact_current.db
research/current/selection/selection_research.db
research/current/selection/model_feature_store.db
research/current/selection/model_market_index_daily.db
research/current/market_heat/
cache/
artifacts/
incoming/
```

## 4. NAS 角色核查

### 4.1 作为生产环境

当前结论：

1. NAS 继续承担线上生产环境，这一点没有问题。
2. `2026-06-09` 晚间已把 Mac 本地正式 `live/market_data.db` 的当天结果同步到 NAS 生产库。
3. 当前两端已经对齐到：
   - `history_daily_l2=7739`
   - `history_5m_l2=349019`
   - `stock_universe_meta=5532`
4. 也就是说，如果你的要求是“Mac 修好后，生产应该直接看到同样结果”，这条最核心的业务目标现在已经达成。

### 4.2 作为备份节点

当前结论：

1. **代码备份成立**。
   - `git ls-remote nas HEAD` 可用
   - NAS 上存在 Gitea 仓库：
   - `/volume1/docker/gitea/git/repositories/zhangdong/market-live-terminal.git`
2. **数据库轻量快照机制成立，但不再绑定每日主链**。
   - 现有备份脚本：
   - `ops/nas/nas_backup_runtime_db_snapshot.sh`
   - 默认落点：`/volume1/docker/market-live-terminal/backups/runtime_snapshots`
   - 默认不复制 `research/current/atomic_facts` 里的 68G+ atomic 大库。
3. **旧的 `backups/db_snapshots` 已降级为历史待清理目录**。
   - 这个目录里的旧快照来自早期“每日主链成功后后台触发全量快照”的策略。
   - 该策略已确认会快速浪费空间，后续不再作为默认口径。
4. **如果以后要完全脱离 Mac 人工触发备份，仍需要 NAS 侧更高权限用户或 DSM 计划任务来挂定时**。

## 5. 这轮已经做掉的收口

1. 修复 Mac 断掉的 `cache` 入口：
   - `cache/market_heat`
   - `cache/eastmoney_sector_cache`
2. 给 Windows 补出和 Mac/NAS 一致的可见入口层：
   - `data/live`
   - `data/research/current`
   - `data/cache`
   - `data/artifacts`
   - `data/incoming`
3. 给 NAS 补齐缺失的空目录占位：
   - `data/artifacts/reports`
4. 复核 NAS 代码备份和数据库快照落点是否真实存在。
5. 把 `2026-06-09` 的正式 `live` 结果从 Mac 同步到了 NAS 生产库。
6. 把 NAS 快照从“每日收盘主链成功后后台触发”降级为“人工或 NAS 计划任务触发”，避免每天复制 atomic 大库。

## 6. 还差哪三步

这三步才是你这个目标真正没做完的部分：

1. **决定 NAS 轻量快照以后是否升级成完全独立定时**。
   - 现在日跑默认不再触发快照；如果要自动备份，应由 NAS 计划任务每周触发轻量快照。
2. **决定 `research/current` 是否需要每天整包发布到 NAS**。
   - 现场验证表明这条链路体量太大，不适合继续绑在每天收盘主链后面。
   - 大容量同步必须区分网络环境：在外网 / Tailscale 环境只做代码、小文件、远程查数和服务验证；`research/current` 整包、数 GB 级数据库、批量报告资产和模型产物同步，等回到家里局域网后再做。
   - 如果排障结果只卡在 Mac 到 NAS 的大容量传输速度或入口可达性上，不把它当成当前开发阻塞；记录待同步清单，回家后走 `192.168.3.43` 局域网链路补传。
3. **决定 Windows 后续是保留“别名层方案”，还是继续做物理目录终态整理**。
   - 从协作角度，别名层已经够用；
   - 从洁癖角度，还不是最终物理终态。

## 7. 当前建议

如果继续只做和你业务目标直接相关的动作，优先级应该是：

1. 维持现在这条 **Mac 收盘主链成功后 -> 同步 NAS 生产库** 的日常动作。
2. 再决定 **NAS 轻量快照要不要升级成 NAS 自己的每周计划任务**。
3. 最后再决定 **Windows 要不要继续做物理层大整理**。

不要再把精力分散到新的研究问题上。
