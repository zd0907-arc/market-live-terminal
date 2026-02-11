# Market Live Terminal (智能博弈监控系统)

**ZhangData 智能博弈监控系统** 是一款专业的金融数据分析工具，专注于 A 股市场的资金流向监控与历史博弈分析。

## 📚 项目文档
详细信息请查阅 `docs/` 目录下的文档：

- **[系统设计与架构](docs/SYSTEM_DESIGN.md)**: 业务逻辑、技术栈及架构概览。
- **[API 接口文档](docs/API_REFERENCE.md)**: 端口配置 (Frontend: 3001, Backend: 8000) 及接口定义。
- **[开发指南](docs/GUIDE.md)**: 环境搭建与快速启动说明。

## 🚀 快速开始

**后端服务 (端口 8000)**
```bash
pip install -r backend/requirements.txt
python -m backend.app.main
```

**前端服务 (端口 3001)**
```bash
npm install
npm run dev
```
