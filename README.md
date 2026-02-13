# ZhangData 金融实时终端 (v2.8.0)

> **⚠️ 重要声明**: 本项目面向中文用户，所有文档、注释、Commit Message 必须使用 **中文** 编写。
> **Strict Rule**: All documentation and comments must be written in Chinese.

## 1. 项目简介
**ZhangData** 是一个本地部署的金融数据终端，专注于 A 股市场的 **主力资金流向监控** 与 **微观博弈分析**。

通过结合 React 前端的实时可视化能力与 Python 后端的复杂计算能力，本系统解决了传统网页无法进行深度历史回溯和高频 tick 级分析的痛点。

### 核心功能
*   **实时资金博弈**: 秒级监控主力买入/卖出，识别“超大单”动向。
*   **微观听诊器**: 基于腾讯 Level-1 快照推演主力操盘手法（冰山压单、虚假撤单）。
*   **散户情绪分析**: 爬取股吧评论，利用 LLM (AI) 生成市场舆情摘要。

## 2. 快速开始 (Quick Start)

### 环境要求
*   Node.js 18+
*   Python 3.9+
*   SQLite (无需安装，内置)

### 启动命令
你需要打开两个终端窗口，分别启动后端和前端。

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
```
访问浏览器: `http://localhost:3001`

## 3. 文档导航 (Documentation)

为了方便交接与维护，本项目建立了完整的文档体系，请在开发前详细阅读：

*   📚 **[业务逻辑说明书 (Business Logic)](docs/BUSINESS_LOGIC.md)**
    *   **必读**。解释了什么是“主力资金”、“净流入”、“冰山单”等核心概念。
*   🏗️ **[系统架构设计 (Architecture)](docs/ARCHITECTURE.md)**
    *   解释了前后端交互流程、数据流向设计。
*   💾 **[数据库字典 (Database Schema)](docs/DATABASE_SCHEMA.md)**
    *   详细的 SQLite 表结构说明。
*   🛠️ **[开发与贡献指南 (Developer Guide)](docs/DEV_GUIDE.md)**
    *   **AI 协作必读**。包含了环境搭建、测试规范 (`pytest`) 以及代码风格要求。
*   🔌 **[API 接口文档 (API Reference)](docs/API_REFERENCE.md)**
    *   后端接口定义。

## 4. 技术栈
*   **Frontend**: React 19, Vite, TailwindCSS, Recharts
*   **Backend**: FastAPI, AsyncIO, HTTPX, SQLite
*   **AI**: DeepSeek / OpenAI (用于舆情分析)

## 5. 更新日志 (Changelog)

### v2.8.0 (Latest)
*   **Feature**: **资金博弈 (Funds Game) 模块全面升级**。
    *   **Backend**: 深度解析腾讯行情快照，新增 **压单 (Ask1)**、**托单 (Bid1)** 及 **Tick量 (瞬时成交)** 的实时解析与持久化存储。
    *   **Frontend**: 优化“微观听诊器”面板，支持实时显示压托单挂单量及 Tick 成交差值。
    *   **UX**: 创新实现 **持久化趋势闪烁 (Persistent Trend Flash)**。价格上涨/下跌时，背景色会保留微弱红/绿底色，解决瞬时闪烁易遗漏的问题。
    *   **Fix**: 修复 Tick 量计算逻辑，增加当日日期过滤，彻底解决因历史脏数据导致的 Tick 量异常偏大问题。
    *   **Optimization**: 优化 Monitor 数据采集逻辑，确保高频数据在任何时间段均可强制写入，保证数据连续性。

> [查看完整更新历史 (v2.7.0 - v2.1.0)](docs/CHANGELOG.md)

## 6. 许可证
MIT License
