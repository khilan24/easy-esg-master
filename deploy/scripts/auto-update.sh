#!/bin/bash
# 定时自动更新：仅当远程有新提交时才拉取、安装依赖、重启服务，减少无意义重启
# 建议配合 cron 每 5 分钟执行：*/5 * * * * /home/esg/easy-esg/deploy/scripts/auto-update.sh
# 需在项目目录下运行，或设置 DEPLOY_DIR 环境变量

set -e
DEPLOY_DIR="${DEPLOY_DIR:-/home/esg/easy-esg}"
cd "$DEPLOY_DIR"

# 获取当前分支（默认 main）
BRANCH="${BRANCH:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)}"

# 拉取远程信息（不合并）
git fetch origin 2>/dev/null || exit 0

# 检查远程是否有新提交（origin/分支 有而本地没有的）
BEHIND=$(git rev-list HEAD..origin/"$BRANCH" --count 2>/dev/null || echo 0)
if [ "$BEHIND" -eq 0 ]; then
    exit 0
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 检测到 $BEHIND 个新提交，开始更新..."

git pull origin "$BRANCH"

echo "==> 激活虚拟环境并安装依赖..."
source venv/bin/activate
pip install -r requirements.txt -q

echo "==> 重启 esg-app 服务..."
sudo systemctl restart esg-app

echo "==> 完成。"
systemctl is-active --quiet esg-app && echo "服务状态: 运行中" || echo "服务状态: 异常，请检查 sudo journalctl -u esg-app -n 50"
