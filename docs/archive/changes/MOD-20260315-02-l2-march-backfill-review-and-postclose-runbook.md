# MOD-20260315-02-l2-march-backfill-review-and-postclose-runbook

## 1. 基本信息
- 标题：2026-03 L2 正式回补复盘、失败影响评估与盘后日常 Runbook 冻结
- 状态：DONE
- 负责人：Codex / 后端 AI
- 关联 Task ID：`CHG-20260315-02`
- 关联 CAP：`CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 关联需求：`REQ-20260314-04`

## 2. 复盘目标
- 对本次 Windows `2026-03-02 ~ 2026-03-13` 正式回补结果做一次数据完整性复盘；
- 明确失败样本会不会污染整体结果、会不会导致前端查询失真；
- 给出未来每天盘后自动跑数的正式执行方案，并把需要修复的项沉淀到待办。

## 3. 已确认事实
- 当前分支已完成 `2026-03-02 / 03 / 04 / 05 / 06 / 09 / 10 / 11 / 12 / 13` 共 `10` 个交易日的正式回补。
- 正式结果累计：
  - `history_daily_l2 = 74614`
  - `history_5m_l2 = 3360187`
- 当前缺口分成两类：
  1. **显式失败**：`43` 个 `symbol-day`，主要是 `OrderID` 与 `逐笔委托.csv` 完全无法对齐；
  2. **空结果样本**：`105` 个 `symbol-day`，原始包可读，但未形成正式 `5m + daily` 结果（例如交易时段内无有效逐笔、无成交、停牌或源数据异常）。

## 4. 失败影响评估
### 4.1 不会污染其他股票/日期
- `backend/scripts/l2_daily_backfill.py` 是按 `symbol + trade_date` 粒度处理；
- 只有在单个 symbol 成功产出正式 `5m + daily` 后，才会调用覆盖写：
  - `replace_history_5m_l2_rows(...)`
  - `replace_history_daily_l2_row(...)`
- 因此单个 symbol/day 失败时，不会把错误 L2 写进其他 symbol/day，也不会发生跨股票污染。

### 4.2 但会造成“局部数据不准/不完整”，必须修
- `/api/history/multiframe` 的 finalized 历史只读 `history_5m_l2 / history_daily_l2`，不会对缺失的历史日逐日自动补 fallback；
- `/api/history_analysis` 只有在“整只股票没有正式历史结果”时才整体回退 `sina`，不会修补“中间少一天”的正式缺口；
- 所以失败样本在前端的实际表现会是：
  - 历史多维某些日期缺 bar；
  - 日线/复盘对这些 symbol/day 看不到正式 L2；
  - source 可能仍显示为正式底座，但个别日期缺失。

### 4.3 本轮结论
- **整体数据集可继续作为基线使用**，不需要推翻这 10 天已完成的正式回补；
- **43 个显式失败 + 105 个空结果样本必须进入 repair/review queue**，否则对应 symbol/day 在盯盘页和复盘页仍属于局部不完整。

## 5. Windows 本次跑数复盘
### 5.1 已验证稳定路径
- 稳定可复现路径是：
  1. Windows 负责保存原始 `.7z` 与解压 staging；
  2. 控制端直接通过多条 SSH 会话并发启动 worker；
  3. 每个 worker 独立执行 `l2_daily_backfill.py --symbols-file ...`；
  4. 全部 worker 结束后再汇总结果、清理 staging。
- 本轮实战稳定配置：**单日 8 worker shard**。

### 5.2 已证伪路径
- `backend/scripts/l2_day_sharded_backfill.py` 当前采用 Windows Python 父进程 `Popen` 拉多个子进程；
- 在 `2026-03-12` 首轮尝试中，出现多组 `partial_done` 且 `symbol_count=0 / rows_daily=0` 的异常 run；
- 这类失败不是单个股票数据问题，而是**编排层不稳定**，不能作为日常正式任务主路径。

### 5.3 本轮暴露出的流程短板
1. `OrderID` 完全无法对齐的样本会落 `l2_daily_ingest_failures`，但此前“空结果样本”不会显式入失败表；
2. 同一天多次试跑时，若没有单独留 review 记录，后续很难快速还原“哪次是正式 run、哪次是试探 run”；
3. 目前正式并发路径依赖人工组织多条 SSH，会话稳定但运维动作仍偏手工。

## 6. 本轮补强
- 已补强 `backend/scripts/l2_daily_backfill.py`：
  - 若某个 symbol/day **未形成正式 5m/daily**，现在会写入 `l2_daily_ingest_failures`，错误信息明确标注“无有效 bar”；
  - 这类样本不再被静默计入 success；
  - 后续每日盘后 run 将能直接导出显式 repair/review queue。
- 已修复 `OrderID` 单边完全无法对齐的容错：
  - 若 **买/卖任一侧仍有另一侧可对齐**，则不再整只 symbol 失败；
  - 缺失侧改为回退使用 `trade-side parent total`（按成交侧同一 order_id 的日内累计成交额）；
  - 仅在**买卖两侧都完全无法对齐**时，才继续判定为硬失败。
- 已补测试：
  - `backend/tests/test_l2_daily_backfill.py`
  - 覆盖“无有效 bar 进入失败表、正式结果不写库”的场景；
  - 覆盖“单边 0 overlap 允许修复、双边 0 overlap 仍失败”的场景。

## 6.1 本次修复实绩（2026-03-15）
- 已在 Windows 对历史 `43` 个 `OrderID 无法...` 的 `symbol-day` 做定向 repair run：
  - 新增脚本：`backend/scripts/l2_repair_failed_samples.py`
  - repair run：`run_id=84 ~ 93`
- 修复结果：
  - `43 / 43` 全部恢复为正式成功；
  - 各 repair run 均为 `status=done`；
  - `history_daily_l2` 总量由 `74614` 增至 `74657`；
  - `history_5m_l2` 总量由 `3360187` 增至 `3361224`。
- 修复后剩余问题：
  - 原来的 `43` 个显式 OrderID 失败已消化；
  - 当前剩余主要缺口收敛为 `105` 个空结果样本，后续应按“停牌/无成交 vs 源包异常”继续 review。

## 7. 未来每天盘后定时执行的最优方案
### 7.1 推荐结论
- **当前可立即上线的正式方案**：`Windows 数据面 + 常在线控制端 SSH 编排面`
- 当前不推荐直接把 Windows `Popen` 父进程版作为正式每日调度主路径。

### 7.2 推荐拓扑
1. **Windows 节点（数据面）**
   - 保存供应商原始包：`D:\MarketData\YYYYMM\YYYYMMDD.7z`
   - staging 解压目录：`Z:\l2_stage\YYYYMMDD`
   - 正式库：`D:\market-live-terminal\data\market_data.db`
2. **控制端（编排面）**
   - 优先使用当前已验证的 Mac；
   - 若要完全无人值守，应把同样的 SSH 编排迁到一台**常在线**控制节点（例如长期在线的 Mac mini 或已加入同一 Tailnet 的 Linux 跳板）；
   - 编排逻辑保持“一个 worker = 一条独立 SSH 命令”，不要回退到 Windows 父进程 `Popen`。

### 7.3 盘后时序
1. **16:15 ~ 16:20**：检查当日日包 `.7z` 已到齐且文件大小稳定；
2. **16:20 ~ 16:25**：解压到 `Z:\l2_stage\YYYYMMDD`，生成 `worker_*.symbols.txt`；
3. **16:25 ~ 17:00**：控制端并发启动 `8` 个 worker；
4. **worker 全部结束后**：
   - 汇总 `history_daily_l2/history_5m_l2` 写入量；
   - 导出 `l2_daily_ingest_failures`；
   - 若存在失败/空结果，登记 repair queue；
   - 清理 `Z:\l2_stage\YYYYMMDD`，保留原始 `.7z`；
5. **次日开盘前抽样**：关键股票在盯盘页/复盘页做 finalized 冒烟。

### 7.4 Repair Queue 规则
- `OrderID` 完全无法对齐：进入 **hard repair**；
- `无有效 bar`：进入 **review queue**，先区分是停牌/无成交，还是源包异常；
- 每日收盘后 run 的验收条件不是“0 失败”，而是：
  - 正式主批次完成；
  - 失败样本已被完整记录；
  - 次日可针对 repair queue 单独重跑，不阻塞绝大多数已成功样本对外可用。

## 8. 后续待办
1. 对现有 `43` 个显式失败样本做专项归因，优先看 ETF/基金类与重复失败 symbol；
2. 对历史上已经发生的 `105` 个空结果样本做一次补录/复核，避免它们只停留在人工统计口径；
3. 把“多 SSH worker 编排”从人工命令固化为正式定时任务；
4. 等 repair queue 规则稳定后，再决定是否要对某些交易所/品种增加更宽松的 L2 容错逻辑。
