# 开发与贡献指南 (Developer Guide)

欢迎参与 **ZhangData** 项目开发。为了确保项目的长期可维护性与 AI 协作效率，请严格遵守以下规范。

## 1. 快速启动 (Quick Start)

### 1.1 环境准备
*   **Python**: 3.9+
*   **Node.js**: 18+
*   **SQLite**: 3.x (系统自带即可)

### 1.2 启动服务
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
# 服务运行在 http://localhost:3001
```

---

## 2. AI 协作规范 (AI Co-pilot Rules)

**🤖 致 AI 助手**: 当你在本项目中编写代码时，必须遵守以下铁律。

### 2.1 语言规范
*   **文档**: 必须使用 **中文**。
*   **注释**: 核心逻辑必须有 **中文注释**。
*   **变量名**: 使用标准的英文驼峰命名 (Frontend) 或下划线命名 (Backend)。

### 2.2 代码质量 "三不准"
1.  **不准使用魔术数字 (No Magic Numbers)**:
    *   ❌ `parts[3]`
    *   ✅ `parts[TencentSource.PRICE]`
2.  **不准破坏数据库配置**:
    *   修改 DB 连接逻辑时，必须保留 `ensure_wal_mode()` 调用，确保并发安全。
3.  **不准裸奔提交**:
    *   修改核心算法（如 `monitor.py` 或 `analysis.py`）后，必须运行测试。

### 2.3 领域知识
在开始工作前，请务必阅读：
*   [业务逻辑说明书](./BUSINESS_LOGIC.md) (理解什么是主力、冰山单)
*   [数据库字典](./DATABASE_SCHEMA.md) (理解表结构)

---

## 3. 测试指南 (Testing)

本项目使用 `pytest` 进行后端单元测试。

### 3.1 运行测试
```bash
cd backend
python -m pytest
```

### 3.2 编写新测试
在 `backend/tests/` 目录下创建 `test_*.py` 文件。
*   **原则**: 每修复一个 Bug，必须增加一个复现该 Bug 的测试用例。

---

## 4. 目录结构说明

```text
market-live-terminal/
├── src/                  # 前端 (React)
│   ├── components/       # UI 组件
│   └── services/         # API 调用层
├── backend/              # 后端 (FastAPI)
│   ├── app/
│   │   ├── services/     # 核心业务逻辑 (monitor.py, analysis.py)
│   │   ├── routers/      # API 路由
│   │   └── db/           # 数据库操作
│   └── tests/            # 单元测试
└── docs/                 # 项目文档
```
