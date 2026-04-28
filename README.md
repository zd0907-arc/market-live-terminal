# ZhangData 金融实时终端（v5.0.19）

## 项目定位
- 当前主线版本：`v5.0.19`
- 当前运行模式：**Windows 数据主站 + Mac 本地研究站 + Cloud 轻量盯盘**
- 当前唯一主工作目录：`/Users/dong/Desktop/AIGC/market-live-terminal`
- 当前项目真相总入口：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/changes/MOD-20260421-01-project-current-state-and-doc-governance-normalization.md`

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

### 4) 启动本地研究站前端
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
BACKEND_PORT=8001 FRONTEND_PORT=3001 bash ops/start_local_research_frontend.sh
```

默认访问：`http://localhost:3001`  
默认本地后端：`http://127.0.0.1:8001`

## 关键文档
- 架构：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/01_SYSTEM_ARCHITECTURE.md`
- 业务能力地图：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/02_BUSINESS_DOMAIN.md`
- 数据/接口契约入口：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/03_DATA_CONTRACTS.md`
- 运维与发版入口：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/04_OPS_AND_DEV.md`
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
6. 当前任务过程再看 `docs/changes/*`。
7. 协作追踪看 `00_AI_HANDOFF_PROTOCOL.md` + `AI_HANDOFF_LOG.md` + `07_PENDING_TODO.md`。
8. 真正开始开发前，再看 `docs/ops/development-workflow.md`。

## 核心文档编号（固定）
- `00` 协作协议，`01` 架构，`02` 需求总册，`03` 契约，`04` 运维发布，`05` 安全，`06` 变更流程，`07` 待办阻塞，`08` 文档治理。
- `09+` 不再用于核心文档编号；动态文档使用 `docs/changes/` 的类型编号体系。
- 编号冻结规则见：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/08_DOCS_GOVERNANCE.md`

## 发布与同步
- 云端发布：`/Users/dong/Desktop/AIGC/market-live-terminal/deploy_to_cloud.sh`
- Windows 脚本同步：`/Users/dong/Desktop/AIGC/market-live-terminal/sync_to_windows.sh`
- 本地离线补数上云：`/Users/dong/Desktop/AIGC/market-live-terminal/sync_local_to_cloud.sh`

## 最小自检
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
npm run check:baseline
```

## 注意事项
- `WRITE_API_TOKEN` 仅允许保留在服务端环境变量中；前端静态资源不得携带该值。
- 当前仍使用 CDN Tailwind；后续将迁移到本地构建链路。
- 后端测试与本地研究站请优先使用 `backend/requirements.txt` 对应环境，不要只装根目录精简依赖。
