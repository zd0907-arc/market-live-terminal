# ZhangData 金融实时终端 (v3.0.0)

> **⚠️ 重要声明**: 本项目面向中文用户，所有文档、注释、Commit Message 必须使用 **中文** 编写。
> **Strict Rule**: All documentation and comments must be written in Chinese.

## 1. 项目简介
**ZhangData** 是一个**个人私有云**金融数据终端，专注于 A 股市场的 **主力资金流向监控** 与 **微观博弈分析**。

它采用 **“云主地辅”** 的架构设计：
*   **云端 (Cloud)**: 部署在腾讯云/阿里云。后端 24 小时运行，持续监控您的“核心关注池”，积累高频历史数据。
*   **多端 (Clients)**: 支持 PC 浏览器、手机浏览器随时访问，数据实时同步。
*   **本地 (Local)**: 仅用于开发调试，拥有独立的沙盒环境。

### 核心功能
*   **实时资金博弈**: 秒级监控主力买入/卖出，识别“超大单”动向。
*   **微观听诊器**: 基于腾讯 Level-1 快照推演主力操盘手法（冰山压单、虚假撤单）。
*   **散户情绪分析**: 爬取股吧评论，利用 LLM (AI) 生成市场舆情摘要。

## 2. 快速开始 (Quick Start)

### 2.1 本地试运行 (Local Development)
如果您想在本地修改代码或体验功能：

**终端 1 (后端)**:
```bash
cd backend
pip install -r requirements.txt
python -m app.main
```

**终端 2 (前端)**:
```bash
npm install
npm run dev
# 访问 http://localhost:3001
```

### 2.2 云端部署 (Production Deployment)
如果您想在服务器上部署属于自己的 ZhangData：

请参考详细的 **[🚀 部署指南 (Deployment Guide)](docs/DEPLOY.md)**。
简而言之，只需在服务器执行：
```bash
cd deploy && ./setup.sh && docker compose up -d
```

## 3. 文档导航 (Documentation)

为了方便交接与维护，本项目建立了完整的文档体系，请在开发前详细阅读：

*   📚 **[业务逻辑说明书 (Business Logic)](docs/BUSINESS_LOGIC.md)**
    *   **必读**。解释了什么是“主力资金”、“净流入”、“冰山单”等核心概念。
*   🏗️ **[系统架构设计 (Architecture)](docs/ARCHITECTURE.md)**
    *   解释了前后端交互流程、数据流向设计。
*   💾 **[数据库字典 (Database Schema)](docs/DATABASE_SCHEMA.md)**
    *   详细的 SQLite 表结构说明。
*   🛠️ **[开发与贡献指南 (Developer Guide)](docs/DEV_GUIDE.md)**
    *   **AI 协作必读**。包含了 Git Flow 规范、环境搭建、测试规范 (`pytest`)。
*   🚀 **[部署指南 (Deployment Guide)](docs/DEPLOY.md)**
    *   服务器环境初始化、Docker 部署与日常运维手册。
*   🔌 **[API 接口文档 (API Reference)](docs/API_REFERENCE.md)**
    *   后端接口定义。

## 4. 技术栈
*   **Frontend**: React 19, Vite, TailwindCSS, Recharts
*   **Backend**: FastAPI, AsyncIO, HTTPX, SQLite
*   **Infrastructure**: Docker, Nginx, Tencent Cloud
*   **AI**: DeepSeek / OpenAI (用于舆情分析)

## 5. 更新日志 (Changelog)

### v2.8.0 (Latest)
*   **Architecture**: **云原生架构升级**。
    *   新增 Docker 部署支持 (`deploy/` 目录)。
    *   重构前端 API 配置，支持 `API_BASE_URL` 动态切换，完美适配本地/云端环境。
    *   新增 `health` 健康检查接口。
*   **Feature**: **资金博弈 (Funds Game) 模块全面升级**。
    *   **Backend**: 深度解析腾讯行情快照，新增 **压单 (Ask1)**、**托单 (Bid1)** 及 **Tick量 (瞬时成交)** 的实时解析与持久化存储。
    *   **Frontend**: 优化“微观听诊器”面板，支持实时显示压托单挂单量及 Tick 成交差值。
    *   **UX**: 创新实现 **持久化趋势闪烁 (Persistent Trend Flash)**。

> [查看完整更新历史 (v2.7.0 - v2.1.0)](docs/CHANGELOG.md)

## 6. 许可证
MIT License
