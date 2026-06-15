# MOD-20260616-01 Mac 代码与数据仓库恢复规划

- 日期：2026-06-16
- 状态：DONE（2026-06-16 恢复完成，20260615 跑数验收通过）
- 范围：Mac 本地开发仓库、Mac 本地研究站数据仓库、NAS 恢复源、Windows 只读/跑数节点
- 已执行边界：不覆盖旧 iCloud 目录、不拉回 67G atomic 全量大库、不把 Windows 当 Git 跳板、不推送 NAS Git remote
- 最新路径决策：统一恢复到 `/Users/dong/ZhangData`，代码仓库和数据库都放在这个根目录下。

## 1. 目标和成功标准

目标是把 Mac 本地环境恢复成可日常开发、可本地研究、可继续接 10 个金融研究 Agent 的稳定状态。

成功标准：

1. 代码仓库恢复为真正 Git 仓库，能看到 `git status`、分支、remote，并且工作树干净或只剩明确的待恢复差异。
2. 代码能力至少恢复到 2026-06-15 前后的本地开发状态：`v5.2.17` 生产底座 + `v5.2.18-5.2.20` 的 Agentic 公司研究嵌入、星标盯盘页和相关 UI 修复。
3. Mac 本地有一套非 iCloud 管控的统一根目录，能同时承载代码仓库和本地研究站数据。
4. 67G 级别的 5 分钟 atomic 大库不直接拉回 Mac；需要它的查询通过 NAS、派生轻量库或后续接口解决。
5. `ops/start_local_research_station.sh`、`ops/start_local_research_frontend.sh`、`ops/run_daily_new_framework.sh` 这些正式入口可执行，且不再读错路径。
6. 恢复完成后，以 `2026-06-15` 单日跑数作为最终验收：Windows 负责跑数，Mac 完成增量合并，NAS 同步通过，本地页面/API 能读到 6 月 15 日结果。

## 1.0 恢复完成结果

本轮已按统一根目录完成恢复：

```text
/Users/dong/ZhangData/market-live-terminal
/Users/dong/ZhangData/market-data
/Users/dong/ZhangData/recovery
```

代码恢复结果：

1. 从 NAS Git `a89c7c4` 克隆，创建本地分支 `codex/mac-recovery-20260616`。
2. 已提交 3 个本地 checkpoint：
   - `29b1325 Recover Mac research station code and data paths`
   - `2289019 Restore agentic finance research playbook`
   - `bd54f94 Load recovery env for daily runner`
3. `nas` remote 已配置为 `nas-git:zhangdong/market-live-terminal.git`。
4. 版本已统一到 `5.2.20`。
5. 恢复了 `agentic_finance_agents/`、星标盯盘页、Agentic 公司研究嵌入、watchlist 服务端排序与重排接口、6 月 13-15 期间缺失的 `backend/scripts` 和运维脚本。
6. `ops/start_local_research_station.sh`、`ops/start_local_research_frontend.sh`、`ops/run_daily_new_framework.sh` 已能读取新路径 `.env.local`。

验证结果：

1. `bash scripts/check_baseline.sh` 通过：后端 `215 passed, 8 warnings`，前端 `vite build` 通过，治理检查仅历史 warning。
2. 新路径服务已启动：
   - Backend: `http://127.0.0.1:8001`
   - Frontend: `http://127.0.0.1:3001`
3. `/api/selection/health` 最新信号日为 `2026-06-15`。
4. `/api/selection/daily-candidates?trade_date=2026-06-15&include_exit_watchlist=true` 返回 11 个候选，市场水位可用。
5. Playwright 页面验证通过：
   - `/selection-research` 显示 `2026-06-15`、全部 11、买点 3、观察 8、水位 25.0。
   - `/watchlist` 显示 4/4 星标卡片和 live 行情/资金字段。

数据恢复结果：

