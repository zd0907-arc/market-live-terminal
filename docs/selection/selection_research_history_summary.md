# 选股研究历史压缩摘要

> 这是 `docs/selection` 的历史压缩入口，不是当前日常决策入口。
> 当前默认入口仍先看 `docs/selection/daily_candidate_source_contract.md`、`docs/selection/opportunity_discovery_model_final.md`。
> 当前顶层只保留少数现行入口，其他阶段过程材料默认进 archive。

## 1. 这份摘要解决什么

把选股研究里那些已经完成的阶段性内容压成少量可回看的历史摘要，避免后续 AI 先读大量过程文档。

## 2. 已完成的主线

### 2.1 每日选股工作台

当前主线已经从“手动选择策略”转成“按日期看统一候选池 + 来源标签 + 右侧解释”。

核心方向：
- 当天所有来源统一写入候选池；
- 页面按日期读统一候选；
- 右侧统一看原因、风险和动作。

### 2.2 机会发现模型

机会发现模型已收口成盘后候选来源研究主线，不再和 H5、早盘执行、卖飞审计、旧滚动验证混成一条线。

### 2.3 长期趋势研究

长期趋势研究已经单独成线，关注的是产业趋势、估值压力、生命周期、长期持仓纪律，不和短线热点混用。

### 2.4 市场热点

热点研究已经明确：
- 可作为解释市场主线、辅助候选验证、建立追强候选池；
- 不能直接等同于自动买入系统。

### 2.5 model feature store

模型训练特征库已从“临时研究材料”转向正式主链的一部分，接下来主要是命名和入口收口，而不是重新设计。

## 3. 历史材料怎么理解

以下文件夹内的内容多为历史材料：

- `docs/selection/cycle_returns/`
- `docs/selection/litong_similarity/`
- `docs/selection/research_watchlist/`
- `docs/selection/doublers/`
- `docs/selection/market_heat/`

它们不是无用，只是应被理解为：
- 历史案例
- 阶段回放
- 研究样本
- 规则验证材料

而不是当前系统入口。

## 4. 以后怎么用

1. 想找当前入口：看 `daily_candidate_source_contract.md`
2. 想找模型正式说明：看 `opportunity_discovery_model_final.md`
3. 想找历史脉络：先看这份摘要，再下钻 archive

## 5. 顶层不再保留

- `selection_research_master.md`、`selection_research_archive_decision_summary.md`、`daily_selection_workbench_integration_plan_2026-05-16.md` 这类阶段材料已下沉到 archive 视角。
- 顶层只保留能直接服务当前候选池与模型交付的入口。

## 5. 顶层控量规则

- 顶层不再保留过程计划、实现笔记、训练审计一类材料。
- 新增阶段材料先判断它是“当前入口”还是“阶段过程”。
- 阶段过程默认进入 `docs/archive/selection/`，只在顶层保留这份总摘要承接脉络。
