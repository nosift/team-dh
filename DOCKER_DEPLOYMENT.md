# Docker 容器化部署指南

## 📦 Docker 部署概述

本指南介绍如何使用Docker容器化部署ChatGPT Team兑换码系统。

### 优势

- ✅ **一键部署** - 无需手动安装依赖
- ✅ **环境隔离** - 不影响宿主机环境
- ✅ **易于迁移** - 跨平台部署
- ✅ **快速扩展** - 支持多实例
- ✅ **版本管理** - 镜像版本控制

---

## 🔧 前置要求

### 必需软件

- Docker Engine 20.10+
- Docker Compose 2.0+ (可选,推荐)

### 安装Docker

#### Linux (Ubuntu/Debian)

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
```

#### macOS

```bash
brew install --cask docker
```

#### Windows

下载并安装 [Docker Desktop](https://www.docker.com/products/docker-desktop)

### 验证安装

```bash
docker --version
docker-compose --version
```

---

## 🚀 快速开始

### 方法1: 使用Docker Compose (推荐)

#### 1. 准备配置文件

```bash
# 复制配置文件
cp config.toml.example config.toml
cp .env.example .env

# 编辑config.toml (修改管理密码等)
nano config.toml

# 创建team.json (从 https://chatgpt.com/api/auth/session 获取)
nano team.json
```

#### 2. 启动服务

**Linux/macOS:**
```bash
chmod +x start.sh
./start.sh
```

**Windows:**
```cmd
start.bat
```

**或手动启动:**
```bash
docker-compose up -d
```

#### 3. 访问服务

- 用户兑换页面: http://localhost:5000/
- 管理后台: http://localhost:5000/admin

### 方法2: 使用Docker命令

#### 1. 构建镜像

**Linux/macOS:**
```bash
chmod +x build.sh
./build.sh
```

**Windows:**
```cmd
build.bat
```

**或手动构建:**
```bash
docker build -t team-dh:latest .
```

#### 2. 运行容器

```bash
# 创建数据目录
mkdir -p data

# 启动容器
docker run -d \
  --name team-dh \
  -p 5000:5000 \
  -v $(pwd)/config.toml:/app/config.toml:ro \
  -v $(pwd)/team.json:/app/team.json:ro \
  -v $(pwd)/data:/app/data \
  -e LOG_LEVEL=INFO \
  --restart unless-stopped \
  team-dh:latest
```

**Windows PowerShell:**
```powershell
docker run -d `
  --name team-dh `
  -p 5000:5000 `
  -v ${PWD}/config.toml:/app/config.toml:ro `
  -v ${PWD}/team.json:/app/team.json:ro `
  -v ${PWD}/data:/app/data `
  -e LOG_LEVEL=INFO `
  --restart unless-stopped `
  team-dh:latest
```

---

## 📁 目录结构

```
team-dh/
├── Dockerfile              # Docker镜像定义
├── docker-compose.yml      # Docker Compose配置
├── .dockerignore          # Docker构建忽略文件
├── .env.example           # 环境变量模板
├── .env                   # 环境变量 (自己创建)
│
├── config.toml            # 应用配置 (挂载到容器)
├── team.json              # Team凭证 (挂载到容器)
│
├── data/                  # 数据目录 (持久化)
│   └── redemption.db      # SQLite数据库
│
├── nginx/                 # Nginx配置 (可选)
│   └── nginx.conf
│
├── build.sh / build.bat   # 构建脚本
└── start.sh / start.bat   # 启动脚本
```

---

## ⚙️ 配置说明

### docker-compose.yml

```yaml
version: '3.8'

services:
  redemption-web:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "${WEB_PORT:-5000}:5000"
    volumes:
      - ./data:/app/data              # 数据持久化
      - ./config.toml:/app/config.toml:ro
      - ./team.json:/app/team.json:ro
    environment:
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
    restart: unless-stopped
```

### .env 环境变量

```env
# Web服务端口
WEB_PORT=5000

# Nginx端口
NGINX_HTTP_PORT=80
NGINX_HTTPS_PORT=443

# 日志级别
LOG_LEVEL=INFO

# 时区
TZ=Asia/Shanghai

# 管理后台密码（生产环境必填）
ADMIN_PASSWORD=your-secure-password

# Flask session 加密密钥（生产环境必填；多进程/多实例必须固定，否则登录态会随机失效）
SECRET_KEY=

