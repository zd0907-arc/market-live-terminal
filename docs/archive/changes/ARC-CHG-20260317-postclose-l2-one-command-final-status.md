> Archive-Meta
- Archive-ID: ARC-CHG-20260317-postclose-l2-one-command-final-status
- Archive-Type: CHG
- Archived-At: 2026-03-17
- Source-Path: docs/changes/REQ-20260317-10-postclose-l2-one-command-final-status.md
- Status: FROZEN

# REQ-20260317-10-postclose-l2-one-command-final-status

## 1. 基本信息
- 标题：盘后 L2 一条命令最终态收口（PASS / PASS_WITH_WARNINGS / FAIL）
- 状态：DONE
- 负责人：Codex / 运维 AI
- 关联 Task ID：`CHG-20260317-10`
- 关联 CAP：`CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 前置依赖：`REQ-20260316-07-postclose-l2-one-command-runner`

## 2. 背景与目标
- `2026-03-16` 与 `2026-03-17` 两次真实盘后跑数说明：主链路已经能完成“Windows prepare → 8 worker → cloud merge → 正式库可查”，但控制台最终仍只输出 `done / partial_done`，不利于业务侧快速判断“今天到底算不算生产可用”。
- 本卡目标是把总控脚本收口为业务可读的三档结论：
  - `PASS`
  - `PASS_WITH_WARNINGS`
  - `FAIL`

## 3. 方案与边界
- 做什么：
  - 在 `backend/scripts/run_postclose_l2_daily.py` 中新增总控级执行总结；
  - 内建 cloud 失败样本读取与分级；
  - 将“仅无有效 bar 空样本”归类为 `PASS_WITH_WARNINGS`；
  - 保持 `./ops/run_postclose_l2.sh` 作为唯一日常入口。
- 不做什么：
  - 不新增生产 API 抽查；
  - 不改变 worker / merge 既有数据写库逻辑；
  - 不改变 `merge_l2_day_delta.py` 内部 `done / partial_done / failed` 记录方式。

## 4. 冻结规则
- `PASS`：
  - worker 全部成功；
  - cloud merge 成功；
  - `verify_report` 与 merge 行数一致；
  - 无失败样本。
- `PASS_WITH_WARNINGS`：
  - worker 全部成功；
  - cloud merge 成功；
  - `verify_report` 与 merge 行数一致；
  - 失败样本仅包含“无有效 bar：交易时段内无可用逐笔（可能停牌、无成交或原始数据为空）”。
- `FAIL`：
  - 任一 worker 非零退出；
  - 或 cloud merge 失败；
  - 或正式库写入为空；
  - 或 verify 不一致；
  - 或存在非空样本类硬失败。

## 5. 操作说明（冻结）
- 执行机器：**Mac 本机**
- 执行目录：
  ```bash
  cd /Users/dong/Desktop/AIGC/market-live-terminal
  ```
- 日常执行：
  ```bash
  ./ops/run_postclose_l2.sh
  ```
- 指定日期：
  ```bash
  ./ops/run_postclose_l2.sh --date 20260317
  ```
- 结果判定：
  - 看终端输出中的 `final_status`
  - 以及本地报告：
    - `.run/postclose_l2/latest.json`
    - `.run/postclose_l2/YYYYMMDD/report.json`

## 6. 结果回填
- 实际改动：
  1. `run_postclose_l2_daily.py` 新增 `execution_summary`；
  2. 新增云端失败样本汇总读取；
  3. 最终输出统一收口为 `PASS / PASS_WITH_WARNINGS / FAIL`。
- 验证结果：
  - 对现有 `20260317` 报告重算分类后，结果为：
    - `PASS_WITH_WARNINGS`
    - 原因：仅存在 `13` 个“无有效 bar”空样本软告警
    - `is_production_ready = true`

## 7. 归档信息
- 归档时间：2026-03-17
- Archive ID：ARC-CHG-20260317-postclose-l2-one-command-final-status
- 归档路径：docs/archive/changes/ARC-CHG-20260317-postclose-l2-one-command-final-status.md
