# REQ-20260315-03-monitor-multiframe-quality-info-lightweight

## 1. 基本信息
- 标题：新版历史多维轻量质量提示（`quality_info` 单字段 + 查询层占位补点）
- 状态：DONE
- 负责人：Codex / 前后端 AI
- 关联 Task ID：`CHG-20260315-03`
- 关联 CAP：`CAP-HISTORY-30M`, `CAP-L2-HISTORY-FOUNDATION`
- 前置依赖：`REQ-20260314-08`, `MOD-20260315-02`

## 2. 背景与目标
- 你已明确：不接受“大而全”的质量体系，也不希望为了数据质量问题把老功能和后续新开发都拖复杂。
- 目标改为一个**最小可用、最小侵入**的版本：
  1. 正式 `5m / 1d` 结果可携带一段人类可读的质量说明；
  2. 对完全缺失的日/5m 点，在新版历史多维查询时补出 placeholder，让前端能“看到缺失”；
  3. 前端只使用**一种统一异常样式**，具体问题靠 `quality_info` 文案解释；
  4. 老版页面与其它模块先不接入，不把复杂度扩散到全系统。

## 3. 方案与边界
### 3.1 本卡要做什么
- 在正式表 `history_5m_l2 / history_daily_l2` 增加 `quality_info` 文本字段；
- 在新版历史多维查询链路中：
  - 已有数值但质量可疑 → 返回真实值 + `quality_info`
  - 某个日/5m 桶缺失 → 返回 placeholder 行 + `quality_info`
- 前端历史多维组件统一显示一种异常标记，不细分多套颜色和状态机。

### 3.2 本卡不做什么
- 不新增独立“质量表”；
- 不把质量逻辑接入旧版页面；
- 不要求在本期内对复盘页、分时页、老版日线做同步改造；
- 不在本期做复杂的逐点质量传播体系（只聚焦新版历史多维当前查看粒度）。

## 4. 设计冻结
### 4.1 后端存储
- `history_5m_l2` 新增：
  - `quality_info TEXT NULL`
- `history_daily_l2` 新增：
  - `quality_info TEXT NULL`
- 语义：
  - `NULL` / 空字符串：该条记录没有已知质量问题；
  - 非空：该条记录存在质量问题，但仍允许展示真实数值。

### 4.2 `quality_info` 文案原则
- 只保留一段人类可读文本，不额外拆复杂枚举；
- 示例：
  - `L2 单边回退，数值可能偏小`
  - `该日部分 5m 缺失，聚合值可能偏小`
  - `该 5 分钟桶缺失`
  - `原始成交字段异常，未形成有效正式数据`

### 4.3 placeholder 规则
- 若某个**应存在**的 `5m` 桶缺失：
  - 查询接口返回一条 placeholder item；
  - 数值字段为 `null`；
  - `is_placeholder=true`；
  - `quality_info='该 5 分钟桶缺失'`。
- 若某个**应存在**的交易日缺失：
  - 查询接口返回一条日级 placeholder item；
  - 价格/资金字段为 `null`；
  - `is_placeholder=true`；
  - `quality_info='该日缺失正式数据'` 或更具体的文案。
- 红线：
  - placeholder 绝不伪装成 `0`；
  - 前端绝不把 placeholder 画成真实 0 值。

### 4.4 前端展示规则
- 只做一种统一异常标记：
  - 正常值照画；
  - 只要 `quality_info` 非空，就在点/柱附近加统一告警标记（如 `!`）；
  - placeholder 用灰色空位/灰点显示，但也沿用同一异常提示入口。
- tooltip：
  - 正常展示原有数值；
  - 若 `quality_info` 非空，则追加显示该文案；
  - 若 `is_placeholder=true`，明确显示“该点缺失，不按 0 处理”。

### 4.5 聚合规则（轻量版）
- `30m / 1h` 仍由 `5m` 聚合；
- 若子 `5m` 中任一条：
  - `quality_info` 非空，或
  - bucket 缺失（被补成 placeholder）
  - 则聚合后父级点也写一条简单 `quality_info`，例如：
    - `该区间包含缺失 5m，聚合值可能偏小`
- 不做复杂 issue code/状态机传播。

## 5. 实现顺序（STRICT）
1. 先更新文档与契约；
2. 后端 schema/helper 补 `quality_info`；
3. 回补/查询逻辑写入或传播 `quality_info`；
4. `/api/history/multiframe` 返回 `quality_info + is_placeholder`；
5. 新版前端历史多维接统一异常样式；
6. 最后回填 handoff 与变更结果。

## 6. 验收标准（Given / When / Then）
- Given 某条 `5m` 正式记录使用了单边 fallback，When 查询新版历史多维，Then 该点仍展示真实值，但返回 `quality_info='L2 单边回退，数值可能偏小'`。
- Given 某个 `5m` 桶缺失，When 查询新版历史多维，Then 返回 placeholder item，且前端展示为空位/灰点，而不是 `0`。
- Given 某个交易日缺失正式日线，When 查看 `日` 维度，Then 该日期仍占据时间轴位置，并通过统一异常样式提示“该日缺失正式数据”。
- Given 某个 `30m/1h` 桶由带异常的子 `5m` 聚合而来，When hover 该聚合点，Then 可看到简单质量说明“该区间包含缺失 5m，聚合值可能偏小”。

## 7. 风险与回滚
- 风险：
  1. 若 placeholder 在前端被错误当成 `0`，会误导用户；
  2. 若把 `quality_info` 接入老版页面，可能引入不必要回归；
  3. 若 `30m/1h` 聚合文案过长，会影响 tooltip 可读性。
- 回滚：
  - 本方案只接新版历史多维；
  - 若出现问题，可关闭前端异常标记展示，正式表中的 `quality_info` 字段仍可保留，不影响原有数值字段。

## 8. 结果回填
- 实际改动：
  1. `history_5m_l2 / history_daily_l2` 已增加 `quality_info`，并在 schema 初始化阶段补了兼容 migration；
  2. `l2_daily_backfill.py` 已把“单边 0 overlap / 部分 OrderID 缺失”写成轻量 `quality_info`，同步落到 5m 与 daily 正式结果；
  3. `/api/history/multiframe` 已返回 `quality_info + is_placeholder`，并在查询层为缺失 `5m / 1d` 补 placeholder；
  4. `30m / 1h` 聚合已继承 `5m` 的异常提示，统一输出“该区间包含缺失 5m，聚合值可能偏小”；
  5. 新版 `HistoryMultiframeFusionView` 已接入统一黄色 `!` 异常标记，tooltip 可直接查看 `quality_info`，placeholder 不再被误画成 `0`。
- 验证结果：
  - `python3 -m pytest backend/tests/test_l2_history_foundation.py backend/tests/test_l2_daily_backfill.py backend/tests/test_history_multiframe_router.py` ✅
  - `npm run build` ✅
- 遗留问题：
  1. 当前 `quality_info` 仍是轻量文本，不做更细粒度分类；
  2. 交易日判断仍依赖现有 `TradeCalendar`，离线测试场景下会退化到周末规则；
  3. 老版页面、复盘页、本期之外的图表暂不接入该质量提示体系。

## 9. 归档信息
- 归档时间：
- Archive ID：
- 归档路径：
