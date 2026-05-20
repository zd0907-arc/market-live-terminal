# 每日选股工作台模型接入方案（2026-05-16）

## 结论

删文件这件事，当前优先级范围内已经完成。

已清理：

- S06 融合复盘页和静态报告。
- 已替代的 `postclose_exit_v0_1/`。
- H5、早盘执行、卖飞审计、旧滚动 split 等过程性实验产物。
- 旧 S06 编号文档和对应实验结论，已压缩到 `docs/selection/selection_research_archive_decision_summary.md`；详细留痕已迁入 `docs/archive/`。

未清理但暂不阻塞开发：

- PPO / evolution lab：仍有页面、API、服务和 79M 数据目录引用，建议第三批单独删。
- 旧研究脚本：可作为旧实验重跑入口，先不和产物清理混删。
- `aggressive_10cm`、长期趋势、热点研究：属于其他研究线，单独判断；热点主题暂不进入每日选股候选池。

接下来开发不应该继续围绕“选择一个策略下拉框”做。正确方向是：

```text
每天盘后刷新数据
→ 各策略/模型自动生成候选
→ 写入正式选股库的统一候选表
→ 页面按日期读取统一候选池
→ 左侧列表展示来源标签
→ 右侧详情展示该票所有来源、解释、风险和后续动作
```

## 当前现状

### 前端

主页面：

```text
src/components/selection/SelectionResearchPage.tsx
```

当前已经有“每日复盘决策”聚合雏形：

- 默认 `activeStrategy = daily_review`。
- 内部同时请求：
  - `stable_capital_callback`
  - `trend_continuation_callback`
  - `v2` 观察池
- 左侧已经能按“明日可操作 / 观察中 / 已拦截”分组。
- 卡片上已有 `strategy_display_name`、`strategy_internal_id` 标签。
- 右侧复用 `SelectionDecisionPanel`。

主要问题：

- 页面顶部仍然有策略下拉框。
- `daily_review` 是前端拼装，不是后端统一候选池。
- 不支持模型来源，例如星火机会模型。
- 同一只票多来源命中时没有合并，只是多条候选。
- 日期可选性仍依赖单策略或两个策略的结果，不看模型结果。
- `v2` 观察池实际价值低，应从日常候选池移除，只保留为后台调试/回测入口。

### 后端 API

当前入口：

```text
backend/app/routers/selection.py
```

已有接口：

| 接口 | 状态 |
|---|---|
| `GET /api/selection/candidates?strategy=...` | 单策略候选 |
| `GET /api/selection/trade-dates?strategy=...` | 单策略可选日期 |
| `GET /api/selection/profile/{symbol}?strategy=...` | 单来源详情 |
| `POST /api/selection/refresh` | 刷新旧选股特征和信号 |

当前策略分流：

| strategy | 实现 |
|---|---|
| `stable_capital_callback` | `selection_stable_callback.py`，读 S01 实验 CSV |
| `trend_continuation_callback` | `selection_trend_continuation.py`，读 S02 实验 CSV |
| `v2` | `selection_strategy_v2.py`，实时从 atomic/selection 库计算；不进入新日常候选池 |
| `stealth/breakout/distribution` | `selection_research.py`，旧信号表 |

主要问题：

- 没有 `/selection/daily-candidates` 这类统一接口。
- 旧 S01/S02 仍读文档目录里的 CSV，不是正式库。
- 星火机会模型没有 API 接入。
- 模型结果目前只是 CSV：`latest_candidates.csv`、`latest_actionable_candidates.csv`。

### 数据库

正式选股库：

```text
/Users/dong/Desktop/AIGC/market-data/selection/selection_research.db
```

当前表：

| 表 | 行数/范围 |
|---|---|
| `selection_feature_daily` | 1,582,064 行，2025-01-02 ~ 2026-05-14 |
| `selection_signal_daily` | 1,582,064 行，2025-01-02 ~ 2026-05-14 |
| `selection_backtest_*` | 旧回测记录 |

缺的表：

- `selection_strategy_registry`
- `selection_candidate_daily`
- `selection_candidate_sources`
- `model_position_daily`
- `model_action_daily`
- `selection_strategy_runs`

### 当前可接入来源

| 来源 | source_id | 类型 | 当前状态 | 接入建议 |
|---|---|---|---|---|
| 资金流回调稳健 | `stable_capital_callback` | 规则策略 | 页面已接入，但读 CSV | 第一批迁入每日真实跑数 |
| 趋势中继高质量回踩 | `trend_continuation_callback` | 规则策略 | 页面已接入，但读 CSV | 第一批迁入每日真实跑数 |
| 星火机会模型 | `spark_opportunity_selector` | 模型 | 有模型和 latest CSV，未入库 | 第一批先接候选，后补标准每日推理 |
| 守势持仓模型 | `sentinel_postclose_exit` | 持仓动作模型 | 当前研究产物不能直接作为每日动作接口 | 等新模型产出符合契约后接入 |

