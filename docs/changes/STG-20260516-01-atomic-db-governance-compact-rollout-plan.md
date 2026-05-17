# Atomic DB 治理、页面融合与上线验证计划

状态：COMPACT_DEFAULT_USER_ACCEPTED_IN_WORKTREE  
分支：`codex/db-governance`  
worktree：`/Users/dong/Desktop/AIGC/market-live-terminal-db-governance`  
日期：2026-05-17

## 0. 暂停点快照

2026-05-16 曾按用户要求暂停，记录当前改进进度、已做事项和后续事项。

2026-05-17 已恢复执行，并完成 schema 拆分后的重跑验证。

2026-05-17 已完成全窗口 compact shadow DB 构建、补齐到 `2026-05-15`、新旧 API 对比、页面 smoke，并已在本 worktree 把本地研究站默认读取切到 compact。

2026-05-17 用户已在独立端口服务上完成主要页面人工验收，反馈整体无明显问题。本轮人工验收作为 compact 默认读取方案通过依据之一。

2026-05-17 为暴露仍硬读老路径的功能，已把 Mac 老 full reverse DB 从原路径移动到同盘备份目录。数据未删除，可回滚。

当前代码状态：

- worktree 已独立于主工作区。
- 当前分支：`codex/db-governance`。
- 当前改动准备提交到治理分支；主线合并在独立 integration worktree 执行，不直接改用户当前开发 worktree。
- 本 worktree 的默认启动流程已优先读取 compact；compact 可用时不再要求老 full reverse DB 原路径存在。
- 正式 atomic 老库数据未修改，文件已移动到备份目录保留。
- 本轮已生成的 shadow compact DB 已作为本 worktree 默认读取库使用，不覆盖正式库。

当前暂停点的关键结论：

1. 本轮方向已经从“5m 涨跌停稀疏记录”收敛为“废弃默认 5m 涨跌停状态表”。
2. `atomic_limit_state_daily` 作为涨跌停唯一长期状态表。
3. 5分钟触板 / 封板 / 炸板只在需要时从 `atomic_trade_5m + atomic_limit_state_daily` 派生。
4. `atomic_trade_5m` 保留全量；单票 5m 查询优先走 `(symbol, bucket_start)` 主键索引。
5. 正式清理前不删除老库表、不 drop 老索引；默认读取先切 compact，老库只作为备份回滚。

2026-05-17 继续推进后的新增结论：

1. 正式库已更新到 `2026-05-15`，原 compact 只到 `2026-05-14`，已用增量脚本补齐。
2. 新旧后端 24 个关键 API 响应 hash 全一致，必需项 0 失败。
3. compact 页面 smoke 8 个页面全部通过；`/selection-research` 常规 Chrome 截图会等待超时，已用 CDP fallback 复验页面实际渲染正常。
4. `ops/start_local_research_station.sh` 已改为：存在 `market_atomic_mainboard_compact_current.db` 时默认开启 compact；不存在时自动回落正式库。
5. 本地正式库仍不能仅凭“Windows 理论上有一份”直接删除；清理前必须核对 Windows 文件路径、大小、最新日期和关键表行数。
6. PPO 相关页面和报告属于模型训练阶段的临时可视化，不作为本轮数据库切换阻塞项；后续如保留，应归入模型研究任务入口治理，不放在 DB 改造验收里。
7. Mac 老库已移动到 `/Users/dong/Desktop/AIGC/market-data/atomic_facts/backup_pre_compact_cutover_20260517_172307/market_atomic_mainboard_full_reverse.db`；原路径不再作为正常读取入口。

截至暂停点，已完成的代码改造：

| 模块 | 已完成内容 | 状态 |
| --- | --- | --- |
| `backend/app/core/config.py` | 增加 `ENABLE_ATOMIC_COMPACT_READ` / `ATOMIC_COMPACT_DB_PATH`，支持 compact shadow DB 优先读取 | 已完成 |
| `backend/app/db/l2_history_db.py` | atomic fallback 改只读连接；单票 5m 查询从 `trade_date` 范围改为 `bucket_start` 范围 | 已完成 |
| `backend/app/services/selection_strategy_v2.py` | atomic 路径解析支持 compact path | 已完成 |
| `backend/app/services/intraday_evolution_lab.py` | 不再 join `atomic_limit_state_5m`，改用 `atomic_limit_state_daily` 派生 5m 状态字段 | 已完成 |
| `backend/scripts/build_limit_state_from_atomic.py` | 默认只生成 daily；只有显式 `--include-5m` 才生成 legacy 5m | 已完成 |
| `backend/scripts/sql/limit_state_schema.sql` | 默认 schema 只保留日级涨跌停表 | 已完成，已重跑验证 |
| `backend/scripts/sql/limit_state_legacy_5m_schema.sql` | 新增 legacy 5m schema，供显式兼容使用 | 已完成，已重跑验证 |
| 日 delta / 合并 / 回填 / finalize / 单票校验脚本 | 不再把 `atomic_limit_state_5m` 当必需表 | 已完成 |
| `ops/start_local_research_station.sh` | 支持 compact 读取环境变量检查和启动日志；compact 可用时把 `ATOMIC_MAINBOARD_DB_PATH` / `ATOMIC_DB_PATH` 指向 compact | 已完成 |
| `backend/app/services/market_heat.py` | 市场热点 atomic 读取改走统一候选路径，避免硬读老 full reverse 路径 | 已完成 |
| `backend/scripts/audit_atomic_db.py` | 新增只读审计脚本 | 已完成 |
| `backend/scripts/build_atomic_compact_shadow.py` | 新增 compact shadow DB 构建脚本 | 已完成 |
| `backend/scripts/append_atomic_compact_shadow.py` | 新增 compact 增量补齐脚本 | 已完成 |
| `scripts/compare_atomic_backend_modes.py` | 新增正式库 / compact API hash 对比脚本 | 已完成 |
| `scripts/smoke_compact_research_station.py` | 新增 compact API / 页面 smoke 脚本 | 已完成 |
| `scripts/probe_page_cdp.mjs` | 新增页面 CDP fallback 探测脚本 | 已完成 |
| 单元测试 | 增加 daily-only schema、compact 读取、日级派生 5m 状态测试 | 已完成，已重跑验证 |

