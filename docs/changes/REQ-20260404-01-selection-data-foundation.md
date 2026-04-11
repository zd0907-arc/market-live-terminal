# REQ-20260404-01-selection-data-foundation

> 当前真实状态优先看：`docs/changes/MOD-20260404-01-selection-research-current-state.md`

## 1. 基本信息
- 标题：选股研究一期｜独立数据底座与弱耦合复用边界
- 状态：DONE
- 负责人：Codex
- 关联 CAP：`CAP-SELECTION-RESEARCH`
- 关联 Task ID：`CHG-20260404-01`

## 2. 目标
- 在不影响原有模块的前提下，建立独立的选股研究数据平面，并为右侧复盘嵌入提供只读数据支持。

## 3. 冻结方案
- 源数据只读主库：`local_history / history_daily_l2 / history_5m_l2 / sentiment_* / stock_universe_meta`
- 结果写入独立库：`data/selection/selection_research.db`
- 独立表：
  - `selection_feature_daily`
  - `selection_signal_daily`
  - `selection_backtest_runs`
  - `selection_backtest_trades`
  - `selection_backtest_summary`
- 名称映射优先读 `stock_universe_meta`；若为空，可做只读 fallback，不改旧口径

## 4. 实际结果
- 已新增 `backend/app/db/selection_db.py`
- 已完成 schema 创建、读写 helper、回测 run/result 持久化
- 已扩展回测表字段以支持窗口最高机会口径
- 未改写旧主库任何表结构与旧接口契约
