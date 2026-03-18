#!/bin/bash

# ==============================================================================
# ZhangData - Mac to Windows 遥控部署与安装向导
# ==============================================================================
# 目标：将最新实时 crawler 脚本与计划任务注册器同步到 Windows，
#       并自动重建正式计划任务（开机启动 + 每5分钟重复触发）。
# ==============================================================================

set -euo pipefail

WIN_IP="100.115.228.56"
WIN_USER="laqiyuan"
WIN_BASE_DIR="D:\market-live-terminal"

REMOTE_POWERSHELL="powershell -NoProfile -ExecutionPolicy Bypass"

echo "========================================================"
echo " 📡 正在建立 Mac -> Windows 的超空间传送通道..."
echo "========================================================"

echo "[1/4] 准备 Windows 目录结构..."
ssh ${WIN_USER}@${WIN_IP} "if not exist \"${WIN_BASE_DIR}\\backend\\scripts\" mkdir \"${WIN_BASE_DIR}\\backend\\scripts\" && if not exist \"${WIN_BASE_DIR}\\ops\" mkdir \"${WIN_BASE_DIR}\\ops\" && if not exist \"${WIN_BASE_DIR}\\.run\" mkdir \"${WIN_BASE_DIR}\\.run\" && if exist \"${WIN_BASE_DIR}\\ops\\win_ensure_live_crawler.ps1\" del /f /q \"${WIN_BASE_DIR}\\ops\\win_ensure_live_crawler.ps1\""

echo "[2/4] 同步 crawler / task 注册脚本..."
scp backend/scripts/live_crawler_win.py ${WIN_USER}@${WIN_IP}:${WIN_BASE_DIR}/backend/scripts/
scp start_live_crawler.bat ${WIN_USER}@${WIN_IP}:${WIN_BASE_DIR}/
scp ops/win_register_live_crawler_tasks.ps1 ${WIN_USER}@${WIN_IP}:${WIN_BASE_DIR}/ops/

echo "[3/4] 在 Windows 上重建正式计划任务..."
ssh ${WIN_USER}@${WIN_IP} "${REMOTE_POWERSHELL} -File \"${WIN_BASE_DIR}\\ops\\win_register_live_crawler_tasks.ps1\""

echo "[4/4] 返回当前计划任务状态..."
ssh ${WIN_USER}@${WIN_IP} "cmd /c schtasks /Query /TN ZhangDataLiveCrawler /V /FO LIST"

echo "========================================================"
echo "✅ Windows 实时 crawler 已同步，正式计划任务已重建。"
echo "   - ZhangDataLiveCrawler : 开机启动 + 每5分钟重复触发 (SYSTEM, IgnoreNew)"
echo "========================================================"
