# 模型特征库实施锁定方案

日期：2026-05-17  
分支：`codex/model-training-data-audit`  
worktree：`/Users/dong/Desktop/AIGC/market-live-terminal-model-data-audit`

## 结论

本轮要做的是训练数据底座，不是训练模型。

先新增独立模型特征库：

```text
/Users/dong/Desktop/AIGC/market-data/selection/model_feature_store.db
```

不把模型字段塞回 atomic，不恢复 `atomic_limit_state_5m`，不改每日盘后主流程。P0 只做 schema、构建脚本、小样本构建、验证报告。

## 当前数据事实

Mac 当前正式训练入口应使用 compact：

```text
/Users/dong/Desktop/AIGC/market-data/atomic_facts/shadow/market_atomic_mainboard_compact_current.db
```

当前覆盖：

| 表 | 覆盖 | 交易日 |
|---|---|---:|
| `atomic_trade_daily` / `atomic_trade_5m` | `2025-01-02 ~ 2026-05-15` | 327 |
| `atomic_limit_state_daily` | `2025-01-02 ~ 2026-05-15` | 327 |
| `atomic_order_daily` / `atomic_order_5m` | `2026-03-02 ~ 2026-05-15` | 49 |
| `atomic_book_state_daily` / `atomic_book_state_5m` | `2026-03-02 ~ 2026-05-15` | 49 |
| `selection_feature_daily` / `selection_signal_daily` | `2025-01-02 ~ 2026-05-15` | 328 |
| `fine_theme_heat_daily_v2` | `2025-01-02 ~ 2026-05-13` | 325 |
| `fine_theme_heat_daily` / `member` / `lifecycle` | `2025-01-02 ~ 2026-04-30` | 319 |

核心缺口：

1. `2024-09 ~ 2024-12` 尚未进入 Mac compact。
2. `2025-01 ~ 2026-02` 目前只有 trade / limit，缺 order / book / auction。
3. 指数日线还没有稳定落入训练库，必须补 `中证1000 > 20日线`。
4. heat 不覆盖 `2024-09 ~ 2024-12`，不能默认为“没有热点”。
5. compact current 当前没有 `atomic_open_auction_*` 表；旧 full backup 有 auction 表。P0 特征库先不强依赖 auction，除非后续模型训练侧明确要求 auction 进入 P0。

## Windows 数据与容量事实

路径澄清：

```text
D: 负责长期存放原始 .7z、正式 SQLite 数据库、跑数产物
Z: 负责解压、staging、临时 worker 分片
G: 不作为当前执行盘位；旧经验里已废弃
```

Windows 当前磁盘：

| 盘 | 当前结论 |
|---|---|
| `D:` | 只剩约 `109MB`，不能作为解压 / staging 盘 |
| `Z:` | 约 `304GB` 可用，后续解压和批量加工必须用这里 |

Windows 当前日包根目录：

```text
D:\MarketData
```

已确认：

| 路径 | 内容 | 大小 / 状态 |
|---|---|---|
| `D:\MarketData\20240902.7z` | 2024-09-02 单日日包 | 已存在，约 `3.0GB` |
| `D:\MarketData\202501` | 2025-01 日包 | 18 个交易日，约 `68.7GB` |
| `D:\MarketData\202602` | 2026-02 日包 | 14 个交易日，约 `76.2GB` |
| `D:\MarketData\202605` | 2026-05 日包 | 8 个交易日，约 `50.8GB` |

`20240902.7z` 已验到单票结构：

```text
20240902\000001.SZ\行情.csv
20240902\000001.SZ\逐笔委托.csv
20240902\000001.SZ\逐笔成交.csv
```

当前执行路径：

```text
L2 worker staging:      Z:\l2_stage\<YYYYMMDD>
atomic staging:         Z:\atomic_stage\postclose_<YYYYMMDD>\<YYYYMMDD>
Windows L2 artifacts:   D:\market-live-terminal\.run\l2_postclose\<YYYYMMDD>
Windows atomic reports: D:\market-live-terminal\.run\postclose_atomic\<YYYYMMDD>
```

现有脚本结束时会清理：

```text
Z:\l2_stage\<YYYYMMDD>
Z:\atomic_stage\postclose_<YYYYMMDD>\<YYYYMMDD>
```

后续批量重跑仍应遵守这个约束：原始 `.7z` 留在 `D:\MarketData`，解压只落 `Z:`，跑完一天清理一天。

### D 盘空间决策

当前最高优先级是释放 `D:`，否则新 atomic / selection / model feature store 都没有落库空间。

Windows `D:\market-live-terminal\data` 最大文件：