截至暂停点，已完成的数据验证：

| 验证项 | 结果 |
| --- | --- |
| 一日 shadow DB | 已构建，`2026-05-14`，约 159M |
| 大窗口 shadow DB | 已构建，`2026-03-01 ~ 2026-05-14`，约 7.4G |
| 大窗口行数对比 | trade/order/book/limit daily 与正式库窗口一致 |
| `atomic_limit_state_5m` | shadow DB 未复制，符合目标 |
| 查询计划 | `symbol + bucket_start` 命中 `(symbol, bucket_start)` 主键索引 |

2026-05-17 恢复后的功能验证：

| 验证项 | 结果 |
| --- | --- |
| `py_compile` | 通过 |
| 后端相关测试 | `29 passed` |
| `npm run build` | 通过 |
| `atomic_limit_state_5m` 引用重扫 | 代码硬依赖已移除，只剩 legacy / 审计 / 历史文档引用 |
| compact API smoke | 通过 |
| compact 页面截图 smoke | 8 个页面均生成非空截图 |
| evolution lab catalog | 通过 |
| evolution lab `rl-random-smoke` | 通过 |
| evolution lab `seed-backtest` | 通过 |

2026-05-17 补齐与默认接入验证：

| 验证项 | 结果 |
| --- | --- |
| compact 增量补齐 | 已补 `2026-05-15`，不复制 `atomic_limit_state_5m` |
| compact 当前别名 | `/Users/dong/Desktop/AIGC/market-data/atomic_facts/shadow/market_atomic_mainboard_compact_current.db` |
| compact 覆盖 | `atomic_trade_5m` `50,608,009` 行，最大日期 `2026-05-15` |
| `atomic_limit_state_5m` | compact 中不存在 |
| 新旧 API 对比 | 24 个接口 body hash 全一致，必需项 0 失败 |
| compact API smoke | 25 个接口；22 个必需项 0 失败，2 个允许失败为既有数据文件缺口 |
| 页面 smoke | 8 个页面全部通过 |
| 默认启动验证 | `ops/start_local_research_station.sh` 自动开启 compact，复盘/V2 接口通过 |
| V2 评估 | `2026-05-12 ~ 2026-05-15` 返回 14 笔交易，和正式库一致 |

2026-05-17 全窗口 compact 验证：

| 验证项 | 结果 |
| --- | --- |
| 全窗口 compact DB | 已构建：`market_atomic_mainboard_compact_20250102_20260514.db` |
| 文件体积 | `23,620,218,880` bytes，约 22G |
| 构建方式 | `--no-vacuum`，避免额外占用临时空间 |
| `atomic_limit_state_5m` | 不存在，符合目标 |
| `atomic_trade_5m` | `50,453,254` 行，`2025-01-02 ~ 2026-05-14` |
| `atomic_trade_daily` | `1,035,026` 行，`2025-01-02 ~ 2026-05-14` |
| `atomic_limit_state_daily` | `1,035,026` 行，`2025-01-02 ~ 2026-05-14` |
| `atomic_order_5m` | `7,415,554` 行，`2026-03-02 ~ 2026-05-14` |
| `atomic_book_state_5m` | `7,304,908` 行，`2026-03-02 ~ 2026-05-14` |
| 查询计划 | `symbol + bucket_start` 命中 `(symbol, bucket_start)` 主键索引 |
| API smoke | 通过，包括 2025 弱窗口和 2026 full 窗口 |
| 页面截图 smoke | 8 个页面均生成非空截图 |
| evolution lab smoke | `catalog-data` / `rl-random-smoke` / `seed-backtest` 均通过 |

磁盘说明：

- 全窗口 compact 构建完成后，本机可用空间约 10G。
- 后续不应再生成大型 shadow / audit / vacuum 文件，除非先释放空间。

