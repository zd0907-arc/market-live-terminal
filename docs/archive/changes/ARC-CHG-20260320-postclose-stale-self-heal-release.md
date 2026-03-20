> Archive-Meta
- Archive-ID: ARC-CHG-20260320-postclose-stale-self-heal-release
- Archive-Type: CHG
- Archived-At: 2026-03-20
- Source-Path: docs/changes/REQ-20260320-01-postclose-stale-self-heal-release.md
- Status: FROZEN

# REQ-20260320-01-postclose-stale-self-heal-release

## 1. 基本信息
- 标题：盘后主动自愈补齐当日分时停更个股并发布 v4.2.27
- 状态：DONE
- 负责人：Codex / 发布 AI
- 关联 Task ID：`CHG-20260320-01`
- 关联 CAP：`CAP-REALTIME-FLOW`, `CAP-WIN-PIPELINE`
- 前置依赖：`CHG-20260319-02`, `CHG-20260319-03`, `v4.2.26`

## 2. 背景与目标
- `2026-03-19` 盘中与盘后仍出现少数股票当日分时停在 `14:45` / `14:50` 左右，而其他股票正常更新。
- 前一轮修复已支持“用户打开页面时按请求自愈”，但这仍然过于被动：若无人打开该股票页面，盘后数据不会主动补齐。
- 本次目标是在不改变前端接口的前提下，补一层**盘后主动自愈扫盘**，让自选股在收盘后自动修补陈旧 today ticks，并同步完成聚合层刷新。

## 3. 方案与边界
- 做什么：
  1. 新增 `trade_ticks` 最新时间查询能力，用于识别“今日最后 tick 是否早于 `14:55:00`”；
  2. 在云端 scheduler 新增盘后自愈任务，固定于 `15:02 / 15:07 / 15:12 / 15:17` 扫描自选股；
  3. 对陈旧个股执行 `fetch_live_ticks -> overwrite trade_ticks -> aggregate_intraday_1m -> refresh_realtime_preview` 闭环；
  4. 为该链路补单元测试，覆盖 fresh skip / stale heal / 仅处理陈旧股票 / 非盘后不执行。
- 不做什么：
  1. 不修改前端轮询与页面布局；
  2. 不新增多源行情 provider；
  3. 不改统一双轨接口契约。

## 4. 冻结规则
- “盘后主动自愈”仅处理**交易日当天**且**最新 tick 时间早于 `14:55:00`** 的自选股；
- 自愈成功后必须同步刷新：
  - `trade_ticks`
  - `history_1m`
  - `realtime_5m_preview`
- 页面访问触发的 stale rehydrate 仍保留，作为盘中/盘后兜底；本次只是在盘后增加主动修复层。

## 5. 结果回填
- 实际改动：
  1. `backend/app/db/crud.py` 新增 `get_latest_tick_time`；
  2. `backend/app/scheduler.py` 新增盘后主动扫盘与自愈逻辑；
  3. `backend/tests/test_scheduler_postclose_self_heal.py` 新增专项测试；
  4. 发布版本提升至 `v4.2.27`。
- 验证结果：
  - `npm run check:baseline` 通过；
  - `python3 -m pytest -q backend/tests/test_scheduler_postclose_self_heal.py backend/tests/test_realtime_dashboard_router.py` 通过；
  - 生产接口核查时，`sz000833 / sz000759 / sz002570 / sh603629` 均已回到 `2026-03-19 15:00`。
- 产出：
  - `v4.2.27`

## 6. 风险与后续
- 当前主动自愈仍调用 AkShare 单源 `fetch_live_ticks`；若上游源持续超时，盘后扫盘也可能补齐失败。
- 后续仍建议补：
  1. 实时 tick 多源 fallback；
  2. 更明确的盘后自愈日志落盘与失败告警。

## 7. 归档信息
- 归档时间：2026-03-20
- Archive ID：ARC-CHG-20260320-postclose-stale-self-heal-release
- 归档路径：docs/archive/changes/ARC-CHG-20260320-postclose-stale-self-heal-release.md