1. 已从 NAS 恢复到 Mac：
   - `live/market_data.db`
   - `live/user_data.db`
   - `research/current/selection/selection_research.db`
   - `research/current/selection/model_feature_store.db`
   - `research/current/selection/model_market_index_daily.db`
   - `research/current/market_heat/`
   - `research/current/selection/market_environment_gate_2026-06-10/`
2. 67G `atomic_facts/market_atomic_mainboard_compact_current.db` 未拉回 Mac。
3. 20260615 跑数后，Mac 仅保留当天 atomic day delta 小库用于本地校验：
   - `atomic_trade_daily`: 3187
   - `atomic_trade_5m`: 155022
4. 为恢复每日候选链路，从旧本地恢复了 55MB 被 `.gitignore` 忽略的运行时模型产物：
   - `data/selection/opportunity_discovery/opportunity_discovery_trade_l2_v0_1/`
   - `data/selection/opportunity_discovery/postclose_exit_v0_2/`

20260615 最终验收结果：

| 项 | 结果 |
|---|---:|
| Mac `live.history_daily_l2` | 7926 |
| Mac `live.history_5m_l2` | 349821 |
| Mac `selection_feature_daily` | 3187 |
| Mac `selection_signal_daily` | 3187 |
| Mac `selection_candidate_daily` | 11 |
| Mac `model_feature_daily_v1` | 3187 |
| Mac `model_market_index_daily` | 5 |
| Mac `fine_theme_heat_daily_v2` | 633 |
| Mac 水位目录 | 430 行，最新 `2026-06-15` |
| NAS `live.history_daily_l2` | 7926 |
| NAS `live.history_5m_l2` | 349821 |
| NAS `stock_universe_meta` | 5533 |
| NAS 水位目录 | 430 行，最新 `2026-06-15` |

最终证据文件：

```text
/Users/dong/ZhangData/recovery/final_validation_20260615.json
```

注意事项：

1. 第一次 `bash ops/run_daily_new_framework.sh --date 20260615 --json --sync-nas` 的主报告为 `fail`，原因是 repo 内运行时模型产物缺失，导致 `spark_opportunity_selector` 失败。
2. 恢复模型产物后，已补跑本地候选，五个必需策略源全部 `success`。
3. `postclose_l2` 有一次 prepare SSH 子进程卡住；已复用已完成的 Windows worker artifacts，通过正式合并/导出函数补齐 Mac live 和 NAS live。
4. 没有触发 NAS 快照任务；本轮仅做 NAS live 与市场水位同步验收。

## 1.1 本轮执行时采用的假设

本节保留为恢复过程审计记录。恢复已完成，后续目标模式不应再按本节重新执行恢复。

本轮执行时采用的默认假设：

1. 新统一根目录使用：

   ```text
   /Users/dong/ZhangData
   ```

2. 代码仓库目标路径：

   ```text
   /Users/dong/ZhangData/market-live-terminal
   ```

3. 数据仓库目标路径：

   ```text
   /Users/dong/ZhangData/market-data
   ```

4. 现有 iCloud 目录只作为恢复输入读取，不在第一阶段删除或覆盖。
5. 下一轮执行可以创建目录、克隆 Git、传输 NAS 数据、写本地 `.env.local`、运行测试和启动本地服务。
6. Windows 电脑当前可用，但只按两个角色使用：
   - 只读数据来源：只查看项目数据、日包、运行日志和正式数据库，不碰其它资料。
   - 跑数节点：只执行本项目正式日跑所需命令，不做 Git 开发或发布跳板。
7. 恢复后先验证截至 `2026-06-12` 的库和页面，再执行 `20260615` 单日跑数；`2026-06-13`、`2026-06-14` 是周末，不作为缺口交易日处理。
8. 如果遇到非破坏性冲突，优先自动绕开：例如目标目录已存在时改名备份，端口被旧进程占用时按正式启动脚本重启。
9. 只有三类情况需要停下来问用户：
   - 目标目录里已有不可识别的重要文件，且无法安全备份。
   - NAS/Gitea、NAS 数据 SSH、Windows SSH 认证失败。
   - 恢复所需空间预估超过本机安全阈值。

