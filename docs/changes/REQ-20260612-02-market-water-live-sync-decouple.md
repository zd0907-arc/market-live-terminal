# REQ-20260612-02-market-water-live-sync-decouple

## 1. 基本信息
- 标题：每日市场水位与 live/L2 后处理解耦
- 状态：VERIFY
- 负责人：Codex
- 关联 Task ID：`REQ-20260612-02-market-water-live-sync-decouple`
- 关联 CAP：`CAP-SELECTION-RESEARCH`, `CAP-NAS-OPS`, `CAP-L2-HISTORY-FOUNDATION`
- 关联 STG：选股工作台每日市场环境辅助判断

## 2. 背景与目标
2026-06-12 单日报数完成后，选股工作台仍看不到当天“近期市场趋势”。排查确认当天核心研究数据已经完整落库，但每日主链在刷新市场水位前先执行 `live/L2` 后处理；当 `run_postclose_l2_daily.py` 失败时，主链提前失败退出，导致 2026-06-12 水位没有生成。

目标：
- 市场水位只依赖选股研究所需的核心数据，不被 live/L2 后处理失败挡住。
- 每日主链在核心数据完整后优先刷新市场水位，并重新做完整性校验。
- live/L2 后处理失败时只记录告警，不能让选股页缺当天水位。
- 带 `--sync-nas` 时，即使 live/L2 同步失败，也要继续同步市场水位小目录到 NAS 数据卷。

## 3. 方案与边界
- 做什么：
  - `run_daily_new_framework.py` 改为先执行 `local_market_environment_gate`，再执行 `local_live_sync`。
  - `local_live_sync` 异常被记录为 `status=failed` 和 `warnings`，不再中断主链。
  - NAS 后处理继续接收两类产物；live 缺失时按既有逻辑跳过 live 同步，但市场水位仍可同步。
  - 测试覆盖“水位先于 live 同步”和“live 失败不阻断水位同步”两条路径。
- 不做什么：
  - 不改变市场水位计算公式。
  - 不改变 live/L2 后处理自身逻辑；其失败原因作为独立问题继续排查。
  - 不改变选股候选生成、排序、买卖点和前端展示规则。

## 4. 本次补算结果
- 2026-06-12 已补算到本地运行态目录。
- 最新市场状态：`防守-修复观察`。
- 水位分数：`24.7265`。
- 默认动作：`暂停新开仓`。
- 主要原因：`5日全市场上涨占比26.4%；5日全市场中位涨跌幅-3.0%；5日小盘上涨占比16.2%`。

## 5. 验收标准
- Given：单日核心研究数据完整，且 live/L2 后处理失败。
- When：执行每日主链。
- Then：`local_market_environment_gate.status=generated`。
- Then：`local_live_sync.status=failed` 且报告包含告警。
- Then：`status=pass` 取决于核心数据与市场水位完整性，不被 live/L2 失败单独拉成失败。
- Then：`--sync-nas` 继续同步市场水位目录，选股页能读取当天水位。

## 6. 验证结果
- 本地接口：`/api/selection/market-environment?date=2026-06-12` 返回 `available=True, water_score=24.7265, recent=90`。
- 本地 3001 代理接口同样返回 `available=True`。
- `python3 -m py_compile backend/scripts/run_daily_new_framework.py backend/app/services/selection_market_environment_gate.py` 通过。
- `/usr/bin/python3 -m pytest backend/tests/test_run_daily_new_framework_auto.py backend/tests/test_selection_market_environment_gate.py -q` 通过：8 passed。
- `git diff --check` 通过。

## 7. 风险与后续
- `run_postclose_l2_daily.py` 在 2026-06-12 的失败仍需单独排查；本卡只保证它不再拖垮市场水位。
- 市场水位刷新仍是全量重算，短期可接受，后续再评估增量化。

## 8. 归档信息
- 当前状态：验证中，待生产发布和公开入口冒烟后更新为 `RELEASED`。
- 归档条件：下一交易日单日报数自动生成并同步水位后，可归档。