页面截图 smoke 说明：

- 使用后端 `8012`、前端 `3012` 临时服务。
- 验证后已停止本轮启动的 `8012 / 3012` 监听进程。
- Chrome headless 在 `dump-dom` 等待阶段会超时，但截图已生成且非空；本轮将其作为“页面无白屏 smoke 通过”，不等同于截图级逐项对比。

## 1. 结论

本轮数据库治理不直接修改正式库，只在新 worktree 和 shadow compact DB 内验证。

核心判断：

1. `atomic_trade_5m` 是事实底座，保留全量。
2. `atomic_limit_state_daily` 是涨跌停状态主表，保留。
3. `atomic_limit_state_5m` 不应继续作为默认存储表存在，应废弃。
4. 如果以后需要盘中“触板 / 炸板 / 封板变化”研究，优先从 `atomic_trade_5m + atomic_limit_state_daily` 按需计算，不默认落一张全量 5m 状态表。

正式接入前必须完成 shadow DB、页面、训练、回测、查询性能验证。验证通过后才允许默认接入新方案；老表和老索引最后清理。

## 2. 为什么废弃 `atomic_limit_state_5m`

涨停 / 跌停本质是日级交易规则和日内价格边界，不是 5m 粒度的独立事实。

现在这张表的含义是：

- 每只股票、每个交易日、每个 5m bar 都落一行。
- 如果该 5m 的高价触到当天涨停价，就标记触涨停。
- 如果该 5m 的收盘价等于涨停价，就标记该 5m “封住涨停收”。
- 如果全天一字板或长时间封板，很多 5m bar 会重复出现相同状态。
- 如果全天正常，则每个 5m bar 都是一行 `normal`。

这带来两个问题：

1. 数据价值低：大量 normal 或重复封板状态，和 `atomic_trade_5m` / `atomic_limit_state_daily` 可推导信息重合。
2. 存储成本高：它当前和 `atomic_trade_5m` 行数完全一致，相当于复制了一张 5m 级别派生快照表。

结论：`atomic_limit_state_5m` 不作为长期目标表。  
日级涨跌停状态由 `atomic_limit_state_daily` 承担；盘中触板细节按需计算。

## 3. 当前核验事实

正式 atomic 主库：

`/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_full_reverse.db`

只读核验结果：

| 表 | 行数 | 覆盖 |
| --- | ---: | --- |
| `atomic_trade_5m` | 50,608,009 | 2025-01-02 ~ 2026-05-15 |
| `atomic_limit_state_5m` | 50,608,009 | 2025-01-02 ~ 2026-05-15 |
| `atomic_limit_state_daily` | 1,038,208 | 2025-01-02 ~ 2026-05-15 |
| `atomic_order_5m` | 7,570,362 | 2026-03-02 ~ 2026-05-15 |
| `atomic_book_state_5m` | 7,457,644 | 2026-03-02 ~ 2026-05-15 |

典型状态分布：

- `2026-05-12`、`2026-05-13`、`2026-05-14` 的 `atomic_limit_state_5m` 全部是 `normal`。
- `2026-03-01 ~ 2026-05-14` 的日级非 normal 约 2,631 个 symbol-day。

这说明当前 `atomic_limit_state_5m` 的主要成本不是事件记录，而是全量 normal 快照。

## 3.1 当前执行结果

已完成到 shadow compact smoke 验证阶段。

代码侧已完成：

1. atomic DB resolver 增加 compact 读取开关。
2. 单票 5m 历史查询改为 `symbol + bucket_start` 范围。
3. `intraday_evolution_lab` 不再读取 `atomic_limit_state_5m`，改用 `atomic_limit_state_daily` 派生 5m 展示字段。
4. 涨跌停重建脚本默认 daily-only，只有显式 `--include-5m` 才创建 / 写入 legacy 5m 表。
5. 日 delta 导出 / 合并、回填 finalize、单票校验流程不再把 `atomic_limit_state_5m` 当必需表。

shadow DB 已完成：

| shadow DB | 窗口 | 体积 | 结果 |
| --- | --- | ---: | --- |
| `market_atomic_mainboard_compact_20260514_smoke.db` | 2026-05-14 | 159M | 一日 smoke 通过 |
| `market_atomic_mainboard_compact_20260301_20260514.db` | 2026-03-01 ~ 2026-05-14 | 7.4G | 已由用户删除 |
| `market_atomic_mainboard_compact_20250102_20260514.db` | 2025-01-02 ~ 2026-05-15 | 22G | 已增量补齐并验证通过 |

大窗口复制行数：

| 表 | 行数 |
| --- | ---: |
| `atomic_trade_5m` | 7,410,889 |
| `atomic_trade_daily` | 152,851 |
| `atomic_order_5m` | 7,415,554 |
| `atomic_order_daily` | 152,851 |
| `atomic_book_state_5m` | 7,304,908 |
| `atomic_book_state_daily` | 152,851 |
| `atomic_limit_state_daily` | 152,851 |
| `cfg_limit_rule_map` | 7 |
| `atomic_limit_state_5m` | 未复制 |