## 2. 当前已确认事实

### 2.1 Mac 当前代码树

当前目录：

```text
/Users/dong/Desktop/桌面 - Zhangdong的MacBook Air/AIGC/market-live-terminal
```

已确认问题：

1. 当前目录不是 Git 仓库，`.git` 缺失，`git status` 直接失败。
2. `package.json`、`README.md`、`src/version.ts` 显示 `v5.2.20`，但 `backend/app/main.py` 仍是 `5.2.17`，版本口径不一致。
3. `backend/scripts/` 整个目录缺失；但 `ops/run_daily_new_framework.sh` 仍调用 `backend/scripts/run_daily_new_framework.py`，测试也引用 `backend.scripts.run_postclose_l2_daily`。
4. 当前树包含一些 6 月 13 日后的前端/研究域文件，例如：
   - `agentic_finance_agents/`
   - `src/components/selection/AgenticCompanyResearchEmbed.tsx`
   - `src/components/watchlist/WatchlistBoardPage.tsx`
   - `src/components/dashboard/IntradayMonitorChart.tsx`
5. 星标盯盘前端存在，但后端 `watchlist` 仍是 NAS `v5.2.17` 旧实现；缺 `sort_order`、`PUT /api/watchlist/reorder` 等后端能力，当前功能不是完整可运行态。

### 2.2 NAS 代码基线

NAS Gitea 可读：

```text
nas-git:zhangdong/market-live-terminal.git
main = a89c7c4d4570d5b177db5d203fac44c1acbb9266
```

临时克隆确认：

1. NAS `main` 是 `v5.2.17` 稳定底座。
2. NAS `main` 有完整 `backend/scripts/`，约 3.9MB。
3. NAS `main` 没有 `agentic_finance_agents/`、`AgenticCompanyResearchEmbed.tsx`、`WatchlistBoardPage.tsx`。
4. 近期对话记录显示这些本地后续改动曾经没有全部推送 NAS：
   - `9a00d25 Merge agentic finance research workflow`
   - `7e5bca9 Merge agentic company research embed prototype`
   - `ce52ea4 feat: add watchlist board`

### 2.3 Mac 当前数据

已确认：

1. 正式 `market-data` 目录当前不存在：
   - `/Users/dong/Desktop/AIGC/market-data`
   - `/Users/dong/Desktop/桌面 - Zhangdong的MacBook Air/AIGC/market-data`
   - `/Users/dong/Projects/AIGC/market-data`
   - `/Users/dong/Data/market-data`
2. 当前仓库内 `data/` 约 1.5G，但项目文档已明确 `repo/data` 只是兼容/回退，不是正式数据根。
3. 根目录 `user_data.db` 是 0 字节。
4. 当前 Mac 可用空间约 54GiB，不适合直接恢复 67G atomic 大库。
5. `/Users/dong/ZhangData` 当前不存在，可作为新的非 iCloud 统一恢复根目录。

### 2.4 NAS 当前数据

NAS 数据根：

```text
/volume1/docker/market-live-terminal/data
```

只读盘点结果：

| 路径 | 大小 | 结论 |
|---|---:|---|
| `data/live/market_data.db` | 823M | 应恢复到 Mac |
| `data/live/user_data.db` | 20K | 应恢复到 Mac |
| `data/research/current/atomic_facts/market_atomic_mainboard_compact_current.db` | 67G | 不直接拉回 Mac |
| `data/research/current/selection/selection_research.db` | 3.3G | 倾向恢复到 Mac |
| `data/research/current/selection/model_feature_store.db` | 4.6G | 需按磁盘阈值决定；可先恢复或做轻量替代 |
| `data/research/current/selection/model_market_index_daily.db` | 64K | 应恢复到 Mac |
| `data/research/current/market_heat/` | 约 477M | 应恢复到 Mac |
| `data/research/current/selection/market_environment_gate_2026-06-10/` | 约 2M | 应恢复到 Mac |

