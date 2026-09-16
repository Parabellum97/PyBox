#!/usr/bin/env bash
# PyBox 快速启动脚本 (Linux/Mac)

set -e

echo "========================================"
echo "   PyBox - Python Sandbox"
echo "========================================"
echo ""

# 检查 Docker
if ! docker info >/dev/null 2>&1; then
    echo "[ERROR] Docker 未运行,请先启动 Docker"
    exit 1
fi

echo "[1/3] 构建镜像..."
docker-compose build

echo ""
echo "[2/3] 启动服务..."
docker-compose up -d

echo ""
echo "[3/3] 等待服务就绪..."
sleep 3

until curl -s http://localhost:6811/ping >/dev/null 2>&1; do
    echo "   等待中..."
    sleep 2
done

echo ""
echo "========================================"
echo "   ✓ PyBox 已启动成功!"
echo "========================================"
echo ""
echo "   HTTP API:  http://localhost:6811"
echo "   文档:      http://localhost:6811/docs"
echo "   健康检查:  http://localhost:6811/ping"
echo ""
echo "   数据目录:  ./data"
echo "   日志查看:  docker-compose logs -f"
echo "   停止服务:  docker-compose down"
echo ""
echo "========================================"
echo ""

# 可选: 运行测试
read -p "是否运行测试? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "运行测试..."
    python3 test_api.py
fi
