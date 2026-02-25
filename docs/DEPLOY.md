# ZhangData 云端一键发布指南 (v3.1.0+)

本指南详细说明如何将整个 AIGC 行情监控系统自动化发布到腾讯云生产服务器上。

## 🚀 推荐方式：Mac 终控端一键自动发布
为了让您专注于本地代码开发，从 v3.1.0 开始，我们在项目根目录预制了交互式自动发版脚本。您 **无需** 每次手动 SSH 进服务器去敲打构建命令。

### 第一步：确保本地代码已入库
云服务器是去 Github 上直接拉取代码的。因此请确保您在 Mac 本地的修改已经执行了 `git commit` 和 `git push origin main`。

### 第二步：在您的 Mac 本地执行脚本
直接打开您的 Mac 本地终端，进入项目根目录：
```bash
./deploy_to_cloud.sh
```

### 第三步：人工确认与自动流转
脚本会自动：
1. 拦截并向您展示本次投向腾讯云的所有 Docker 重建指令流。
2. 弹出人工授权提示：`请审核部署指令，确认是否立即下发发布任务向云端投送？ [y/N]`。
3. 输入 `y` 之后，脚本将自动发起跨网段 SSH 隧道直连，在云服务器后台强制拉取 GitHub 最新版本。
4. 自动停止旧进程，无缓存重建并重启所有微服务架构集群。
5. 出片成功并打印出访问地址 (`http://111.229.144.202`)。

---

## 🛠 如果您更喜欢传统的手动发布方式 (SOP)
（如果在您公司的网络策略中禁用了直接 SSH 登录，您可以在云端宿主机内手动执行以下步骤）

### 1. 更新代码
```bash
cd ~/market-live-terminal
git pull origin main
```

### 2. 强制重建并重启服务 (推荐使用 --no-cache)
```bash
cd deploy
sudo docker compose down
sudo docker compose build --no-cache
sudo docker compose up -d
```

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
