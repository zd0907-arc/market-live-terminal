# MOD-20260606-09 Phase 7 治理收尾审计

## 1. 基本信息
- 标题：Phase 7 治理收尾审计
- 状态：DONE
- 负责人：Codex
- 关联 Task ID：`MOD-20260606-09-phase7-governance-closeout-audit`
- 关联 CAP：`CAP-DOCS-GOVERNANCE`, `CAP-NAS-OPS`, `CAP-SELECTION-RESEARCH`
- 关联 STG：`MOD-20260606-02`, `MOD-20260606-03`, `MOD-20260606-08`

## 2. 背景与目标

前 6 个 phase 已分别完成真相收口、资产盘点、首批文件治理、文档统一和三端协作校验。  
最后这一张卡只做一件事：把“看起来已经差不多”压成“有证据的完成状态”，避免后续新会话再次把本轮治理当成未完成事项重开。

## 3. 本轮收尾要回答的问题

1. 总控卡的阶段目标是否都已有证据支撑。
2. 仓库体积下降、残留大对象和删改边界是否已写清。
3. `Mac / Windows / NAS` 三端协作是否已具备当前正式口径与运行证据。
4. `07_PENDING_TODO` 是否还把已收口事项继续挂成 ACTIVE。

## 4. 核心结论

### 4.1 本轮治理主目标已达成

当前已经可以确认：

1. 仓库文件层已形成“正式对象 / 兼容对象 / 候选归档 / 候选删除”的清单，不再是只看体积猜垃圾。
2. 高曝光文档已统一到当前真相，不再把旧 Cloud 叙事、repo 内 fallback 库或根目录历史库误写成正式主线。
3. `Mac -> NAS` 控制面、Git、`research/current` 发布链和线上服务当前均有直接验证证据。

### 4.2 本轮没有继续扩 scope

以下对象本轮刻意不当成“继续清理”的目标：

1. `docs/portfolio-ops/*`
2. 外部 `/Users/dong/Desktop/AIGC/market-data`
3. `data/market_data.db`
4. `data/selection/selection_research.db`
5. 最近两天 `.run/daily_new_framework/*processed*`

原因：它们要么是用户明确排除，要么仍有正式兼容语义。

## 5. 最终证据

### 5.1 体积与大文件

- 当前仓库约 `6.2G`
- 当前 `data/` 约 `5.0G`
- 当前 `.run/` 约 `507M`
- 当前 `data/legacy/` 约 `1.9G`

剩余 `>100MB` 文件只有：

1. `.git/objects/pack/pack-01836c0fdc256dbd0596dab8ae834dad86dce62c.pack`
2. `.run/daily_new_framework/20260604/processed/atomic_day_delta_20260604.db`
3. `.run/daily_new_framework/20260605/processed/atomic_day_delta_20260605.db`
4. `data/legacy/root_market_data_history.db`
5. `data/market_data.db`
6. `data/selection/selection_research.db`

### 5.2 自动化验证

执行：

```bash
pytest -q backend/tests/test_market_data_path_config.py \
  backend/tests/test_research_script_path_defaults.py \
  backend/tests/test_nas_release_scripts.py
```

结果：

- `14 passed`

### 5.3 NAS 运行态验证

执行：

```bash
bash ops/nas_list_research_releases.sh
bash ops/nas_check_crawler_status.sh
curl -fsS --max-time 10 http://dxp4800pro:8080/api/health
curl -i --max-time 20 http://dxp4800pro:8080/api/selection/health
```

当前结果：

1. `research/current` 存在，当前版本是 `nas_daily_new_20260605`
2. `research/archive` 已保留 `20260604 / 20260605` 两个回滚点
3. `market-backend-nas`、`market-frontend-nas`、`market-crawler-nas` 均在线
4. crawler 日志持续出现 tick / snapshot push
5. `/api/health` 返回 `200`
6. `/api/selection/health` 返回 `200`，`latest_signal_date` 为 `2026-06-05`

## 6. 对 `07_PENDING_TODO` 的收口判断

1. `T-033` 继续保持 `DONE`
2. `T-035` 本轮应改成 `DONE`
3. `T-034` 仍保持 `ACTIVE`

原因：

1. `T-033` 的入口降噪与真相统一已经完成，继续保留为活跃待办只会误导。
2. `T-035` 原先要求的 Git、服务、发布链、最新正式库发布和回滚点都已有证据，不应再挂成 ACTIVE。
3. `T-034` 是下一轮“正式别名 / shadow sample 迁移”主题，不属于本轮综合治理剩余缺口。

## 7. 结论与下一轮边界

这轮项目综合治理到这里可以正式关闭。  
后续若继续做，应直接新开主题，不再把以下问题作为当前未完成事实重复打开：

1. 仓库 8G 来源不清
2. 高曝光文档三端口径打架
3. NAS Git 还没打通
4. `research/current` 仍停留在 bootstrap

下一轮如果继续，默认只看：

1. `T-034` 正式别名与 shadow/sample 迁移
2. 具体业务策略与数据链的新需求