| 文件 | 大小 | 判断 |
|---|---:|---|
| `D:\market-live-terminal\data\atomic_facts\market_atomic_mainboard_full_reverse.db` | `43.2GB` | 旧 full reverse 主库，数据库治理后不应继续作为新默认入口 |
| `D:\market-live-terminal\data\market_data.db` | `2.3GB` | 业务消费库，保留 |
| `D:\market-live-terminal\data\selection\selection_research_windows.db` | `2.1GB` | selection 研究库，保留 |
| `D:\market-live-terminal\data\selection\selection_research.db` | `60KB` | 空/占位库，低价值但清不出空间 |

决策：

1. 优先处理 `market_atomic_mainboard_full_reverse.db`。
2. 不建议继续把新重跑结果写回这个旧文件名，避免和旧治理前口径混淆。
3. 已执行稳妥方案：先移到 `Z:\atomic_legacy_backup\market_atomic_mainboard_full_reverse_20260516_pre_feature_store.db`，确认新链路可跑后再删除。
4. 执行结果：`D:` 可用空间从约 `109MB` 释放到约 `43.3GB`。
5. 后续跑数前必须同步改跑数配置，Windows atomic 目标库改成新路径，例如：

```text
D:\market-live-terminal\data\atomic_facts\market_atomic_mainboard_compact_rebuild.db
```

或继续使用明确的新正式名，避免脚本默认回写旧 full reverse。

不建议清理 `D:\MarketData\202501 / 202602 / 202605` 原始包；这些正是后续重跑输入。原始包只能在确认已完成长期备份或可重新下载后再删。

### 单日容量统计口径

每次小样本重跑都必须记录：

1. 跑前 `D:` / `Z:` 可用空间。
2. 原始 `.7z` 文件大小。
3. `Z:\l2_stage` 解压峰值。
4. `Z:\atomic_stage` 解压峰值。
5. Windows 目标 atomic DB 跑前 / 跑后文件大小。
6. Mac compact / model feature store 跑前 / 跑后文件大小。
7. 本地增量 artifact 大小：
   - `atomic_day_delta_YYYYMMDD.db`
   - `l2_day_delta_YYYYMMDD.db`
   - `selection_day_delta_YYYYMMDD.db`

现有 `2026-05` processed artifact 只能作为参考，不等于最终 SQLite 主库增量。

## P0 交付

新增：

```text
backend/scripts/sql/model_feature_store_schema.sql
backend/scripts/build_model_feature_store.py
backend/scripts/validate_model_feature_store.py
docs/selection/model_feature_store_implementation_notes.md
```

本地产物：

```text
/Users/dong/Desktop/AIGC/market-data/selection/model_feature_store.db
/Users/dong/Desktop/AIGC/market-data/selection/model_feature_store_validation_YYYYMMDD.json
```

P0 表：

| 表 | P0 行为 |
|---|---|
| `model_feature_build_runs` | 每次构建必写，失败也写 |
| `model_feature_manifest` | 每张表覆盖、行数、source、coverage |
| `model_market_index_daily` | 至少中证1000，建议同步 500/300/上证/创业板 |
| `model_market_state_daily_v1` | 市场环境，必须含中证1000 20日线字段 |
| `model_feature_daily_v1` | `symbol + trade_date` 日级宽表 |
| `model_feature_intraday_shape_v1` | 5m 压缩形态表 |
| `model_label_forward_return_v1` | 标签表，严禁生产候选读取 |

P1 再做：

```text
model_feature_entry_window_v1
model_feature_exit_daily_v1
```

## 字段来源锁定

数据库边界继续保持：

| 库 | 定位 | 本轮动作 |
|---|---|---|
| `market_data.db` | 主业务消费库 | 不新增模型训练字段 |
| `atomic_facts/*` | 原子事实层 | 只保留事实表；不塞模型派生特征 |
| `selection_research.db` | 选股研究 / 候选 / 规则信号 | 保持研究层定位，不做训练宽表主库 |
| `model_feature_store.db` | 模型训练与回测特征库 | 新增，承接本轮 P0/P1 |

本轮数据库设计更新不是改旧库，而是新增模型特征库，并要求 `atomic / selection / heat / index` 作为只读输入。

`model_feature_daily_v1`：

| 字段方向 | 来源 |
|---|---|
| OHLC / amount / trade_count / L1/L2 成交资金 | `atomic_trade_daily` |
| 3/5/10/20/60 日价格位置 | `selection_feature_daily` 优先，不足时从 `atomic_trade_daily` 计算 |
| OIB / CVD / add / cancel / support / pressure | `atomic_order_daily` |
| book imbalance / depth / close bid ask | `atomic_book_state_daily` |
| 涨跌停、触板、炸板、首次触板时间 | `atomic_limit_state_daily` |
| 规则分数与旧策略解释 | `selection_signal_daily` |
| 主题成员、排名、生命周期 | `fine_theme_heat_daily` + `fine_theme_member_daily` + `fine_theme_lifecycle_daily` |
| 市场环境 | `model_market_state_daily_v1` |

