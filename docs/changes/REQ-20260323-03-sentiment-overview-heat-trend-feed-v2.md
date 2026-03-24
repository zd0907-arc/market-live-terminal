# REQ-20260323-03-sentiment-overview-heat-trend-feed-v2

> ⚠️ 本卡保留为 **阶段性设计记录**。当前真实接口口径（含 `60D`、`daily_scores`、股吧单源收敛）请优先查看：
> `docs/changes/MOD-20260324-01-retail-sentiment-v2-current-state.md`

## 1. 基本信息
- 标题：散户一致性观察 V2 Phase 2（overview / heat_trend / feed 正式接口）
- 状态：DONE
- 负责人：AI / Dong
- 关联 Task ID：`CHG-20260323-01`
- 关联 CAP：`CAP-RETAIL-SENTIMENT`
- 关联 STG：`STG-20260323-01-retail-sentiment-v2-heat-event-stream`

## 2. 背景与目标
- 目标：把首页主链路从 `dashboard|trend|comments` 切到热度主导的新接口。

## 3. 方案与边界
- 做什么：
  - 新增：
    - `GET /api/sentiment/overview/{symbol}?window=5d|20d`
    - `GET /api/sentiment/heat_trend/{symbol}?window=5d|20d`
    - `GET /api/sentiment/feed/{symbol}?window=5d|20d&source=all|guba|xueqiu|ths&sort=latest|hot`
  - overview 返回：
    - `event_count / post_count / reply_count`
    - `relative_heat_index`
    - `latest_event_time`
    - `active_source_count`
    - `coverage_status`
    - `price_latest_date`
  - heat_trend 返回：
    - `time_bucket`
    - `event_count / post_count / reply_count`
    - `relative_heat_index`
    - `price_close / price_change_pct`
    - `has_price_data / is_gap`
  - feed 返回统一事件流
- 不做什么：
  - 不继续在新首页主链路中消费旧 `dashboard/trend/comments`
  - 不输出方向类主结论

## 4. 验收标准
- Given `2026-03-24 20:30`，When 调 `overview`，Then 所有统计字段都必须和同一窗口一致。
- Given `2026-03-24 20:35`，When 调 `heat_trend?window=5d`，Then 图表数据同时含价格与事件量，并能区分 gap。
- Given `2026-03-24 20:40`，When 调 `feed?source=xueqiu`，Then 返回仅雪球事件；`source=all` 时按统一事件流混排。

## 5. 风险与回滚
- 风险：相对热度基线若 30 交易日均值过低，需保护分母，避免异常放大。
- 回滚：旧接口保留，直到首页切换稳定。

## 6. 实施回填
- 已落地：
  - `GET /api/sentiment/overview/{symbol}?window=5d|20d`
  - `GET /api/sentiment/heat_trend/{symbol}?window=5d|20d`
  - `GET /api/sentiment/feed/{symbol}?window=5d|20d&source=all|guba|xueqiu|ths&sort=latest|hot`
- 当前实现口径：
  - `5D / 20D` 先按交易日级桶输出，主图表达稳定优先于更细分时粒度；
  - `relative_heat_index = 当前桶事件数 / 自身前 30 个交易日平均日事件数`；
  - 旧 `dashboard / trend / comments` 保留兼容，不再作为首页主链路。
