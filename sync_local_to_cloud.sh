#!/bin/bash

# ==============================================================================
# ZhangData - 云端反爬兜底方案：本地直连抓取并同步至云端数据库
# ==============================================================================
# 说明：此脚本用于解决云服务器 IP 被东方财富等数据源封锁的情况。
# 它会在当前本地网络环境下执行爬虫，生成 SQL 包，并自动注入到云端。

SERVER_IP="111.229.144.202"
SERVER_USER="ubuntu"
PROJECT_DIR="~/market-live-terminal"

if [ "$#" -eq 0 ]; then
    echo "用法: ./sync_local_to_cloud.sh 股票代码1 [股票代码2 ...]"
    echo "示例: ./sync_local_to_cloud.sh sz000833 sz000759"
    exit 1
fi

echo "========================================================"
echo " 🌐 正在绕过云节点封锁，使用本地宽带直连东方财富 API..."
echo "========================================================"

# 1. 在本地使用 Python 抓取数据并生成 SQL 文件
python3 backend/scripts/fetch_local_data.py sync_data.sql "$@"
if [ $? -ne 0 ]; then
    echo "❌ 本地数据抓取失败，终止同步。"
    exit 1
fi

echo ""
echo "========================================================"
echo " ☁️ 数据包打包完毕，准备通过 SSH 隧道注入云端服务器..."
echo "========================================================"

# 2. 传输文件到服务器 (先传到 ubuntu 用户的 home 目录，避开 Docker 的 root 权限导致 Permission denied)
scp sync_data.sql $SERVER_USER@$SERVER_IP:~/sync_data.sql
if [ $? -ne 0 ]; then
    echo "❌ SCP 传输失败，请确认是否需要密码登录或网络连通性。"
    rm -f sync_data.sql
    exit 1
fi

# 3. 登录远程服务器并执行 SQL 导入
ssh -t $SERVER_USER@$SERVER_IP << 'EOF'
    echo "🔌 正在连线 SQLite 数据库核心..."
    cd ~/market-live-terminal/deploy
    # 容器是精简版 python 没预装 sqlite3 命令行工具，因此直接用内置的 python sqlite3 库执行 SQL 管道
    sudo docker compose exec -T backend python -c "import sys, sqlite3; conn=sqlite3.connect('data/market_data.db'); conn.executescript(sys.stdin.read()); conn.close()" < ~/sync_data.sql
    echo "✅ 云端数据库 30 分钟 K 线历史合并/覆盖完成！"
    
    # 顺手把服务器上的同步包删掉，保持整洁
    rm -f ~/sync_data.sql
    exit
EOF

# 清理本地残余文件
rm -f sync_data.sql

echo "========================================================"
echo "🚀 离线定点修复任务全流程结束！请刷新网页图表查看结果。"
echo "========================================================"
