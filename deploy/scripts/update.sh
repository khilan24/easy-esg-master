#!/bin/bash
# 服务器端一键更新：拉取最新代码、安装依赖、重启服务
# 使用前请将 DEPLOY_DIR 改为实际项目目录，并 chmod +x update.sh
# 用法：在项目根目录执行 ./deploy/scripts/update.sh 或 bash deploy/scripts/update.sh

set -e
DEPLOY_DIR="${DEPLOY_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$DEPLOY_DIR"

echo "==> 拉取最新代码..."
git pull

echo "==> 激活虚拟环境并安装依赖..."
source venv/bin/activate
pip install -r requirements.txt -q

echo "==> 重启 esg-app 服务..."
sudo systemctl restart esg-app

echo "==> 完成。"
systemctl is-active --quiet esg-app && echo "服务状态: 运行中" || echo "服务状态: 异常，请检查 sudo journalctl -u esg-app -n 50"
