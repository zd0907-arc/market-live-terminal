# 选股模型开发与接入 SOP

更新时间：2026-05-16

> 提示：这份 SOP 是模型交付规范文档，不是当前项目总入口真相。
> 其中出现的数据源文件名是模型产物 manifest 的示例写法；当前正式 atomic 默认入口应以 `docs/03_DATA_CONTRACTS.md` 和运行时 resolver 为准。

## 结论

以后所有选股模型都必须按“每日候选来源契约”交付。模型侧不能只交 `.joblib`、回测 CSV 或 `latest_candidates.csv`。

模型进入工作台前，必须满足：

```text
冻结模型版本
-> 提供按 trade_date 推理的适配器
-> 输出标准候选记录
-> 说明点时安全和数据依赖
-> 写入统一候选表
-> 页面只读统一候选池
```

## 1. 当前接入契约

开发侧已经定义了两个核心文档：

| 文档 | 作用 |
|---|---|
| `docs/archive/selection/daily_selection_workbench_integration_plan_2026-05-16.md` | 每日选股工作台接入方案（已归档） |
| `docs/selection/daily_candidate_source_contract.md` | 每日候选来源字段契约 |

当前顶层保留的长记忆入口只保留少数几份：
- `docs/selection/daily_candidate_source_contract.md`
- `docs/selection/opportunity_discovery_model_final.md`
- `docs/selection/model_development_sop.md`
- `docs/selection/model_market_index_daily_runbook.md`
- `docs/selection/selection_research_history_summary.md`

当前开发目标是：

```text
trade_date -> source adapter -> standard candidate records
-> selection_candidate_sources
-> selection_candidate_daily
-> workbench
```

模型侧必须适配这个流程。

`daily_selection_workbench_integration_plan_2026-05-16.md` 属于阶段过程材料，已移入 archive 视角，不再作为顶层日常入口。

## 2. 当前星火模型还缺什么

### 星火机会模型

当前已有：

| 项 | 状态 |
|---|---|
| 模型文件 | `data/selection/opportunity_discovery/opportunity_discovery_trade_l2_v0_1/model.joblib` |
| 特征列表 | `feature_columns.json` |
| 最新候选 | `latest_candidates.csv` / `latest_actionable_candidates.csv` |
| 说明文档 | `docs/selection/opportunity_discovery_model_final.md` |

还缺：

1. `generate_daily_candidates(trade_date)` 标准适配器。
2. 按任意目标日期推理，而不是只读 `latest_candidates.csv`。
3. 标准候选 JSON 样例。
4. 模型 manifest，明确 `source_id/source_version/训练截止日/标签定义/数据依赖`。
5. 写入 `selection_candidate_sources` 的转换逻辑。

### 守势持仓模型

当前已有：

| 项 | 状态 |
|---|---|
| 模型目录 | `data/selection/opportunity_discovery/postclose_exit_v0_2/models/` |
| 研究回测摘要 | `postclose_exit_v0_2/summary.json` |
| 锁定验证 | `postclose_exit_locked_validation_v0_1/` |

还缺：

1. `model_position_daily` 输入表。
2. 真实/模拟持仓标准输入格式。
3. `generate_daily_actions(trade_date, positions)` 持仓动作适配器。
4. 输出 `hold / watch_risk / sell_next_open` 的标准动作记录。
5. 明确生产时到底使用哪个冻结窗口模型，不能让页面或用户手动选 `2026-03_postclose_exit.joblib` 这种文件。

因此第一批只能先接星火机会模型候选；守势持仓模型应放到 P4。

## 3. 模型命名规则

每个模型必须有稳定身份：

| 字段 | 示例 | 说明 |
|---|---|---|
| `source_id` | `spark_opportunity_selector` | 稳定英文 ID，不随版本改 |
| `source_name` | 星火机会模型 | 页面显示名 |
| `source_type` | `model` | 固定为 `model` |
| `source_version` | `1.0` | 对外模型版本 |
| `artifact_version` | `opportunity_discovery_trade_l2_v0_1` | 内部训练产物版本 |
| `package_id` | `spark_opportunity_selector@1.0` | 追溯用完整 ID |
| `horizon` | `22d` | 目标周期 |
| `status` | `active` / `watch_only` / `disabled` | 是否进入每日候选池 |

