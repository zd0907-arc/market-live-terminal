# 04_OPS_AND_DEV (开发与运维 SOP / 远程控制唯一来源)

> **核心定位**：当准备进行系统的架构升级、代码上线部署或本地调试时所需的标准操作流程（SOP）。在动用 `ssh`、`git push` 前，需要严格参考此文档。
>
> **文档边界**：从 2026-03-09 起，Mac/Windows/Cloud 远程控制步骤统一收敛到本文件。`REMOTE_CONTROL_GUIDE.md` 仅保留索引说明，不再维护独立步骤。
>
> **边界提醒**：交易时段判定、回溯展示等业务语义不在本文件裁决，统一以 `docs/02_BUSINESS_DOMAIN.md`（尤其 `CAP-MKT-TIME`）为准。

## 一、 网络联通测试规范 (The Tailscale Gate)

在进行任何 Mac <-> Windows 的联动开发和代码推送前，必须确认虚拟内网组网通畅。所有对家庭主机的操作，**废弃 `192.168.3.108` 的原始局域网称呼，统一切换为 Tailscale 魔方化局域网 IP**。

*   **司令部 Mac (您当前的操作机器)**: `100.112.131.36`
*   **雷达站 Windows (运行无头爬虫与爬虫任务)**: `100.115.228.56`

### 1. 探活测试 (Ping)
必须可以在公网跨越公司防火墙 PING 通家里电脑。如果在公司办公室开发：
```bash
ping -c 4 100.115.228.56
```

### 1.1 连接抖动快速判定（必做）
当 `tailscale status` 显示 `active/idle` 但任务依然失败时，先执行：
```bash
tailscale ping -c 2 100.115.228.56
ssh -o ConnectTimeout=8 laqiyuan@100.115.228.56 "echo ok"
```
- 两条都成功：可继续执行同步/回传/ETL。
- 任一失败：进入 `07_PENDING_TODO.md` 阻塞流程，不要盲目重试大文件传输。
### 2. 登陆检查与状态恢复 (SSH)
如果需要手动连进家里机器看清洗日志或重启进程：
```bash
ssh laqiyuan@100.115.228.56
# 密码：请从本地 1Password/备忘录中获取
```
*提示：由于 Windows 不是完整的 Git Repo，且是“无感隐藏自启运行”，如果您只是为了发代码，本步骤甚至都是多余的。直接看发版流程。*

### Windows 运行目录约定（2026-03-07 更新）
- **Windows 统一项目目录**：`D:\market-live-terminal`
- 凡是脚本同步、自启脚本、ETL 执行路径，均以该目录为准。

### Windows 盘后 L2 日包目录约定（2026-03-14 冻结）
- **原始数据根目录**：`D:\MarketData`
- **统一目录结构**：
```text
D:\MarketData\
  └── YYYYMM\
      └── YYYYMMDD\
          └── {symbol}.SZ|SH|BJ\
              ├── 行情.csv
              ├── 逐笔成交.csv
              └── 逐笔委托.csv
```
- 规则：
  - 月目录必须存在，如 `202603`；
  - 单日日包不得长期裸放在 `D:\MarketData\20260311\...` 根下；
  - 如供应商先给到裸日目录，落盘后第一步应先归档进对应月目录，再允许进入 ETL/回补流程。
- 运维要求：
  - 目录扫描、回补、失败重跑均以 `YYYYMM/YYYYMMDD` 为准；
  - 新日日包上线前必须先通过日包验真脚本，再允许进入正式回补链路。

### Mac 控 Windows 长任务执行与验真（2026-03-12 新增）
当任务由 Mac 编写、但必须在 Windows 节点持续运行时，执行前后统一遵循以下规则：

