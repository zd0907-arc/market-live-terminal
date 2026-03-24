# REQ-20260322-04-sentiment-price-linked-visualization-v3

## 1. 基本信息
- 标题：散户一致性观察 Phase 3（价格联动可视化）
- 状态：DONE
- 负责人：AI / Dong
- 关联 Task ID：`CHG-20260322-01`
- 关联 CAP：`CAP-RETAIL-SENTIMENT`
- 关联 STG：`STG-20260322-01-retail-sentiment-rebuild`

## 2. 背景与目标
- 目标：让模块从“看热闹”升级为“能辅助判断”，通过价格联动图识别情绪与价格的同步、背离和拥挤风险。

## 3. 方案与边界
- 做什么：
  - 扩展 `GET /api/sentiment/trend` 返回：
    - `price_close`
    - `price_change_pct`
    - `volume_proxy`（如可稳定拿到）
    - `has_price_data`
  - 趋势图规则冻结为：
    - 柱：看多 / 看空 / 中性样本数
    - 线 1：热度
    - 线 2：价格（副轴）
    - gap 桶保留为空，不连成零平台
  - 新增前端观察标签：
    - `情绪升温但价格走弱`
    - `价格新高但情绪未跟随`
    - `情绪冰点但跌速放缓`
    - `高热一致看多，警惕兑现`
    - `高热一致看空，关注反抽`
  - 时间窗口冻结为 `72H / 14D`
- 不做什么：
  - 不新增更细粒度
  - 不做复杂情绪打分引擎或策略回测系统

## 4. 执行步骤（按顺序）
1. 冻结趋势接口的价格联动字段。
2. 冻结前端价格-情绪联动标签的触发语义。
3. 重绘趋势图，确保 gap / 0 / price 三者共存时可读。

## 5. 验收标准（Given/When/Then，绝对时间）
- Given `2026-03-27 19:00`，When 查看 `72H` 视图，Then 用户可同时看到情绪热度与价格变化。
- Given 某股票存在空桶，When 渲染趋势图，Then 图上不应把 gap 误画成连续 0 值平台。
- Given 某段时间“热度抬升但价格走弱”，When 前端计算联动标签，Then 页面能展示 `情绪升温但价格走弱` 类提示。
- Given 非交易时段 `2026-03-27 20:30`，When 打开首页模块，Then 重点显示 `14D + 最新摘要` 视图。

## 6. 风险与回滚
- 风险：
  - 价格联动若只拿到局部时间窗口，需严格使用 `has_price_data` 控制展示，不能假设价格全量存在；
  - 若 `volume_proxy` 不稳定，首期允许返回 `null`，不阻塞主图上线。
- 回滚：
  - 允许先只上线“热度 + 价格”双线图，但 gap 语义与副轴价格不可回退。

## 7. 结果回填
- 实际改动：
  - `GET /api/sentiment/trend` 已扩展价格联动字段：
    - `neutral_vol`
    - `price_close`
    - `price_change_pct`
    - `volume_proxy`
    - `has_price_data`
  - `72H` 价格口径：
    - 读取正式 `history_5m_l2` 与 `realtime_5m_preview`
    - 以自然小时桶对齐 sentiment `strftime('%Y-%m-%d %H:00')`
    - preview 与 history 重叠时优先 preview
  - `14D` 价格口径：
    - 优先读取 `history_daily_l2`
    - 当天若存在 preview，则由 `realtime_5m_preview` 聚合成日桶覆盖
  - 前端趋势图已改为：
    - 柱：`偏多 / 偏空 / 中性`
    - 线：`热度`
    - 副轴线：`价格`
  - 首页新增前端联动观察标签：
    - `情绪升温但价格走弱`
    - `价格新高但情绪未跟随`
    - `情绪冰点但跌速放缓`
    - `高热一致看多，警惕兑现`
    - `高热一致看空，关注反抽`
  - 非交易时段首次进入页面时，默认窗口会切到 `14D`。
- 验证结果：
  - `python3 -m pytest backend/tests/test_sentiment_response_shape.py`：`6 passed`
  - `npm run build`：通过
  - 本地样本验证：
    - `sz000833 / sh603629` 在 `72H` 与 `14D` 都能返回 `price_close / price_change_pct / has_price_data`
    - 当 sentiment 无新增样本时，价格数据仍可独立显示，gap 语义未被破坏
- 遗留问题：
  - `volume_proxy` 当前在 `14D` 下优先使用 `history_daily_l2.total_amount` 或 preview 聚合量，属于“成交活跃度代理”，不是严格统一的成交量口径；
  - `72H` 小时价格桶当前按自然小时对齐而非交易所标准 1h K 桶，这是为了和舆情小时桶直接对齐，后续若要统一需单独开卡。

## 8. 归档信息
- 归档时间：
- Archive ID：
- 归档路径：