组合也要单独命名：

| 组合 | ID | 含义 |
|---|---|---|
| 星火进攻版 | `spark_aggressive@20260516` | top1 + 条件 top2 + `pc_model_th6_stop12` |
| 星火稳健版 | `spark_guarded@20260516` | top1 + `pc_model_th6_guard12_stop12` |

## 4. 标准模型产物目录

以后新模型建议按这个结构交付：

```text
data/selection/models/{source_id}/{source_version}/
  source_manifest.json
  model.joblib
  feature_columns.json
  training_config.json
  label_spec.json
  backtest_summary.json
  sample_candidates.json
  latest_candidates.csv
  README.md
```

如果模型不止一个文件，例如持仓模型，可以这样：

```text
data/selection/models/{source_id}/{source_version}/
  source_manifest.json
  models/
    exit_model.joblib
    continuation_model.joblib
  feature_columns.json
  action_contract.json
  backtest_summary.json
  sample_actions.json
  README.md
```

当前星火模型可以暂时保留旧目录，但补齐 manifest 和 adapter 后再视情况迁移。

## 5. `source_manifest.json` 必填内容

每个模型版本必须带 manifest：

```json
{
  "source_id": "spark_opportunity_selector",
  "source_name": "星火机会模型 1.0",
  "source_type": "model",
  "source_version": "1.0",
  "artifact_version": "opportunity_discovery_trade_l2_v0_1",
  "horizon": "22d",
  "status": "watch_only",
  "artifact_paths": {
    "model": "model.joblib",
    "feature_columns": "feature_columns.json"
  },
  "train_start_date": "2025-01-02",
  "train_end_date": "2026-05-14",
  "label_definition": "D日盘后信号，D+1开盘买入，未来22个交易日最大冲高机会分",
  "data_sources": [
    "market_atomic_mainboard_compact_current.db",
    "selection_research.db",
    "fine_theme_heat_daily.db"
  ],
  "point_in_time_safe": true,
  "owner_note": "研究可用，需人工确认次日开盘条件"
}
```

## 6. 每日候选适配器

每个选股模型必须提供：

```python
SOURCE_ID = "spark_opportunity_selector"
SOURCE_NAME = "星火机会模型 1.0"
SOURCE_TYPE = "model"
SOURCE_VERSION = "1.0"
HORIZON = "22d"

def generate_daily_candidates(trade_date: str, *, limit: int = 50) -> list[dict]:
    """Return standard candidate records for one signal date."""
```

输出必须符合 `docs/selection/daily_candidate_source_contract.md`。

最低标准：

| 字段 | 要求 |
|---|---|
| `trade_date` | 明确目标日期，不能只输出 latest |
| `symbol` | 小写 `sh/sz/bj` + 6 位代码 |
| `source_id/source_version` | 必须可追溯到模型产物 |
| `rank/score` | 来源内部排序和分数 |
| `suggested_action` | `candidate_buy` / `watch` / `blocked` |
| `entry_allowed` | 是否允许次日操作 |
| `buy_rule` | 买入约束 |
| `reason_summary` | 一句话中文解释 |
| `risk_tags` | 风险标签数组 |
| `explain_factors` | 结构化解释字段 |

## 7. 持仓动作适配器

持仓模型不能混进候选池。它必须单独输出动作：

```python
SOURCE_ID = "sentinel_postclose_exit"
SOURCE_NAME = "守势持仓模型"
SOURCE_TYPE = "model"
SOURCE_VERSION = "postclose_exit_v0_2"

def generate_daily_actions(trade_date: str, positions: list[dict]) -> list[dict]:
    """Return hold/watch_risk/sell_next_open actions for current positions."""
```

输入依赖：

```text
model_position_daily
```

输出写入：

```text
model_action_daily
```

动作枚举：

