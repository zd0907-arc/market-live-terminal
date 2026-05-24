# REQ-20260318-03-order-event-factors-and-5m-contract

## 1. 基本信息
- 标题：Phase 1｜逐笔委托事件化、5m 因子补齐与双轨基础契约冻结
- 状态：ACTIVE
- 负责人：Codex / 后端 AI
- 关联 Task ID：`CHG-20260319-01`
- 关联 CAP：`CAP-L2-HISTORY-FOUNDATION`, `CAP-REALTIME-FLOW`
- 关联 STG：`STG-20260318-03`

## 2. 背景与目标
- 当前正式 `history_5m_l2` 只覆盖 L1/L2 绝对买卖金额，不包含资金博弈新增所需的订单事件因子；
- 当前 preview 层也没有 `total_volume`，前端无法用统一 5m 基础字段稳定计算当日 VWAP；
- 本阶段目标是：
  1. 用真实 `逐笔委托.csv` 样本冻结 v1 事件解释；
  2. 把 `total_volume / add / cancel / l2_cvd_delta / l2_oib_delta` 纳入正式 schema 与 API 契约；
  3. 明确数据库字段命名与 API 字段命名的映射，避免实现期再做二次设计。

## 3. 方案与边界
- 做什么：
  - 冻结真实样本与 v1 假设；
  - 为 finalized 5m、preview 5m、统一双轨接口补齐资金博弈必需字段；
  - 明确 ETL 聚合公式与可追溯要求。
- 不做什么：
  - 本阶段不实现前端双轨渲染；
  - 本阶段不产出文字信号；
  - 本阶段不把 `U` 拆出独立统计口径。

## 4. 数据样本依据（冻结到文档）
### 4.1 已核样本
- 样本来源：`D:\MarketData\202603\20260317.7z -> 20260317\000833.SZ\逐笔委托.csv`
- 已确认字段：`时间 / 委托编号 / 交易所委托号 / 委托类型 / 委托代码 / 委托价格 / 委托数量`
- 样本统计：
  - `委托类型=0`：`129146` 行，均表现为新增委托；
  - `委托类型=1`：`197` 行，多数为 `价格=0` 的负向事件；
  - `委托类型=U`：`13` 行，少量带价格，语义待进一步复核，但 v1 一并并入 cancel。

### 4.2 v1 事件解释（必须写死）
- `委托类型=0` → `新增委托`
- `委托类型 in {1, U}` → `撤单/改单类负向事件`
- `委托代码=B` → buy side
- `委托代码=S` → sell side
- v1 业务约束：
  - ETL 侧统一把 `{1,U}` 计入 cancel；
  - 若未来需要拆分 `cancel` 与 `modify`，必须另开 `INV-*` 文档并补样本依据。

## 5. 字段冻结（数据库字段 vs API 字段）
### 5.1 finalized / preview 存储字段（数据库命名）
- `total_volume`
- `l2_add_buy_amount`
- `l2_add_sell_amount`
- `l2_cancel_buy_amount`
- `l2_cancel_sell_amount`
- `l2_cvd_delta`
- `l2_oib_delta`

### 5.2 统一接口字段（对前端命名）
- `total_volume`
- `add_buy_amount` ← 映射 `l2_add_buy_amount`
- `add_sell_amount` ← 映射 `l2_add_sell_amount`
- `cancel_buy_amount` ← 映射 `l2_cancel_buy_amount`
- `cancel_sell_amount` ← 映射 `l2_cancel_sell_amount`
- `l1_net_inflow`
- `l2_net_inflow`
- `l2_cvd_delta`
- `l2_oib_delta`

> 约束：后端允许返回绝对值与净值，但禁止返回任何文字信号、图标信号、主观结论文本。

## 6. 聚合公式（冻结）
1. **5m 基础量价**
   - `total_amount = Σ 成交额`
   - `total_volume = Σ 成交量`（统一折算到股数口径，禁止前端自行猜单位）
2. **L2 CVD**
   - `l2_cvd_delta = Σ 主动买入额 - Σ 主动卖出额`
   - 主动方向取自 L2 `逐笔成交` 的 `BS`/成交方向标识，不再用价格涨跌推演。
3. **L2 OIB**
   - `l2_oib_delta = (l2_add_buy_amount - l2_cancel_buy_amount) - (l2_add_sell_amount - l2_cancel_sell_amount)`
4. **新增委托金额**
   - `l2_add_buy_amount = Σ(委托类型=0 AND 委托代码=B 的 委托价格*委托数量)`
   - `l2_add_sell_amount = Σ(委托类型=0 AND 委托代码=S 的 委托价格*委托数量)`
5. **撤单/改单金额**
   - `l2_cancel_buy_amount = Σ(委托类型 in {1,U} AND 委托代码=B 的 金额)`
   - `l2_cancel_sell_amount = Σ(委托类型 in {1,U} AND 委托代码=S 的 金额)`
   - 若事件金额无法直接由事件行价格可靠得出，允许回退到同委托号最近有效价格，但必须保留可追溯规则并在失败表记审计。

## 7. 执行步骤（按顺序）
1. 把真实样本与 `0/1/U` 解释写死到 ETL 设计与测试用例；
2. 为 `history_5m_l2`、`realtime_5m_preview`、必要的日级汇总层补字段；
3. 调整盘后 L2 回补脚本，产出新增/撤单/L2 CVD/L2 OIB 因子；
4. 统一在查询层把 DB 字段映射成前端接口字段；
5. 补样本追溯与失败登记，确保 `cancel_*` 可以追到真实 order-event 样本。

## 8. 验收标准（Given/When/Then，绝对时间）
- Given `2026-03-17 21:00`，When 用 `000833.SZ` 的 `逐笔委托.csv` 跑 5m 聚合，Then `委托类型=0` 只进入 `add_*`，`委托类型 in {1,U}` 只进入 `cancel_*`。
- Given `2026-03-17 21:10`，When 聚合 `09:30~09:35` 的 5m 样本，Then `l2_oib_delta` 必须可由 `add/cancel` 四个绝对因子复算得到。
- Given `2026-03-17 21:20`，When 查询统一双轨接口的单个 bar，Then 响应同时具备 `total_amount + total_volume + l1_net_inflow + l2_net_inflow + cancel_*`，且不含任何文字信号字段。
- Given `2026-03-17 21:30`，When 样本中存在 `委托类型=U` 事件，Then v1 结果必须明确进入 `cancel_*`，且文档/测试都能说明这是阶段性假设而非隐式实现。

## 9. 风险与回滚
- 风险：
  1. 若 `逐笔委托` 金额回填规则未冻结，实施时极易出现“有的 cancel 用 0，有的用最近价”的混口径；
  2. 若不区分 DB 字段名与 API 字段名，前端后端会重复暴露 `l2_` 前缀实现细节；
  3. `委托类型=U` 真实含义若后续反转，需要专项复盘。
- 回滚：
  - 文档阶段无代码回滚；
  - 实施阶段若 `U` 解释被推翻，优先改 ETL 与接口映射，再通过 `MOD-*` 回填文档。

## 10. 结果回填
- 实际改动：当前仅完成 Phase 1 文档冻结，尚未修改 schema/ETL/测试。
- 验证结果：真实样本依据与字段映射已写死到文档。
- 遗留问题：`委托类型=U` 是否独立、撤单金额回填细则、日级汇总是否需要直接持久化 `add/cancel`。

## 11. 归档信息
- 归档时间：
- Archive ID：
- 归档路径：