1. **先确认真实路径**
   - `scp` 上传到 Windows 时，文件常先落到 `C:\Users\laqiyuan\`，不要默认它已经在 `D:\market-live-terminal`。
   - 启动前必须核对 4 个路径：项目根目录、Python 可执行路径、脚本实际落点、日志落点。
2. **优先使用 `cmd.exe /c` 包一层**
   - `schtasks /Create /TR` 当前最稳的方式是 `cmd.exe /c <bat>`，或 `cmd.exe /c "<python.exe> <script> <args>"`。
   - 不要直接把整段 Python 命令裸写进 `/TR`，否则 Windows 可能把它整体当成一个“可执行文件路径”。
3. **停止任务要双重确认**
   - `schtasks /End` 只结束计划任务本身，不保证 Python 子进程一起退出。
   - 停止后必须再查 `tasklist`；若子进程仍在，使用 `taskkill /PID <pid> /F`。
4. **任务是否真跑，不能只看窗口或任务状态**
   - 至少同时验证以下三类信号中的两类：
     - Python 进程存在；
     - CPU 时间持续增长；
     - 日志文件大小 / 修改时间持续增长；
     - 数据库 run 记录或进度记录持续推进。
   - 特别注意：本项目月批日志的正常进度可能落在 `out.log` 或 `err.log`；排查时两边都要看，以最近一次任务实际写入的文件为准。
5. **Mac 侧读取 Windows 文本时注意编码**
   - `cmd` / `schtasks` / `tasklist` 输出在 Mac 侧建议按 `gbk` 解码，避免中文或列宽乱码导致误判。
6. **推荐配套 Skill**
   - 若在 Codex 中处理这类跨机任务，优先使用外部 Skill：`mac-windows-ops-bridge`，其中已沉淀本项目实战经验与检查命令。

### Sandbox Review V2 全月份总控启动约定（2026-03-12 新增）
当需要让 Windows 节点一次性把 `2025-01-01 ~ 2026-02-28` 全段复盘数据跑完时，统一改为启动总控脚本，而不是每月人工拉起一次：

```bat
C:\Users\laqiyuan\AppData\Local\Programs\Python\Python311\python.exe -u backend\scripts\sandbox_review_v2_run_all_months.py D:\MarketData --workers 12 --min-workers 8 --mem-high-watermark 80 --day-symbol-batch-size 240 --resume
```

- 运行语义：默认按 `2026-02 -> 2025-01` 逐月逆序串行执行。
- 默认停机策略：
  - 月份状态为 `done`：自动进下一个月；
  - 月份状态为 `partial_done` / 子进程失败：默认停机等待人工处理；
  - 全部月份完成：停在 `done` 态，不自动同步云端、不自动发布版本。
- 观察入口：
  - 月份级状态：`data/sandbox/review_v2/meta.db::sandbox_backfill_month_runs`
  - 总控状态文件：`data/sandbox/review_v2/logs/run_all_months_latest.json`
  - 单月明细日志：`data/sandbox/review_v2/logs/backfill_month_YYYY_MM.out.log`
- 切换注意：若当前已有单月任务在运行（例如 `SandboxBackfillMonth202602`），不要并发再起总控任务；应先等旧任务结束，或显式停掉旧任务后再切换。
- Mac 本地检查脚本：`/Users/dong/Desktop/AIGC/market-live-terminal/check_windows_review_v2_progress.py`。执行示例：`python3 /Users/dong/Desktop/AIGC/market-live-terminal/check_windows_review_v2_progress.py --tail 12`；默认会输出计划任务状态、相关 Python 进程、总控状态文件、月份完成信号以及总控日志尾部。
- `2026-03-14` 首轮实绩：
  - Windows 总控状态文件 `run_all_months_latest.json` 已到 `status=done`；
  - 通过 `scp -3 -r` 已完成 `data/sandbox/review_v2/symbols` 从 Windows 到云端的首轮全量同步；
  - 若云端 symbol DB 已存在但 `/api/sandbox/review_data` 仍为空，优先排查容器内是否还在运行旧版 `sandbox_review_v2_db.py`（1m 旧逻辑），必要时同步代码并 `sudo docker compose build backend frontend && sudo docker compose up -d backend frontend`。

### 盘后 L2 正式回补 SOP（设计冻结，待实现）
当每日盘后 L2 日包进入 Windows 后，正式流程应固定为：

1. **先归档目录**
   - 确认数据已放入 `D:\MarketData\YYYYMM\YYYYMMDD\{symbol}` 结构；
   - 若供应商只给了裸日目录，先完成归档整理。
2. **先做日包验真**
   - 使用 `backend/scripts/inspect_daily_l2_package.py` 检查结构、列名、OrderID、样本可读性；
   - 验真失败的日包不得进入正式回补。
3. **执行按日回补**
   - 从同一份日包同时产出 L1/L2 的 `5m + daily` 正式派生结果；
   - 写入前按 `symbol + trade_date` 执行整日删后重写。
4. **记录回补状态**
   - 必须写 `l2_daily_ingest_runs` / `l2_daily_ingest_failures`；
   - 失败股票、失败文件、错误信息必须可追溯。
5. **次日历史验真**
   - 次日从盯盘页历史模式和日K历史模式抽样确认查询已转为正式值。

> 注意：
> - 原始 `逐笔成交/逐笔委托/行情` 不上云；
> - 云端只接收正式派生结果；
> - `15m/30m/1h` 不单独落库，统一由 `5m` 聚合。

---

## 二、 发版与一键装填协议 (CD/CI Pipeline)

所有的后端业务核心逻辑（包括 Web 服务 `app`、爬虫调度 `scripts`）都会在 Mac 司令部被研发完毕。完成修改后，你面对两个目的地：【腾讯云】和【Windows 雷达站】。

### 发版前强制变量检查（v4.2.3+）

在云端 `deploy/.env` 中，以下变量必须完成配置：

```env
# 内部 ingest 鉴权（云端 + Windows 必须一致）
INGEST_TOKEN=replace-with-strong-token

