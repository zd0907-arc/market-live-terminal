# MOD-20260524-08 selection watchlist / doubler 边界治理

## 1. 基本信息
- 标题：`selection watchlist / doubler` 边界治理
- 状态：DRAFT
- 负责人：Codex
- 关联 Task ID：`MOD-20260524-08-selection-watchlist-and-doubler-boundary-governance`
- 关联 CAP：`CAP-SELECTION-RESEARCH`

## 2. 这次治理回答的问题

这批不是在问“这些文件有没有价值”，而是在问：

> 它们到底是不是当前系统主链？

结论是：

1. `watchlist` 是一条独立的“研究后持续盯盘”产物链
2. `doubler` 是一条独立的“案例库 / 样本研究”产物链
3. 它们都不是当前 `/selection-research` 页面主流程，也不是每日选股工作台主链

## 3. 当前两条独立链路

### 3.1 watchlist 链路

```text
watchlist.json
-> build_research_watchlist_snapshot.py
-> snapshots/YYYY-MM-DD.csv
-> docs/selection/research_watchlist/daily/YYYY-MM-DD.md
```

它的角色是：

- 研究完成后的持续跟踪
- 轻量盯盘
- 人工判断是否买入、加减仓、卖出

它不是：

- 自动选股主链
- 当前页面主入口

### 3.2 doubler 链路

```text
study.csv
-> build_ytd_doubler_analysis.py
-> 2026_ytd_doublers_master_manifest.csv
-> 2026_ytd_doublers_top20_manifest.csv
-> top20 reports
```

它的角色是：

- 翻倍股样本库
- 案例模式沉淀
- 后续新票做相似性对照

它不是：

- 每日候选源
- 当前页面主链

## 4. 本轮实际动作

### 4.1 入口文档口径收口

已更新：

- `docs/selection/research_watchlist/README.md`
- `docs/selection/doublers/2026-ytd/README.md`

现在两份文档都明确写了：

- 这条链的正式入口是什么
- 它服务什么用途
- 它不等于什么

### 4.2 维护脚本默认 atomic 收口

已更新：

- `backend/scripts/build_research_watchlist_snapshot.py`
- `backend/scripts/build_ytd_doubler_analysis.py`

两者之前都把旧 `market_atomic_mainboard_full_reverse.db` 写成默认 atomic。

现在统一改成：

1. 优先显式 `ATOMIC_MAINBOARD_DB_PATH / ATOMIC_DB_PATH`
2. 再走全局 `candidate_atomic_db_paths()`
3. 如果当前环境没有可用路径，最后才回到 `compact_current` 作为正式默认兜底

这意味着它们会跟随当前正式 atomic 解析链，而不是私自回到旧库名。

## 5. 当前结论

这批最重要的不是“删案例文档”，而是：

1. 让后续 AI 不再把 `watchlist` 误当页面主链
2. 让后续 AI 不再把 `doubler` 误当实时候选源
3. 让仍在用的维护脚本跟随当前正式 atomic 口径

## 6. 下一步建议

下一批更适合治理：

1. `snapshot / sync / local compatibility` 脚本族
2. 其后再看是否需要补一轮“selection 顶层入口地图”

不建议下一步马上去改 `top20/*.md` 或日记文件；它们本身就是产物，不是入口。
