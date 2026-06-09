# NAS research 发布 Runbook

更新时间：2026-06-02

## 1. 目的

这份 runbook 只服务一个任务：

- 把 Windows 盘后产物稳定发布到 NAS `research/current`

它不负责盘中 realtime crawler，也不负责公网域名。

## 2. 目标目录口径

NAS 数据根统一按下面结构：

```text
/volume1/docker/market-live-terminal/data/
  live/
  research/
    current/
    staging/
    archive/
  cache/
  artifacts/
  incoming/
```

其中：

- `live/`：盘中在线轻量库
- `research/current/`：当前正式研究库
- `research/staging/<release_name>/`：Windows 新产物待发布区
- `research/archive/<archive_name>/`：旧版回滚点

## 3. 一次性准备

先建目录：

```bash
bash ops/nas/nas_prepare_research_dirs.sh
```

完成标准：

- NAS 上 `live/`、`research/current/`、`research/staging/`、`research/archive/` 都存在

## 4. staging 目录要求

Windows 每次盘后交付一版时，先把完整产物传到：

```text
research/staging/<release_name>/
```

当前已提供两种入口：

1. 先在当前正式数据根生成 release 清单：

```bash
bash ops/nas/build_nas_research_release_manifest.sh <release_name>
```

2. 直接把这版 release 上传到 NAS staging：

```bash
bash ops/nas/upload_nas_research_release.sh <release_name>
```

如果要一口气跑完整个阶段 B 发布链，可直接执行：

```bash
bash ops/nas/nas_run_phase_b_release.sh <release_name>
```

3. 发布前先做 release 校验：

```bash
bash ops/nas/check_nas_research_release.sh /Users/dong/Desktop/AIGC/market-data
```

这一步主要验证正式库、正式表、关键交易日是否完整。

如果已经上传到 NAS staging，也可以直接校验 staging 版本目录：

```bash
ssh zhangdong@dxp4800pro \
  'bash /volume1/docker/market-live-terminal/app/ops/nas/check_nas_research_release.sh /volume1/docker/market-live-terminal/data/research/staging/<release_name>'
```

区别要点：

- 校验本地 `market-data` 时，重点是正式库 / 正式表 / 关键交易日是否完整
- 校验 NAS `staging/<release_name>` 或 `current/` 时，会额外强制检查：
  - `market_heat/latest.json` 的 `meta.atomic_db` 已指向 release 内的 `atomic_facts/market_atomic_mainboard_compact_current.db`

最低要求必须包含：

- `atomic_facts/`
- `selection/`
- `market_heat/`

推荐 release 命名：

- `20260529_postclose`
- `20260529_postclose_r1`

## 5. 发布 current

发布命令：

```bash
bash ops/nas/nas_publish_research_release.sh <release_name>
```

例子：

```bash
bash ops/nas/nas_publish_research_release.sh 20260529_postclose
```

发布动作：

1. 校验 staging 版本目录存在
2. 校验 `atomic_facts/ selection/ market_heat/` 三个必要目录存在
3. 若 `current/` 已有正式版本，先整体挪到 `archive/<timestamp>_<release_name>/`
4. 把 `staging/<release_name>` 直接提升为 `current/`
5. 写入 `.release_name` 和 `.published_at`
6. 发布后执行：

```bash
bash ops/nas/nas_smoke_research_release.sh
```

它会做三件事：

- 校验 `research/current/`
- 刷新 `fine_dashboard` cache
- 冒烟 `/api/health`、`/api/selection/health`、`/api/selection/daily-candidates`、`/api/market_heat/latest`、`/api/trend-research/ideas`

如果希望在发布命令后自动连跑这一步，可执行：

```bash
RUN_SMOKE_AFTER_PUBLISH=true bash ops/nas/nas_publish_research_release.sh <release_name>
```

## 6. 查看当前版本

```bash
bash ops/nas/nas_list_research_releases.sh
```

重点看：

- 当前 `current/` 是否存在
- 当前 `.release_name`
- staging 里还有哪些待发布版本
- archive 里有哪些可回滚版本

## 7. 回滚

如果当前版本有问题，执行：

```bash
bash ops/nas/nas_rollback_research_release.sh <archive_name>
```

例子：

```bash
bash ops/nas/nas_rollback_research_release.sh 20260529_231500_20260529_postclose
```

回滚动作：

1. 当前 `current/` 若非空，先归档成 `archive/failed_<timestamp>/`
2. 指定 archive 版本提升回 `current/`
3. 写入 `.rollback_from_archive` 和 `.rolled_back_at`