# 业务写接口鉴权（前端构建和后端校验共用）
WRITE_API_TOKEN=replace-with-strong-token

# 架构护栏：云端默认只被动 ingest
ENABLE_CLOUD_COLLECTOR=false
```

云端快速核验：
```bash
cd ~/market-live-terminal/deploy
sudo docker exec market-backend env | grep -E "INGEST_TOKEN|WRITE_API_TOKEN|ENABLE_CLOUD_COLLECTOR"
```

Windows 节点核验：
```bat
echo %INGEST_TOKEN%
echo %CLOUD_API_URL%
```
如果为空，`start_live_crawler.bat` 会直接退出。  
`CLOUD_API_URL` 生产推荐值：`http://111.229.144.202`（由 Nginx 80 端口反代到 backend），不要写成 `:8000`。

### 目的 A：发版到云端 (腾讯云 FastAPI + Web)
腾讯云运行的主程序通过 Docker 承载。为了避免手工敲一大堆 Docker 构建命令，我们已经封装了完全的流水线。

1. **提交代码核心库**：
   ```bash
   git add .
   git commit -m "feat: added new indicator"
   git push origin main
   ```
2. **触发无间断上线**：
   在 Mac 根目录下执行即可。底层会自动通过 SSH 登入并触发拉取和 Docker 重建。
   ```bash
   ./deploy_to_cloud.sh
   ```
3. **上线后冒烟验证（强制，默认由你手动执行）**：
   - **A. 业务冒烟（默认优先）**
     1) 打开生产首页并进入“当日分时”，确认曲线非空（不只股价线）。
     2) 在交易时段（北京时间）切换 2 只自选股，确认两只都能看到最新分时与逐笔。
     3) 观察“最新成交时间”是否随时间推进（建议连续看 1~2 分钟至少推进一次）。
     4) 刷新页面后再次进入“当日分时”，确认不回退为空态。
     5) 若页面显示“交易中”但分时持续空白 > 3 分钟，判定为失败。
     6) 若当前是周末/节假日/盘前，进入“当日分时”应显示回溯模式标签，且上一交易日分时图非空。
   - **B. 技术冒烟（可选补充）**
   ```bash
   # 1) 云端健康检查
   curl -s http://111.229.144.202/api/health

   # 2) 写接口未带 token 必须拒绝（401/503 任一即为护栏生效）
   curl -s -o /tmp/w_no_token.json -w "%{http_code}\n" -X POST "http://111.229.144.202/api/config" \
     -H "Content-Type: application/json" \
     -d '{"key":"large_threshold","value":"200000"}'

   # 3) 写接口带 token 必须成功（200）
   curl -s -o /tmp/w_with_token.json -w "%{http_code}\n" -X POST "http://111.229.144.202/api/config" \
     -H "Content-Type: application/json" \
     -H "X-Write-Token: ${WRITE_API_TOKEN}" \
     -d '{"key":"large_threshold","value":"200000"}'

   # 4) ingest token 错误必须拒绝（401）
   curl -s -o /tmp/i_bad.json -w "%{http_code}\n" -X POST "http://111.229.144.202/api/internal/ingest/ticks" \
     -H "Content-Type: application/json" \
     -d '{"token":"bad-token","ticks":[]}'
   ```
- **执行边界（2026-03-10 生效）**：
  - 生产环境冒烟默认由你手动执行；
  - AI 只提供“检查清单 + 预期结果 + 结果模板”，不主动直连生产执行；
  - 仅当你明确要求“代测生产”时，AI 才执行线上冒烟命令。

### 目的 B：隔空装填 Windows 洗地/抓取节点
**红线**：Windows 不受 Git 控制。绝不允许手动通过 RDP 等工具拷贝文件过去拖拽！它是一个被物理封印的黑盒主机。