`market_atomic_mainboard_compact_current.db` 包含：

```text
atomic_trade_5m
atomic_order_5m
atomic_book_state_5m
atomic_trade_daily
atomic_order_daily
atomic_book_state_daily
...
```

所以它正好命中“5 分钟最大原始/atomic 数据留 NAS”的新口径。

最新空间评估：

```text
Mac 可用空间：约 53GiB
计划本地恢复数据：live 823M + selection 7.9G + market_heat 477M + 代码约 100M
不恢复到 Mac：atomic_facts 67G
```

结论：一步到位恢复轻量本地数据是可行的；直接恢复 67G atomic 不可行。

### 2.5 Windows 当前可用性与时间线

Windows 数据主站当前按只读/跑数节点使用，不作为 Git 开发或发布跳板。

已确认入口：

```text
Tailscale: 100.115.228.56
LAN:       192.168.3.108
SSH:       laqiyuan@100.115.228.56
Hostname:  DESKTOP-9LMADRQ
```

已确认连通性：

1. `100.115.228.56` ping 可达。
2. `192.168.3.108` ping 可达。
3. `ssh laqiyuan@100.115.228.56 "echo WIN_SSH_OK && hostname"` 可返回 `DESKTOP-9LMADRQ`。

时间线口径：

1. 当前交易数据应至少恢复到 `2026-06-12`。
2. `2026-06-13`、`2026-06-14` 是周末，不跑交易日补数。
3. `2026-06-15` 是恢复完成后的最终验证交易日。
4. 目标模式执行时，先完成 Mac 代码和数据库恢复，再跑 `20260615` 单日主链。

## 3. 推荐恢复目标路径

不建议继续把真实代码和数据放在 iCloud 管控的 Desktop/文稿路径。新的 canonical 根目录统一为：

```text
/Users/dong/ZhangData
```

目录结构：

```text
/Users/dong/ZhangData/
  market-live-terminal/   # Git 代码仓库
  market-data/            # Mac 本地研究站数据仓库
  recovery/               # 本次恢复 manifest、日志、临时核对结果
```

兼容入口只作为后续可选动作：

```text
/Users/dong/Desktop/AIGC/market-live-terminal -> /Users/dong/ZhangData/market-live-terminal
/Users/dong/Desktop/AIGC/market-data -> /Users/dong/ZhangData/market-data
```

原因：

1. 旧脚本和旧 Codex 线程还能继续访问 `/Users/dong/Desktop/AIGC/...`。
2. 真实文件脱离 iCloud，避免 `.git`、SQLite、日志、大文件被占位、同步或搬迁。
3. 后续可以逐步把脚本默认路径收敛到 `FORMAL_MARKET_DATA_ROOT`，不一次性全仓改硬编码。
4. 代码和数据库都在 `/Users/dong/ZhangData` 下面，避免再拆成两个外层目录。

## 4. 代码恢复方案

### 4.1 原则

1. 不在当前残缺目录上直接覆盖。
2. 先从 NAS Gitea 克隆一份干净仓库，恢复 Git 元数据和 `backend/scripts/` 底座。
3. 再把当前残缺树中 NAS 没有的后续功能作为候选差异导入。
4. 每一类后续功能都按对话记录和文件级验证单独恢复，不把残片一次性全拷。

### 4.2 推荐步骤

1. 冻结当前残缺目录。
   - 生成文件 manifest。
   - 保留当前目录为恢复输入，不再继续开发。
2. 新建稳定路径并克隆 NAS：
   - `mkdir -p /Users/dong/ZhangData/recovery`
   - `git clone nas-git:zhangdong/market-live-terminal.git /Users/dong/ZhangData/market-live-terminal`
