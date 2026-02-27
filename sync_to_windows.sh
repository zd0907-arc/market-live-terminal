#!/bin/bash

# ==============================================================================
# ZhangData - Mac to Windows 遥控部署与安装向导
# ==============================================================================
# 目标：将 Mac 上的最新清洗脚本和开机自启程序，一键静默安装到 Windows 系统中
# ==============================================================================

WIN_IP="192.168.3.108"
WIN_USER="laqiyuan"
WIN_BASE_DIR="D:\market-live-terminal"

echo "========================================================"
echo " 📡 正在建立 Mac -> Windows 的超空间传送通道..."
echo "========================================================"
echo "[提示] 稍后可能会提示您输入 Windows 的开机密码 (可能需要输入两到三次)"

# 1. 创建目标目录结构 (防止 Windows 上目录不存在)
ssh $WIN_USER@$WIN_IP "if not exist \"$WIN_BASE_DIR\backend\scripts\" mkdir \"$WIN_BASE_DIR\backend\scripts\""

# 2. 将最新的 Python 脚本发射到 Windows 对应目录
echo ""
echo "📦 正在传送后端脚本集群 (etl_worker_win.py, live_crawler_win.py)..."
scp -r backend/scripts/* $WIN_USER@$WIN_IP:$WIN_BASE_DIR/backend/scripts/
if [ $? -ne 0 ]; then
    echo "❌ 脚本传送失败，请检查密码或网络连接。"
    exit 1
fi

# 3. 将开机自启的 BAT 脚本传送到 Windows 的主目录
echo ""
echo "⚙️ 正在传送自动唤醒雷达 (start_live_crawler.bat)..."
scp start_live_crawler.bat $WIN_USER@$WIN_IP:$WIN_BASE_DIR/
if [ $? -ne 0 ]; then
    echo "❌ 启动脚本传送失败。"
    exit 1
fi

# 4. 终极免接触：通过 SSH 在 Windows 本地将 bat 拷贝进它的隐藏启动文件夹
echo ""
echo "🚀 正在 Windows 系统底层注册开机自启任务..."
ssh $WIN_USER@$WIN_IP "copy /Y \"$WIN_BASE_DIR\start_live_crawler.bat\" \"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\\\""
if [ $? -ne 0 ]; then
    echo "❌ 自启注册失败。"
    exit 1
fi

echo ""
echo "========================================================"
echo "✅ 部署完毕！Windows 节点已升级为全自动雷达级主机！"
echo "未来每次 Windows 重启，都会在后台静默启动爬虫，您再也无需接触它。"
echo "========================================================"
