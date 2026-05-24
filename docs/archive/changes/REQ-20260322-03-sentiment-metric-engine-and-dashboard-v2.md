# REQ-20260322-03-sentiment-metric-engine-and-dashboard-v2

## 1. 基本信息
- 标题：散户一致性观察 Phase 2（指标引擎重构 + 首页大模块重做）
- 状态：DONE
- 负责人：AI / Dong
- 关联 Task ID：`CHG-20260322-01`
- 关联 CAP：`CAP-RETAIL-SENTIMENT`
- 关联 STG：`STG-20260322-01-retail-sentiment-rebuild`

## 2. 背景与目标
- 目标：把旧的 `情绪得分 / 多空词频比` 升级为真正有业务解释力的观察指标，并重排首页大模块的信息架构。

## 3. 方案与边界
- 做什么：
  - 首页主指标固定为：`热度 / 一致性 / 偏向 / 风险`
  - 冻结核心字段：
    - `heat_score`
    - `consensus_direction = bullish | bearish | mixed | neutral`
    - `consensus_strength = 0~100`
    - `risk_tag = 拥挤看多 | 拥挤看空 | 高热分歧 | 低热观望 | 情绪冰点`
  - 评论展示层从旧三分类兼容升级为四层：
    - `偏多 / 偏空 / 中性 / 高热中性(噪音)`
  - 首页中部结构冻结为：
    - 左：摘要卡
    - 中：关键词 / 主题词
    - 右：代表帖子
  - 新增 `GET /api/sentiment/keywords/{symbol}?window=72h|14d`
- 不做什么：
  - 本期不强制替换底层 NLP 引擎
  - `topics` 首期可选，若成本过高可先只做 `keywords`

## 4. 执行步骤（按顺序）
1. 冻结新 dashboard 主指标字段及业务含义。
2. 冻结代表帖子排序：`最新 / 最热 / 分歧`。
3. 冻结关键词接口返回结构。
4. 首页大模块改为三段式信息架构。

## 5. 验收标准（Given/When/Then，绝对时间）
- Given `2026-03-24 10:00`，When 查看首页模块，Then 顶部应直接显示 `热度 / 一致性 / 风险 / 最新样本时间(或覆盖状态)`。
- Given 某股票存在大量中性高热噪音样本，When 查看代表帖子，Then 页面不应将其全部误标为“看多/看空”。
- Given `GET /api/sentiment/keywords/sh000833?window=72h` 有返回，When 打开首页中部分析区，Then 关键词区优先展示高频主题词，而不是把大部分空间留给长评论列表。
- Given `2026-03-24 10:30`，When 用户切换代表帖子排序，Then 仅切换展示维度，不改变 dashboard 主指标口径。

## 6. 风险与回滚
- 风险：
  - 若 Phase 1 字段未先稳定，新 KPI 卡会同时读旧字段与新字段，容易造成口径混杂；
  - 关键词抽取若完全依赖正则，首期应接受“有用但不完美”，不得伪装成主题建模。
- 回滚：
  - 允许临时保留旧帖子列表作为 fallback，但首页 KPI 和关键词区不回退到“多空词频比中心”的旧设计。

## 7. 结果回填
- 实际改动：
  - 新增 `GET /api/sentiment/keywords/{symbol}?window=72h|14d`，返回 `keywords + topics + sample_count + latest_comment_time + coverage_status`；
  - `GET /api/sentiment/comments/{symbol}` 已升级为代表帖子接口，支持 `sort=latest|hot|controversial` 与 `window=72h|14d`，并为每条样本增加 `sentiment_label / sentiment_label_text`；
  - 首页 `散户一致性观察` 模块已改为三段式结构：
    - 顶部：`热度 / 一致性 / 偏向 / 风险`
    - 中部：`缓存摘要 / 关键词主题词 / 代表帖子`
    - 底部：趋势图（仍保持 `72H / 14D`）
  - 展示层已把原先“中性”进一步拆出 `高热中性/噪音`，避免高互动但无明确方向的帖子污染偏多/偏空观察。
- 验证结果：
  - `python3 -m pytest backend/tests/test_sentiment_response_shape.py`：`6 passed`
  - `npm run build`：通过
  - 本地样本验证：`sz000833 / sh603629` 在 `14d` 窗口下可返回关键词、主题聚合与代表帖子，窗口切换到 `72h` 时若无新增样本则正确回落为空态。
- 遗留问题：
  - 关键词抽取仍是规则/统计法，存在“昨天 / 亿元”这类泛词混入的可能，Phase 2.1 可继续压词库；
  - `高热中性/噪音` 当前主要依赖 `heat/read/reply` 阈值判定，还不是严格主题去噪模型；
  - 价格联动与背离标签尚未进入本期，后续由 Phase 3 完成。

## 8. 归档信息
- 归档时间：
- Archive ID：
- 归档路径：
