# REQ-20260314-03-l2-history-db-and-directory-spec

## 1. 基本信息
- 标题：Phase 1｜盘后 L2 历史底座数据库与目录规范
- 状态：DONE
- 负责人：Codex / 后端 AI
- 关联 Task ID：`CHG-20260314-03`
- 关联 CAP：`CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 关联 STG：`STG-20260314-01`

## 2. 背景与目标
- 为后续盘后 L2 正式接入生产链路，先冻结数据库设计、目录命名、覆盖写规则、回补状态模型。
- 本阶段是整个方案的第一优先级，目标是“**数据库与目录规范先行**”。

## 3. 方案与边界
- 做什么：
  - 定义 Windows 月/日两级目录规范；
  - 定义 `history_5m_l2` / `history_daily_l2` / 回补状态表；
  - 定义按日覆盖写语义；
  - 定义生产正式库与 sandbox 库职责边界。
- 不做什么：
  - 不实现 ETL；
  - 不改前端；
  - 不开始生产数据迁移。

## 4. 执行步骤
1. 固化目录规范：`D:\MarketData\YYYYMM\YYYYMMDD\{symbol}`。
2. 固化正式生产表字段与主键。
3. 固化回补状态表与失败表字段。
4. 固化查询优先级与 fallback 语义。
5. 在 `02/03/04` 中同步写死这些规则。

## 5. 验收标准（Given/When/Then）
- Given `2026-03-14 18:00`，When 阅读本卡与 `03_DATA_CONTRACTS`，Then 可明确正式生产历史表、状态表与唯一键。
- Given `2026-03-14 18:05`，When 阅读 `04_OPS_AND_DEV`，Then 可明确 Windows 新日包必须放入月目录，而不是裸日目录。
- Given `2026-03-14 18:10`，When 评审 Phase 2/3/4 方案，Then 不需要再回头争论“5m 还是 1m”“多周期是否单独落库”“复盘是否长期双库”。

## 6. 风险与回滚
- 风险：若本阶段规则写得不够死，后续实现时会重新分叉出第二套 schema/第二套目录/第二套正式口径。
- 回滚：纯文档阶段，无生产回滚成本。

## 7. 结果回填
- 实际改动：
  - 新增生产 L2 历史 DB 模块：`backend/app/db/l2_history_db.py`
  - 新增目录规范 helper：`backend/app/core/l2_package_layout.py`
  - `backend/app/db/database.py` 已在 `init_db()` 中补挂 `ensure_l2_history_schema()`
  - `backend/scripts/inspect_daily_l2_package.py` 已支持标准 `YYYYMM/YYYYMMDD` 与旧双层日期目录的统一解析
  - 新增测试：`backend/tests/test_l2_history_foundation.py`
- 验证结果：
  - `history_5m_l2 / history_daily_l2 / l2_daily_ingest_runs / l2_daily_ingest_failures` schema 已可通过 `init_db()` 自动创建；
  - 已验证同一 `symbol + trade_date` 的 `5m/day` 写入支持整日覆盖重写；
  - 已验证回补 run/failure 生命周期 helper 可正常写入与查询；
  - 已验证目录 helper 同时兼容旧 `20260311/20260311` 与新 `202603/20260311` 两种输入；
  - 自动化：`python3 -m pytest -q backend/tests/test_l2_history_foundation.py backend/tests/test_sandbox_review_v2.py` 通过（12/12）。
- 遗留问题：
  1. Phase 2 仍需把这些 schema/helper 真正接入 Windows 日包 ETL 与正式回补流程；
  2. 生产查询接口与前端页面尚未切到新正式历史表；
  3. 旧裸日目录迁入月目录的实际迁移脚本尚未实现。

## 8. 归档信息
- 归档时间：
- Archive ID：
- 归档路径：