3. 建立恢复分支：
   - 从 `a89c7c4` 起新建 `codex/mac-recovery-20260616`。
4. 从当前残缺树恢复这些后续模块：
   - `agentic_finance_agents/`
   - `src/components/selection/AgenticCompanyResearchEmbed.tsx`
   - `src/components/selection/SelectionDecisionPanel.tsx` 中 Agentic 嵌入挂载
   - `src/components/watchlist/WatchlistBoardPage.tsx`
   - `src/services/stockService.ts` 的 `reorderWatchlist`
   - `src/App.tsx` 的 `/watchlist` 路由
   - `src/components/dashboard/IntradayMonitorChart.tsx` 及资金图真实比例修复相关文件
5. 从对话记录补齐当前残缺树没有的后端改动：
   - `watchlist.sort_order`
   - `PUT /api/watchlist/reorder`
   - `crud` 层排序读写
   - Config modal 星标管理后台读写一致性
6. 恢复 6 月 15 路径和日跑修复：
   - `ops/start_local_research_station.sh` / `ops/start_local_research_frontend.sh` 的 UTF-8 进程识别修复
   - `backend/scripts/run_postclose_l2_daily.py` 失败 worker retry 修复
   - `backend/scripts/run_daily_new_framework.py` 水位先于 live/L2 后处理、live 失败只告警的修复
   - `ops/run_daily_new_framework.sh` 是否默认 `DAILY_SYNC_NAS=true` 需要重新按对话确认，避免本地排障跑误写 NAS
7. 同步版本到一个新的恢复版本，例如 `v5.2.21-recovery` 或正式 `v5.2.21`。
8. 跑最小验证：
   - `npm run check:version`
   - `npm run build`
   - `bash scripts/check_baseline.sh`
   - `pytest backend/tests/test_run_postclose_l2_daily.py backend/tests/test_run_daily_new_framework_auto.py -q`
9. 验证通过后，把恢复分支提交到本地 Git；是否推 NAS 另行按用户明确指令执行。
10. 执行 `20260615` 单日跑数作为最终验收：
    - 优先从 Mac 新仓库调用正式入口，让它编排 Windows 跑数和 Mac/NAS 同步。
    - 推荐命令：`bash ops/run_daily_new_framework.sh --date 20260615 --json --sync-nas`
    - 如果脚本实际参数不是 `--date`，先用 `python3 backend/scripts/run_daily_new_framework.py --help` 核对，不猜参数。
    - Windows 仅允许访问 `D:\MarketData`、`D:\market-live-terminal`、`.run`、正式日志和正式输出库。
    - 不在 Windows 上做 Git 提交、推送、文档编辑或无关文件操作。

## 5. 数据恢复方案

### 5.1 本地化数据清单

第一批应恢复到 Mac：

```text
/Users/dong/ZhangData/market-data/live/market_data.db
/Users/dong/ZhangData/market-data/live/user_data.db
/Users/dong/ZhangData/market-data/research/current/selection/selection_research.db
/Users/dong/ZhangData/market-data/research/current/selection/model_market_index_daily.db
/Users/dong/ZhangData/market-data/research/current/selection/market_environment_gate_2026-06-10/
/Users/dong/ZhangData/market-data/research/current/market_heat/
```

第二批本轮也纳入一步到位恢复：

```text
/Users/dong/ZhangData/market-data/research/current/selection/model_feature_store.db
```

当前可用空间约 53GiB，`model_feature_store.db` 4.6G 可放；本轮直接恢复它，除非执行前空间低于 20GiB 安全线。

不直接恢复到 Mac：

```text
/volume1/docker/market-live-terminal/data/research/current/atomic_facts/market_atomic_mainboard_compact_current.db
```

这份 67G DB 留在 NAS。Mac 本地如需要日线或少量 5m 查询，应后续做以下二选一：

