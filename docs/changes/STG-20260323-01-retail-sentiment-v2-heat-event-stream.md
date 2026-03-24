# STG-20260323-01-retail-sentiment-v2-heat-event-stream

> ⚠️ 本卡保留为 **过程方案记录**。若要查看当前真实落地状态，请优先阅读：
> `docs/changes/MOD-20260324-01-retail-sentiment-v2-current-state.md`

## 1. 基本信息
- 标题：散户一致性观察 V2（热度主导 + 多源事件流）
- 状态：HISTORICAL
- 负责人：AI / Dong
- 关联 Task ID：`CHG-20260323-01`
- 关联 CAP：`CAP-RETAIL-SENTIMENT`

## 2. 背景与目标
- 当前首页散户模块已经完成 Phase 1~3 的“定位纠偏 / 指标重构 / 价格联动”首轮升级，但页面仍存在两个根问题：
  - 顶部结论与中下部内容口径混杂，用户难以确认“到底有没有数据、图到底在表达什么”；
  - 数据源仍停留在股吧主帖标题流，既没有回复正文，也无法兼容雪球/同花顺的后续扩展。
- 本轮目标冻结为：
  - 首页重构成 **热度观察主图 + 右侧原文流**；
  - 底层从 `sentiment_comments` 升级到统一 `sentiment_events` 事件流；
  - 首期实现 `股吧主帖+回复正文 + 雪球主帖/评论`，同花顺先预留模型与前端入口；
  - AI 解读仅保留占位，不在本期落地。

## 3. 方案与边界
- 做什么：
  - 新增统一事件模型 `sentiment_events`
  - 新增首页正式接口：`overview / heat_trend / feed`
  - 首页窗口统一冻结为 `5D / 20D`
  - 主图核心冻结为：`事件量 + 相对热度 + 价格`
  - 右侧原文流按 `全部 / 股吧 / 雪球 / 同花顺` 来源 Tab 展示
- 不做什么：
  - 本期不把偏多/偏空/一致性继续作为首页主图层
  - 本期不实现同花顺抓取
  - 本期不实现 AI 解读生成
  - 本期不同时重构覆盖池/调度策略

## 4. 分期顺序
1. 数据模型与契约：`sentiment_events` + `overview/heat_trend/feed`
2. 两源接入：股吧回复正文 + 雪球事件流
3. 首页 V2 UI：热度主图 + AI 预留窄区 + 右侧原文流

## 5. 总体验收总线
- Given `2026-03-24 20:30`，When 打开 `sz000833` 首页模块并切到 `5D`，Then 左侧主图显示价格 + 事件数柱 + 相对热度线，右侧可查看完整原文事件流。
- Given `2026-03-24 20:35`，When 切换到 `20D`，Then 顶部信息卡、主图、原文流全部同步切换到 `20D` 口径。
- Given 某股票当前窗口只有回复没有主帖，When 查看模块，Then 主图事件量仍大于 0，且顶部卡正确拆分主帖数/回复数。
- Given 雪球事件已接入、同花顺尚未接入，When 查看右侧来源 Tab，Then `雪球` 可用、`同花顺` 为灰态无数据。

## 6. 风险与回滚
- 风险：
  - 股吧回复正文与雪球评论抓取都涉及新解析链路，首轮规则可能不稳定；
  - `sentiment_events` 若不和旧 `sentiment_comments` 做兼容，历史已抓存量会立刻“消失”；
  - `5D / 20D` 统一口径若没有价格表兜底，非交易日很容易出现空窗。
- 回滚：
  - 允许旧 `/api/sentiment/dashboard|trend|comments` 继续保留；
  - 新首页若失败，可临时回退到旧版散户模块，但 `sentiment_events` 表不回删。

## 7. 分期卡列表
- `REQ-20260323-02-sentiment-events-and-two-source-contract.md`
- `REQ-20260323-03-sentiment-overview-heat-trend-feed-v2.md`
- `REQ-20260323-04-sentiment-homepage-v2-heat-led-ui.md`

## 8. 结果回填
- 实际改动：
  - 已新增 `sentiment_events` 正式事件流模型，并支持旧 `sentiment_comments -> sentiment_events` 懒回填；
  - 已新增首页正式接口 `overview / heat_trend / feed`；
  - 已完成首页 V2：热度主图 + AI 预留窄区 + 右侧来源 Tab 原文流。
- 验证结果：
  - `python3 -m pytest backend/tests/test_sentiment_response_shape.py` 通过；
  - `npm run build` 通过；
  - 本地样本 `sz000833 / sh603629` 可返回 `5D` overview、heat trend、feed 数据。
- 遗留问题：
  - 股吧回复正文抓取与雪球适配器尚未实装，当前正式可见数据仍以股吧主帖兼容回填为主；
  - 同花顺继续仅保留 schema / Tab 预留。
