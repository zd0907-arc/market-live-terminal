# REQ-20260404-03-selection-backtest-engine

> 当前真实状态优先看：`docs/changes/MOD-20260404-01-selection-research-current-state.md`

## 1. 基本信息
- 标题：选股研究一期｜双口径回测引擎
- 状态：DONE
- 负责人：Codex
- 关联 CAP：`CAP-SELECTION-RESEARCH`
- 关联 Task ID：`CHG-20260404-01`

## 2. 目标
- 保留固定持有回测，同时补充“窗口内最高机会”口径，避免中期走势被冲高回落完全抹平。

## 3. 冻结口径
- 入场：信号日下一可用交易日收盘价
- 持有期：`5 / 10 / 20 / 40`
- 一期输出两套结果：
  - 固定持有结果：`fixed_exit_return_pct`
  - 窗口机会结果：`max_runup_within_holding_pct`
- 同时记录：`max_drawdown_within_holding_pct`
- 动态出货退出回测仅预留，不在一期实现

## 4. 实际结果
- 已升级回测表与回测接口
- summary 现可同时输出：
  - `win_rate`（固定持有胜率）
  - `opportunity_win_rate`
  - `avg_max_runup_pct`
  - `median_max_runup_pct`
- trades 现可同时输出：
  - `fixed_exit_return_pct`
  - `max_runup_within_holding_pct`
  - `max_drawdown_within_holding_pct`