## 8. 发布后校验

至少要留这几类证据：

1. `bash ops/nas/nas_list_research_releases.sh` 输出
2. `docker compose ps`
3. 页面 / API 抽样验证
4. `release_manifest.json`
5. `bash ops/nas/check_nas_research_release.sh ...` 输出
6. `bash ops/nas/nas_smoke_research_release.sh` 输出

建议最少验证：

- `/api/selection/health`
- `/api/selection/daily-candidates`
- `/api/market_heat/latest`
- `/api/trend-research/ideas`
- `/selection-research`

## 9. 当前边界

这份 runbook 当前只解决：

- NAS research 目录准备
- staging -> current 发布
- archive 回滚

它当前不直接解决：

- Windows 如何自动上传 staging
- 发布前的内容级校验
- 公网域名

## 10. B0 离线验证证据

更新时间：2026-06-02

这部分只记录当前 NAS 不可达时，阶段 B0 已拿到的离线证据。

### 10.1 已验证命令

以下脚本已通过 `bash -n`：

- `ops/nas/nas_prepare_research_dirs.sh`
- `ops/nas/build_nas_research_release_manifest.sh`
- `ops/nas/check_nas_research_release.sh`
- `ops/nas/rewrite_market_heat_release_metadata.sh`
- `ops/nas/upload_nas_research_release.sh`
- `ops/nas/nas_publish_research_release.sh`
- `ops/nas/nas_rollback_research_release.sh`
- `ops/nas/nas_list_research_releases.sh`
- `ops/nas/nas_smoke_research_release.sh`
- `ops/nas/nas_run_phase_b_release.sh`

### 10.2 自动化测试

已新增：

- [test_nas_release_scripts.py](/Users/dong/Desktop/AIGC/market-live-terminal/backend/tests/test_nas_release_scripts.py)

执行结果：

```bash
pytest -q backend/tests/test_nas_release_scripts.py
```

结果：

- `6 passed`

覆盖点：

1. `build_nas_research_release_manifest.sh`
   - flat `market-data/` 口径可生成 manifest
   - `research/current/` 口径优先级正确
2. `check_nas_research_release.sh`
   - 本地 flat 正式库不会因为旧 `latest.json` 路径失败
   - 本地 `market-data/research/current` 不会被误判成 NAS 已发布 `current`
   - 带 `.release_name` 的已发布 `current` 会强制检查 release metadata
3. `rewrite_market_heat_release_metadata.sh`
   - 只改写带 `meta` 的 JSON
   - 不会给老 cache 强塞 `meta`
4. `nas_prepare_research_dirs.sh`
   - 可在 fake remote 下正确建出 `live/ research/current/ staging/ archive/ cache/ artifacts/ incoming`
5. `upload_nas_research_release.sh`
   - 可用 manifest 将正式库上传到 `staging/<release_name>`
   - 上传后会执行 metadata rewrite
6. `nas_publish_research_release.sh`
   - `staging -> current` 可完成
   - 旧 `current` 会进入 `archive`
   - 发布后会再次 rewrite `current`
7. `nas_rollback_research_release.sh`
   - archive 可提升回 `current`
   - 失败版本会被归档到 `failed_<timestamp>`
8. `nas_list_research_releases.sh`
   - 可列出 `current / staging / archive`
9. `nas_run_phase_b_release.sh`
   - 本地自检、上传、远端校验、发布、smoke 可串起来

### 10.3 本轮修正的两个关键问题

#### 问题 1：本地 `research/current` 被误判成 NAS 已发布 `current`

现象：

- `ops/nas/check_nas_research_release.sh` 之前只要目录名叫 `current`，就会强制要求 `market_heat/latest.json` 指向 release 内 atomic 路径。
- 这会导致本地 `FORMAL_MARKET_DATA_ROOT/research/current` 无法通过阶段 B 的本地自检。

修正：

- 现在自动模式只在下面几种情况下强制 `enforce_release_metadata=true`：
  - 目录里存在 `release_manifest.json`
  - 目标目录父级是 `staging` 或 `archive`
  - 目标目录名为 `current` 且目录里存在 `.release_name`

#### 问题 2：发布后 `current/latest.json` 仍指向 `staging` 路径

现象：

- `upload_nas_research_release.sh` 会先把 `latest.json` 改写到 `staging/<release_name>/atomic_facts/...`
- 如果直接 `mv staging/<release_name> -> current`，那么 `latest.json` 里的 `atomic_db` 仍保留旧 staging 路径

修正：

