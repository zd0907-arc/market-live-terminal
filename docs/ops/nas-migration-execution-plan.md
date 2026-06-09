# NAS 迁移执行规划

更新时间：2026-06-04

关联文档：

- [nas-migration-master-plan.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/ops/nas-migration-master-plan.md)
- [nas-crawler-cutover-runbook.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/ops/nas-crawler-cutover-runbook.md)
- [nas-research-release-runbook.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/ops/nas-research-release-runbook.md)
- [market-data-reclassification-plan.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/ops/market-data-reclassification-plan.md)

## 1. 这份文档怎么用

这份文档只服务一件事：后续每次开“目标模式”时，直接按这里定义的当前子任务推进。

执行规则：

- 一次只推进一个子任务
- 没有证据，不算完成
- 腾讯云先不动
- 能在线推进就优先在线推进
- 不能在线推进时，立即切到离线推进线，不空等

每次目标模式都固定写 5 个字段：

1. `objective`
2. `scope`
3. `done definition`
4. `evidence required`
5. `fallback if blocked`

通用模板：

```text
按 docs/ops/nas-migration-execution-plan.md 推进 <子任务编号>。
范围只限于本文档定义的当前子任务。
完成标准是该子任务的验收证据全部拿到并回写到对应 runbook / 规划文档。
如果当前子任务因为 NAS 不可达或运行条件不满足无法继续，则切到本文档规定的下一条推进线。
```

## 2. 当前执行基线

### 2.1 已确认的在线事实

- NAS 当前可以通过以下入口访问：
  - 局域网：`http://192.168.3.43:8080`
  - Tailscale 私网：`http://dxp4800pro:8080`
  - Tailscale Funnel 临时公网：`https://dxp4800pro.tailfff556.ts.net/`
- Tailscale Funnel 对访问者不要求安装 Tailscale 客户端
- 但当前公网方案仍然不算 `D1` 完成；`D1` 仍要求 `Cloudflare Tunnel + 自定义域名`
- 当前容器已验证在运行：
  - `market-backend-nas`
  - `market-frontend-nas`
  - `gitea`
  - `tailscale-nas`
- 当前查询链路已验证可用：
  - `/api/health`
  - `/api/selection/health`
  - `/api/selection/daily-candidates`
  - `/api/market_heat/latest`
  - `/api/trend-research/ideas`
  - `/selection-research`

### 2.2 已确认的部署事实

- NAS 线上容器已经切到新版 compose 口径
- 关键环境变量已经变成：
  - `FORMAL_MARKET_DATA_ROOT=/runtime-data`
  - `LIVE_DATA_ROOT=/runtime-data/live`
  - `RESEARCH_CURRENT_ROOT=/runtime-data/research/current`
  - `DB_PATH=/runtime-data/live/market_data.db`
  - `SELECTION_DB_PATH=/runtime-data/research/current/selection/selection_research.db`
  - `ATOMIC_FACTS_DIR=/runtime-data/research/current/atomic_facts`
  - `MARKET_HEAT_DIR=/runtime-data/research/current/market_heat`
- 这说明：
  - `B1c` 已完成
  - NAS 查询主链已经切到新目录口径

### 2.3 已确认的数据根事实

- NAS 目标目录骨架已存在：
  - `live/`
  - `research/current`
  - `research/staging`
  - `research/archive`
  - `cache/market_heat`
  - `cache/eastmoney_sector_cache`
  - `artifacts/market_heat`
  - `artifacts/selection`
  - `incoming`
- 当前 `research/current` 不是一版从本地完整上传的正式 release
- 当前 `research/current` 是基于 NAS 既有 flat 数据整理出的 bootstrap current
- 当前 bootstrap current 的关键标记为：
  - `.release_name = nas_release_bootstrap_from_flat_20260604`
- 当前 NAS 研究数据日期大致为：
  - atomic / selection / feature / index / heat_v2：`2026-05-27`
  - heat_v1：`2026-04-30`
  - forecast：`2026-05-13`

这说明：

- 迁移结构已经跑通
- 但数据仍落后于本地正式数据

### 2.4 已确认的本地正式库事实

- 本地正式数据根：`/Users/dong/Desktop/AIGC/market-data`
- 本地正式库关键日期已经比 NAS 新：
  - atomic / selection / model feature / market index：`2026-06-02`
  - `fine_theme_heat_daily_v2.db`：`2026-06-02`
  - `fine_theme_heat_daily.db`：`2026-04-30`
  - `forecast`：`2026-05-13`
