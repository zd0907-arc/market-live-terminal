# MOD-20260524-07 market_heat 模块边界治理

## 1. 基本信息
- 标题：`market_heat` 模块边界治理
- 状态：DRAFT
- 负责人：Codex
- 关联 Task ID：`MOD-20260524-07-market-heat-module-boundary-governance`
- 关联 CAP：`CAP-MARKET-HEAT`, `CAP-L2-HISTORY-FOUNDATION`

## 2. 这次治理回答的问题

不是问“热点模块有没有很多文件”，而是先问：

> 哪些才是当前页面真的在用的链路？

结论分三层：

1. **页面正式消费链路**
2. **研究/训练底座**
3. **专题/案例/历史材料**

## 3. 当前正式页面链路

当前 `market_heat` 页面真正依赖的是：

```text
tradable_theme_map.db
+ fine_heat_snapshots_*_m5_80.json
+ /api/market_heat/fine_dashboard
```

代码入口：

- `backend/app/routers/market_heat.py`
- `backend/app/services/market_heat.py`

文档入口：

- `docs/selection/market_heat/README.md`
- `docs/selection/market_heat/theme_taxonomy_management.md`
- `docs/changes/REL-20260512-v5.1.4-market-heat-mainline-dashboard.md`

## 4. 当前不应再被当成默认入口的对象

### 4.1 研究/训练底座

这些对象要保留，但不应被理解成“当前页面默认入口”：

- `backend/scripts/build_stock_sector_map.py`
- `backend/scripts/build_tradable_theme_map.py`
- `backend/scripts/build_fine_theme_heat_daily.py`
- `backend/scripts/build_fine_theme_heat_daily_v2.py`
- `backend/scripts/dump_market_hot_sectors.py`

它们的角色分别是：

- 原始板块映射构建
- 主题清洗与 canonical 合并
- 兼容热度主表构建
- 训练/预测长表构建
- 快照导出/排查

### 4.2 专题/案例/历史材料

这些对象不属于正式页面链路：

- `docs/selection/market_heat/backtests/**`
- `docs/selection/market_heat/fine_theme_heat_trend_*.html`
- `docs/selection/market_heat/fine_theme_heat_forecast_baseline_2026-05-13.md`
- 各类 `build_*trend*.py`、`build_*case*.py`、`analyze_*`、`backtest_*`
- 各类 `docs/changes/*market-heat*` 阶段卡

## 5. 本轮实际收口动作

### 5.1 文档口径收口

已把两份模块文档写清楚：

1. `README.md` 明确三层结构：
   - 页面正式消费链路
   - 研究/训练底座
   - 专题/案例材料
2. `theme_taxonomy_management.md` 明确：
   - 它是模块维护说明
   - `build_stock_sector_map.py` / `build_tradable_theme_map.py` 是模块维护脚本
   - 不属于全项目正式日常白名单脚本

### 5.2 维护脚本默认入口收口

`backend/scripts/build_stock_sector_map.py` 之前仍把旧 `full_reverse` 写成默认 atomic 候选。

本轮已改成：

1. 优先显式 `ATOMIC_MAINBOARD_DB_PATH`
2. 再走全局 `candidate_atomic_db_paths()`
3. 不再自己单独把 `full_reverse` 写成默认兜底

这样它会跟随当前正式 atomic 解析链，而不是偷偷回到旧库。

## 6. 当前结论

`market_heat` 这批治理不应该变成“批量改所有热点脚本”。

更合理的做法是：

1. 把页面正式链路钉死
2. 把模块维护脚本和专题材料区分清楚
3. 后续如果继续治理，再按专题脚本族逐批处理

## 7. 下一步建议

下一批更适合处理：

1. `selection/watchlist/doubler` 研究脚本族
2. `snapshot/sync/local compatibility` 脚本族

不建议下一步马上去改所有 `market_heat/analyze_*`，因为这批大多是研究材料，收益不如继续收系统其他高混淆区域。