1. 从 NAS 派生轻量只读库，只包含近期日期、指定股票或日线表。
2. 在 NAS 提供查询/导出接口，Mac 按需拉小结果集。

### 5.2 恢复方式

推荐传输方式：

1. 小文件和 DB：`scp -O` 或 `tar | ssh`。
2. 目录：优先 `tar | ssh`，避免 macOS/iCloud 扩展属性干扰。
3. 每次传输前先生成 manifest，但不把 manifest 当作停止点；manifest 通过后继续自动传输：
   - 源路径
   - 目标路径
   - 大小
   - sha256 或 sqlite quick_check
   - 是否恢复到 Mac
   - 恢复理由

### 5.3 启动环境变量

恢复后本地 `.env.local` 或启动脚本环境应显式指向：

```bash
FORMAL_MARKET_DATA_ROOT=/Users/dong/ZhangData/market-data
LIVE_DATA_ROOT=/Users/dong/ZhangData/market-data/live
RESEARCH_CURRENT_ROOT=/Users/dong/ZhangData/market-data/research/current
DB_PATH=/Users/dong/ZhangData/market-data/live/market_data.db
USER_DB_PATH=/Users/dong/ZhangData/market-data/live/user_data.db
SELECTION_DB_PATH=/Users/dong/ZhangData/market-data/research/current/selection/selection_research.db
```

`ATOMIC_COMPACT_DB_PATH` 不应默认指向本地 67G 大库。需要 atomic 查询时，先走 NAS 轻量接口或派生库方案。

## 6. 对话记录恢复线索

后续 Goal Mode 应优先读取这些线程：

| 线程 | 用途 |
|---|---|
| `019e9d8f-fd79-7bd2-bfa5-8580551786fd` | 三端职责、文档治理、Mac/NAS/Windows 数据口径 |
| `019eb474-54f3-7f71-a67d-e2ce24de8742` | 10 个金融研究 Agent 迁移、`agentic_finance_agents` 架构 |
| `019eb73f-9e61-7833-b1e7-1029efe1269a` | Agentic 公司研究嵌入，`v5.2.18-v5.2.19` |
| `019ebc1f-e527-77d3-9bc9-2bb16b22638b` | 星标盯盘页、服务端 watchlist、`v5.2.20` |
| `019ec016-4cfc-7c50-8d40-af5ea38a274a` | 盯盘页坐标轴、iCloud 路径、日跑/NAS 同步修复 |
| `019eb6f2-de85-7640-ac9d-77b3d0465072` | 选股研究页瘦身、旧研究摘要下线方向 |
| `019eaff2-e861-76f0-976e-e1e583b4f3e7` | 选股页左侧导航、小 K 线、多分类、市场水位 UI |
| `019eb1d1-6754-7332-b68a-fa2623f03c0b` | 市场水位门控、6 月 12 日水位修复、NAS 发布分叉处理 |

## 7. 验收清单

代码验收：

1. `git status` 可用。
2. `git remote -v` 至少包含 `nas` 或 `origin`，且能 `git fetch`。
3. `backend/scripts/run_daily_new_framework.py`、`backend/scripts/run_postclose_l2_daily.py` 存在。
4. `package.json`、`README.md`、`src/version.ts`、`backend/app/main.py` 版本一致。
5. `/watchlist` 页面存在，且后端支持服务端排序。
6. 选股右侧 Agentic 公司研究卡能显示简版卡和详情弹层。

数据验收：

1. `/Users/dong/ZhangData/market-data/live/market_data.db` 存在并通过 `sqlite3 ... "pragma quick_check"`。
2. `/Users/dong/ZhangData/market-data/live/user_data.db` 存在且 watchlist 表可读。
3. `selection_research.db`、`model_market_index_daily.db`、`market_heat/` 已恢复。
4. 本地研究站通过正式脚本启动：
   - `bash ops/start_local_research_station.sh`
   - `bash ops/start_local_research_frontend.sh`
