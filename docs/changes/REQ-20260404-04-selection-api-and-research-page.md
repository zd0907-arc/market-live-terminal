# REQ-20260404-04-selection-api-and-research-page

> 当前真实状态优先看：`docs/changes/MOD-20260404-01-selection-research-current-state.md`

## 1. 基本信息
- 标题：选股研究一期｜Top10 候选池 + 右侧复盘决策视图
- 状态：DONE
- 负责人：Codex
- 关联 CAP：`CAP-SELECTION-RESEARCH`
- 关联 Task ID：`CHG-20260404-01`

## 2. 目标
- 把页面从“研究数表页”调整成真正服务你工作流的“左筛右看”工作台。

## 3. 冻结页面
- 路由：`/selection-research`
- 左侧：Top10 breakout 候选卡片
- 右侧：复盘决策视图（复用旧复盘能力）
- 新增判断块：
  - 当前综合判断
  - 为什么选中它
  - 出货风险判断
  - 事件时间线
- 不跳转旧复盘页，不替换旧首页，不改旧 `realtime/review/sentiment` 页面逻辑

## 4. 实际结果
- 已将候选列表收敛为 Top10 卡片
- 已把右侧改为复盘决策视图
- 已复用原复盘多周期 L1/L2 视图能力
- 已保留独立接口前缀 `/api/selection/*`