- `ops/nas/nas_publish_research_release.sh` 现在在两处补做 rewrite：
  1. 旧 `current` 归档到 `archive` 后，重写 archive 内 metadata
  2. 新 release 提升为 `current` 后，立即重写 current 内 metadata

### 10.4 当前结论

阶段 B0 里“脚本测试和文档证据”这一块已经补齐。

仍未完成的只有在线证据：

- NAS `staging -> current` 实机发布
- NAS `smoke` 实机输出
- 页面 / API 实机验证

## 11. B1a 当前推进状态

更新时间：2026-06-02

这部分只记录阶段 `B1a` 当前已经拿到的事实，以及当前尚未完成的在线阻塞。

### 11.1 本地正式库已重新校验

执行：

```bash
bash ops/nas/build_nas_research_release_manifest.sh nas_release_20260602_online
bash ops/nas/check_nas_research_release.sh /Users/dong/Desktop/AIGC/market-data
```

当前结果：

- `release_name`: `nas_release_20260602_online`
- `member_count`: `136`
- `total_size_bytes`: `78916500093`
- 本地正式库校验已通过
- 当前关键日期：
  - `atomic_trade_daily`: `2026-06-02`
  - `selection_candidate_daily`: `2026-06-02`
  - `model_feature_daily_v1`: `2026-06-02`
  - `model_market_index_daily`: `2026-06-02`
  - `fine_theme_heat_daily_v2`: `2026-06-02`
- 已知旧口径仍存在：
  - `fine_theme_heat_daily.db`: `2026-04-30`
  - `fine_theme_heat_forecast.db`: `2026-05-13`
  - `market_heat/latest.json` 仍指向 `full_reverse`，上传到 `staging/current` 后必须 rewrite

### 11.2 本轮发现并修复的本地正式库问题

问题：

- `/Users/dong/Desktop/AIGC/market-data/selection/model_feature_store.db` 当时在原路径无法打开
- 直接执行：

```bash
sqlite3 /Users/dong/Desktop/AIGC/market-data/selection/model_feature_store.db '.tables'
```

会报：

- `Error: unable to open database file`

但复制到 `/private/tmp/model_feature_store_probe.db` 后可正常打开，并且：

```bash
sqlite3 /private/tmp/model_feature_store_probe.db 'pragma integrity_check;'
```

结果为：

- `ok`

说明：

- 数据内容本身没有坏
- 问题在原文件实体，不在数据库内容

处理：

- 已保留原文件备份：
  - `/Users/dong/Desktop/AIGC/market-data/selection/model_feature_store.db.backup_20260602_101012`
- 已把经过校验可读的副本原地替换回：
  - `/Users/dong/Desktop/AIGC/market-data/selection/model_feature_store.db`

修复后验证：

```bash
sqlite3 /Users/dong/Desktop/AIGC/market-data/selection/model_feature_store.db 'pragma integrity_check;'
```

结果：

- `ok`

### 11.3 上传脚本当前状态

`ops/nas/upload_nas_research_release.sh` 本轮已完成两处补强：

1. `scp` 上传模式已通过本地 fake remote 验证
2. SSH / `scp` 的 `ConnectTimeout` 已提取为环境变量：

```bash
SSH_CONNECT_TIMEOUT="${SSH_CONNECT_TIMEOUT:-8}"
```

这样在 NAS 响应慢时，可以直接用：

```bash
SSH_CONNECT_TIMEOUT=20 bash ops/nas/upload_nas_research_release.sh <release_name>
```

不需要再改脚本。

本地验证结果：

```bash
bash -n ops/nas/upload_nas_research_release.sh
pytest -q backend/tests/test_nas_release_scripts.py
```

结果：

- `bash -n` 通过
- `6 passed`

### 11.4 当前未完成项

原计划里的真实 `B1a` 大库上传还没完成。

最近一次尝试执行：

```bash
bash ops/nas/upload_nas_research_release.sh nas_release_20260602_online
```

实际阻塞：

- `ssh: connect to host dxp4800pro port 22: Operation timed out`

随后复测：

```bash
ssh -o BatchMode=yes -o ConnectTimeout=8 zhangdong@dxp4800pro 'echo ok'
ssh -o BatchMode=yes -o ConnectTimeout=20 zhangdong@dxp4800pro 'echo ok'
```

结果仍然都是：

- `Operation timed out`

当前结论：

- 本地发布输入已经就绪
- 上传脚本已经就绪
- 当前阻塞只剩 NAS SSH 连通性恢复

## 12. B1 当前实机落地结果（2026-06-04）