# 数据目录（建议挂载到持久化卷，比如 /data 或 /app/data）
DATA_DIR=/data

# SQLite 数据库文件路径（建议放在 DATA_DIR 里，避免重启丢数据）
REDEMPTION_DATABASE_FILE=/data/redemption.db

# 兑换码并发锁占用时间（秒）
REDEMPTION_CODE_LOCK_SECONDS=120

# 反向代理信任（用于获取真实客户端 IP）
TRUST_PROXY=true

# 自动转移（按月到期后自动邀请到新 Team；不会“踢出旧 Team”）
AUTO_TRANSFER_ENABLED=false
AUTO_TRANSFER_TERM_MONTHS=1
AUTO_TRANSFER_POLL_SECONDS=300
# 是否强制踢出旧 Team 成员（需要后端接口支持；开启后若踢人失败将不会转移）
AUTO_TRANSFER_KICK_OLD_TEAM=false
# 是否自动退出旧 Team（等价于“踢出旧 Team”，只是命名更贴近业务；建议使用此变量）
AUTO_TRANSFER_AUTO_LEAVE_OLD_TEAM=false
```

### Dockerfile 分析

```dockerfile
# 多阶段构建，减小镜像体积
FROM python:3.12-slim as base
# ... 安装依赖

FROM python:3.12-slim
# ... 复制依赖和代码

# 使用非root用户运行
USER appuser

# 使用Gunicorn启动
CMD ["gunicorn", "--workers", "4", ...]
```

---

## 🔧 常用命令

### 服务管理

```bash
# 启动服务
docker-compose up -d

# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 查看日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f redemption-web

# 查看服务状态
docker-compose ps

# 进入容器
docker-compose exec redemption-web bash
```

### 镜像管理

```bash
# 构建镜像
docker-compose build

# 重新构建(不使用缓存)
docker-compose build --no-cache

# 拉取最新镜像
docker-compose pull

# 查看镜像
docker images | grep team-dh

# 删除镜像
docker rmi team-dh:latest
```

### 数据管理

```bash
# 备份数据库
docker-compose exec redemption-web cp /app/data/redemption.db /app/data/backup.db

# 导出数据库到宿主机
docker cp team-dh:/data/redemption.db ./backup/

# 恢复数据库
docker cp ./backup/redemption.db team-dh:/data/
```

### 兑换码管理

```bash
# 生成兑换码
docker-compose exec redemption-web python code_generator.py generate --team TeamA --count 10

# 查看兑换码列表
docker-compose exec redemption-web python code_generator.py list

# 查看统计
docker-compose exec redemption-web python code_generator.py stats
```

---

## 🌐 使用Nginx反向代理

### 启用Nginx

```bash
# 使用profile启动Nginx
docker-compose --profile with-nginx up -d
```

### SSL/HTTPS配置

#### 1. 准备SSL证书

```bash
mkdir -p nginx/ssl
# 将证书文件放入 nginx/ssl/
# - cert.pem (证书)
# - key.pem (私钥)
```

#### 2. 修改nginx.conf

取消注释HTTPS配置部分:

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    # ...
}
```

#### 3. 重启Nginx

```bash
docker-compose restart nginx
```

---

## 📊 监控和日志

### 查看实时日志

```bash
# 所有服务
docker-compose logs -f

# 只看Web服务
docker-compose logs -f redemption-web

# 查看最近100行
docker-compose logs --tail=100 redemption-web
```

### 健康检查

```bash
# 查看容器状态
docker ps

# 查看健康检查状态
docker inspect team-dh | grep -A 10 Health

# 手动健康检查
curl http://localhost:5000/health
```

### 资源监控

```bash
# 查看容器资源使用
docker stats team-dh

# 查看所有容器资源
docker stats
```

---

## 🔐 生产环境部署

### 1. 安全配置

**修改默认密码**
```toml
[web]
admin_password = "your-very-secure-password-here"
```

**关闭调试模式**
```toml
[web]
debug = false
```

**配置IP限流**
```toml
[redemption]
rate_limit_per_hour = 10
enable_ip_check = true
```

### 2. 使用HTTPS

```bash
# 使用Let's Encrypt获取免费证书
docker run -it --rm \
  -v /etc/letsencrypt:/etc/letsencrypt \
  certbot/certbot certonly \
  --standalone \
  -d your-domain.com
```

### 3. 设置环境变量

```bash
# 使用环境变量覆盖配置
docker-compose up -d \
  -e WEB_PORT=5000 \
  -e LOG_LEVEL=WARNING
```