2026-05-17 增量补齐 `2026-05-15` 后行数：

| 表 | 行数 | 覆盖 |
| --- | ---: | --- |
| `atomic_trade_5m` | 50,608,009 | 2025-01-02 ~ 2026-05-15 |
| `atomic_trade_daily` | 1,038,208 | 2025-01-02 ~ 2026-05-15 |
| `atomic_order_5m` | 7,570,362 | 2026-03-02 ~ 2026-05-15 |
| `atomic_order_daily` | 156,033 | 2026-03-02 ~ 2026-05-15 |
| `atomic_book_state_5m` | 7,457,644 | 2026-03-02 ~ 2026-05-15 |
| `atomic_book_state_daily` | 156,033 | 2026-03-02 ~ 2026-05-15 |
| `atomic_limit_state_daily` | 1,038,208 | 2025-01-02 ~ 2026-05-15 |
| `atomic_limit_state_5m` | 未复制 | 符合目标 |

全窗口复制行数：

| 表 | 行数 |
| --- | ---: |
| `atomic_trade_5m` | 50,453,254 |
| `atomic_trade_daily` | 1,035,026 |
| `atomic_order_5m` | 7,415,554 |
| `atomic_order_daily` | 152,851 |
| `atomic_book_state_5m` | 7,304,908 |
| `atomic_book_state_daily` | 152,851 |
| `atomic_limit_state_daily` | 1,035,026 |
| `cfg_limit_rule_map` | 7 |
| `atomic_limit_state_5m` | 未复制 |

查询计划验证：

- `symbol + bucket_start` 使用主键索引 `(symbol, bucket_start)`。
- `symbol + trade_date` 仍会使用 `idx_atomic_trade_5m_symbol_trade_date` 且需要临时排序。
- 因为仍存在多票日期窗口查询，本阶段不删除日期索引，只保留实验开关用于后续 A/B。

已跑验证：

- `py_compile` 通过。
- 相关单元测试：`29 passed`。
- `npm run build` 通过。
- compact 环境读取 smoke 通过：
  - `catalog_intraday_data`
  - `load_intraday_panel`
  - `load_trend_daily_panel`
  - `query_l2_history_5m_rows`
  - `query_l2_history_daily_rows`

正式库 vs compact 大窗口行数对比：

| 表 | 正式库 | compact | 结果 |
| --- | ---: | ---: | --- |
| `atomic_trade_5m` | 7,410,889 | 7,410,889 | 一致 |
| `atomic_trade_daily` | 152,851 | 152,851 | 一致 |
| `atomic_order_5m` | 7,415,554 | 7,415,554 | 一致 |
| `atomic_book_state_5m` | 7,304,908 | 7,304,908 | 一致 |
| `atomic_limit_state_daily` | 152,851 | 152,851 | 一致 |
| `atomic_limit_state_5m` | 存在 | 不存在 | 符合目标 |

页面 / API smoke：

| 页面 / 功能 | 路径或接口 | 结果 |
| --- | --- | --- |
| 首页 | `/` | 截图 smoke 通过 |
| 复盘页 | `/review?symbol=sh601138` | 截图 smoke 通过；`/api/review/data` 返回 146 条 5m 数据 |
| 选股研究台 | `/selection-research` | 渲染正常，候选 / profile / multiframe 接口 200 |
| PPO 回测报告 | `/selection-ppo-report` | 截图 smoke 通过；当前本地报告文件缺失仍是既有数据缺口 |
| 机会交易复盘 | `/selection-opportunity-review` | 截图 smoke 通过 |
| 市场热点 | `/market-heat` | 截图 smoke 通过；latest / low-position summary / list 接口 200 |
| 热点低位样本 | `/market-heat/low-position-samples` | 截图 smoke 通过；summary / list 接口 200 |
| 趋势研究 | `/trend-research` | 截图 smoke 通过；ideas 接口 200 |
| V2 选股评估 | `/api/selection/v2/evaluate` | 2026-05-12 ~ 2026-05-14 返回 3 天结果、9 笔交易 |
| 2025 弱窗口复盘 | `/api/review/data` | 2025-01-02 ~ 2025-01-06 返回 147 条 5m 数据 |

2026-05-17 默认接入后验证：

| 验证项 | 结果 |
| --- | --- |
| 启动日志 | `ENABLE_ATOMIC_COMPACT_READ=true`，`ATOMIC_COMPACT_DB_PATH=.../market_atomic_mainboard_compact_current.db` |
| 复盘 5m | `2026-05-12 ~ 2026-05-15` 返回 195 条，最后时间 `2026-05-15 15:00:00` |
| V2 评估 | `2026-05-12 ~ 2026-05-15` 返回 14 笔交易 |
| compact 表检查 | `atomic_limit_state_5m` 不存在 |

新旧 API hash 对比：

