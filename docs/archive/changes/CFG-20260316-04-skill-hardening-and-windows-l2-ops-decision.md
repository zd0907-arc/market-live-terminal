# CFG-20260316-04-skill-hardening-and-windows-l2-ops-decision

## 1. 基本信息
- 标题：文档/发布 Skill 优化 + Windows 正式 L2 回补自动化结论澄清
- 状态：DONE
- 负责人：Codex
- 关联 Task ID：`CHG-20260316-04`
- 关联 CAP：`CAP-WIN-PIPELINE`, `CAP-L2-HISTORY-FOUNDATION`, `CAP-HISTORY-30M`

## 2. 背景与目标
- 基于本轮新版历史多维 + 盘后 L2 正式回补 + 生产发布复盘，需要回答三个问题：
  1. 现有 `$governance-doc-keeper` 和 `$release-ops-commander` 是否需要补强；
  2. “不要再用 Windows 本机跑数”这个结论是否过度；
  3. 是否值得把盘后正式回补经验沉淀成独立 Skill。

## 3. 结论
### 3.1 Skill 优化结论
- `$governance-doc-keeper` 需要新增“复杂项目收口 / retrospective”能力：
  - 支持多张变更卡的统一复盘；
  - 区分 `Done / Released / Archived` 三个状态；
  - 强制检查 `07_PENDING_TODO` 是否与复盘结果一致。
- `$release-ops-commander` 需要补强：
  - 发生产前强制先 bump 版本；
  - 发布后校验前端静态产物确实包含目标版本号；
  - 支持“功能专项冒烟”，而不只是通用 health/token 冒烟；
  - 显式记录回滚锚点（tag / commit / 上一版本）。

### 3.2 Windows 自动化结论（纠偏）
- 需要纠正之前容易被误读的说法：
  - **不是“Windows 本机不能自动跑正式回补”**；
  - 而是 **“当前这版 `l2_day_sharded_backfill.py` 的 Python 父进程 `Popen` 编排不稳定，不能作为正式主路径”**。
- 更准确的结论是：
  1. **已验证稳定**：Windows 数据面 + 外部控制端 SSH 并发 8 worker；
  2. **可接受的未来目标**：Windows 本机通过 Task Scheduler / PowerShell / cmd 作为 OS 级控制器，拉起 8 个独立 worker，并用 `l2_daily_ingest_runs` 轮询验真；
  3. **当前不接受**：Windows Python 父进程长期托管多个 shard 子进程。

### 3.3 是否值得做新 Skill
- 值得，而且优先级高。
- 推荐新 Skill：`l2-postclose-ops`
- 原因：
  - 盘后正式回补流程长、顺序敏感、错误类型固定；
  - 已沉淀出明确的稳定路径、失败分类和验真规则；
  - 后续会反复执行（每日增量 + 月度历史补数），ROI 高。

## 4. 对正式自动化方案的澄清
### 4.1 为什么 sandbox V2 能在 Windows 全量跑成功
- sandbox V2 的全月份总控是“按月串行调用单月 backfill 脚本”；
- 重点是月级总控 + 自身断点续跑；
- 它没有走“一个 Python 父进程常驻托管 8 个正式回补 shard 子进程写生产库”的模式。

### 4.2 为什么正式 L2 日包回补暴露出不同问题
- 正式回补的并发目标是同一交易日、同一正式库、多个 shard 并发写入；
- 当前 `l2_day_sharded_backfill.py` 把“切 shard + 起子进程 + 等待返回”全包在一个 Windows Python 父进程里；
- 已出现 `partial_done + 0 rows` 的编排层不稳定现象。

### 4.3 可接受的未来 Windows 本机方案
- 若未来每天都要靠 Windows 自动化完成盘后正式回补，可以做，但要换控制方式：
  - 用 `schtasks` / PowerShell / `cmd /c` 做控制器；
  - 每个 worker 仍然是独立的 `python backend/scripts/l2_daily_backfill.py --symbols-file ...`；
  - 控制器不负责“推断成功”，只负责：拉起 worker、轮询 DB run 状态、导出失败清单、清理 staging。
- 这个方向是可行的，且比“必须依赖 Mac”更符合长期无人值守目标。

## 5. 实际改动
- 回填 `docs/04_OPS_AND_DEV.md`：
  - 明确“问题在当前 Python 父进程编排，不在 Windows 本机本身”；
  - 允许未来演进到 Windows 本机 OS 级控制器。
- 回填 `docs/07_PENDING_TODO.md`：
  - 更新 `T-014` 的目标表述；
  - 新增 `T-015`：固定池、按月回补、按月上线。
- 回填 `docs/02_BUSINESS_DOMAIN.md`：
  - 增加“固定池快照 + 逐月回补 + 月度同步生产”的拟变更点。

## 6. 风险与后续
- 当前只是澄清方向与治理，不等于 Windows 本机自动控制器已经实现；
- 真正要切到 Windows 本机无人值守，还需要：
  1. 控制脚本；
  2. 计划任务定义；
  3. run/failure 轮询与收尾；
  4. 冒烟与回滚预案。

## 7. 归档信息
- 归档时间：
- Archive ID：
- 归档路径：
