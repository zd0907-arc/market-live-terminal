# Daily Candidate Source Contract（每日候选源契约）

## 1. 定位

本文档定义工作台统一候选池的单一入口，回答“每日候选从哪里来、如何汇入同一入口、哪些只是子专题解释层”。

统一链路：

```text
trade_date -> source adapter -> standard candidate records -> selection_candidate_sources -> selection_candidate_daily -> workbench
```

## 2. 当前统一入口

- 工作台统一候选池入口：`Selection Research` 工作台。
- `机会发现模型` / `spark_opportunity_selector` 是盘后模型候选源，接入工作台统一候选池和模拟盘。
- 日常入口应先从统一候选池进入，再决定是否查看热点、复盘、长期趋势等子专题解释。

## 3. 候选源边界

主候选源：

- `Selection Research` 工作台主候选池。
- `机会发现模型` 输出的盘后模型候选。

子专题，不是独立主线入口：

- `market_heat`
  - 定位：选股研究子专题。
  - 作用：解释市场主线、辅助候选验证、建立追强候选池。
  - 边界：不是独立主线，不单独定义项目级候选入口。

工作台不直接读取训练报告、临时 CSV、随意命名 JSON 或 Notebook 输出；任何新模型或新策略要接入选股工作台，都必须输出标准“每日候选记录”。

## 4. 来源注册

每个来源必须先登记：

| 字段 | 示例 | 要求 |
|---|---|---|
| `source_id` | `spark_opportunity_selector` | 稳定英文 ID，不随版本变 |
| `source_name` | 星火机会模型 | 页面显示名 |
| `source_type` | `model` | `model` / `rule_strategy` |
| `source_version` | `opportunity_discovery_trade_l2_v0_1` | 可随模型升级 |
| `horizon` | `22d` | 目标周期 |
| `status` | `active` | `active` / `watch_only` / `disabled` |
| `owner_note` | 研究可用，需人工确认开盘条件 | 中文说明 |

暂不进入候选池的东西也可以登记为 `disabled`，但页面不展示。

## 5. 候选记录

适配器返回 `list[dict]`，每条记录至少包含：

```json
{
  "trade_date": "2026-05-14",
  "symbol": "sh600769",
  "name": "祥龙电业",
  "source_id": "spark_opportunity_selector",
  "source_name": "星火机会模型",
  "source_type": "model",
  "source_version": "opportunity_discovery_trade_l2_v0_1",
  "rank": 1,
  "score": 39.001,
  "score_scale": "raw",
  "horizon": "22d",
  "suggested_action": "candidate_buy",
  "action_label": "明日可买",
  "entry_allowed": true,
  "buy_rule": "次日开盘高开不超过6.8%且不接近涨停才买",
  "reason_summary": "22日冲高机会分靠前，资金与突破结构较强",
  "risk_tags": [],
  "entry_block_reasons": [],
  "explain_factors": {
    "model_score": 35.42,
    "rule_score": 51.68,
    "breakout_score": 82.83,
    "stealth_score": 59.43,
    "distribution_score": 25.0
  },
  "raw_payload": {}
}
```

## 6. 字段约束

| 字段 | 必填 | 约束 |
|---|---|---|
| `trade_date` | 是 | 信号日，只能是 `YYYY-MM-DD` |
| `symbol` | 是 | 小写，`sh/sz/bj` + 6 位代码 |
| `source_id` | 是 | 与注册表一致 |
| `source_type` | 是 | 只允许 `model` / `rule_strategy` |
| `source_version` | 是 | 可追溯到模型/策略产物 |
| `rank` | 是 | 来源内部排序，从 1 开始 |
| `score` | 是 | 数值 |
| `suggested_action` | 是 | `candidate_buy` / `watch` / `blocked` |
| `entry_allowed` | 是 | 布尔值 |
| `reason_summary` | 是 | 一句话中文解释 |
| `explain_factors` | 是 | JSON object，不允许只给空字符串 |

允许但不强制：

- `market_cap`
- `close`
- `return_5d_pct`
- `return_20d_pct`
- `risk_level`
- `candidate_tags`
- `artifact_path`

## 7. 点时安全

所有来源必须保证：

```text
生成 trade_date 的候选时，只使用 trade_date 收盘时已经可获得的数据。
```

禁止：

- 使用未来收益、未来高低点、未来标签参与当日候选。
- 用验证集结果 CSV 伪装成每日候选。
- 只输出 latest 而不支持明确 `trade_date`。
- 输出文件覆盖后无法知道来自哪个模型版本。

## 8. Python 适配器

推荐每个来源暴露：

```python
SOURCE_ID = "spark_opportunity_selector"
SOURCE_NAME = "星火机会模型"
SOURCE_TYPE = "model"
SOURCE_VERSION = "opportunity_discovery_trade_l2_v0_1"


def generate_daily_candidates(trade_date: str, *, limit: int = 50) -> list[dict]:
    """Return standard candidate records for one signal date."""
```

工作台每日任务只调用适配器，不进入模型内部实现。

## 9. 持仓动作模型

持仓模型不要混进候选记录。它输出 `model_action_daily`：

```json
{
  "trade_date": "2026-05-14",
  "symbol": "sh600769",
  "source_id": "sentinel_postclose_exit",
  "source_name": "守势持仓模型",
  "source_version": "postclose_exit_v0_2",
  "position_id": "manual-or-simulated-id",
  "action": "hold",
  "action_label": "继续持有",
  "action_score": 6.2,
  "reason_summary": "收益保护未触发，收盘后风险未升高",
  "risk_tags": [],
  "raw_payload": {}
}
```

动作枚举：

| action | 含义 |
|---|---|
| `hold` | 继续持有 |
| `watch_risk` | 风险观察 |
| `sell_next_open` | 次日开盘卖出 |

持仓模型接入前必须先有 `model_position_daily` 输入，不能只靠历史回测产物生成动作。

## 10. 交付清单

其他会话开发新来源时，至少交付：

1. `source_id/source_name/source_type/source_version/horizon/status`。
2. `generate_daily_candidates(trade_date)` 或等价命令。
3. 一天的标准候选 JSON 样例。
4. 点时安全说明。
5. 使用的数据源列表。
6. 回测摘要和主要风险。
7. 是否允许进入 `active`，还是只能 `watch_only`。

不满足这些要求的模型，只能保留在研究目录，不能接入每日选股工作台。

## 11. 治理使用规则

1. 先确认当前任务是治理入口澄清还是业务实现。
2. 治理入口澄清时，只更新本契约、`selection_research_master.md` 与入口文档。
3. 若涉及候选池合流、页面入口或策略实现，必须另开 change card，不在本契约中直接展开。
