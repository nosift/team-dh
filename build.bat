@echo off
REM Docker 构建脚本 (Windows)

echo 🐳 开始构建 ChatGPT Team 兑换码系统 Docker 镜像...

REM 检查Docker是否安装
docker --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 错误: 未安装Docker
    exit /b 1
)

REM 镜像名称和标签
set IMAGE_NAME=team-dh
set VERSION=%1
if "%VERSION%"=="" set VERSION=latest
set FULL_IMAGE_NAME=%IMAGE_NAME%:%VERSION%

echo 📦 镜像名称: %FULL_IMAGE_NAME%

REM 构建镜像
echo 🔨 开始构建...
docker build -t %FULL_IMAGE_NAME% .

REM 同时标记为latest
if not "%VERSION%"=="latest" (
    docker tag %FULL_IMAGE_NAME% %IMAGE_NAME%:latest
    echo ✅ 已标记为 %IMAGE_NAME%:latest
)

echo.
echo ✅ 构建完成!
echo.
echo 📊 镜像信息:
docker images | findstr %IMAGE_NAME%

echo.
echo 🚀 使用以下命令启动容器:
echo    docker-compose up -d
echo.
echo 或者直接运行:
echo    docker run -d -p 5000:5000 ^
echo      -v %CD%\config.toml:/data/config.toml:ro ^
echo      -v %CD%\team.json:/data/team.json:ro ^
echo      -v %CD%\data:/data ^
echo      -e DATA_DIR=/data ^
echo      -e REDEMPTION_DATABASE_FILE=/data/redemption.db ^
echo      --name team-dh ^
echo      %FULL_IMAGE_NAME%

pause