### 4. 定期备份

```bash
# 创建备份脚本
cat > backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="./backups/$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR
docker cp team-dh:/data/redemption.db $BACKUP_DIR/
echo "Backup completed: $BACKUP_DIR"
EOF

chmod +x backup.sh

# 添加到crontab (每天凌晨2点备份)
0 2 * * * /path/to/backup.sh
```

---

## 🐛 故障排查

### 容器无法启动

```bash
# 查看完整日志
docker-compose logs redemption-web

# 检查配置文件
docker-compose config

# 检查端口占用
netstat -tuln | grep 5000
```

### 配置文件未找到

```bash
# 检查文件挂载
docker-compose exec redemption-web ls -la /app/

# 确认配置文件存在
ls -la config.toml team.json
```

### 数据库权限问题

```bash
# 修改数据目录权限
sudo chown -R 1000:1000 data/

# 或者使用容器用户
docker-compose exec redemption-web chown -R appuser:appuser /app/data
```

### 内存不足

编辑 `docker-compose.yml` 增加内存限制:

```yaml
services:
  redemption-web:
    deploy:
      resources:
        limits:
          memory: 512M
        reservations:
          memory: 256M
```

---

## 📈 性能优化

### 1. 增加Worker数量

编辑 `Dockerfile`:

```dockerfile
CMD ["gunicorn", "--workers", "8", ...]  # 改为8个worker
```

### 2. 使用Redis缓存 (高级)

添加Redis服务到 `docker-compose.yml`:

```yaml
services:
  redis:
    image: redis:alpine
    restart: unless-stopped

  redemption-web:
    depends_on:
      - redis
    environment:
      - REDIS_URL=redis://redis:6379
```

### 3. 配置数据库连接池

修改应用代码使用连接池 (database.py)

---

## 🚢 多实例部署

### 使用Docker Swarm

```bash
# 初始化Swarm
docker swarm init

# 部署Stack
docker stack deploy -c docker-compose.yml redemption

# 扩展到3个实例
docker service scale redemption_redemption-web=3
```

### 负载均衡

Nginx配置:

```nginx
upstream redemption_cluster {
    server redemption-web-1:5000;
    server redemption-web-2:5000;
    server redemption-web-3:5000;
}
```

---

## 📦 镜像发布

### 推送到Docker Hub

```bash
# 登录Docker Hub
docker login

# 标记镜像
docker tag team-dh:latest your-username/team-dh:latest

# 推送镜像
docker push your-username/team-dh:latest
```

### 推送到私有Registry

```bash
# 标记镜像
docker tag team-dh:latest registry.example.com/team-dh:latest

# 推送
docker push registry.example.com/team-dh:latest
```

---

## 📚 更多资源

- [Docker官方文档](https://docs.docker.com/)
- [Docker Compose文档](https://docs.docker.com/compose/)
- [Dockerfile最佳实践](https://docs.docker.com/develop/develop-images/dockerfile_best-practices/)

---

## 💡 提示和技巧

1. **使用.dockerignore** - 减小构建上下文，加快构建速度
2. **多阶段构建** - 减小最终镜像体积
3. **使用特定版本标签** - 避免使用latest，便于版本管理
4. **健康检查** - 确保容器正常运行
5. **资源限制** - 防止单个容器占用过多资源
6. **定期更新** - 及时更新基础镜像和依赖

---

## 🎯 快速命令参考

```bash
# 完整部署流程
cp config.toml.example config.toml  # 1. 准备配置
nano config.toml                    # 2. 编辑配置
nano team.json                      # 3. 配置Team凭证
docker-compose up -d                # 4. 启动服务
docker-compose logs -f              # 5. 查看日志

# 日常维护
docker-compose restart              # 重启服务
docker-compose logs --tail=100 -f   # 查看日志
docker stats                        # 监控资源
docker-compose exec redemption-web python code_generator.py stats  # 查看统计

# 备份和恢复
docker cp team-dh:/data/redemption.db ./backup/  # 备份
docker cp ./backup/redemption.db team-dh:/data/  # 恢复
```

---

## ✅ 总结

通过Docker容器化部署，你可以:

- ✅ 一键启动完整服务
- ✅ 轻松迁移到不同服务器
- ✅ 快速扩展到多实例
- ✅ 隔离运行环境，提高安全性
- ✅ 简化运维管理

现在你可以开始使用Docker部署兑换码系统了！🚀