| 项 | 结果 |
| --- | --- |
| 报告 | `/tmp/market-live-terminal-db-governance-compare/report-20260517.json` |
| 接口数 | 24 |
| body hash 不一致 | 0 |
| 必需项失败 | 0 |
| 允许失败项 | 2 个，但新旧 body 也一致：PPO 报告文件缺失、`2026-05-15` 细颗粒热点缓存缺失 |

页面 smoke：

| 项 | 结果 |
| --- | --- |
| 报告 | `/tmp/market-live-terminal-compact-smoke/pages-after-default-20260517.json` |
| 页面数 | 8 |
| 必需项失败 | 0 |
| 说明 | `/selection-research` 常规 Chrome 截图命令会超时，CDP fallback 已确认页面渲染出工作台内容且无渲染错误 |

人工页面验收：

| 项 | 结果 |
| --- | --- |
| 验证方式 | 独立 worktree 前后端服务，前端 `3003`，后端 `8003` |
| 验证环境 | `ENABLE_ATOMIC_COMPACT_READ=true`，读取 `market_atomic_mainboard_compact_current.db` |
| 用户结论 | 主要页面基本无问题，可进入切换收口 |
| PPO 页面 | 用户确认属于临时训练可视化，不作为 DB 切换阻塞项 |

2026-05-17 老库移位后验证：

| 验证项 | 结果 |
| --- | --- |
| 老库备份位置 | `/Users/dong/Desktop/AIGC/market-data/atomic_facts/backup_pre_compact_cutover_20260517_172307/market_atomic_mainboard_full_reverse.db` |
| 老库原路径 | 已移走；一次旧路径探测产生的 0B 空文件已移到备份目录旁记录 |
| 启动日志 | `ATOMIC_MAINBOARD_DB_PATH` / `ATOMIC_DB_PATH` 均指向 compact symlink |
| 健康检查 | `GET /api/health` 通过 |
| 复盘接口 | `GET /api/review/data` 通过 |
| 市场热点接口 | `GET /api/market_heat/latest` 通过 |
| V2 评估接口 | `GET /api/selection/v2/evaluate` 通过 |

页面验证说明：

- 验证端口：后端 `8012`，前端 `3012`。
- 验证环境：`ENABLE_ATOMIC_COMPACT_READ=1`，`ATOMIC_COMPACT_DB_PATH` 指向大窗口 compact DB。
- 验证后已停止本轮启动的 `8012 / 3012` 进程。
- 复盘页曾出现 ECharts `title/graphic` 组件注册 warning，是既有前端告警，不属于本轮 DB 改造问题。
- API smoke 初次使用系统代理路径时出现 502；用 `curl --noproxy '*'` 直连本地服务后通过，后端自身健康检查和接口均正常。

训练 / 回放 smoke：

| 命令 | 窗口 / 样本 | 结果 |
| --- | --- | --- |
| `catalog-data` | compact DB 全窗口 | 通过，catalog 不再包含 `atomic_limit_state_5m` |
| `rl-random-smoke` | 2026-05-12 ~ 2026-05-14，3 只股票 | 通过，13 笔交易，最终权益 `1,001,254.10` |
| `seed-backtest` | 2026-05-12 ~ 2026-05-14，3 只股票 | 通过，2 笔交易，最终权益 `995,728.46` |

执行说明：

- evolution lab 脚本需用 `/usr/bin/python3`；当前 shell 的 `python` 入口缺少 `numpy`。
- 本轮没有跑完整 PPO 训练，也没有重建 PPO 报告文件。

## 4. 目标架构

### 4.1 保留表

事实层：

- `atomic_trade_5m`
- `atomic_trade_daily`
- `atomic_order_5m`
- `atomic_order_daily`
- `atomic_book_state_5m`
- `atomic_book_state_daily`

状态层：

- `atomic_limit_state_daily`

### 4.2 废弃表

- `atomic_limit_state_5m`

废弃方式：

1. shadow compact DB 不复制这张表。
2. 代码不再把它作为必需依赖。
3. 旧库验证期内保留原表，避免回滚困难。
4. 正式迁移通过后，另起清理变更删除老表或停止同步。

### 4.3 按需派生盘中触板信息

如页面或模型需要盘中触板细节，用查询或临时计算生成：

```sql
SELECT
  t.symbol,
  t.trade_date,
  t.bucket_start,
  CASE
    WHEN d.up_limit_price IS NOT NULL AND t.high >= d.up_limit_price - 0.005 THEN 1
    ELSE 0
  END AS touch_limit_up_5m,
  CASE
    WHEN d.down_limit_price IS NOT NULL AND t.low <= d.down_limit_price + 0.005 THEN 1
    ELSE 0
  END AS touch_limit_down_5m,
  CASE
    WHEN d.up_limit_price IS NOT NULL AND abs(t.close - d.up_limit_price) <= 0.005 THEN 1
    ELSE 0
  END AS close_at_up_limit_5m,
  CASE
    WHEN d.down_limit_price IS NOT NULL AND abs(t.close - d.down_limit_price) <= 0.005 THEN 1
    ELSE 0
  END AS close_at_down_limit_5m
FROM atomic_trade_5m t
LEFT JOIN atomic_limit_state_daily d
  ON d.symbol = t.symbol
 AND d.trade_date = t.trade_date
```