- 这意味着后续更合理的动作不是全量重传 79GB，而是定向补齐 `2026-05-27` / `2026-05-28` 之后缺失的几天

### 2.5 已确认的离线资产与测试事实

- 阶段 B 脚本链已具备可用基础：
  - `ops/nas/nas_prepare_research_dirs.sh`
  - `ops/nas/build_nas_research_release_manifest.sh`
  - `ops/nas/check_nas_research_release.sh`
  - `ops/nas/upload_nas_research_release.sh`
  - `ops/nas/rewrite_market_heat_release_metadata.sh`
  - `ops/nas/nas_publish_research_release.sh`
  - `ops/nas/nas_rollback_research_release.sh`
  - `ops/nas/nas_list_research_releases.sh`
  - `ops/nas/nas_smoke_research_release.sh`
  - `ops/nas/nas_run_phase_b_release.sh`
- 阶段 C 的一批路径治理已经完成并有测试支撑

## 3. 当前任务顺序

长期收口顺序不变：

1. 阶段 A：NAS 接管盘中 realtime crawler
2. 阶段 B：Windows 收口成盘后工人机，并建立研究库发布 / 同步链
3. 阶段 C：`market-data` 路径治理与物理收口
4. 阶段 D：正式公网域名接入
5. 阶段 E：腾讯云退役决策

但按当前现场事实，执行顺序更新为：

1. `A1`：先让 NAS 接管盘中 realtime crawler
2. `B1-补`：定向补齐 NAS 上缺失日期数据
3. `C1`：继续完成 `market-data` 与 NAS 数据目录治理
4. `B2`：把 Windows 盘后跑数后的同步机制改成以 NAS 为中心
5. `D1`：Cloudflare Tunnel + 自定义域名
6. `E1`：腾讯云退役决策

切线规则：

- 交易时段可观察窗口充足：优先 `A1`
- 非交易时段或不适合启 crawler：优先 `B1-补` 或 `C1`
- `A1` 没完成前，不允许下线 Windows 盘中 crawler
- `B1-补` 没完成前，不能把 NAS 数据日期误判为已经追平本地正式库
- 当前 Funnel 可用，不允许把它误记成 `D1` 完成

## 4. 子任务清单

### A1：NAS 接管盘中 realtime crawler

适用条件：

- `B1c` 已完成
- full 查询版稳定
- 当前可进入交易日验证窗口

目标模式建议：

```text
按 docs/ops/nas-migration-execution-plan.md 推进 A1，让 NAS 接管盘中 realtime crawler，并用容器状态、日志、API 和数据库证据验证它可以替代 Windows 盘中链路。
```

执行入口：

- `bash ops/nas/nas_probe_market_sources.sh`
- `bash ops/nas/nas_run_phase_a.sh`
- `bash ops/nas/nas_check_crawler_status.sh`
- `bash ops/nas/nas_verify_crawler_ingest.sh`

完成标准：

- `market-crawler-nas` 容器稳定运行
- crawler 日志出现 fetch / push 成功记录
- `live/market_data.db` 的 `trade_ticks`、`sentiment_snapshots` 行数增长
- `live/user_data.db` 的 `watchlist` 可读
- realtime 相关接口返回更新数据
- Windows 盘中 crawler 暂停后，NAS 连续 2 个交易日稳定

证据必须回写到：

- [nas-crawler-cutover-runbook.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/ops/nas-crawler-cutover-runbook.md)

### B1-补：定向补齐 NAS 缺失日期数据

适用条件：

- 当前 bootstrap current 已可运行
- 本地正式库日期新于 NAS

目标模式建议：

```text
按 docs/ops/nas-migration-execution-plan.md 推进 B1-补，以 NAS 当前 bootstrap research/current 为基线，只同步 2026-05-27 / 2026-05-28 之后缺失的正式数据，不重做一次全量 79GB 上传。
```

完成标准：

- NAS `research/current` 的关键日期追平到目标日期
- `market_heat/latest.json` 等元数据仍指向 current 内合法路径
- 关键页面 / API smoke 复核通过

证据必须回写到：

- [nas-research-release-runbook.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/ops/nas-research-release-runbook.md)

说明：

- 这一步是“补齐缺口”，不是“重做全量发版”

### C1：`market-data` 路径治理彻底收口

适用条件：