明确不进入 P1：

- `v2` 旧策略观察池：从日常候选池移除。
- 热点主题：暂时不作为候选来源，只保留后续做解释/共振标签的可能。

## 目标产品形态

页面默认只做一件事：

```text
选择日期 → 看当天所有来源给出的候选票
```

页面顶部保留：

- 日期选择器。
- 刷新按钮。
- 来源筛选小按钮：全部 / 模型 / 策略 / 观察 / 已拦截。

不再保留：

- 日常使用路径里的策略下拉框。

左侧列表：

| 元素 | 展示方式 |
|---|---|
| 股票名/代码 | 保持现在格式 |
| 总排序 | 综合候选池排序 |
| 来源标签 | `星火机会`、`资金流回调`、`趋势中继` |
| 动作标签 | `明日可买`、`观察`、`风险拦截`、`持有`、`次日卖出` |
| 多来源命中 | 显示来源数量和徽标 |
| 简短原因 | 取最高优先级来源的 `reason_summary` |

右侧详情：

- 仍用 `SelectionDecisionPanel` 做价格/K线/研究上下文。
- 新增“来源解释”区：
  - 每个来源为什么命中。
  - 每个来源的 rank、score、周期、买入条件。
  - 风险标签和拦截原因。
- 如果有持仓动作：
  - 展示 `hold / watch_risk / sell_next_open`。
  - 展示守势模型理由。

## 建议数据结构

### `selection_strategy_registry`

登记所有来源，避免前端写死。

核心字段：

| 字段 | 说明 |
|---|---|
| `source_id` | `spark_opportunity_selector` |
| `source_name` | 星火机会模型 |
| `source_type` | `model` / `rule_strategy` / `theme` / `manual` |
| `source_version` | 模型或策略版本 |
| `horizon` | `22d`、`swing`、`watch` |
| `status` | `active` / `watch_only` / `deprecated` |
| `description` | 中文说明 |
| `updated_at` | 更新时间 |

### `selection_candidate_daily`

按“日期 + 股票”合并后的候选主表。

核心字段：

| 字段 | 说明 |
|---|---|
| `trade_date` | 信号日 |
| `symbol` | 股票代码 |
| `name` | 股票名 |
| `combined_rank` | 综合排序 |
| `combined_score` | 综合分 |
| `suggested_action` | `candidate_buy` / `watch` / `blocked` / `hold` / `sell_next_open` |
| `action_label` | 中文动作 |
| `source_count` | 命中来源数 |
| `source_ids_json` | 来源 ID 列表 |
| `primary_source_id` | 主来源 |
| `primary_source_name` | 主来源中文名 |
| `reason_summary` | 列表摘要 |
| `risk_tags_json` | 风险标签 |
| `entry_block_reasons_json` | 拦截原因 |
| `buy_rule` | 次日买入约束 |
| `created_at` / `updated_at` | 时间 |

### `selection_candidate_sources`

保留“同一只票每个来源为什么命中”。

核心字段：

| 字段 | 说明 |
|---|---|
| `trade_date` | 信号日 |
| `symbol` | 股票代码 |
| `source_id` | 来源 |
| `source_type` | 类型 |
| `source_name` | 中文名 |
| `rank` | 来源内排序 |
| `score` | 来源内分数 |
| `horizon` | 周期 |
| `suggested_action` | 来源建议 |
| `reason_summary` | 来源解释 |
| `risk_tags_json` | 风险 |
| `explain_factors_json` | 解释因子 |
| `raw_payload_json` | 原始候选数据 |

### `model_position_daily` / `model_action_daily`

第二阶段做持仓动作时用。

`model_position_daily` 记录真实或模拟持仓：

- `trade_date`
- `symbol`
- `entry_date`
- `entry_price`
- `quantity`
- `position_source`
- `notes`

`model_action_daily` 记录持仓模型动作：

- `trade_date`
- `symbol`
- `source_id = sentinel_postclose_exit`
- `action = hold / watch_risk / sell_next_open`
- `action_score`
- `reason_summary`
- `raw_payload_json`

## 后端改造

## 外部模型/策略接入要求

后续其他会话开发的新模型或新策略，要先满足“每日候选来源契约”，才能接入工作台。工作台不直接读取临时 CSV、训练报告或任意格式 JSON。

### 候选生成契约

每个来源必须提供一个稳定的每日产物：

```text
run(source_id, trade_date) -> candidate records
```

最低要求：

