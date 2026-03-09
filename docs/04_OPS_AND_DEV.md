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
```
如果为空，`start_live_crawler.bat` 会直接退出。

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
3. **上线后 3 分钟冒烟验证（强制）**：
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
3. `git commit -m "release: vX.Y.Z"`
4. `git tag vX.Y.Z && git push origin main --tags`

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
   - 执行“目的 A”中的 4 条强制冒烟检查。
5. **文档回填与交接**  
   - 更新 `02/03/04`（按是否涉及业务/契约/SOP）。  
   - 在 `AI_HANDOFF_LOG.md` 记录短日志；有阻塞则同步 `07_PENDING_TODO.md`。
   - 将完成的变更卡归档到 `docs/archive/changes/`（命名遵循 `ARCHIVE_NAMING_STANDARD`）。
