#!/bin/bash

# ==============================================================================
# ZhangData 金融实时终端 - 腾讯云一键发布脚本 (v3.1.0)
# ==============================================================================
# 使用说明:
# 1. 确保服务器配置了免密登录 (SSH Key)，或者在执行时按提示输入密码。
# 2. 如果您的云服务器 IP 或用户名改变，请在此处修改。
# ==============================================================================

SERVER_IP="111.229.144.202"
SERVER_USER="ubuntu"
PROJECT_DIR="~/market-live-terminal"

echo "========================================================"
echo " 🚀 准备向生产环境 ($SERVER_USER@$SERVER_IP) 发布最新版 🚀"
echo "========================================================"
echo ""

# 1. 本地状态检查 (可选，确保本地代码已经推送到 Github)
echo "🔍 检查本地代码库状态..."
UNCOMMITTED=$(git status --porcelain)
if [ -n "$UNCOMMITTED" ]; then
    echo "⚠️ 警告: 您本地还有未提交 (Uncommitted) 的更改。"
    echo "这些本机的更改不会被推送到云端。请确保您想发布的代码已经 Push 到了 Github main 分支。"
fi
echo ""

# 2. 交互式动作确认 (必须由人工审核)
echo "📋 即将在云服务器上自动执行以下指令流:"
echo "  1) cd $PROJECT_DIR                  --> 切换到项目目录"
echo "  2) git fetch && git reset --hard    --> 强制覆盖拉取 Github 最新 main 分支"
echo "  3) sudo docker compose down         --> 停止旧版后台运行的服务"
echo "  4) sudo docker compose build        --> 无缓存重新编译打包前后端"
echo "  5) sudo docker compose up -d        --> 以后台模式启动最新版系统"
echo ""

read -p "🚨 请审核部署指令，确认是否立即下发发布任务向云端投送？ [y/N]: " confirm

if [[ "$confirm" == "y" || "$confirm" == "Y" ]]; then
    echo ""
    echo "========================================================"
    echo "🌐 正在连接至云服务器 (执行过程需几分钟，请勿强制退出)..."
    echo "========================================================"
    
    # 通过 SSH 远程传送指令序列
    ssh -t $SERVER_USER@$SERVER_IP << 'EOF'
        echo "--------------------------------------------------------"
        echo "[1/4] 准备目标目录..."
        if [ ! -d "market-live-terminal" ]; then
            echo "❌ 找不到项目目录 ~/market-live-terminal 所在的初始安装环境！"
            echo "如果是首次部署，请先参考 docs/DEPLOY.md 进行极简初装。"
            exit 1
        fi
        cd market-live-terminal

        echo "[2/4] 与 Github 远端仓库强制同步..."
        git fetch --all
        git reset --hard origin/main
        
        echo "[3/4] 启动 Docker 容器微服务剥离与重建..."
        cd deploy
        sudo docker compose down
        sudo docker compose build --no-cache
        
        echo "[4/4] 重新挂载服务集群并启动守护进程..."
        sudo docker compose up -d
        
        echo "--------------------------------------------------------"
        echo "✅ 云端指令序列执行完毕！"
        exit
EOF

    # SSH 会话结束
    if [ $? -eq 0 ]; then
        echo ""
        echo "========================================================"
        echo "🎉 发布成功！最新架构已在云端挂机运行。"
        echo "🔗 请在浏览器(手机/PC通用)打开: http://$SERVER_IP"
        echo "========================================================"
    else
        echo "❌ 远程部署指令执行时发生错误，请检查服务器网络或 Docker 状态。"
    fi

else
    echo ""
    echo "⏹️ 发布提议已被人工取消。系统保持原状。"
fi