| 要求 | 说明 |
|---|---|
| 点时可用 | 只能使用 `trade_date` 当日收盘前已经存在的数据 |
| 可重复运行 | 同一天重复运行结果可覆盖，不产生重复候选 |
| 输出目标日期 | 必须明确 `trade_date`，不能只写“latest” |
| 输出来源信息 | 必须有稳定 `source_id`、中文名、版本号 |
| 输出候选解释 | 每条候选必须有 `reason_summary` 和结构化因子 |
| 输出风险/拦截 | 不能买的票必须写 `suggested_action=blocked/watch` 和原因 |
| 不依赖页面选择 | 来源由后台注册和每日任务调度，不由页面下拉框决定 |

### 标准候选记录

每个模型/策略至少输出这些字段：

| 字段 | 必填 | 说明 |
|---|---|---|
| `trade_date` | 是 | 信号日，YYYY-MM-DD |
| `symbol` | 是 | `sh600000` / `sz000001` 格式 |
| `name` | 否 | 没有可由系统补 |
| `source_id` | 是 | 稳定英文 ID |
| `source_name` | 是 | 中文名 |
| `source_type` | 是 | `model` / `rule_strategy` |
| `source_version` | 是 | 模型或策略版本 |
| `rank` | 是 | 来源内部排序 |
| `score` | 是 | 来源内部分数 |
| `score_scale` | 否 | 默认 `raw`，可为 `0_100`、`probability` |
| `horizon` | 是 | `1d` / `5d` / `22d` / `swing` |
| `suggested_action` | 是 | `candidate_buy` / `watch` / `blocked` |
| `action_label` | 是 | 中文动作 |
| `entry_allowed` | 是 | 是否允许作为明日可操作 |
| `buy_rule` | 否 | 买入约束 |
| `reason_summary` | 是 | 一句话解释 |
| `risk_tags` | 否 | 数组 |
| `entry_block_reasons` | 否 | 数组 |
| `explain_factors` | 是 | 结构化解释对象 |
| `raw_payload` | 否 | 原始输出，供追溯 |

### 标准 Python 适配器

每个可接入来源建议提供一个适配器函数：

```python
def generate_daily_candidates(trade_date: str, *, limit: int = 50) -> list[dict]:
    ...
```

如果是模型，还要提供：

```python
MODEL_SOURCE_ID = "spark_opportunity_selector"
MODEL_SOURCE_NAME = "星火机会模型"
MODEL_SOURCE_TYPE = "model"
MODEL_VERSION = "..."
```

工作台只认适配器返回的标准候选记录，不关心模型内部是 joblib、csv、pytorch 还是规则函数。

### 当前两个新模型的判断

| 模型 | 当前状态 | 接入判断 |
|---|---|---|
| 星火机会模型 | 已冻结 1.0，并提供 `generate_daily_candidates(trade_date)` 标准适配器；保留 latest CSV 桥接作为兜底 | P1 进入统一候选池，默认 `watch_only` 前推观察 |
| 守势持仓模型 | 当前是研究回测产物，缺真实/模拟持仓输入和每日动作输出 | 不在 P1 硬接；等新版输出 `model_action_daily` 契约后接入 |

### 对其他会话的交付要求

其他会话如果开发新模型，要交付：

1. 模型/策略说明：source_id、中文名、周期、适用场景、不能用的场景。
2. 每日推理脚本或适配器：输入 `trade_date`，输出标准候选记录。
3. 依赖数据说明：读哪些库/表/文件，是否点时安全。
4. 输出样例：至少 1 天 JSON 或 DataFrame 示例。
5. 回测摘要：样本范围、胜率、收益、回撤、主要风险。
6. 接入状态：`active`、`watch_only`、`disabled`。

### 新增服务

已新增：

```text
backend/app/services/selection_daily_workbench.py
backend/app/services/selection_candidate_store.py
```

职责：

- 从统一表读取当天候选。
- 合并多来源。
- 给前端返回兼容 `SelectionCandidateItem` 的结构。
- 提供 symbol 详情，聚合多来源解释。

### 新增 API

已新增，不破坏旧接口：

| 接口 | 作用 |
|---|---|
| `GET /api/selection/daily-candidates?date=YYYY-MM-DD&limit=50&source_type=` | 页面左侧统一候选 |
| `GET /api/selection/daily-trade-dates?start_date=&end_date=` | 日期选择器 |
| `GET /api/selection/daily-profile/{symbol}?date=YYYY-MM-DD` | 右侧详情，多来源解释 |
| `POST /api/selection/daily-refresh?date=YYYY-MM-DD` | 触发当日候选生成 |

旧接口先保留给回测和调试。

### 新增每日脚本

已新增：

```text
backend/scripts/run_daily_model_signals.py
```

第一版做三件事：