只需在 Mac 根目录执行隔空输送指令：
```bash
./sync_to_windows.sh
```
该指令会在背后：
1. 使用 SCP 命令，极其蛮横地把 Mac 里刚写好的最新 Python `backend/scripts/` 文件覆盖向 Windows 的运行目录。
2. 注入开机自启的注册表批处理，让明早断电来电时它自动跑最新的爬虫逻辑。

---

## 三、 架构变动与 ADR (Architecture Decision Records) 记录法则

如果你（AI 或人类研发）在开发或诊断问题时认为需要**改变系统组件物理位置、改变大纲数据流向**（如：提出要在前端直连某新 API、或提出更换数据库引擎）：
1. 必须查阅 `01_SYSTEM_ARCHITECTURE.md` 确认是否触碰物理红线。
2. 在获得批准变更后，**强制要求你主动在项目根目录 / 文档库中新增或修改架构记录**，清晰写明：`变更前 -> 变更后 -> 变更原因 (Why)`。不能让未来的接替者去猜你的修改动机！

---

## 四、 SQLite 数据库同步与覆盖

### 4.1 云端→本地同步（日常开发用）
本地开发前，使用 `sync_cloud_db.sh` 从云端拉取生产库的只读副本：
```bash
./sync_cloud_db.sh
```
> 底层使用 **rsync 增量同步**（`-avz --progress --partial`）。首次拉取 ~1.67GB 需要较长时间，后续只传差异块，通常 **几十秒** 完成。

### 4.2 历史 ETL 数据合并上云
Windows ETL 产出的 `market_data_history.db` 需要合并到云端生产库：
```bash
# 1. 从 Windows 拉取 ETL 产出库
scp laqiyuan@100.115.228.56:D:/market-live-terminal/market_data_history.db ./data/

# 2. 上传到云端并执行 merge
scp data/market_data_history.db ubuntu@111.229.144.202:~/market-live-terminal/data/
ssh ubuntu@111.229.144.202 "cd ~/market-live-terminal && python3 backend/scripts/merge_historical_db.py"

# 3. 验证合并结果
ssh ubuntu@111.229.144.202 "sqlite3 ~/market-live-terminal/data/market_data.db 'SELECT count(DISTINCT date) FROM local_history'"
```

### 4.3 盘后 L2 正式历史上云原则（设计冻结）
- 云端正式持久化只接收：
  - `history_5m_l2`
  - `history_daily_l2`
  - 回补状态表
- 云端不接收：
  - 原始 `逐笔成交.csv`
  - 原始 `逐笔委托.csv`
  - 原始 `行情.csv`
- 写入语义：
  - 以交易日为单位覆盖写；
  - 同一 `symbol + trade_date` 重跑必须覆盖旧值，而不是追加。

### 4.4 本地验证盘后 L2 历史切换（Phase 3 smoke）
```bash
# 1) 把某一天盘后日包整理成统一结构
#    D:\\MarketData\\202603\\20260311\\000833.SZ\\{行情.csv,逐笔成交.csv,逐笔委托.csv}

# 2) 执行单日回补（示例：本地 SQLite）
python3 backend/scripts/l2_daily_backfill.py \
  "/tmp/manual_l2_day/202603/20260311" \
  --symbols sz000833 \
  --db-path /tmp/manual_l2_test.db \
  --json

# 3) 验证正式表已落库
sqlite3 /tmp/manual_l2_test.db "select count(*) from history_5m_l2;"
sqlite3 /tmp/manual_l2_test.db "select count(*) from history_daily_l2;"

# 4) 启动后端并检查接口
DB_PATH=/tmp/manual_l2_test.db USER_DB_PATH=/tmp/manual_l2_user.db python3 -m backend.app.main
curl "http://127.0.0.1:8000/api/history/trend?symbol=sz000833&days=5&granularity=30m"
curl "http://127.0.0.1:8000/api/history_analysis?symbol=sz000833"
```
预期：
- `history/trend` 返回 `source=l2_history` 的历史趋势；
- `history_analysis` 返回 `date=2026-03-11` 且 `source=l2_history`；
- 这意味着第二天在本地打开页面时，`2026-03-11` 已能看到基于 L2 派生的正式历史结果。

补充：
- 若要验证盯盘页“历史分时日期回溯”，可再执行：
```bash
curl "http://127.0.0.1:8000/api/realtime/dashboard?symbol=sz000833&date=2026-03-11"
```
- 预期返回：
  - `source=l2_history`
  - `bucket_granularity=5m`
  - `chart_data` 非空

---

