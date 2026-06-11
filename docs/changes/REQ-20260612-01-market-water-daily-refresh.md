# REQ-20260612-01-market-water-daily-refresh

## 1. 基本信息
- 标题：每日主链补齐选股页近期市场水位刷新
- 状态：LOCAL_READY_PENDING_PROD
- 负责人：Codex
- 关联 Task ID：`REQ-20260612-01-market-water-daily-refresh`
- 关联 CAP：`CAP-SELECTION-RESEARCH`, `CAP-NAS-OPS`
- 关联 STG：选股工作台市场环境辅助判断

## 2. 背景与目标
2026-06-11 用户在选股工作台切到当日后，看不到“近期市场趋势”。排查确认前端组件和生产代码仍存在，问题是市场水位研究产物没有被每日主链刷新；服务读取的静态研究快照只覆盖到 2026-06-10，`2026-06-11` 精确匹配失败后返回 `available=false`。

目标：
- 每日单日报数跑完后，自动生成当天市场水位。
- 选股页接口能直接读到最近 90 日水位走势。
- 带 `--sync-nas` 时，把小型市场水位目录同步到 NAS 生产数据卷，不再依赖重建 backend 镜像。

## 3. 方案与边界
- 做什么：
  - `run_daily_new_framework.py` 在本地核心数据完整后执行 `research_market_environment_gate.py`，输出到运行态目录 `research/current/selection/market_environment_gate_2026-06-10`。
  - 日报完整性校验新增 `market_environment_gate`，要求目标交易日已有水位。
  - `--sync-nas` 新增同步市场水位目录到 NAS 数据卷。
  - `selection_market_environment_gate.py` 改为优先读取运行态数据目录，仓库 docs 仅作为兜底。
  - 服务读取 CSV 按文件 mtime/size 缓存，避免每日文件更新后必须重启进程。
- 不做什么：
  - 不改变市场水位计算公式。
  - 不把水位研究脚本改成增量算法；当前仍是全量重算。
  - 不改变候选生成、排序、买卖点和交易建议规则。

## 4. 验收标准
- Given：本地正式数据已包含 2026-06-11。
- When：执行市场水位刷新。
- Then：运行态 `market_state_daily.csv` 最新日期为 `2026-06-11`。
- Then：`get_market_environment("2026-06-11")` 返回 `available=true`、`recent.length=90`。
- Then：`run_daily_new_framework` 的完整性校验中 `market_environment_gate.available=true` 才视为完整。
- Then：生产 NAS 后端读取运行态数据卷后，不需要重建镜像即可消费每日新水位文件。
- Then：即使当日候选池为空，只要市场水位已生成，选股工作台日期也能切到当天并展示“近期市场趋势”。

## 5. 本次补算结果
- 2026-06-11 已补算到本地运行态目录。
- 最新市场状态：`防守-弱势承压`。
- 水位分数：`17.1262`。
- 默认动作：`暂停新开仓`。
- 主要原因：`5日全市场上涨占比19.3%；5日全市场中位涨跌幅-4.1%；5日小盘上涨占比13.2%`。

## 6. 验证结果
- `python3 -m py_compile backend/scripts/run_daily_new_framework.py backend/app/services/selection_market_environment_gate.py` 通过。
- `/usr/bin/python3 -m pytest backend/tests/test_run_daily_new_framework_auto.py backend/tests/test_selection_market_environment_gate.py -q` 通过：7 passed。
- 本地服务读取验证：`2026-06-11 available=True, water_score=17.1262, recent=90`。
- 本地日报完整性验证：`core_complete=True, complete=True`。
- 页面入口补充验证：`daily-trade-dates` 会把 `has_market_environment=true` 的日期标为可选；`2026-06-11` 本地真实数据返回 `selectable=True`、`market_environment.available=True`、`water_score=17.1262`。
- 定向回归：`/usr/bin/python3 -m pytest backend/tests/test_selection_daily_workbench.py backend/tests/test_selection_market_environment_gate.py -q` 通过：13 passed。
- 前端构建：`npm run build` 通过。

## 7. 风险与后续
- 当前水位刷新仍是全量重算，耗时约十几秒；短期可接受，后续若数据量继续扩大再做增量化。
- 生产需要部署服务读取路径改造、日期入口补丁，并同步运行态水位目录到 NAS 数据卷。
- 仓库 docs 下的研究目录保留为历史兜底，不再作为每日运行态真相源。

## 8. 归档信息
- 当前状态：未归档。
- 归档条件：生产部署并验证 2026-06-11 水位在选股工作台可见后归档。
