# 开发指南 (Development Guide)

## 环境要求
- **Node.js**: v18 或更高版本
- **Python**: v3.9 或更高版本

## 快速启动

### 1. 启动后端服务
后端提供数据接口支持。

1.  进入项目根目录。
2.  安装依赖：
    ```bash
    pip install -r backend/requirements.txt
    ```
    *(注: 如果 `backend/requirements.txt` 不存在，请确保安装了 `fastapi`, `uvicorn`, `sqlalchemy`, `pydantic`)*
3.  启动服务：
    ```bash
    python -m backend.app.main
    ```
    服务启动后将监听 `http://127.0.0.1:8000`。

### 2. 启动前端服务
前端提供用户交互界面。

1.  安装依赖：
    ```bash
    npm install
    ```
2.  启动开发服务器：
    ```bash
    npm run dev
    ```
    应用将在 `http://localhost:3001` 启动。

## 常见问题排查

### "Connection Refused" (连接被拒绝)
- 确认后端服务是否正在运行，且监听端口为 **8000**。
- 检查是否有代理软件（如 VPN）拦截了 localhost 的请求。

### "Data Not Updating" (数据未更新)
- 实时数据依赖外部接口（腾讯/新浪），请确保网络连接正常。
- 历史数据通常在收盘后（15:30 以后）更新当日数据。
