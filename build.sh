#!/bin/bash
# Docker 构建脚本

set -e

echo "🐳 开始构建 ChatGPT Team 兑换码系统 Docker 镜像..."

# 检查Docker是否安装
if ! command -v docker &> /dev/null; then
    echo "❌ 错误: 未安装Docker"
    exit 1
fi

# 镜像名称和标签
IMAGE_NAME="team-dh"
VERSION="${1:-latest}"
FULL_IMAGE_NAME="${IMAGE_NAME}:${VERSION}"

echo "📦 镜像名称: ${FULL_IMAGE_NAME}"

# 构建镜像
echo "🔨 开始构建..."
docker build -t "${FULL_IMAGE_NAME}" .

# 同时标记为latest
if [ "$VERSION" != "latest" ]; then
    docker tag "${FULL_IMAGE_NAME}" "${IMAGE_NAME}:latest"
    echo "✅ 已标记为 ${IMAGE_NAME}:latest"
fi

echo ""
echo "✅ 构建完成!"
echo ""
echo "📊 镜像信息:"
docker images | grep "${IMAGE_NAME}"

echo ""
echo "🚀 使用以下命令启动容器:"
echo "   docker-compose up -d"
echo ""
echo "或者直接运行:"
echo "   docker run -d -p 5000:5000 \\"
echo "     -v \$(pwd)/config.toml:/data/config.toml:ro \\"
echo "     -v \$(pwd)/team.json:/data/team.json:ro \\"
echo "     -v \$(pwd)/data:/data \\"
echo "     -e DATA_DIR=/data \\"
echo "     -e REDEMPTION_DATABASE_FILE=/data/redemption.db \\"
echo "     --name team-dh \\"
echo "     ${FULL_IMAGE_NAME}"
