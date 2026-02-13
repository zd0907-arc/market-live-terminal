#!/bin/bash
set -e

echo "开始安装 Docker 环境..."

# 1. 更新系统并安装必要工具
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg lsb-release

# 2. 配置 Docker 镜像加速 (腾讯云/阿里云/网易)
# 这是解决国内下载慢的关键步骤
sudo mkdir -p /etc/docker
cat <<EOF | sudo tee /etc/docker/daemon.json
{
  "registry-mirrors": [
    "https://mirror.ccs.tencentyun.com",
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com"
  ]
}
EOF

# 3. 使用官方脚本安装 Docker (指定阿里云镜像源加速安装过程)
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh --mirror Aliyun

# 4. 启动 Docker 并设置开机自启
sudo systemctl enable docker
sudo systemctl start docker

# 5. 将当前用户加入 docker 组 (免 sudo 使用 docker)
sudo usermod -aG docker $USER

# 6. 安装 Docker Compose (如果脚本没装的话，通常现在都包含在 docker-compose-plugin 中了)
sudo apt-get install -y docker-compose-plugin

echo "=========================================="
echo "Docker 安装完成！"
echo "请执行 'newgrp docker' 或重新登录 SSH 以使权限生效。"
echo "=========================================="