5. 本地页面验证：
   - `http://localhost:3001/selection-research`
   - `http://localhost:3001/watchlist`
6. 本地 API 验证：
   - `/api/health`
   - `/api/selection/health`
   - `/api/watchlist`
   - `/api/selection/daily-candidates?include_exit_watchlist=true`

最终跑数验收：

1. `20260615` 日跑报告状态为成功，或失败原因明确且不是恢复环境问题。
2. Mac 本地 `market-data` 的核心库覆盖到 `2026-06-15`：
   - `live/market_data.db`
   - `selection/selection_research.db`
   - `selection/model_feature_store.db`
   - 市场水位运行态目录
3. NAS 同步通过：
   - `live/market_data.db` 覆盖到 `2026-06-15`
   - 市场水位目录覆盖到 `2026-06-15`
   - NAS 快照任务已触发或有明确跳过原因
4. 本地页面可验证：
   - `/selection-research` 能选择或默认进入 `2026-06-15`
   - `/watchlist` 可读 6 月 15 日本地 live 数据
5. 如果 `20260615` 原始日包在 Windows 不完整，应停止并说明缺哪个包或目录；不要临时改算法绕过完整性 gate。

## 8. 风险和决策点

1. 当前残缺目录没有 `.git`，不能把它当作可信主线。
2. NAS `main` 稳定但偏旧，不能直接覆盖掉当前树中的 Agentic 和 watchlist 后续工作。
3. `v5.2.20` 残缺风险已处理：后端版本、watchlist 服务端排序与重排接口已补齐并通过基线测试。
4. 67G atomic DB 已超过当前 Mac 安全恢复阈值，应明确留在 NAS。
5. 旧文档里仍有 `/Users/dong/Desktop/AIGC/market-data` 和 `v5.2.2` 等旧口径，恢复后要统一修订。
6. iCloud 问题不是“路径名字难看”，而是真实文件仍受 Desktop/文稿同步管理。必须把真实目录迁出 iCloud。
7. Windows 只用于项目数据和跑数，不能把“可 SSH”扩大理解成可以浏览或移动其它资料。

## 9. 后续 Goal Mode 建议入口

本恢复目标已完成。后续目标模式不要再从旧 iCloud 路径恢复一遍，默认从新根目录继续开发、研究或跑数。

后续目标建议写成：

```text
继续在已恢复的新根目录推进 Market Live Terminal。主工作区是 /Users/dong/ZhangData/market-live-terminal，正式本地数据根是 /Users/dong/ZhangData/market-data，旧 iCloud Desktop 目录只作为只读历史输入，不再作为开发主线。开始前先读 AGENTS.md、docs/changes/MOD-20260616-01-mac-code-and-data-recovery-plan.md、/Users/dong/ZhangData/recovery/final_validation_20260615.json。默认按 Mac 本地研究站验证；Windows 只作为只读数据来源和跑数节点，NAS 只按明确目标做 live/水位/发布同步。67G atomic 全量大库继续留 NAS，Mac 只保留必要日增量或轻量派生库。涉及 NAS/Gitea/Tailscale/SSH 时优先使用 nas skill。若要跑后续交易日，先确认交易日和 Windows 日包，再从新仓库执行 bash ops/run_daily_new_framework.sh --date YYYYMMDD --json --sync-nas，并最终验证 Mac 本地库、NAS live/水位、/selection-research、/watchlist。
```

已完成恢复留下的关键证据：

```text
/Users/dong/ZhangData/recovery/recovery_code_manifest_20260616.json
/Users/dong/ZhangData/recovery/recovery_data_manifest_20260616.json
/Users/dong/ZhangData/recovery/final_validation_20260615.json
```

当前服务入口：

```text
Backend:  http://127.0.0.1:8001
Frontend: http://127.0.0.1:3001
```

如果后续需要推送代码到 NAS Gitea，先明确目标 remote/branch，再按 NAS skill 校验 remote 和 push；不要默认自动推送。
