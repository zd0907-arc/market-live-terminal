# REQ-20260322-05-sentiment-coverage-and-source-expansion-v4

## 1. 基本信息
- 标题：散户一致性观察 Phase 4（覆盖池与数据源扩展）
- 状态：DRAFT
- 负责人：AI / Dong
- 关联 Task ID：`CHG-20260322-01`
- 关联 CAP：`CAP-RETAIL-SENTIMENT`
- 关联 STG：`STG-20260322-01-retail-sentiment-rebuild`

## 2. 背景与目标
- 目标：解决当前“主要依赖自选股驱动抓取、覆盖不足、平台单一”的天花板，让模块具备稳定的覆盖池与后续扩源能力。

## 3. 方案与边界
- 做什么：
  - 抓取池从单一 watchlist 扩展为三层：
    - `watchlist_pool`
    - `focus_pool`
    - `hot_pool`
  - 调度策略冻结为：
    - 盘前：重点池全量预热
    - 盘中：重点池高频、热池低频
    - 盘后：补抓 + 摘要生成
    - 非交易日：低频补样本，不伪装成实时
  - 每个股票补充覆盖状态：
    - `covered`
    - `latest_comment_time`
    - `last_crawl_result`
    - `coverage_level`
    - `stale_level`
  - 文档预留多源扩展位：
    - 雪球
    - 新闻标题
    - 公告标题
    - 热门题材榜
- 不做什么：
  - 本期不强制接入多源
  - 不在首页直接暴露“补抓按钮矩阵”或复杂调度控制 UI

## 4. 执行步骤（按顺序）
1. 冻结 coverage state 字段和未覆盖态文案。
2. 冻结抓取池三层优先级与调度语义。
3. 冻结多源扩展位，仅在契约与待办中登记，不在本期落地。

## 5. 验收标准（Given/When/Then，绝对时间）
- Given 某股票不在自选但在重点池，When 打开首页，Then 页面仍能显示舆情数据。
- Given 某股票未进入任何覆盖池，When 打开模块，Then 页面必须明确展示“未覆盖”，而不是回退成“暂无情绪数据”。
- Given 非交易日 `2026-03-28 10:00`，When 打开模块，Then 最新时间与 stale 状态必须明确表达为历史快照，不得伪装成实时更新。
- Given 后续引入多源扩展，When 查看契约文档，Then 可明确知道哪些字段预留给 future source fusion，而不会与当前单源股吧链路冲突。

## 6. 风险与回滚
- 风险：
  - 覆盖池扩大后抓取频率与性能成本会显著上升，需要与后续运维卡协同；
  - 如果 `focus_pool` 与 `hot_pool` 口径不冻结，后续极易变成“谁都能往里塞”的灰区。
- 回滚：
  - 若调度资源不足，允许回退到 `watchlist + focus_pool` 两层，但不能再回到“只有自选股才有覆盖”的默认认知。

## 7. 结果回填
- 实际改动：待实施
- 验证结果：待实施
- 遗留问题：待实施

## 8. 归档信息
- 归档时间：
- Archive ID：
- 归档路径：
