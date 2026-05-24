# REQ-20260404-02-selection-features-and-signals

> 当前真实状态优先看：`docs/changes/MOD-20260404-01-selection-research-current-state.md`

## 1. 基本信息
- 标题：选股研究一期｜信号职责重排
- 状态：DONE
- 负责人：Codex
- 关联 CAP：`CAP-SELECTION-RESEARCH`
- 关联 Task ID：`CHG-20260404-01`

## 2. 目标
- 保留三类规则信号，但只让 `breakout` 驱动核心工作流，其余信号退到解释与风险层。

## 3. 冻结职责
- `stealth`：内部前置 / 解释信号，不做左侧主列表入口
- `breakout`：唯一主筛选信号，负责每日输出全市场 Top10
- `distribution`：当前票风险识别能力，不做全市场榜单

## 4. 实际结果
- 已在候选接口里默认收敛到 `breakout` Top10
- 已新增：
  - `current_judgement`
  - `reason_summary`
  - `distribution_risk_level`
  - `breakout_reason_summary`
  - `distribution_reason_summary`
- 已补事件时间线输出，服务右侧决策视图
