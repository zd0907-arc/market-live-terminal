# 操盘 Agent 落地规划

## 结论

当前不是只参考 Agent 逻辑，而是分三层落地：

1. 文档层：先把角色、数据源、公司卡、复盘模板固定下来。
2. 执行层：每次分析时按 Agent 分工调用工具和子 Agent。
3. 自动化层：后续做脚本或定时任务，把数据读取、新闻监控、星火验证仓跟踪固化。

## 当前已经完成

- 建立 `docs/portfolio-ops/` 持仓操盘跟踪目录。
- 建立当前持仓记录。
- 建立每日复盘模板。
- 建立三只持仓公司研究卡。
- 明确振德医疗、领益智造是星火模型 22 日冲高验证仓。
- 明确粤桂股份外部变量包括原油、伊朗局势、特朗普/和谈表态、硫磺/硫酸价格。
- 建立 Agent 架构文档。

## 后续每次持仓分析必须执行的 Agent 流程

### 1. Data Freshness Agent

执行方式：主 Agent 直接查库。

检查：

- 原子库最新日期。
- 选股库最新日期。
- 模型特征库最新日期。
- 热点库最新日期。
- 是否有 delta 未合并。

### 2. Spark Validation Agent

执行方式：主 Agent 查库 + 必要时子 Agent 协助查回测/模型产物。

模型定义：

- 星火机会模型不是普通日内买卖模型。
- 它的目标是：信号日盘后给出股票，次日按真实开盘价买入，未来 22 个交易日内是否有较高冲高空间，重点看是否达到 10% / 15% / 20%。
- 当前振德医疗、领益智造按这个逻辑作为验证仓跟踪。

检查：

- 振德医疗、领益智造的星火信号日。
- 买入日和买入价。
- 22 个交易日窗口剩余天数。
- 信号后最高涨幅。
- 距离 15% 冲高目标还差多少。
- 当前回撤是否超过历史容忍区间。
- 是否触发守势持仓模型退出。

最小读取路径：

- 星火候选详情：`/Users/dong/Desktop/AIGC/market-data/research/current/selection/selection_research.db` 的 `selection_candidate_sources`。
- 条件：`source_id='spark_opportunity_selector'`，按 `trade_date + symbol` 查。
- 星火验证仓跟踪：`selection_exit_watchlist_daily`，优先看 `policy_id='pc_model_th6_stop12'`。
- `signal=0` 表示继续持有，`signal=1` 表示次日卖出。
- 回测摘要：`data/selection/opportunity_discovery/walk_forward_old_v0_1/walk_forward_summary.csv`。
- 22 日冲高明细：`data/selection/opportunity_discovery/opportunity_discovery_trade_l2_v0_1/validation_topk.csv`。
- 守势持仓模型产物：`data/selection/opportunity_discovery/postclose_exit_v0_2/`。
- 锁定验证：`data/selection/opportunity_discovery/postclose_exit_locked_validation_v0_1/locked_strategy_summary.csv`。

常用 SQL：

```sql
SELECT trade_date, symbol, name, source_id, rank, score, horizon,
       suggested_action, action_label, entry_allowed,
       buy_rule, reason_summary, risk_tags_json,
       entry_block_reasons_json, explain_factors_json, raw_payload_json
FROM selection_candidate_sources
WHERE source_id = 'spark_opportunity_selector'
  AND trade_date = :signal_date
  AND symbol = :symbol;
```

```sql
SELECT *
FROM selection_exit_watchlist_daily
WHERE trade_date = :asof_date
  AND policy_id = 'pc_model_th6_stop12'
ORDER BY signal DESC, rank ASC, symbol ASC;
```

### 3. Company Research Agent

执行方式：读公司研究卡 + 本地事件库 + 外部新闻。

检查：

- 公司逻辑是否变化。
- 最新公告是否影响利润。
- 财报关键变量是否变化。
- 是否有重大证伪或新催化。

### 4. Industry / Macro Driver Agent

执行方式：本地热点库 + 外部搜索。

检查：

- 领益：AI硬件、液冷、消费电子、机器人、折叠屏。
- 振德：医疗耗材、海外订单、零售线。
- 粤桂：原油、伊朗局势、硫磺、硫酸、湿法磷酸、定增。

### 5. News / Event Agent

执行方式：本地 `stock_events` + 外部搜索。

检查：

- 公司公告。
- 董秘问答。
- 行业新闻。
- 地缘和商品新闻。
- 标注每条新闻的方向：利好 / 利空 / 中性 / 噪音。

### 6. Technical / Microstructure Agent

执行方式：主 Agent 查原子库。

检查：

- 日线、5m、30m。
- L2 主力、超大单、L1。
- OIB、CVD。
- 委买委卖和尾盘承接。
- 只做执行层判断，不单独否定 22 日模型仓。

### 7. Candidate / Model Agent

执行方式：主 Agent 查选股库。

检查：

- 当天星火候选。
- 两个策略候选。
- 统一候选池。
- 风险拦截。
- 新候选是否明显强于当前持仓。

### 8. Portfolio Risk Agent

执行方式：主 Agent 汇总。

检查：

- 仓位集中度。
- 是否过度暴露在同一主题。
- 是否需要腾仓。
- 是否允许不动。

## 子 Agent 使用规则

以后不是每次都机械启动十个子 Agent。只有当任务可并行且有独立产出时启动，例如：

- 一个 Agent 查公司/公告。
- 一个 Agent 查行业/宏观新闻。
- 一个 Agent 查系统模型和回测产物。
- 主 Agent 本地查行情、L2、候选池并做最终组合决策。

子 Agent 的输出必须是结构化结论，不能直接替代最终建议。

## Skill 化计划

如果这个流程稳定，后续可以做一个项目专用 skill：

```text
portfolio-ops-agent
```

触发场景：

- 用户问“持仓怎么办”。
- 用户问“明天怎么操作”。
- 用户新增买入股票。
- 用户要求复盘系统推荐。

Skill 内容：

- 固定读取 `docs/portfolio-ops/`。
- 固定执行 Data Freshness、Spark Validation、Company Research、News、Technical、Candidate、Risk。
- 固定输出短结论 + 触发条件。

## 自动化计划

后续可创建盘后自动化：

- 每天数据跑完后检查最新日期。
- 生成持仓状态摘要。
- 扫持仓新闻和关键外部变量。
- 更新星火验证仓窗口。
- 输出一份待人工确认的次日计划。

先不自动下单。