更新时间：2026-06-04

这部分记录阶段 `B1` 在当前现场条件下的真实收口方式。

### 12.1 为什么这次没有先走 79GB 大上传

现场事实：

- NAS 上已有一套可工作的 flat 正式库：
  - `atomic_facts/`
  - `selection/`
  - `market_heat/`
- 当前主要目标是先把迁移结构跑通，而不是先把 NAS 数据追到最新
- 从 Mac 上传完整正式库接近 `79GB`，而现场 `SSH` 经常在长连接下超时

因此本轮采用的策略不是：

- `Mac -> NAS` 先传完整新 release

而是：

- 直接复用 NAS 现有 flat 研究库
- 在 NAS 本机引导出 `research/current`
- 先完成 `B1b + B1c`
- 后续再补“缺失日期同步”

### 12.2 本轮实际执行的 `B1b`

执行结果：

- 已在 NAS 上创建：
  - `/volume1/docker/market-live-terminal/data/research/current`
- 当前 `research/current` 不是一份物理复制的大 release，而是指向现有 flat 库的符号链接：
  - `atomic_facts -> ../../atomic_facts`
  - `selection -> ../../selection`
  - `market_heat -> ../../market_heat`
- 已写入：
  - `.release_name = nas_release_bootstrap_from_flat_20260604`
  - `.published_at = 2026-06-04 11:37:23`
- 已执行：
  - `bash ops/nas/rewrite_market_heat_release_metadata.sh /volume1/docker/market-live-terminal/data/research/current`

验证结果：

- `bash ops/nas/check_nas_research_release.sh /volume1/docker/market-live-terminal/data/research/current`
  已通过
- `latest.json` 的 `meta.atomic_db` 已重写为：
  - `/volume1/docker/market-live-terminal/data/research/current/atomic_facts/market_atomic_mainboard_compact_current.db`

当前 `research/current` 数据日期：

- `atomic_trade_daily`：`2026-05-27`
- `selection_candidate_daily`：`2026-05-27`
- `model_feature_daily_v1`：`2026-05-27`
- `model_market_index_daily`：`2026-05-27`
- `fine_theme_heat_daily_v2`：`2026-05-27`
- `fine_theme_heat_daily.db`：`2026-04-30`
- `fine_theme_heat_forecast.db`：`2026-05-13`

说明：

- 这一步完成的是“结构迁移”和“口径切换”
- 不是“数据已更新到本地 2026-06-03”

### 12.3 本轮实际执行的 `B1c`

执行：

```bash
cd /volume1/docker/market-live-terminal/app
docker compose --env-file .env.nas-full -f deploy/docker-compose.nas-full.yml up -d --build backend frontend
```

结果：

- `market-backend-nas` 已按新版 compose 重建启动
- `market-frontend-nas` 已按新版 compose 重建启动

启动后确认后端环境变量已经切到新口径：

- `FORMAL_MARKET_DATA_ROOT=/runtime-data`
- `LIVE_DATA_ROOT=/runtime-data/live`
- `RESEARCH_CURRENT_ROOT=/runtime-data/research/current`
- `DB_PATH=/runtime-data/live/market_data.db`
- `SELECTION_DB_PATH=/runtime-data/research/current/selection/selection_research.db`
- `ATOMIC_FACTS_DIR=/runtime-data/research/current/atomic_facts`
- `MARKET_HEAT_DIR=/runtime-data/research/current/market_heat`

### 12.4 当前 smoke 结果

已验证通过：

- `GET /api/health`
- `GET /api/selection/health`
- `GET /api/selection/daily-candidates?limit=3`
- `GET /api/market_heat/latest`
- `GET /api/trend-research/ideas`
- `GET /selection-research`

当前实际结论：

- NAS 前后端已经按新版 compose 跑在 `research/current` 口径上
- 迁移结构已跑通
- 当前 NAS 查询主链已经不再是“只读旧 flat 直接口径”
- 但 `research/current` 目前仍是基于 NAS 旧 flat 研究库引导出来的 bootstrap 版本

### 12.5 本轮之后还没完成的事

本轮完成的是：

- `B1b`
- `B1c`

本轮没有完成的是：

- 按原计划把本地最新正式库完整上传到 `research/staging/<release_name>`
- 用真正的 staged release 替换当前 bootstrap current

所以后续还需要补一轮：

1. 把本地更新到 `2026-06-03` 的正式库上传到 NAS
2. 再把 `research/current` 从当前 bootstrap 版本切到真正的 staged release

但这已经不再阻塞“迁移先跑通”这个目标。
