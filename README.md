# ZhangData 金融实时终端（v5.2.2）

## 项目定位
- 当前工作版本：`v5.2.2`
- 当前运行模式：**Mac 主开发控制台 + Windows 数据主站 + NAS 在线运行节点**
- 当前唯一主工作目录：`/Users/dong/Desktop/AIGC/market-live-terminal`
- 当前 Mac 正式主读数据根目录：`/Users/dong/Desktop/AIGC/market-data`
- 当前已验证 NAS 直连入口：`dxp4800pro`（Tailscale MagicDNS） / `100.119.0.126`
- 当前 NAS 局域网备用入口：`192.168.3.43`
- 当前 NAS Git 主入口：`nas-git:zhangdong/market-live-terminal.git`
- 当前临时公网入口：`https://dxp4800pro.tailfff556.ts.net/`
- repo 内 `data/` 只按本地回退/兼容副本理解，不是默认正式研究根目录
- 当前项目真相总入口：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/changes/MOD-20260421-01-project-current-state-and-doc-governance-normalization.md`
- 当前已落地核心模块：盯盘、正式复盘、选股研究工作台；当前线上运行节点是 NAS，研究页默认也按 NAS `research/current` 口径提供在线查询。
- 当前探索中能力：热点板块 / 市场热度研究；本地研究站仍是主研究工作台，NAS 线上查询能力已经打通，但盘中 crawler 切换仍处观察期。

## Mac 连接 NAS 快速入口

以后从 Mac 管 NAS，按这套顺序，不再先想 Windows：

- SSH 管理：`ssh zhangdong@dxp4800pro`
- 项目服务：`http://dxp4800pro:8080`
- Gitea：`http://dxp4800pro:3000`
- Git 提交：`git push nas main`
- 局域网备用：`192.168.3.43`

规则：

- 私网运维默认走 `dxp4800pro`
- 外部访客当前走 `https://dxp4800pro.tailfff556.ts.net/`
- 正式自定义域名仍属于 D1，后续单独通过 `Cloudflare Tunnel + 自定义域名` 收口
- 所有 `Mac <-> NAS` 协作细节统一看：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/ops/mac-nas-collaboration.md`

## 快速启动（本地）

### 1) 准备 Python / Node 依赖
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
npm install
```

### 2) 首次把 Windows 处理后全量库同步到 Mac
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
bash ops/bootstrap_mac_full_processed_sync.sh
```

### 3) 启动本地研究站后端
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
PORT=8001 bash ops/start_local_research_station.sh
```

补充：
- 这个脚本现在自带“同仓库重复实例保护”；
- 再次执行同一命令时，会先停止旧的本地后端实例，再启动新的实例；
- 不会再默默叠出多个 `backend.app.main` 进程把业务接口拖到超时。

### 4) 启动本地研究站前端
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
BACKEND_PORT=8001 FRONTEND_PORT=3001 bash ops/start_local_research_frontend.sh
```

默认访问：`http://localhost:3001`  
默认本地后端：`http://127.0.0.1:8001`

### 5) 每日盘后正式跑数
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
bash ops/run_daily_new_framework.sh --json
```

不传 `--date` 时会自动检测 Windows 已有日包中 Mac 尚未完整完成的最新日期；完整性包含市场环境指数、热点结果、热点页面缓存和选股工作台模型/策略输出。已完整的历史日期不会重复跑，早于最新完整日的历史缺口只记录在报告里。

## 关键文档
- 架构：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/01_SYSTEM_ARCHITECTURE.md`
- 业务能力地图：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/02_BUSINESS_DOMAIN.md`
- 数据/接口契约入口：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/03_DATA_CONTRACTS.md`
- 运维与发版入口：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/04_OPS_AND_DEV.md`
- Mac <-> NAS 协作入口：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/ops/mac-nas-collaboration.md`
- LLM 与密钥安全：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/05_LLM_KEY_SECURITY.md`
- 变更与阶段目标流程：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/06_CHANGE_MANAGEMENT.md`
- AI 协作交接：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/00_AI_HANDOFF_PROTOCOL.md`
- AI 快速入口：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/AI_QUICK_START.md`
- 最新交接日志：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/AI_HANDOFF_LOG.md`
- 人工待办（含 Windows 离线阻塞）：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/07_PENDING_TODO.md`
- 文档治理与索引：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/08_DOCS_GOVERNANCE.md`
- 归档命名规范与映射：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/archive/ARCHIVE_NAMING_STANDARD.md`、`/Users/dong/Desktop/AIGC/market-live-terminal/docs/archive/ARCHIVE_CATALOG.md`

## 文档阅读顺序（推荐）
1. 先看 `docs/AI_QUICK_START.md`（当前主线、目录、阅读顺序）。
2. 再看 `docs/02_BUSINESS_DOMAIN.md`（能力地图）。
3. 再看 `docs/03_DATA_CONTRACTS.md`（契约入口）。
4. 再看 `docs/04_OPS_AND_DEV.md`（运维入口）。
5. 需要细节时再下钻：
   - `docs/domain/*`
   - `docs/contracts/*`
   - `docs/ops/*`
   - Mac 直连 NAS、远程查库、发布路径优先看 `docs/ops/mac-nas-collaboration.md`
6. 当前任务过程再看 `docs/changes/*`。
7. 协作追踪看 `00_AI_HANDOFF_PROTOCOL.md` + `AI_HANDOFF_LOG.md` + `07_PENDING_TODO.md`。
8. 真正开始开发前，再看 `docs/ops/development-workflow.md`。

## 核心文档编号（固定）
- `00` 协作协议，`01` 架构，`02` 需求总册，`03` 契约，`04` 运维发布，`05` 安全，`06` 变更流程，`07` 待办阻塞，`08` 文档治理。
- `09+` 不再用于核心文档编号；动态文档使用 `docs/changes/` 的类型编号体系。
- 编号冻结规则见：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/08_DOCS_GOVERNANCE.md`

## 发布与同步
- 旧云端发布：`/Users/dong/Desktop/AIGC/market-live-terminal/deploy_to_cloud.sh`
- Windows 脚本同步：`/Users/dong/Desktop/AIGC/market-live-terminal/sync_to_windows.sh`
- 本地离线补数上云：`/Users/dong/Desktop/AIGC/market-live-terminal/sync_local_to_cloud.sh`

## Git 仓库

| Remote 名 | 地址 | 适用场景 |
|---|---|---|
| `origin` | `https://github.com/zd0907-arc/market-live-terminal.git` | GitHub 公开备份 |
| `nas` | `nas-git:zhangdong/market-live-terminal.git` | NAS 私有仓库主入口（家里/外网统一） |
| `nas-local` | `ssh://git@192.168.3.43:2222/zhangdong/market-live-terminal.git` | NAS 私有仓库局域网备用 |

推送方式：

- 推送到 GitHub：`git push origin main`
- 推送到 NAS：`git push nas main`

## 最小自检
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
npm run check:baseline
```

## 注意事项
- `WRITE_API_TOKEN` 仅允许保留在服务端环境变量中；前端静态资源不得携带该值。
- 当前仍使用 CDN Tailwind；后续将迁移到本地构建链路。
- 后端测试与本地研究站请优先使用 `backend/requirements.txt` 对应环境，不要只装根目录精简依赖。
- 若页面出现“`服务: 正常` 但历史多维 / 散户一致性观察一直转圈或超时”，先检查是否误起了多个本地后端：`ps aux | rg 'backend\\.app\\.main'`。正常应只保留 1 个实例。
