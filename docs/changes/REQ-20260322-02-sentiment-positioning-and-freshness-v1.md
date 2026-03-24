# REQ-20260322-02-sentiment-positioning-and-freshness-v1

## 1. 基本信息
- 标题：散户一致性观察 Phase 1（定位纠偏 + freshness 治理）
- 状态：DONE
- 负责人：AI / Dong
- 关联 Task ID：`CHG-20260322-01`
- 关联 CAP：`CAP-RETAIL-SENTIMENT`
- 关联 STG：`STG-20260322-01-retail-sentiment-rebuild`

## 2. 背景与目标
- 目标：先把当前模块从“实验型舆情面板”纠偏成“可信的观察器”。
- 首期只解决业务真相与契约错误，不做首页大改版布局。

## 3. 方案与边界
- 做什么：
  - 首页标题从 `散户情绪监测` 改为 `散户一致性观察`
  - 删除“Updated = 页面刷新时间”的误导性表达
  - `GET /api/sentiment/dashboard/{symbol}` 禁止同步调 LLM，只返回缓存摘要或 `summary=null`
  - `GET /api/sentiment/trend` 增加 `has_data / is_gap`
  - dashboard 新增 freshness 字段：`latest_comment_time / latest_crawl_time / latest_summary_time / summary_stale / coverage_status`
  - 首页顶部展示改读新 freshness / risk 语义
- 不做什么：
  - 不改抓虫数据源
  - 不做独立详情页
  - 不在本期替换底层规则打分引擎

## 4. 执行步骤（按顺序）
1. 冻结 dashboard 新字段与旧字段兼容策略。
2. 冻结 trend gap 语义：无新增样本不再等同于 0 值。
3. 冻结 summary 异步策略：读接口只读缓存，手动/定时负责生成。
4. 首页按新字段替换“页面刷新时间”与旧标题文案。

## 5. 验收标准（Given/When/Then，绝对时间）
- Given `2026-03-22 09:30`，When 首页打开，Then 模块标题为 `散户一致性观察`，且不再显示“Updated: 页面刷新时间”。
- Given `2026-03-22 20:30`，When 请求 `GET /api/sentiment/dashboard/sh603629`，Then 返回中允许 `summary=null`，但不得触发任何同步 LLM 调用。
- Given `2026-03-22 20:35`，When 请求 `GET /api/sentiment/trend/sh603629?interval=72h`，Then 每个 gap 桶可通过 `has_data/is_gap` 与真实 0 值桶区分。
- Given `2026-03-22 20:40`，When 某股票未被抓取覆盖，Then 页面空态应表达“暂未进入舆情抓取覆盖”，而不是笼统写“暂无情绪数据”。

## 6. 风险与回滚
- 风险：
  - 旧前端仍可能读取 `status/bull_bear_ratio/risk_warning`，需保留兼容字段；
  - `latest_crawl_time` 若没有持久化来源，首期允许回落为空但必须显式为 `null`。
- 回滚：
  - UI 若来不及完全换新，允许暂时保留旧布局，但不得回滚“读接口不调 LLM”和 freshness 契约。

## 7. 结果回填
- 实际改动：
  - `GET /api/sentiment/dashboard/{symbol}` 已改为只读缓存摘要，不再在读接口中同步调用 LLM；
  - 新增服务层 `retail_sentiment.py`，统一收敛 dashboard freshness 字段与摘要缓存写入逻辑；
  - `GET /api/sentiment/trend` 已增加 `has_data / is_gap`；
  - `GET /api/sentiment/comments` 空态已开始区分 `Symbol not covered / No samples found`；
  - 首页模块标题已改为 `散户一致性观察`，并删除旧 `Updated: 页面刷新时间` 语义；
  - 首页顶部已先切换为 `热度 / 一致性 / 风险 / 最新样本` 四个 KPI 卡，摘要区改为缓存摘要语义，评论区标题改为 `代表帖子 / 最近样本`；
  - scheduler 已新增盘前/盘后摘要缓存刷新任务（`08:40 / 15:25`）。
- 验证结果：
  - `backend/tests/test_sentiment_response_shape.py`：`5 passed`
  - `npm run build`：通过
  - `npm run check:baseline`：通过（`85 passed`）
- 遗留问题：
  - `latest_crawl_time` 当前通过 `sentiment_comments.max(crawl_time)` 推导，老数据若历史缺字段质量不齐，仍需后续观察；
  - 首页 KPI 的 heat / risk 仍是 Phase 1 过渡口径，Phase 2 需继续收敛正式指标含义与关键词区。

## 8. 归档信息
- 归档时间：
- Archive ID：
- 归档路径：
