# ZhangData 金融实时终端（v4.2.18）

## 项目定位
- 云端 FastAPI + 前端 Vite 的 A 股实时资金流终端。
- Windows 节点负责采集并向云端 ingest；云端是唯一权威数据源。

## 快速启动（本地）

### 1) 后端
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m backend.app.main
```

### 2) 前端
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
npm install
npm run dev
```

默认访问：`http://localhost:3001`

## 关键文档
- 架构：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/01_SYSTEM_ARCHITECTURE.md`
- 业务域：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/02_BUSINESS_DOMAIN.md`
- 数据/接口契约：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/03_DATA_CONTRACTS.md`
- 运维与发版：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/04_OPS_AND_DEV.md`
- LLM 与密钥安全：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/05_LLM_KEY_SECURITY.md`
- 变更与阶段目标流程：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/06_CHANGE_MANAGEMENT.md`
- AI 协作交接：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/00_AI_HANDOFF_PROTOCOL.md`
- 最新交接日志：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/AI_HANDOFF_LOG.md`
- 人工待办（含 Windows 离线阻塞）：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/07_PENDING_TODO.md`
- 文档治理与索引：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/08_DOCS_GOVERNANCE.md`
- 归档命名规范与映射：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/archive/ARCHIVE_NAMING_STANDARD.md`、`/Users/dong/Desktop/AIGC/market-live-terminal/docs/archive/ARCHIVE_CATALOG.md`
- 远程控制索引页：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/REMOTE_CONTROL_GUIDE.md`（步骤内容已并入 `04`）

## 文档阅读顺序（推荐）
1. 先看 `06_CHANGE_MANAGEMENT.md`（先建变更卡，再执行）。
2. 再看 `02_BUSINESS_DOMAIN.md`（业务规则与验收）。
3. 接着看 `03_DATA_CONTRACTS.md`（接口字段契约）。
4. 执行前看 `04_OPS_AND_DEV.md`（发布、冒烟、远程 gate）。
5. 协作追踪看 `00_AI_HANDOFF_PROTOCOL.md` + `AI_HANDOFF_LOG.md` + `07_PENDING_TODO.md`。

## 核心文档编号（固定）
- `00` 协作协议，`01` 架构，`02` 需求总册，`03` 契约，`04` 运维发布，`05` 安全，`06` 变更流程，`07` 待办阻塞，`08` 文档治理。
- `09+` 不再用于核心文档编号；动态文档使用 `docs/changes/` 的类型编号体系。
- 编号冻结规则见：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/08_DOCS_GOVERNANCE.md`

## 发布与同步
- 云端发布：`/Users/dong/Desktop/AIGC/market-live-terminal/deploy_to_cloud.sh`
- Windows 脚本同步：`/Users/dong/Desktop/AIGC/market-live-terminal/sync_to_windows.sh`
- 本地离线补数上云：`/Users/dong/Desktop/AIGC/market-live-terminal/sync_local_to_cloud.sh`

## 注意事项
- 根目录下存在历史遗留目录 `market-live-terminal/`（旧副本），请勿在其中开发或发版。
- 当前仍使用 CDN Tailwind；后续将迁移到本地构建链路。