## 五、 版本号管理与 Git 分支规范

### 5.1 版本号格式 (Semantic Versioning)
```
格式: MAJOR.MINOR.PATCH （如 4.1.0）
- MAJOR: 架构级变更（v3→v4 分布式重构）
- MINOR: 功能新增或 UI 重大改版
- PATCH: Bug 修复、文档更新
```

### 5.2 版本号更新流程
1. 修改 `package.json` → `version` 字段
2. 修改 `src/version.ts` → `APP_VERSION` 常量 + `RELEASE_NOTES` 首位添加说明
3. 修改 `README.md` 标题版本（如 `# ...（vX.Y.Z）`）
4. 执行版本一致性核对（至少核对下列 3 处完全一致）：
   - `package.json` `version`
   - `src/version.ts` `APP_VERSION`
   - `README.md` 标题版本
5. `git commit -m "release: vX.Y.Z"`
6. `git tag vX.Y.Z && git push origin main --tags`

### 5.3 Git 分支命名规范
```
main                    # 唯一主干，始终可部署到云端
feature/v4.x-描述       # 功能开发分支，完成后合并删除
hotfix/简短描述         # 紧急修复
release/vX.Y.Z         # 发版准备（如需要冻结测试）
```

> **红线**：GitHub 上只保留 `main` + 版本 Tag。功能分支合并后必须删除。

---

## 六、 AI 协作与测试闭环铁则 (E2E Testing Protocol)


为了杜绝“脚本跑通即宣布胜利”引发的**假性成功**（如：脚本无报错但数据未合入库，导致前端图表依旧无数据），所有协助本项目的 AI 必须将以下测试思想刻入底层：

1. **终端受控目标验证 (End-to-End Objective Verification)**
   - 任何涉及功能变更或 Bug 修复的任务，其验收红线绝不仅是“中间产物（如某个 DB 或 JSON 文件）生成成功”。
   - 验收红线必须是：**系统最末端（通常是 Web UI 或 API 最终 JSON 响应）能够完美展现预期的形态**。例如：修了后端数据处理，就必须模拟发送 HTTP 请求，肉眼/脚本核对返回的图表数值是否符合商业逻辑。
2. **禁止依赖运行日志 (No Logs as Proof)**
   - `[+] SUCCESS`，`Merged 11072 rows` 此类日志不代表最终胜利。你必须**主动执行交叉验证**。
   - 数据入库后，必须针对数据库的极限时间戳、零值、边界条件写一条额外的 `SELECT` 验证语料；API 修改后，必须利用 `curl` 针对端点跑一发探查。
3. **每次研发强制带测 (Test-Driven Mindset)**
   - **以后每一项新功能开发工作流中，最后一步都被强制绑定为“测试（Testing）阶段”**。
   - 在向用户请求 Check/Review 前，必须主动出示一条客观的验证数据链（例如，“我刚获取了前端索要该股票 K 线图的 API 接口数据，截取了最新的收盘价，确认数据已经连贯”）。

---

## 七、 Bug 修复验证流程（推荐默认流程）

用于后续“先修 bug，再验证流程”的统一执行顺序：

1. **建任务与需求定位**  
   - 先在 `docs/changes/` 建立变更卡（遵循 `06_CHANGE_MANAGEMENT.md`）。  
   - 登记 `Task ID`（`CHG-YYYYMMDD-序号`），在 `02_BUSINESS_DOMAIN.md` 对应 CAP 卡写“拟变更点”。
2. **做最小改动并本地验证**  
   - 后端：至少覆盖 1 条目标接口 `curl` 或测试用例。  
   - 前端：至少覆盖 1 条目标视图状态（正常/边界/异常其一）。
3. **Windows 依赖判定**  
   - 若变更涉及 ETL/回传/Windows 采集，先执行“一.1 连接抖动快速判定”。  
   - 任一失败直接转 `07_PENDING_TODO.md`，不得继续大文件回传或 merge。
4. **发布与冒烟**  
   - 按“二、发版与一键装填协议”上线。  
   - 由你手动执行“目的 A”中的 4 条强制冒烟检查（AI 仅提供清单模板与结果汇总）。
5. **文档回填与交接**  
   - 更新 `02/03/04`（按是否涉及业务/契约/SOP）。  
   - 在 `AI_HANDOFF_LOG.md` 记录短日志；有阻塞则同步 `07_PENDING_TODO.md`。
   - 将完成的变更卡归档到 `docs/archive/changes/`（命名遵循 `ARCHIVE_NAMING_STANDARD`）。