默认页面和训练不需要这套 5m 状态时，不计算。

## 5. `atomic_trade_5m` 查询与索引治理

当前 `atomic_trade_5m` 的索引不是异常，但偏重。

重点治理：

- 单票时间段查询从 `symbol + trade_date` 改为 `symbol + bucket_start between`。
- 优先复用主键索引 `(symbol, bucket_start)`。
- shadow 验证通过后，再评估是否删除 `idx_atomic_trade_5m_symbol_trade_date`。

示例：

```sql
-- 旧
WHERE symbol = ?
  AND trade_date >= ?
  AND trade_date <= ?

-- 新
WHERE symbol = ?
  AND bucket_start >= ?
  AND bucket_start < ?
```

## 6. 实施阶段

### 阶段 A：只读盘点和基线冻结

已完成：

- 建立 worktree：`/Users/dong/Desktop/AIGC/market-live-terminal-db-governance`
- 建立分支：`codex/db-governance`
- 只读核验正式 atomic 主库。
- 初步盘点页面入口、核心查询和训练消费路径。

已补充产物：

- `backend/scripts/audit_atomic_db.py`：输出表覆盖、索引、查询计划、5m 状态分布。
- `backend/scripts/build_atomic_compact_shadow.py`：构建不含 `atomic_limit_state_5m` 的 shadow compact DB。
- shadow DB 构建报告。

已补充：

- `scripts/compare_atomic_backend_modes.py`：正式库和 compact API hash 对比。
- `scripts/smoke_compact_research_station.py`：compact API / 页面 smoke。
- `scripts/probe_page_cdp.mjs`：页面截图超时时的 CDP fallback。

### 阶段 B：shadow compact DB

新建 shadow 库，不覆盖正式库：

`/Users/dong/Desktop/AIGC/market-data/atomic_facts/shadow/market_atomic_mainboard_compact_20260301_20260514.db`

第一轮窗口：

- `2026-03-01 ~ 2026-05-14`
- 状态：已完成，shadow DB 为 7.4G。

第二轮窗口：

- `2025-01-02 ~ 2026-05-15`
- 状态：已完成，shadow DB 为约 22G。
- 文件：`market_atomic_mainboard_compact_20250102_20260514.db`
- 默认入口别名：`market_atomic_mainboard_compact_current.db`

说明：文件名仍保留首次全量构建时的 `20260514`，但 manifest 和数据已增量补齐到 `2026-05-15`。默认启动脚本只依赖 `market_atomic_mainboard_compact_current.db` 别名。

构建内容：

1. 复制窗口内 `atomic_trade_5m / atomic_trade_daily`。
2. 复制窗口内 `atomic_order_5m / atomic_order_daily`。
3. 复制窗口内 `atomic_book_state_5m / atomic_book_state_daily`。
4. 复制窗口内 `atomic_limit_state_daily`。
5. 不复制 `atomic_limit_state_5m`。

验收指标：

- trade/order/book/daily 行数与原库窗口一致。
- `atomic_limit_state_daily` 行数与原库窗口一致。
- 页面和脚本不再硬依赖 `atomic_limit_state_5m`。
- shadow 库体积明显下降。
- 核心查询计划不退化。

### 阶段 C：代码兼容改造

改造原则：

- 默认仍读正式库。
- 新增环境变量启用 shadow：
  - `ATOMIC_COMPACT_DB_PATH`
  - `ENABLE_ATOMIC_COMPACT_READ=1`
- 不改页面 API contract。
- 不删除老查询，先以 feature flag 切换。

重点文件：

- `backend/app/core/config.py`
- `backend/app/db/l2_history_db.py`
- `backend/app/services/intraday_evolution_lab.py`
- `backend/app/services/selection_research.py`
- `backend/app/services/aggressive_10cm_strategy.py`
- `backend/app/services/market_heat.py`
- `backend/scripts/build_limit_state_from_atomic.py`

具体改造：

1. atomic DB resolver 支持 compact shadow path。
2. `atomic_trade_5m` 单票历史查询改为 `bucket_start between`。
3. 移除对 `atomic_limit_state_5m` 的必需依赖。
4. 若确实需要 5m 触板信息，统一从 `atomic_trade_5m + atomic_limit_state_daily` 派生。
5. 增加 shadow 对比脚本。

当前状态：1、2、3、4、5 已完成，页面 / API smoke 和新旧 API hash 对比已通过。

### 阶段 D：页面功能验证矩阵

必须验证页面：

