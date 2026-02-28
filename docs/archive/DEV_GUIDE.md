# 开发与贡献指南 (Developer Guide)

欢迎参与 **ZhangData** 项目开发。为了确保项目的长期可维护性与 AI 协作效率，请严格遵守以下规范。

## 1. 架构概览：云主地辅 (Cloud-Local Architecture)

本项目采用 **“本地开发，云端运行”** 的双环境架构。理解这一架构对于开发至关重要。

### 1.1 双环境对比

| 特性 | 本地环境 (Local / Dev) | 云端环境 (Cloud / Prod) |
| :--- | :--- | :--- |
| **用途** | 写代码、调试、功能验证 | 24小时监控、历史数据积累、随时访问 |
| **运行方式** | `npm run dev` + `python main.py` | `docker compose up -d` |
| **数据库** | 本地 SQLite (`market_data.db`) | 云端 SQLite (Docker Volume 挂载) |
| **数据源** | 实时拉取 API (存入本地) | 实时拉取 API (存入云端) |
| **数据同步** | **不互通**。本地只存测试数据。 | **核心数据**。包含所有历史记录。 |

### 1.2 核心原则
*   **隔离性**：本地开发绝对不要连接云端数据库，以免误删数据。
*   **一致性**：本地通过 Docker 镜像验证通过后，云端行为将与本地一致。

---

## 2. Git 工作流规范 (Git Flow)

针对个人项目，我们采用简化的 GitHub Flow。

### 2.1 分支管理
*   **`main` (生产分支)**: 🔴 **神圣不可侵犯**。
    *   对应云端正在运行的代码。
    *   仅接受来自 `develop` 的合并。
    *   **严禁直接 push 到 main**。
*   **`develop` (开发主干)**: 🟡 日常代码汇总地。
*   **`feature/xxx` (功能分支)**: 🟢 开发新功能用。
    *   例如: `feature/mobile-ui`, `feature/add-macd`.

### 2.2 开发 SOP (标准作业程序)

#### 阶段一：开发新功能
1.  **切分支**: `git checkout -b feature/new-function`
2.  **写代码**: 在本地修改，运行测试。
3.  **提交**: `git commit -m "feat: add new function"`

#### 阶段二：合并代码
1.  **切回开发分支**: `git checkout develop`
2.  **同步最新**: `git pull origin develop`
3.  **合并**: `git merge feature/new-function`
4.  **推送到远程**: `git push origin develop`

#### 阶段三：发布上线 (Deploy)
1.  **合并到主分支**:
    ```bash
    git checkout main
    git merge develop
    git push origin main
    ```
2.  **服务器更新**:
    *   登录服务器，拉取 `main` 分支，重启 Docker (详见 [部署指南](./DEPLOY.md))。

---

## 3. 快速启动 (Local Development)

### 3.1 环境准备
*   **Python**: 3.9+
*   **Node.js**: 18+
*   **SQLite**: 3.x (系统自带即可)

### 3.2 启动服务
本项目包含前后端两个服务，需分别启动：

**后端 (Terminal 1)**:
```bash
cd backend
pip install -r requirements.txt
python -m app.main
# 服务运行在 http://127.0.0.1:8000
```

**前端 (Terminal 2)**:
```bash
npm install
npm run dev
# 服务运行在 http://localhost:3001 (自动代理到后端)
```

---

## 4. AI 协作规范 (AI Co-pilot Rules)

**🤖 致 AI 助手**: 当你在本项目中编写代码时，必须遵守以下铁律。

### 4.1 语言规范
*   **文档**: 必须使用 **中文**。
*   **注释**: 核心逻辑必须有 **中文注释**。
*   **变量名**: 使用标准的英文驼峰命名 (Frontend) 或下划线命名 (Backend)。

### 4.2 代码质量 "三不准"
1.  **不准使用魔术数字 (No Magic Numbers)**:
    *   所有大单/阈值判断，必须从 SQLite `app_config` 或 `.env` 读取，严禁在代码里写死 `> 200000`。
2.  **绝对禁止使用相对路径读写核心文件 (No Relative Paths for IO)**:
    *   **历史教训**: 曾经 `os.getcwd()` 导致在不同目录下执行脚本生成多个 `market_data.db` (真假库分裂)。
    *   **法则**: Python 脚本如果需要读写 SQLite DB 或 `.env` 文件，**必须** 使用基于当前文件 `__file__` 动态向上解析 `ROOT_DIR` 的绝对路径。例如: `os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))`。
3.  **不准无声吞没空数据 (No Silent Empty States)**:
    *   **历史教训**: 前后端如果查询到 `[]` 就把图表组件整体 `display: none`，会导致开发者无法分辨是“报错闪退”还是“纯粹没数据”。
    *   **法则**:
        *   后端: 查不到数据需返回 `{"code": 200, "data": [], "message": "No data found"}` 并打印 `logger.warning`。
        *   前端: 必须展示【空状态占位图】(Empty State Placeholder)，如：“暂无数据，请检查本地数据库是否已同步云端”。
4.  **【核心血泪法则】不准在云端运行爬虫 (Cloud is Display Only)**:
    *   **历史教训**: 曾经的 AI 错误地认为“云端服务器资源多，可以直接把爬取 30 分钟 K 线图 (akshare) 的任务挂在云端后台”。结果云端的腾讯云公网 IP 被东方财富等数据源**永久封锁**，导致盘中实时数据全部断流。
    *   **法则**:
        *   云端 (Cloud/Ubuntu) 只能用来跑 FastAPI 和 Web UI，它提供接口暴露给前端，并持有最终的 `market_data.db`。它**绝对不**主动去外网抓数据。
        *   盘中的高频轮询 (每3秒/每3分钟) **必须**运行在拥有动态家宽 IP 的 Windows 或 Mac 机器上。爬取后的数据通过调用云端的 Ingestion API 或 SSH 隧道推送给云端。

### 4.3 架构变动与 ADR (Architecture Decision Records) 记录法则
如果你（AI 助手）在开发或诊断问题时认为需要**改变系统组件物理位置、改变大纲数据流向**（如：提出要在前端直连某新 API、或提出更换数据库引擎）：
1. 你必须先查阅 `/docs/ARCHITECTURE_HISTORY.md`（架构演进史）了解目前的格局原因。
2. 在获得用户批准变更后，**强制要求你主动修改** `/docs/ARCHITECTURE_HISTORY.md`，以 `[ADR-XXX]` 的格式新增一个条目，清晰写明：变更前 -> 变更后 -> 变更原因 (Why)。不能让未来的接替者去猜你的修改动机！
    *   ❌ `parts[3]`
    *   ✅ `parts[TencentSource.PRICE]`
2.  **不准破坏数据库配置**:
    *   修改 DB 连接逻辑时，必须保留 `ensure_wal_mode()` 调用，确保并发安全。
3.  **不准裸奔提交**:
    *   修改核心算法（如 `monitor.py` 或 `analysis.py`）后，必须运行测试。

### 4.3 领域知识
在开始工作前，请务必阅读：
*   [业务逻辑说明书](./BUSINESS_LOGIC.md) (理解什么是主力、冰山单)
*   [数据库字典](./DATABASE_SCHEMA.md) (理解表结构)

---

## 5. 测试指南 (Testing)

本项目使用 `pytest` 进行后端单元测试。

### 5.1 运行测试
```bash
cd backend
python -m pytest
```

### 5.2 编写新测试
在 `backend/tests/` 目录下创建 `test_*.py` 文件。
*   **原则**: 每修复一个 Bug，必须增加一个复现该 Bug 的测试用例。
