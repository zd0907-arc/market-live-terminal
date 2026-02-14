# ZhangData 云端部署指南 (Deployment Guide)

本指南详细说明如何将 ZhangData 部署到腾讯云/阿里云服务器，并实现“云端数据中心 + 多端访问”的架构。

## 1. 部署架构 (Architecture)

我们采用 **Docker Compose** 进行容器化部署，确保环境的一致性。

*   **Host (宿主机)**: Ubuntu 22.04 LTS (推荐)
*   **Containers (容器)**:
    *   `market-backend`: Python FastAPI 服务，负责 API 响应和数据采集 (Monitor)。
    *   `market-frontend`: Nginx 服务，托管 React 静态页面，并作为反向代理网关。
*   **Storage (存储)**:
    *   SQLite 数据库文件挂载在宿主机 `./data/market_data.db`，确保重启不丢失数据。

## 2. 服务器初始化 (首次部署)

假设您已经购买了一台云服务器，并使用 `ssh` 登录成功。

### 2.1 拉取代码
```bash
# 回到用户主目录
cd ~

# 克隆仓库 (如果是私有仓库，需要配置 SSH Key 或输入账号密码)
git clone https://github.com/zd0907-arc/market-live-terminal.git

# 进入部署目录
cd market-live-terminal/deploy
```

### 2.2 安装 Docker 环境
我们提供了一键安装脚本，自动配置国内镜像加速（解决下载慢的问题）。

```bash
# 赋予执行权限
chmod +x setup.sh

# 执行安装 (需要 sudo 权限)
./setup.sh

# 安装完成后，建议退出 SSH 并重新登录，以使用户组权限生效
exit
# (重新 ssh login...)
```

## 3. 启动服务

```bash
cd ~/market-live-terminal/deploy

# 启动所有服务 (后台运行)
# --build 参数确保每次都重新构建镜像，应用最新代码
docker compose up -d --build
```

**验证部署：**
*   访问 `http://您的服务器IP`，应能看到前端页面。
*   查看容器状态：`docker compose ps`
*   查看后端日志：`docker compose logs -f backend`

## 4. 日常运维 (SOP)

### 4.1 更新代码 (发布新版本)
当您在本地开发完成并推送到 GitHub `main` 分支后，在服务器执行：

```bash
# 1. 进入项目目录
cd ~/market-live-terminal

# 2. 拉取最新代码
git pull origin main

# 3. 强制重建并重启服务 (推荐使用 --no-cache 避免缓存问题)
cd deploy
sudo docker compose down
sudo docker compose build --no-cache
sudo docker compose up -d
```

### 4.2 数据备份
数据库文件位于 `~/market-live-terminal/data/market_data.db`。
建议定期备份该文件：

```bash
# 备份到 backup 目录
mkdir -p ~/backup
cp ~/market-live-terminal/data/market_data.db ~/backup/market_data_$(date +%Y%m%d).db
```

### 4.3 查看运行日志
如果发现数据不更新或页面报错，请查看日志：

```bash
# 查看后端实时日志 (Ctrl+C 退出)
cd ~/market-live-terminal/deploy
docker compose logs -f backend

# 查看前端/Nginx日志
docker compose logs -f frontend
```

## 5. 故障排查与最佳实践 (Troubleshooting)

本章节汇总了 v3.0.0 上云过程中的实战经验，请务必阅读。

### 5.1 常见报错与修复

| 现象 | 可能原因 | 解决方案 |
| :--- | :--- | :--- |
| **Backend 启动失败** (`ModuleNotFoundError`) | `requirements.txt` 缺失依赖 | 本地安装的包未必都在 `requirements.txt` 中。请务必核对依赖列表，特别是 `python-dotenv`, `bs4`, `apscheduler` 等隐式依赖。 |
| **Backend 无限重启** (`no such table`) | 数据库未初始化 | 确保 `init_db()` 在 `main.py` 导入任何 routers 之前执行。Docker 纯净环境下，数据库文件是全新的，必须自动初始化表结构。 |
| **版本号不更新** | Docker 构建缓存 | Docker 默认会缓存构建层。如果代码更新了但 `Dockerfile` 没变，可能会沿用旧镜像。发布时请使用 `docker compose build --no-cache`。 |
| **图表空白 (无数据)** | 1. 休市<br>2. 未加入关注 | 后端 Monitor 服务**仅监控 Watchlist 中的股票**。搜索查看但未收藏的股票不会有实时数据。且非交易时间没有新数据产生。 |

### 5.2 安全建议
目前的部署方案直接暴露 80 端口。
1.  **Nginx 密码保护**: 建议在 `nginx.conf` 中配置 Basic Auth。
2.  **防火墙**: 在腾讯云控制台配置安全组，仅允许特定 IP 访问 80 端口。