| 页面 | 路径 | 主要依赖 | 验证重点 |
| --- | --- | --- | --- |
| 盯盘首页 | `/` | `market_data.db` + atomic fallback | 单票搜索、实时/历史切换 |
| 复盘页 | `/review` | sandbox / L2 history / atomic fallback | 5m K、日线、L2 字段 |
| 选股研究台 | `/selection-research` | `selection_research.db` + atomic | 候选列表、详情、历史多周期 |
| PPO 回测报告 | `/selection-ppo-report` | atomic 5m / daily | 交易明细、历史图 |
| 机会交易复盘 | `/selection-opportunity-review` | selection + atomic | 样本详情、首 15m 验证 |
| 市场热点 | `/market-heat` | market_heat + `atomic_limit_state_daily` | 热点列表、涨跌停过滤 |
| 热点低位样本 | `/market-heat/low-position-samples` | market_heat + atomic | 样本详情、收益窗口 |
| 趋势研究 | `/trend-research` | CSV / selection docs | 确认不受 atomic compact 影响 |

每页验证方式：

1. 老库启动一次，保存 API 响应摘要和截图。
2. shadow compact 启动一次，保存 API 响应摘要和截图。
3. 对比关键字段，不要求 JSON 完全一致，但要求业务字段一致。
4. 浏览器冒烟：页面无白屏、无接口错误、图表有数据。

当前状态：全窗口 compact 页面 smoke 已通过；老库 / compact 已完成 API hash 对比，未做逐像素截图对比；用户已完成主要页面人工验收。PPO 页面后续按模型研究入口治理处理，不阻塞本轮 DB 切换。

### 阶段 E：训练 / 回测验证

DB 切换必须跑：

- 选股候选生成。
- `selection_history_multiframe`。
- `intraday_evolution_lab` 数据 catalog。
- opportunity discovery 模型样本加载。
- aggressive 10cm 首 15m 确认。
- market heat 低位样本回放。

不作为本轮 DB 切换阻塞项：

- 完整 PPO 训练。
- PPO 报告生成。
- PPO 临时页面入口去留。

验收：

- 样本数一致或差异有解释。
- 核心收益 / 胜率指标不因 storage 改造漂移。
- runtime 不明显变慢。

### 阶段 F：灰度接入

灰度只在本地研究站做：

1. `ops/start_local_research_station.sh` 支持传入 compact DB。
2. 默认仍使用老库。
3. 增加启动日志：
   - 当前 atomic path
   - compact mode 是否开启
   - `atomic_limit_state_5m` 是否被跳过
4. 连续跑 2 个交易日或 2 次完整研究流程。

当前状态：启动脚本已支持 compact 检查和日志输出；本 worktree 默认优先读取 `market_atomic_mainboard_compact_current.db`。如果该文件不存在，默认回落正式库；如果用户显式开启 compact 但路径不存在，则启动失败。用户已完成一次人工主流程验收并确认无明显问题，满足进入主工作区切换准备的条件。

通过后再考虑：

- 把 compact DB 设为主工作区默认。
- Windows 回填流程同步产出 compact 库。
- 云端不接 full atomic，维持轻量口径。

## 7. 上线流程

### 7.1 分支和版本

1. 当前开发分支：`codex/db-governance`
2. 完成 shadow 验证后打 tag：
   - `snapshot-20260516-pre-atomic-compact`
3. 合并前 review：
   - schema
   - helper
   - scripts
   - tests
   - docs
4. 合并到主线后打 release tag：
   - `v5.1.x-atomic-compact-shadow`

### 7.2 数据版本保存

上线前保留：

- 正式老 atomic 主库原文件。
- compact shadow DB。
- audit report。
- 页面 / API 对比报告。

命名建议：

```text
market_atomic_mainboard_full_reverse.db
market_atomic_mainboard_compact_20260301_20260514.db
atomic_compact_audit_20260516.json
atomic_compact_page_validation_20260516.md
```

### 7.3 切换步骤

1. 停止本地研究站。
2. 设置：
   - `ENABLE_ATOMIC_COMPACT_READ=1`
   - `ATOMIC_COMPACT_DB_PATH=/Users/dong/Desktop/AIGC/market-data/atomic_facts/shadow/...db`
3. 启动本地研究站。compact 可用时，启动脚本会把 `ATOMIC_MAINBOARD_DB_PATH` 和 `ATOMIC_DB_PATH` 都指向 compact，避免服务继续读老 full reverse 路径。
4. 跑页面冒烟。
5. 跑训练 / 回测 smoke。
6. 连续验证通过后，再合并到主工作区。

### 7.4 Windows compact 同步方案

Windows 目前未发现 `D:\market-live-terminal\data\atomic_facts\shadow\market_atomic_mainboard_compact_current.db`。正式切换前需要把 Mac compact DB 传到 Windows。

推荐做法：

1. Windows 创建目录：`D:\market-live-terminal\data\atomic_facts\shadow`。
2. Mac 用 `scp` 或 `rsync` 传输真实 compact 文件：
   - 源文件：`/Users/dong/Desktop/AIGC/market-data/atomic_facts/shadow/market_atomic_mainboard_compact_20250102_20260514.db`
   - 目标文件：`D:\market-live-terminal\data\atomic_facts\shadow\market_atomic_mainboard_compact_20250102_20260514.db`
