# MOD-20260608-01 Windows / NAS 运行目录与公网入口盘点

## 1. 基本信息
- 标题：Windows / NAS 运行目录与公网入口盘点
- 状态：`ACTIVE`
- 负责人：Codex
- 关联 Task ID：`MOD-20260608-01-windows-nas-runtime-storage-and-public-entry-audit`
- 关联 CAP：`CAP-DOCS-GOVERNANCE`, `CAP-NAS-OPS`

## 2. 一句话结论

当前三端口径已经从“代码默认会不会读错库”这个层面收口，下一层真正要做的是：

1. 把 Windows 明确定义成 `原始包 + 跑数产物 + staging / backup` 节点，而不是开发仓。
2. 把 NAS 明确定义成 `在线服务 + 正式发布 + 最终公网入口` 节点。
3. 把 NAS 上仍残留的 old flat-data 根层实体和临时导入/备份区收口到最终结构。
4. 把正式公网入口从 `Tailscale Funnel` 升级到 `Cloudflare Tunnel + 自定义域名`。

## 3. Windows 实机盘点（2026-06-08）

### 3.1 D 盘当前实际角色

#### `D:\MarketData`

- 作用：供应商原始包根目录
- 当前大小：约 `178.79 GB`
- 当前月目录：`202512`、`202605`、`202606`
- 当前月目录内部：按 `YYYYMMDD.7z` 保存，例如 `20260601.7z`、`20260602.7z`

判断：

1. 这是 Windows 原始真相源，应该保留。
2. 路径可以继续固定为 `D:\MarketData`，不建议再改。

#### `D:\market-live-terminal`

- 当前不是真正开发仓：
  - `.git` 不存在
  - `src/` 不存在
  - `docs/` 不存在
  - `package.json` 不存在
- 当前更像“裁剪过的运行仓 / 数据站工作目录”
- 实际顶层只保留了：
  - `.run/`
  - `backend/`
  - `data/`
  - `ops/`
  - `start_live_crawler.bat`

判断：

1. 它应该保留，但角色应改口成 `Windows 运行数据站`，不是开发目录。
2. 以后 Mac 才是开发仓；Windows 只保留运行必需代码和正式数据。

### 3.2 Windows 正式数据目录

当前 `D:\market-live-terminal\data` 下的实际重点对象：

- `market_data.db`：约 `2269.4 MB`
- `user_data.db`：极小，用户态配置库
- `selection\selection_research.db`：约 `2670.2 MB`
- `selection\selection_research_windows.db`：约 `2670.2 MB`（兼容同名）
- `selection\model_feature_store.db`：约 `4653.4 MB`
- `selection\model_market_index_daily.db`
- `market_heat\fine_theme_heat_daily_v2.db`
- `market_heat\tradable_theme_map.db`

当前 `atomic_facts/` 的真实状态：

- 存在巨大实物：`market_atomic_mainboard_compact_smoke_20260401_20260515.db`，约 `71979 MB`
- 存在旧备份：`..._bak_limit_prev_close_...db`，约 `37507 MB`
- 存在若干 smoke / validation / one_day test / rebuild 文件
- `2026-06-08` 已补出 canonical 名 `market_atomic_mainboard_compact_current.db`，当前和旧 `compact_smoke_*` 兼容共存

判断：

1. Windows 侧 `selection_research.db` 的 canonical 名已落盘；旧 `selection_research_windows.db` 当前只按兼容名理解。
2. `model_feature_store.db` 已基本可视为 Windows 正式默认名。
3. `atomic` 这条线已经补出 canonical 名 `market_atomic_mainboard_compact_current.db`；旧 `compact_smoke_*` 当前只按兼容名理解。

### 3.3 Windows 非正式对象

#### `.run/`

当前 `.run/` 下有大量 `*_day_delta_*.db`、`worker_*.db`、`mac_sync_*` 之类文件。

判断：

1. 它们属于运行产物 / 中间产物，不是正式主库。
2. 默认应该保留最近活跃窗口，历史批次按运行留痕处理，不进入正式真相口径。

#### 可清理残留

当前确认的明显残留：

