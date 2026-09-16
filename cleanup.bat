@echo off
REM PyBox 清理脚本 - 清除旧容器和镜像

echo ========================================
echo   PyBox 环境清理
echo ========================================
echo.

echo [1/4] 停止并删除所有容器...
docker-compose down -v

echo.
echo [2/4] 查看当前镜像...
docker images | findstr jupyter

echo.
echo [3/4] 删除旧的 PyBox 镜像...
docker rmi jupyter-api:latest 2>nul
docker rmi jupyter-kernel:latest 2>nul

echo.
echo [4/4] 清理悬空镜像...
docker image prune -f

echo.
echo ========================================
echo   清理完成!
echo ========================================
echo.
echo 现在可以运行 start.bat 重新构建
echo.

pause