- 在线窗口不足
- 或 A1 / B1-补 之外需要继续离线推进

目标模式建议：

```text
按 docs/ops/nas-migration-execution-plan.md 推进 C1，继续完成 market-data 的路径依赖审计、硬编码清理、NAS 数据目录分层和运行态目录治理。
```

完成标准：

- 剩余高风险脚本不再依赖旧机器路径
- 服务 / API 不再向前端暴露本机绝对路径
- `live/`、`research/current/` 路径口径覆盖关键服务和高频研究脚本
- NAS 侧正式库 / 缓存 / 产物 / incoming 的目录边界有正式落位方案

证据必须回写到：

- [market-data-reclassification-plan.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/ops/market-data-reclassification-plan.md)

### B2：Windows 盘后跑数后的同步机制改造

适用条件：

- A1 已基本稳定
- 当前不再把 Mac 当生产数据中转站

目标模式建议：

```text
按 docs/ops/nas-migration-execution-plan.md 推进 B2，把 Windows 盘后正式跑数后的同步目标改成 NAS，而不是继续先回 Mac。
```

完成标准：

- Windows 跑数后有明确同步到 NAS 的入口
- 同步目标是 NAS `staging` 或约定目录，而不是 Mac 本地目录
- 发布 / 校验 / 回滚边界清楚

证据必须回写到：

- [nas-research-release-runbook.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/ops/nas-research-release-runbook.md)
- [nas-migration-master-plan.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/ops/nas-migration-master-plan.md)

### D1：正式公网域名接入

适用条件：

- `A1`
- `B1-补`
- `C1`
- `B2`

都已经稳定

目标模式建议：

```text
按 docs/ops/nas-migration-execution-plan.md 推进 D1，为 NAS 配置 Cloudflare Tunnel 和正式公网域名，并完成基础访问保护。
```

完成标准：

- 外网可访问
- 不依赖局域网 IP
- 不依赖 Tailscale 客户端
- 使用自定义域名
- 不暴露裸应用端口

### E1：腾讯云退役决策

这一步现在不执行。

前提：

- `A1`
- `B1-补`
- `C1`
- `B2`
- `D1`

全部稳定

目标：

- 只做退役决策和回退预案
- 不默认立即下线腾讯云

## 5. 当前建议的下一目标

当前最合理的下一目标仍然是 `A1`。

原因：

- 当前 NAS 查询主链已经切到 `research/current`
- 当前 bootstrap current 已经支持完整查询版运行
- 真正还没切走的是盘中 realtime crawler
- 这一步完成后，Windows 才能开始收口成纯盘后工人机

补充边界：

- 当前 NAS 上的数据不是最新
- 但“数据还没最新”不再阻塞 `A1`
- 当前公网临时通路已经有了
- 但“公网临时通路已通”也不等于 `D1` 完成

直接可用的目标模式文本：

```text
按 docs/ops/nas-migration-execution-plan.md 推进 A1，让 NAS 接管盘中 realtime crawler，并用容器状态、日志、API 和数据库证据验证它可以替代 Windows 盘中链路。
范围只限于 A1。
完成标准是 market-crawler-nas 容器稳定运行、ingest 写入增长、realtime 相关接口有更新结果，并把证据回写到 docs/ops/nas-crawler-cutover-runbook.md。
```

## 6. 证据落点规则

每次目标模式结束，至少落下 3 类证据；部署类任务必须包含容器状态和日志：

1. 配置或脚本改动
2. 命令输出
3. `docker ps` / `docker compose ps`
4. 日志片段
5. 页面 / API 验证结果
6. pytest 或脚本校验结果

回写位置固定：

- 阶段 A：`docs/ops/nas-crawler-cutover-runbook.md`
- 阶段 B：`docs/ops/nas-research-release-runbook.md`
- 阶段 C：`docs/ops/market-data-reclassification-plan.md`
- 阶段 D / E：本文件或单独部署记录

## 7. 当前结论

接下来不要再把事情描述成“NAS 还没迁过去”。

当前真实状态是：

- NAS 已经承载查询主链
- 公开临时访问已经通
- 但还没接盘中 crawler
- 还没补齐缺失日期数据
- 还没完成目录治理
- 还没把 Windows 跑数同步机制改成以 NAS 为中心
- 还没做正式公网域名

接下来只按这个顺序推进：

1. `A1`
2. `B1-补`
3. `C1`
4. `B2`
5. `D1`