- `D:\market-live-terminal\file`：0 字节
- `D:\market-live-terminal\backend\market.db`：0 MB
- `D:\market-live-terminal\backend\app\market_data.db`：0 MB
- `D:\market-live-terminal\backend\app\db\market_data.db`：0 MB

判断：

1. 这批对象不属于 Windows 正式运行资产。
2. 它们是下一轮可直接清理的候选。

### 3.4 Z 盘当前角色

当前重点目录：

- `Z:\atomic_stage`：约 `99.37 GB`
- `Z:\atomic_legacy_backup`：约 `40.21 GB`

`Z:\atomic_stage` 内实际是：

- `daily_new_20260518` ~ `daily_new_20260605`
- `new_framework_202409` ~ `new_framework_202603` 等批次目录
- `postclose_*`
- `smoke_*`
- `one_day_test`

`Z:\atomic_legacy_backup` 当前确认对象：

- `market_atomic_mainboard_full_reverse_20260516_pre_feature_store.db`：约 `40.21 GB`

判断：

1. `Z:\atomic_stage` 是 staging / 临时工作盘，不是正式真相目录。
2. `Z:\atomic_legacy_backup` 是冷备 / 历史回退对象，不是日常运行目录。
3. 后续 Windows 口径应明确成：
   - `D:\MarketData` = 原始包
   - `D:\market-live-terminal\data` = 正式产出
   - `Z:\atomic_stage` = staging
   - `Z:\atomic_legacy_backup` = 冷备
