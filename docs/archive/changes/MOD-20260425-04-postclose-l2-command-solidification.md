# MOD-20260425-04-postclose-l2-command-solidification

## 1. 基本信息
- 标题：盘后 L2 日跑指令固化与 2026-04-24 验证收口
- 状态：DONE
- 负责人：Codex
- 关联 CAP：`CAP-WIN-PIPELINE`, `CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`
- 关联 STG：`STG-20260415-03`

## 2. 背景与目标
- 当前正式日跑入口已经收敛到 `ops/run_postclose_l2.sh`，但主线仓库里仍残留旧版同步逻辑。
- 用户要求把“每天盘后要跑哪条命令”固化，并把 `2026-04-24` 这天补到可验证成功。
- 硬约束：Windows -> Mac 禁止再走 SSH/scp 直拉，只允许：
  1. 局域网 HTTP 直拉
  2. 云端 relay 中转

## 3. 方案与边界
- 做什么：
  - 为日跑主脚本补齐双通道同步链路。
  - 修复 Mac 本地 atomic merge 对 `pandas` 的隐式依赖。
  - 固化日常指令与运维文档。
  - 回填 `2026-04-24` 的实际验证结果。
- 不做什么：
  - 不把 Cloud 改成 full atomic 主库。
  - 不恢复 Windows -> Mac 的 SSH/scp 直拉。

## 4. 执行步骤（按顺序）
1. 核对主线仓库内 `backend/scripts/run_postclose_l2_daily.py` 的真实版本。
2. 新增 `backend/scripts/postclose_http_relay.py`。
3. 将 Windows -> Mac 同步改为：
   - 局域网 `HTTP relay`
   - 失败时自动回退 Cloud relay
4. 修复 `merge_atomic_day_delta.py`，去掉对运行时 `pandas` 环境的间接依赖。
5. 回补 `2026-04-24`：
   - Mac `market_data.db`
   - Mac `atomic`
   - Mac `selection`
   - Cloud `history_daily_l2 / history_5m_l2`
6. 增加“已完整成功则复用现有结果”的恢复语义，避免同一天重复强制重跑。

## 5. 验收标准（Given/When/Then，绝对时间）
- Given `2026-04-24` 的 Windows 日包已存在
- When 执行
  - `cd /Users/dong/Desktop/AIGC/market-live-terminal`
  - `bash ops/run_postclose_l2.sh`
- Then
  - 若当日未完成，则按正式链路跑完；
  - 若当日已完成，则直接复用成功结果；
  - Mac / Cloud 都能查到 `2026-04-24`：
    - `history_daily_l2 = 7644`
    - `history_5m_l2 = 346154`
  - Mac 本地还能查到：
    - `atomic_trade_daily = 3184`
    - `selection_feature_daily = 3184`

## 6. 风险与回滚
- 风险：
  - Cloud merge 仍可能慢，但不应再因为 SSH 挂死导致整条命令失控。
  - 强制重跑已成功日期没有业务价值，因此改成优先复用已有成功结果。
- 回滚：
  - 若新同步链路异常，回退到本卡前版本，并按 `docs/changes/MOD-20260417-01-local-research-current-state.md` 的旧应急路径手工补尾。

## 7. 结果回填
- 实际改动：
  - 更新 `backend/scripts/run_postclose_l2_daily.py`
  - 新增 `backend/scripts/postclose_http_relay.py`
  - 更新 `backend/scripts/merge_atomic_day_delta.py`
  - 更新 `docs/AI_QUICK_START.md`
  - 更新 `docs/ops/postclose-l2-runbook.md`
  - 更新 `docs/04_OPS_AND_DEV.md`
- 验证结果：
  - `2026-04-24` 已完成验证
  - `existing_cloud_days_count = 317`
  - 主日跑 dry-run 返回 `无待跑交易日`
- 遗留问题：
  - Cloud merge 的真实 wall time 仍需要继续观察，但链路已从“会挂死”收敛到“可恢复 / 可复用”。

## 8. 归档信息
- 归档时间：2026-04-25
- Archive ID：待后续归档
- 归档路径：`docs/changes/MOD-20260425-04-postclose-l2-command-solidification.md`
