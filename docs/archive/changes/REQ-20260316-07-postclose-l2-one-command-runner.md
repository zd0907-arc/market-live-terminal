# REQ-20260316-07-postclose-l2-one-command-runner

## 1. 基本信息
- 标题：每日盘后 L2 一条命令总控（Mac 发起、Windows 计算、云端入正式库）
- 状态：IN_PROGRESS
- 负责人：Codex / 后端 AI
- 关联 Task ID：`CHG-20260316-07`
- 关联 CAP：`CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 关联 STG：`STG-20260314-01`

## 2. 背景与目标
- 当前 `2025-01 ~ 2026-03-13` 的历史底座已基本到位，后续不再继续回补 `2025-01` 之前的更老月份。
- 今后只需要处理**每天盘后新增的 L2 日包**，但当前正式回补仍偏手工：需要人工判定日期、手动起多 worker、手动做上云与验真。
- 目标是冻结一套**Mac 一条命令**的日常方案：你只需确认 Windows 已下载好日包，然后在 Mac 执行一次命令，剩余动作全部自动完成。

## 3. 方案与边界
- 做什么：
  - 新增 Mac 总控脚本，自动发现 Windows 上“已下载但未入生产正式库”的交易日；
  - 每个交易日自动完成：日包稳态检查 -> staging 解压 -> 8 worker 并发跑 shard -> 生成 worker artifact -> 上传云端 -> 云端 merge -> 验真 -> 出日报；
  - 默认只处理**日增量**，不再把 `2025-01` 之前月份纳入本流程。
- 不做什么：
  - 本卡不做 Windows 本机全自动定时任务替代；
  - 本卡不再用“整库覆盖云端”的方式同步正式结果；
  - 本卡不处理复盘页并库。

## 4. 核心设计决策
1. **总控发起点固定为 Mac**
   - 用户每天盘后只在 Mac 执行一次命令。
2. **Windows 继续作为数据面 / 计算面**
   - 原始日包仍下载到 `D:\MarketData\YYYYMM\YYYYMMDD.7z`。
3. **云端继续作为唯一正式权威库**
   - 正式表仍是 `history_5m_l2 / history_daily_l2 / l2_daily_ingest_runs / l2_daily_ingest_failures`。
4. **不再让 8 worker 直接并发写正式生产库**
   - 每个 worker 先写自己的 day-delta artifact DB；
   - 由云端 merge 脚本统一按交易日合并到正式库。
5. **日常不追求 0 异常**
   - 允许 partial_done；
   - 失败样本与空样本必须入 `l2_daily_ingest_failures`，前端靠 `quality_info` / 空态识别。

## 5. 执行步骤（按顺序）
1. 新增 Windows 预处理脚本：单日检查 archive、解压到 staging、切 shard。
2. 新增云端 merge 脚本：把 8 个 worker artifact 合并进正式库。
3. 新增 Mac 总控脚本：
   - 发现 pending day；
   - 调 Windows prepare；
   - 并发拉起 8 个 SSH worker；
   - 中转 artifact 到云端；
   - 触发 merge 与验真；
   - 输出 JSON report。
4. 提供最终用户入口：
   - `./ops/run_postclose_l2.sh`
5. 回填 `04/07/AI_HANDOFF_LOG`。

## 6. 验收标准（Given/When/Then，绝对时间）
- Given `2026-03-17 16:20` Windows 已存在 `D:\MarketData\202603\20260317.7z`，When 在 Mac 执行 `./ops/run_postclose_l2.sh`，Then 系统应自动发现 `20260317` 为 pending day，并完成 prepare + shard worker + cloud merge。
- Given `2026-03-17 16:45` 某日有少量异常 symbol，When 总控完成，Then 云端 `l2_daily_ingest_runs` 应记录该日 `status=partial_done`，且失败样本被写入 `l2_daily_ingest_failures`。
- Given `2026-03-17 17:00` 当日 merge 已完成，When 查询云端正式库，Then `history_daily_l2` 与 `history_5m_l2` 应存在该交易日数据，且 staging 被清理、原始 `.7z` 被保留。

## 7. 风险与回滚
- 风险：
  - 若 Mac 与 Windows / 云端任一链路不通，则无法完成一条命令闭环；
  - 若 artifact merge 设计不当，可能把 partial 结果误覆盖成正式结果。
- 回滚：
  - 保留当前“人工按日 + 8 worker + 手工 merge”的旧路径；
  - 云端 merge 失败时，不覆盖原交易日正式结果；
  - 单日强制重跑通过 `--force-date YYYYMMDD` 进行覆盖修复。

## 8. 结果回填
- 实际改动：
  - 新增 Mac 总控：`backend/scripts/run_postclose_l2_daily.py`
  - 新增 Windows prepare：`backend/scripts/l2_postclose_prepare_day.py`
  - 新增云端 merge：`backend/scripts/merge_l2_day_delta.py`
  - 新增入口脚本：
    - `ops/run_postclose_l2.sh`
    - `ops/win_prepare_l2_day.bat`
    - `ops/win_run_l2_shard.bat`
  - 新增单测：`backend/tests/test_merge_l2_day_delta.py`
- 验证结果：
  - `PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile ...` 通过；
  - `python3 -m pytest -q backend/tests/test_merge_l2_day_delta.py` 通过（`1 passed`）；
  - 文档已同步冻结：后续只处理每日新增交易日，`2025-01` 之前不再继续扩历史范围。
  - `2026-03-16` 首个真实演练已完成：
    - dry-run 自动识别 pending day=`20260316`
    - Windows 8 worker artifact 产出成功
    - 云端 merge 最终成功写入生产：
      - `history_daily_l2=7663`
      - `history_5m_l2=345461`
      - `run_id=102`
      - `status=partial_done`
      - `failure_count=15`
- 遗留问题：
  - 当前 cloud merge 仍依赖 `sudo python3 backend/scripts/merge_l2_day_delta.py`；
  - 完全无人值守定时化仍留在 `T-014` 后续阶段；
  - 若后续要把 daily runner 变成正式定时任务，需要把“Windows 端脚本同步”也纳入固定发布动作。

## 9. 归档信息
- 归档时间：
- Archive ID：
- 归档路径：