1. 确认 `selection_feature_daily` 和 `selection_signal_daily` 已覆盖目标日期。
2. 运行或导入符合契约的候选来源。
3. 写入 `selection_candidate_sources` 和 `selection_candidate_daily`。

P1 允许星火模型先导入已有 `latest_candidates.csv`，但这只是过渡；正式接入必须补“按目标日期推理”的适配器。

## 星火模型接入方式

当前第一阶段已经改成“按日期推理优先，latest CSV 桥接兜底”：

```text
trade_date
→ backend.app.services.spark_opportunity_selector.generate_daily_candidates(trade_date)
→ selection_candidate_sources
→ selection_candidate_daily
```

如果模型依赖或特征文件不可用，P1 允许短期兜底：

```text
latest_candidates.csv
→ generate_candidates_from_latest_csv(trade_date)
→ selection_candidate_sources
```

来源标签：

```text
source_id: spark_opportunity_selector
source_name: 星火机会模型 1.0
source_type: model
horizon: 22d
status: watch_only
```

后续仍要补生产化细节：

- 模型目录、atomic/selection/heat 库路径由每日任务显式配置。
- 运行结果记录到 `selection_strategy_runs`。
- watch_only 观察稳定后，再把 registry 状态切到 `active`。

## 规则策略接入方式

P1 可以暂时复用现有服务做过渡：

- `get_stable_callback_candidates(date)`
- `get_trend_continuation_candidates(date)`

由 `run_daily_model_signals.py` 或 `selection_daily_workbench.py` 统一转换成 `selection_candidate_sources`。

但正式版本必须把 S01/S02 改成每日真实跑数：

- 不再长期读取 `docs/strategy-rework/.../experiments/*.csv`。
- 策略运行结果写入统一候选表。
- 每天刷新后，如果当天有信号，页面自动展示。
- 如果当天没有信号，日期仍可选，但页面明确显示该来源无候选。

## 综合排序规则

第一版先简单、透明：

1. `candidate_buy` 排在 `watch` 前面，`blocked` 最后。
2. 多来源命中加分。
3. 模型主来源和规则主来源都命中时优先。
4. `risk_count >= 2` 或有硬拦截原因，降级为 blocked。

建议权重：

```text
base_score = source normalized score
+ 15 * source_count
+ 10 if model + rule_strategy both hit
- 20 if blocked
- 10 if watch_only
```

后续再改成可配置 registry 权重。

## 前端改造

### 第一版

改 `SelectionResearchPage.tsx`：

- 移除顶部策略下拉框。
- 默认调用 `fetchDailySelectionCandidates(date)`。
- 日期选择器调用 `fetchDailySelectionTradeDates()`。
- 左侧列表按：
  - 明日可操作
  - 观察中
  - 已拦截 / 风险提示
  分组。
- 卡片来源标签改为多个徽标。
- 点击候选后调用 `fetchDailySelectionProfile(symbol, date)`。

保留隐藏/折叠的“策略验证 / 回测”区，但不要影响日常路径。

### 第二版

给左侧加来源筛选：

- 全部
- 模型
- 策略
- 已拦截

不要恢复“按策略切换主列表”的下拉框。

## 版本和分支建议

当前分支是：

```text
codex/selection-cleanup-20260516
```

建议先提交清理分支，再从该点新建开发分支：

```text
codex/daily-selection-workbench
```

开发版本建议从 `5.1.6` 升到 `5.2.0`，因为这是选股工作台主流程变化。

## 分阶段执行

### P0：提交当前清理结果

- 提交删除和归档文档。
- 不再继续扩大删除范围。

### P1：最小可用统一候选池

- 新增数据库表。
- 新增 `selection_candidate_store.py`。
- 新增 `run_daily_model_signals.py`。
- 先导入星火 `latest_actionable_candidates.csv` + 当前 S01/S02 候选。
- 新增 `/selection/daily-candidates` 和 `/selection/daily-trade-dates`。
- 页面去掉策略下拉框，改读统一接口。

### P2：右侧多来源解释

- 新增 `/selection/daily-profile/{symbol}`。
- 右侧展示该票所有来源解释。
- 保留原有研究上下文和 K 线能力。

### P3：真正每日自动推理

- 星火模型按目标日期从正式库推理，而不是读 `latest_candidates.csv`。
- 每天盘后数据刷新后自动写入统一候选池。
- S01/S02 规则策略也改成每日计算并入库，不再读固定 CSV。

### P4：守势持仓动作

- 建 `model_position_daily` 和 `model_action_daily`。
- 输入真实/模拟持仓。
- 盘后输出 `hold / watch_risk / sell_next_open`。
- 页面把持仓动作并入左侧和右侧详情。

### P5：第三批清理

- 再判断 PPO / evolution lab 是否删除。
- 再判断旧脚本是否保留或移动到 archive。
