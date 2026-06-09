# NAS 盘中 crawler 切换 Runbook

更新时间：2026-06-04

## 1. 目的

这份 runbook 只服务一个任务：

- 把盘中 realtime crawler 从 Windows 切到 NAS

前提：

- `docs/ops/nas-migration-execution-plan.md` 的阶段 A 正在推进

## 2. 启用前检查

先确认：

1. NAS SSH 可达
2. NAS 查询主链已经稳定跑在 `research/current` 口径上
3. `http://dxp4800pro:8080/api/health` 或 `http://192.168.3.43:8080/api/health` 可达
4. NAS 当前 `backend` / `frontend` 容器正常
5. `.env.nas-full` 中 `INGEST_TOKEN` 已配置

建议先执行：

```bash
ssh -o ServerAliveInterval=5 -o ServerAliveCountMax=6 zhangdong@dxp4800pro 'echo ok'
curl http://dxp4800pro:8080/api/health
bash ops/nas/nas_probe_market_sources.sh
```

说明：

- 当前优先使用 `dxp4800pro` 这条 Tailscale 主机名链路
- `192.168.3.43` 只在本地局域网环境下作为备选
- 当前公网 Funnel 只用于访问验证，不作为 crawler 管理入口

## 3. 启用 crawler

执行：

```bash
bash ops/nas/nas_enable_crawler.sh
```

它会在 NAS 上执行：

```bash
docker compose --env-file .env.nas-full -f deploy/docker-compose.nas-full.yml --profile crawler up -d crawler
```

## 4. 查看状态

执行：

```bash
bash ops/nas/nas_check_crawler_status.sh
```

重点看三类信号：

1. `market-crawler-nas` 容器是否 `Up`
2. crawler 日志是否出现：
   - `Started Snapshot Poller`
   - `Started Trade Ticks Poller`
   - `Fetching Ticks`
   - `Pushed ... ticks to Cloud`
3. backend 日志是否出现：
   - `[Ingest] Saved ... snapshots`
   - `[Ingest] Overwrote ticks`

## 5. 验证数据库是否真的有 ingest

执行：

```bash
bash ops/nas/nas_verify_crawler_ingest.sh
```

重点看：

- `ticks_latest_date`
- `ticks_rows_latest_date`
- `snapshots_latest_date`
- `snapshots_rows_latest_date`

不能只看容器启动成功，必须确认 DB 真有增量。

## 6. 交易时段观察

至少观察：

1. 开盘前启动成功
2. 盘中出现 snapshot / tick 写入
3. 盘后 final sweep 执行

建议保留证据：

- `docker compose ps`
- crawler 日志 tail
- backend 日志 tail
- `nas_verify_crawler_ingest.sh` 输出

## 7. 切走 Windows 盘中 crawler

只有下面全部满足才允许切：

1. NAS crawler 启动正常
2. ingest 正常
3. 页面无退化
4. 至少完整观察过一个交易日
5. 当前 NAS 数据口径已经明确记录了它仍基于 bootstrap current 或后续补齐后的 current，避免把数据缺口误判成 crawler 缺陷

然后再：

- 暂停 Windows `ZhangDataLiveCrawler`
- 保留 Windows 盘后任务

## 8. 回退条件

出现下面任一情况，先回退，不要硬撑：

1. crawler 容器循环退出
2. NAS 到行情源网络不稳定
3. DB 没有实际新增记录
4. 盘后 final sweep 缺失
5. 前端盯盘明显退化

回退动作：

1. 执行 `bash ops/nas/nas_disable_crawler.sh` 停掉 NAS crawler
2. 恢复 Windows `ZhangDataLiveCrawler`
3. 保留 NAS 日志和 DB 证据继续排查

## 9. 2026-06-04 当前推进结果

本轮 `A1` 已完成在线跑通验证，当前状态已经从“容器已启动待验证”推进到“ticks + snapshots 均已确认落库”，但仍未达到“立刻下掉 Windows 盘中 crawler”的最终切换线。

### 9.1 本轮已确认的事实

- NAS `crawler` 容器已经成功拉起：
  - `market-crawler-nas   Up`
- NAS 后端未被 crawler 拖挂：
  - `market-backend-nas   Up`
  - `/api/health`、`/api/selection/health` 可继续返回 `200`
- `ops/nas/nas_probe_market_sources.sh` 已验证：
  - NAS 主机可访问 `qt.gtimg.cn`
  - crawler 容器内也可访问 `qt.gtimg.cn`
- `ops/nas/nas_verify_crawler_ingest.sh` 已验证：
  - `trade_ticks` 已写入 `2026-06-04`
  - `sentiment_snapshots` 也已写入 `2026-06-04`
- 交易时段补验后确认：
  - `active_symbols` 返回：
    - `warm_symbols=["sh600693"]`
  - crawler 日志出现：
    - `-> Pushed 3343 ticks to Cloud`
    - `-> Pushed 1 snapshots to Cloud`
    - `-> Pushed 3356 ticks to Cloud`
    - `-> Pushed 3366 ticks to Cloud`
- 数据库统计已确认持续增长：
  - 第一轮：
    - `ticks_rows_latest_date: 3343`
    - `ticks_max_time_today: 13:54:22`
    - `snapshots_rows_latest_date: 10`
    - `snapshots_max_ts_today: 13:54:37`
  - 继续观察后：
    - `ticks_rows_today: 3374`
    - `ticks_max_time_today: 13:56:13`
    - `snapshots_rows_today: 17`
    - `snapshots_max_ts_today: 13:56:34`

### 9.2 本轮发现的问题

- 原始运维脚本默认 `NAS_HOST` 当时仍指向 `zhangdong@192.168.3.43`
- 当前实际更稳定的运维入口应优先走：
  - `zhangdong@dxp4800pro`
  - 或 `zhangdong@100.119.0.126`
- crawler 的 snapshot 采集代码原来请求的是：
  - `http://qt.gtimg.cn/q=s_<market><code>`
- 但后续解析却按完整版字段位读取，导致 `fetch_tencent_snapshot()` 实际上很容易返回 `None`
- 本轮已把本地代码修正为：
  - 直接请求 `http://qt.gtimg.cn/q={symbol}`
  - 对 snapshot POST 增加返回码检查和日志
- 本轮也已把 `ops/nas/nas_enable_crawler.sh`、`ops/nas/nas_disable_crawler.sh`、`ops/nas/nas_check_crawler_status.sh`、`ops/nas/nas_verify_crawler_ingest.sh`、`ops/nas/nas_probe_market_sources.sh` 的默认 `NAS_HOST` 改为 `zhangdong@dxp4800pro`

### 9.3 当前仍未完成的验收项

- 还没有完整覆盖一个交易日
- 还没有完成“停掉 Windows 盘中 crawler 后连续观察 2 个交易日稳定”
- 因此当前仍不建议立刻切走 Windows 盘中 crawler

### 9.4 当前结论

截至本轮，`A1` 的状态应记为：

- `crawler 容器已运行`
- `ticks ingest 已确认`
- `snapshot ingest 已确认`
- `A1 已跑通，但仍处在观察期`
- `Windows 盘中 crawler 暂不下线，等观察期通过后再切`
