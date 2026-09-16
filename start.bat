@echo off
REM PyBox 快速启动脚本 (Windows)

echo ========================================
echo   PyBox - Python Sandbox
echo ========================================
echo.

REM 检查 Docker 是否运行
docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker 未运行,请先启动 Docker Desktop
    pause
    exit /b 1
)

echo [1/3] 构建镜像...
docker-compose build

echo.
echo [2/3] 启动服务...
docker-compose up -d

echo.
echo [3/3] 等待服务就绪...
timeout /t 5 /nobreak >nul

:check_health
curl -s http://localhost:6811/ping >nul 2>&1
if errorlevel 1 (
    echo    等待中...
    timeout /t 2 /nobreak >nul
    goto check_health
)

echo.
echo ========================================
echo   ✓ PyBox 已启动成功!
echo ========================================
echo.
echo   HTTP API:  http://localhost:6811
echo   文档:      http://localhost:6811/docs
echo   健康检查:  http://localhost:6811/ping
echo.
echo   数据目录:  .\data
echo   日志查看:  docker-compose logs -f
echo   停止服务:  docker-compose down
echo.
echo ========================================
echo.

REM 可选: 运行测试
set /p run_test="是否运行测试? (y/n): "
if /i "%run_test%"=="y" (
    echo.
    echo 运行测试...
    python test_api.py
)

pause