4. `2026-06-08` 已完成一轮退休收口：
   - `selection_research_windows.db` 与 `compact_smoke_20260401_20260515.db` 正式别名已移除
   - `model_feature_store_smoke_*` 与 atomic 历史测试/备份库已下沉到 `Z:\atomic_legacy_backup\windows_retired_20260608\`

## 4. NAS 实机盘点（2026-06-08）

### 4.1 当前服务状态

当前容器在线：

- `market-crawler-nas`
- `market-backend-nas`
- `market-frontend-nas`
- `gitea`
- `tailscale-nas`

说明：

1. NAS 已经是可运行的在线节点。
2. 但还不是“最终公网入口已完成”的状态。

### 4.2 当前数据根不算最终版

当前 NAS 数据根同时存在两套口径：

- 新结构：
  - `data/live/`
  - `data/research/current/`
  - `data/cache/`
  - `data/artifacts/`
  - `data/incoming/`
- 旧 root 实体：
  - `data/market_data.db`（约 `4.7 GB`）
  - `data/user_data.db`
  - `data/atomic_facts/`
  - `data/selection/`
  - `data/market_heat/`

实机确认：

1. 这些 root 对象当前不是软链，而是独立实体。
2. `data/live/market_data.db` 只有约 `2.0 MB`，和 root `data/market_data.db` 不是同一份对象。
3. `data/selection` 与 `data/research/current/selection`、`data/atomic_facts` 与 `data/research/current/atomic_facts` 当前也是并存实体，而不是单一 alias。

判断：

1. `2026-06-08` 已把 root old flat-data 实体下沉到 `/volume1/docker/market-live-terminal/backups/legacy_flat_root_20260608/`。
2. 当前 NAS 顶层正式数据根已收口为 `live / research/current / cache / artifacts / incoming`。
3. 这意味着 NAS 已基本完成目录退场治理，剩余只需继续观察在线稳定性。

### 4.3 NAS 还留着额外大区

当前还看到：

- `/volume1/docker/market-live-terminal/full-import`：约 `78 GB`
- `/volume1/docker/market-live-terminal/data-backup-20260528-211003`：约 `1.9 GB`

判断：

1. `full-import` 更像一次导入期保留区，不该长期和正式数据根并列。
2. `data-backup-*` 是阶段性备份，应纳入归档/备份口径，不应继续混在正式项目根旁。
3. `2026-06-08` 已执行下沉：
   - `full-import/` -> `backups/imports/full-import_20260608`
   - `data-backup-20260528-211003/` -> `backups/manual/data-backup-20260528-211003`

## 5. 公网入口当前状态

当前公网现状：

1. `Tailscale Funnel` 临时公网入口能用。
2. `tailscale-nas` 日志仍在报 `443` 端口冲突。
3. 仓库里已经有：
   - `deploy/docker-compose.cloudflare-tunnel.yml`
   - `ops/nas/nas_enable_cloudflare_tunnel.sh`
   - `ops/nas/nas_disable_tailscale_funnel.sh`
4. 但这些 Cloudflare 资产当前还没有真正部署到 NAS 上。

判断：

1. NAS 当前是“有临时公网入口”，不是“正式公网入口已落地”。
2. 最终版仍缺：
   - 自定义域名
   - Cloudflare Tunnel token
   - `cloudflared-nas` 实际启动
   - 正式域名验证

## 6. 对你当前工作模式的建议

结合“Mac 主开发、Windows 主跑数、NAS 主在线”的模式，推荐固定成下面这套：

### 6.1 Windows

保留：

1. `D:\MarketData`
2. `D:\market-live-terminal\data`
3. `D:\market-live-terminal\.run`
4. `D:\market-live-terminal\backend\scripts`
5. `D:\market-live-terminal\ops`
6. `start_live_crawler.bat`
7. `Z:\atomic_stage`
8. `Z:\atomic_legacy_backup`

不再按正式职责理解：

1. Windows 做 Git 主开发
2. Windows 做文档主编辑
3. Windows 保留无关开发目录

### 6.2 NAS

最终应固定成：

1. `/volume1/docker/market-live-terminal/app`：在线服务代码
2. `/volume1/docker/market-live-terminal/data/live`：在线轻量库
3. `/volume1/docker/market-live-terminal/data/research/current`：正式研究库
4. `/volume1/docker/market-live-terminal/data/research/staging`：待发布研究库
5. `/volume1/docker/market-live-terminal/data/research/archive`：回滚点
6. `/volume1/docker/market-live-terminal/data/cache`：缓存
7. `/volume1/docker/market-live-terminal/data/artifacts`：导出物
8. `/volume1/docker/market-live-terminal/data/incoming`：上传落地区

不该继续长期保留为并行正式层的：

1. `data/market_data.db`
2. `data/user_data.db`
3. `data/atomic_facts`
4. `data/selection`
5. `data/market_heat`
6. `full-import`
7. `data-backup-*`

## 7. 下一步执行顺序

### P1. Windows 数据站定性

1. 把 `D:\market-live-terminal` 正式定义成“运行数据站”，不再叫开发目录。
2. 清掉 0 MB 残留库和 0 字节 `file`。
3. 继续决定旧兼容名 `selection_research_windows.db`、`compact_smoke_*` 是否退休；canonical 名已经落盘，不再需要先做“改名试探”。

### P2. NAS 目录终版收口

1. 先盘清 root 旧实体与 `live/research/current` 的实际关系。
2. 再决定旧 root 实体下线策略。
3. `full-import`、`data-backup-*` 已纳入 `backups/`，不再继续挂在正式项目根。

### P3. 正式公网入口

1. 你提供正式域名
2. 你在 Cloudflare 创建 Tunnel，并提供 `CLOUDFLARE_TUNNEL_TOKEN`
3. 在 NAS 启动 `cloudflared-nas`
4. 验证 `app.<域名>` 和 `/api/health`
5. 关闭 `Tailscale Funnel`

## 8. 当前阻塞

当前真正阻塞“最终版公网入口”的不是代码，而是外部条件：

1. 正式域名
2. Cloudflare Tunnel token

当前真正阻塞“最终版 NAS 目录”的不是 Mac，而是 NAS 自己仍保留着 old flat-data 并行实体。

## 9. 本轮已执行动作

1. Windows 已创建 canonical 硬链接：
   - `D:\market-live-terminal\data\selection\selection_research.db`
   - `D:\market-live-terminal\data\atomic_facts\market_atomic_mainboard_compact_current.db`
2. NAS 已创建结构化备份区：
   - `/volume1/docker/market-live-terminal/backups/imports/`
   - `/volume1/docker/market-live-terminal/backups/manual/`
3. 仓库已新增 NAS 正式数据库快照脚本：
   - `ops/nas/nas_backup_runtime_db_snapshot.sh`
4. 仓库已新增三端存储与备份策略文档：
   - `docs/ops/storage-backup-policy.md`