`model_market_state_daily_v1`：

| 字段方向 | 来源 |
|---|---|
| 市场成交额、涨跌中位数、涨跌家数 | `atomic_trade_daily` |
| 涨停、跌停、炸板率 | `atomic_limit_state_daily` |
| order/book 当日覆盖 | `atomic_order_daily` / `atomic_book_state_daily` |
| 中证1000和其他指数 | `model_market_index_daily` |
| 热点集中度和主题生命周期 | `fine_theme_heat_daily_v2` 优先，必要时回退 v1 |

`model_feature_intraday_shape_v1`：

| 字段方向 | 来源 |
|---|---|
| 开盘/尾盘收益、成交占比、日内高低点时间 | `atomic_trade_5m` |
| 开盘/尾盘 L2 主力净额 | `atomic_trade_5m` |
| OIB / CVD 曲线和连续性 | `atomic_order_5m` |
| 开盘/尾盘盘口不平衡 | `atomic_book_state_5m` |

`model_label_forward_return_v1`：

| 字段方向 | 来源 |
|---|---|
| signal close / entry open / future high low close | `atomic_trade_daily` |
| 买不到判断 | `atomic_limit_state_daily` 的次日涨停状态 |

标签表可以用未来数据；特征表不能出现 `future_*`、`max_runup_*`、`hit_*`。

## coverage 规则

所有主表必须显式写 flag：

```text
has_trade_daily
has_trade_5m
has_order_daily
has_order_5m
has_book_daily
has_book_5m
has_limit_daily
has_heat
has_market_state
```

缺数据时字段可以为空，但 flag 必须为 `0`。尤其是 `2025-01 ~ 2026-02` 的 order/book 缺失，不能填成真实 0。

## 第一轮小样本

按新口径，第一批先用 `2026-05` 最近交易日。原因：

1. 这些日包已经在 `D:\MarketData\202605`。
2. 现有 compact / selection / heat 覆盖较完整。
3. 跑出的 feature store 可以先交给模型训练侧评估“字段够不够用”。
4. 如果新方案新增或修正了 order / book / auction / feature 字段，`2026-03 ~ 2026-05` 也需要按同一新链路重跑，避免最近窗口和历史窗口口径不一致。

### A. 本机现有数据 feature store smoke

```text
2026-05-13
2026-05-14
2026-05-15
```

目标：

| 项 | 预期 |
|---|---|
| schema / 构建器 | 先跑通 P0 七张表 |
| coverage | trade / order / book / limit 都应为 1 |
| 输出 | 生成 validation json，交给模型训练侧评估字段 |
| auction | compact 当前没有 auction，先记录缺失，不伪造 |

### B. Windows 最近日包重跑验证

用于验证“新方案下最近窗口是否需要重跑”和单日容量：

```text
优先：2026-05-15
备选：2026-05-14, 2026-05-13
```

预期：

1. 从 `D:\MarketData\202605\<YYYYMMDD>.7z` 读取日包。
2. 解压到 `Z:\l2_stage` / `Z:\atomic_stage`。
3. 跑完后清理解压目录。
4. 统计单日：
   - 原始 `.7z` 大小；
   - 解压峰值占用；
   - `atomic_day_delta` 大小；
   - `l2_day_delta` 大小；
   - `selection_day_delta` 大小；
   - 最终写入 compact / selection / feature store 后的增量估算。

已知最近 2026-05 本地 processed delta 粗略体积：

| 日期 | processed 总量 | atomic delta | L2 delta | selection delta |
|---|---:|---:|---:|---:|
| `2026-05-06` | `312MB` | `215MB` | `71MB` | `5.6MB` |
| `2026-05-07` | `304MB` | `215MB` | `71MB` | `5.6MB` |
| `2026-05-08` | `295MB` | `215MB` | `70MB` | `5.6MB` |
| `2026-05-11` | `295MB` | `215MB` | `71MB` | `5.6MB` |
| `2026-05-12` | `300MB` | `215MB` | `71MB` | `5.6MB` |
| `2026-05-13` | `292MB` | `215MB` | `71MB` | `5.6MB` |
| `2026-05-14` | `293MB` | `215MB` | `71MB` | `5.6MB` |
| `2026-05-15` | `374MB` | `215MB` | `71MB` | `5.6MB` |

说明：这是本地日增量 artifact / 报告缓存体积，不等同于 compact 最终文件增量；正式容量判断需要在重跑时记录 DB 文件跑前 / 跑后大小。

### C. 跨历史 full L2 验证

用于验证新买历史数据能补出 order/book：