| action | 含义 |
|---|---|
| `hold` | 继续持有 |
| `watch_risk` | 风险观察 |
| `sell_next_open` | 次日开盘卖出 |

## 8. 点时安全检查

任何模型接入前必须通过点时安全检查：

1. 生成 `trade_date` 候选时，只能读 `trade_date` 收盘时已经存在的数据。
2. 禁止使用未来 5/22 日收益、未来最高价、未来标签。
3. 禁止用 `validation_topk.csv` 伪装成每日候选。
4. 禁止只覆盖 `latest_candidates.csv` 导致历史不可复现。
5. 必须支持重复运行同一天并覆盖同一天结果。

## 9. 训练阶段 SOP

每次训练新模型按这个顺序：

1. 定义业务问题：选股、买点、持仓、风控，不能混在一个模型里。
2. 定义 `source_id` 和 `source_version`。
3. 写标签定义：信号日、入场价、目标窗口、收益/回撤口径。
4. 列数据源和可用时间范围。
5. 构造点时安全特征。
6. 训练模型并保存冻结产物。
7. 做月度滚动验证和连续账户验证。
8. 输出 manifest、summary、样例候选。
9. 实现 `generate_daily_candidates` 或 `generate_daily_actions`。
10. 先标记 `watch_only`，连续模拟盘验证后再升为 `active`。

## 9.1 市场指数环境特征

训练或日更使用 `model_feature_store` 时，必须先确认指数缓存已刷新：

```text
/Users/dong/Desktop/AIGC/market-data/selection/model_market_index_daily.db
```

当前 P0 指数为 `000852.SH`、`000905.SH`、`000300.SH`、`000001.SH`、`399006.SZ`。其中 `000852.SH` 是必需项，用来生成 `model_market_state_daily_v1 / model_feature_daily_v1` 的 `csi1000_*` 字段。

运行卡：

```text
docs/selection/model_market_index_daily_runbook.md
```

## 10. 发布门槛

模型状态分三档：

| 状态 | 标准 |
|---|---|
| `research` | 有训练和回测，但无标准适配器 |
| `watch_only` | 有标准输出，可进工作台观察，不建议自动买 |
| `active` | 连续前推验证稳定，可作为正式候选来源 |

星火机会模型当前应是：

```text
watch_only
```

原因：已有回测价值和模型产物，但还缺按 `trade_date` 的生产推理适配器和真实前推记录。

守势持仓模型当前应是：

```text
research
```

原因：研究回测有效，但还缺真实/模拟持仓输入表和每日动作输出接口。

## 11. 当前下一步

模型侧下一步只做三件事：

1. 给星火机会模型补 `source_manifest.json`。
2. 给星火机会模型补 `generate_daily_candidates(trade_date)` 适配器。
3. 产出一天标准候选 JSON 样例，交给工作台开发侧对接。

守势持仓模型等 `model_position_daily` 定下来后，再做动作适配器。

## 12. 星火机会模型 1.0 已固化产物

当前已固化：

| 项 | 路径 |
|---|---|
| 适配器 | `backend/app/services/spark_opportunity_selector.py` |
| 导出脚本 | `backend/scripts/export_spark_opportunity_candidates.py` |
| manifest | `data/selection/opportunity_discovery/opportunity_discovery_trade_l2_v0_1/source_manifest.json` |
| 标准样例 | `data/selection/opportunity_discovery/opportunity_discovery_trade_l2_v0_1/sample_candidates_2026-05-14.json` |

开发侧 P1 可以先用桥接模式：

```bash
python3 backend/scripts/export_spark_opportunity_candidates.py \
  --date 2026-05-14 \
  --mode latest-csv \
  --limit 50
```

P3 正式每日推理使用：

```bash
python3 backend/scripts/export_spark_opportunity_candidates.py \
  --date 2026-05-14 \
  --mode infer \
  --limit 50
```

`infer` 模式会加载 `model.joblib` 和 `feature_columns.json`，从正式 atomic/selection/heat 库按目标日期重新构造点时特征。运行环境必须安装 `numpy`、`pandas`、`scikit-learn`、`joblib`。