3. Windows 创建或更新 current 别名。Windows 符号链接权限不稳定，优先用“复制同名 current 文件”或在环境变量中直接指向真实文件。
4. Windows 启动时设置：
   - `ENABLE_ATOMIC_COMPACT_READ=1`
   - `ATOMIC_COMPACT_DB_PATH=D:\market-live-terminal\data\atomic_facts\shadow\market_atomic_mainboard_compact_20250102_20260514.db`
5. 在 Windows 上跑只读核验：
   - `atomic_trade_5m` 最大日期达到 `2026-05-15`
   - `atomic_limit_state_5m` 不存在
   - `atomic_trade_5m / atomic_trade_daily / atomic_limit_state_daily` 行数与 Mac compact 一致

如果要删除 Windows 老 full reverse DB，也按同样顺序：先切环境变量和启动脚本，确认 Windows 侧 compact 可读，再移动老库到备份目录，最后人工删除。

### 7.5 每日跑数兼容方案

当前每日跑数仍按“Windows 产出正式 full reverse atomic，Mac merge 到 full reverse atomic”的思路组织。compact 模式下需要改成两段式：

1. Windows 继续产出每日 atomic delta，但不再要求包含 `atomic_limit_state_5m`。
2. Mac 先把 daily delta merge 到 compact DB，使用 `backend/scripts/append_atomic_compact_shadow.py` 或等价增量逻辑。
3. 增量完成后校验当天：
   - `atomic_trade_5m` 有当天 5m 行
   - `atomic_trade_daily` 有当天日线行
   - `atomic_limit_state_daily` 有当天日级涨跌停状态
   - compact 中仍不存在 `atomic_limit_state_5m`
4. 更新 `market_atomic_mainboard_compact_current.db` 指向或覆盖到最新 compact。
5. Windows 如果需要本地页面/模型读取，也同步同一份 compact 或同步当天 delta 后在 Windows 侧 append。

实现建议：

- 短期：每日跑数仍由 Mac 维护 compact，Windows 只负责产出 delta；跑完后 Mac append compact 并验证。
- 中期：`backend/scripts/run_postclose_l2_daily.py` 增加 compact append 步骤和 compact 校验报告。
- 长期：Windows 也能直接产出 compact DB，Mac/Windows 都不再维护 full reverse 主库。

## 8. 回滚流程

任何一项失败，立即回滚：

1. 关闭 `ENABLE_ATOMIC_COMPACT_READ`。
2. 恢复 `ATOMIC_MAINBOARD_DB_PATH` 指向老库。
3. 重启本地研究站。
4. 隔离 shadow DB，不影响正式库。

本 worktree 的快速回滚方式：

```bash
ATOMIC_MAINBOARD_DB_PATH=/Users/dong/Desktop/AIGC/market-data/atomic_facts/backup_pre_compact_cutover_20260517_172307/market_atomic_mainboard_full_reverse.db \
ATOMIC_DB_PATH=/Users/dong/Desktop/AIGC/market-data/atomic_facts/backup_pre_compact_cutover_20260517_172307/market_atomic_mainboard_full_reverse.db \
ENABLE_ATOMIC_COMPACT_READ=false \
bash ops/start_local_research_station.sh
```

不得在验证前：

- 删除正式库里的 `atomic_limit_state_5m` 老表。
- drop 老索引。
- 覆盖 `market_atomic_mainboard_full_reverse.db`。

## 9. 最终清理条件

只有同时满足以下条件，才进入正式清理：

1. shadow compact 全量窗口验证通过。
2. 页面验证矩阵全部通过。
3. DB 相关训练 / 回测 smoke 通过；完整 PPO 训练不作为本轮 DB 切换阻塞项。
4. 至少保留一个可回滚数据快照。
5. 用户确认可以清理。

Mac 正式老库文件删除前置条件：

1. Windows 备份库路径明确。
2. Windows 备份库文件大小和修改时间可核对。
3. Windows 备份库最大交易日达到同一版本，例如当前为 `2026-05-15`。
4. 关键表行数一致：`atomic_trade_5m / atomic_trade_daily / atomic_limit_state_daily / atomic_order_5m / atomic_book_state_5m`。
5. 至少保留一个本机或外置盘快照后，再人工删除。

删除节奏：

1. 先合并代码切换，让主工作区默认使用 compact。
2. 正常使用 compact 至少 1-2 天，确认没有需要回滚到老库的问题。
3. 核对 Windows 或外置备份满足上述条件。
4. 用户手动删除 Mac 老库文件；本变更不自动删除数据库文件。

正式 atomic 清理必须另起变更卡，不和 shadow 验证混在一个提交里。

## 10. 下一步执行清单

1. 把本 worktree 的 compact 默认读取逻辑合并回主工作区。
2. 主工作区使用 compact 正常跑 1-2 天。
3. 把 Mac compact DB 同步到 Windows，并在 Windows 上设置 compact 环境变量验证。
4. 改造每日跑数：merge 后 append compact，并输出当天 compact 校验报告。
5. 主工作区和 Windows 都稳定后，再由用户手动删除 Mac / Windows 老 full reverse DB。
6. 老表 / 老索引清理另起变更卡。