```text
2024-09-02
2025-01-02 ~ 2025-01-08 中选 2~3 个交易日
```

预期：

1. 从 `D:\MarketData\20240902.7z` / `D:\MarketData\202501\*.7z` 读取。
2. 解压只落 `Z:`。
3. 2024 / 2025 的 feature store 对 order/book flag 应为 1。
4. heat 对 `2024-09` 应为 0，因为当前 heat 不覆盖；不能填成“无热点”。

### D. 滚动解压策略

批量重跑时不要一次性解压整月。

建议：

1. 预解压 2~3 天到 `Z:`。
2. worker 连续消费已解压日包。
3. 每完成一天，立即删除该天解压目录。
4. 同时补解压下一天，保持窗口内始终有 1~2 天待跑。
5. 验真不能只看任务状态，至少同时看进程 / 日志 / DB 进度两个信号。

## 每日盘后最终顺序

长期目标不是让模型训练脚本直接扫 atomic，而是日跑后增量刷新特征库。

建议最终顺序：

1. `ops/run_postclose_l2.sh` 完成当日 L2 / atomic / selection 增量。
2. `build_fine_theme_heat_daily_v2.py` 补当日 market heat。
3. `build_model_feature_store.py --date D` 写入：
   - `model_market_state_daily_v1`
   - `model_feature_daily_v1`
   - `model_feature_intraday_shape_v1`
4. 同一轮补成熟标签：
   - D-3 / D-5 / D-10 / D-22 对应 horizon 已完整时，写 `model_label_forward_return_v1`。
5. 后续模型推理只读 feature store，再写 `selection_candidate_sources` / `selection_candidate_daily`。

P0 不把第 3 步接入主流程，只提供可手动执行脚本。

## 验收门槛

P0 必须通过：

1. 新库包含 P0 七张表。
2. `2026-02` 样本 order/book coverage 为 0，不误填。
3. `2026-03` 样本 order/book coverage 为 1。
4. `model_market_state_daily_v1` 中 `csi1000_above_ma20` warmup 后只为 0/1。
5. 新增代码不引用 `atomic_limit_state_5m`。
6. 新增构建脚本不硬编码 `market_atomic_mainboard_full_reverse.db`。
7. 特征表不含未来标签字段。
8. 验证报告写明缺失交易日、coverage 摘要、中证1000字段完整性。

## 实施分支建议

当前分支只锁方案。正式开发建议从当前 main 或本分支再开：

```text
worktree: /Users/dong/Desktop/AIGC/market-live-terminal-model-feature-store
branch: codex/model-feature-store-v1
```

开发前先同步本锁定文档和 `model_feature_store_requirements_v1_2026-05-17.md`。

## 子 Agent 并行推进方案

主线程职责：

1. 保持业务框架、数据库边界、Windows/Mac 路径和验收口径不漂移。
2. 集成子 Agent 的代码。
3. 运行小样本构建和验证。
4. 决定是否进入 Windows 单日重跑。

子 Agent 拆分：

| Agent | 类型 | 写权限 | 目标 |
|---|---|---|---|
| Schema Worker | worker | `backend/scripts/sql/model_feature_store_schema.sql` | P0 七张表 DDL、索引、manifest/build_runs |
| Validator Worker | worker | `backend/scripts/validate_model_feature_store.py` | 验证表存在、coverage、中证1000、标签隔离、报告 JSON |
| Builder Explorer | explorer | 无写权限 | 梳理 `build_model_feature_store.py` 的最小实现路线 |

后续可继续拆：

| Agent | 类型 | 写权限 | 目标 |
|---|---|---|---|
| Builder Worker | worker | `backend/scripts/build_model_feature_store.py` | P0 构建器，先跑 `2026-05-13 ~ 2026-05-15` |
| Windows Ops Explorer | explorer | 无写权限 | 单日重跑 `2026-05-15` 的执行命令、容量统计、回滚点 |
| Docs Worker | worker | `docs/selection/model_feature_store_implementation_notes.md` | 记录运行结果、字段缺口、模型训练侧评估材料 |

并行规则：

1. worker 写文件必须互不重叠。
2. 主线程不把长期上下文下放，只下放具体文件任务。
3. 子 Agent 不执行删除 / 移动 Windows 数据文件。
4. Windows 跑数、DB 移动、正式路径切换只由主线程执行。
5. 每次集成后主线程跑：

```bash
python3 -m py_compile backend/scripts/build_model_feature_store.py backend/scripts/validate_model_feature_store.py
sqlite3 /Users/dong/Desktop/AIGC/market-data/selection/model_feature_store.db ".tables"
python3 backend/scripts/validate_model_feature_store.py --db /Users/dong/Desktop/AIGC/market-data/selection/model_feature_store.db
```
