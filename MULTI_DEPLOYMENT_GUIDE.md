# 🚀 多种部署方式指南

本项目支持多种部署方式，适应不同的使用场景和平台需求。

---

## 📋 部署方式对比

| 方式 | 适用场景 | 优点 | 缺点 |
|------|----------|------|------|
| **仓库源码部署** | 开发测试、快速部署 | ✅ 简单快速<br>✅ 自动构建<br>✅ 易于迭代 | ⚠️ 需要平台支持 |
| **Docker镜像部署** | 生产环境、自建服务器 | ✅ 标准化<br>✅ 跨平台<br>✅ 版本控制 | ⚠️ 需要Docker知识 |
| **Docker Compose** | 本地开发、VPS部署 | ✅ 完整环境<br>✅ 易于管理<br>✅ 包含依赖 | ⚠️ 资源要求高 |

---

## 🌐 方式一：仓库源码部署

### 适用平台

- **Zeabur** (推荐) - 国内访问快，支持中文
- **Railway** - 国外平台，免费额度充足
- **Render** - 免费层可用
- **Fly.io** - 边缘计算平台

### 部署步骤

#### 1. Zeabur部署

```bash
# 前提：代码已推送到 GitHub 仓库
https://github.com/nosift/team-dh
```

**Zeabur控制台操作：**

1. 访问 [https://zeabur.com](https://zeabur.com)
2. 点击 "New Project"
3. 选择 "Deploy from GitHub"
4. 选择仓库：`nosift/team-dh`
5. 配置环境变量（可选）：
   ```
   GUNICORN_WORKERS=1
   LOG_LEVEL=INFO
   ```
6. 等待自动构建部署（2-3分钟）
7. 获得访问地址：`https://your-app.zeabur.app`

#### 2. Railway部署

```bash
# Railway CLI 方式
npm install -g @railway/cli
railway login
railway project create
railway connect
railway up
```

**Railway控制台方式：**
1. 访问 [https://railway.app](https://railway.app)
2. 连接GitHub仓库
3. 自动检测Dockerfile并部署

### 优势
- ✅ **零配置**：平台自动检测Dockerfile
- ✅ **自动更新**：git push后自动重新部署
- ✅ **内置HTTPS**：自动SSL证书
- ✅ **扩展性**：支持自动扩缩容

---

## 🐳 方式二：Docker镜像部署

### 自动构建的镜像

**GHCR 镜像地址：**
```
ghcr.io/nosift/team-dh:latest
```

每次推送到GitHub main分支时，会自动构建并推送新镜像到 GHCR。

### 使用预构建镜像

#### 1. 直接运行

```bash
# 拉取最新镜像
docker pull ghcr.io/nosift/team-dh:latest

# 运行容器（需要先准备配置文件）
docker run -d \
  --name team-dh \
  -p 5000:5000 \
  -v $(pwd)/config.toml:/app/config.toml:ro \
  -v $(pwd)/team.json:/app/team.json:ro \
  -v $(pwd)/data:/data \
  -e GUNICORN_WORKERS=2 \
  --restart unless-stopped \
  ghcr.io/nosift/team-dh:latest
```

#### 2. 使用环境变量配置

```bash
# 通过环境变量传递配置
docker run -d \
  --name team-dh \
  -p 5000:5000 \
  -e ADMIN_PASSWORD="your-secure-password" \
  -e TEAM_JSON_B64="<base64(team.json)>" \
  -e GUNICORN_WORKERS=2 \
  --restart unless-stopped \
  ghcr.io/nosift/team-dh:latest
```

### 在云平台使用镜像

#### Zeabur镜像部署

```yaml
# zeabur.yaml
version: '1'
services:
  app:
    image: ghcr.io/nosift/team-dh:latest
    environment:
      GUNICORN_WORKERS: "1"
      LOG_LEVEL: "INFO"
      ADMIN_PASSWORD: "your-secure-password"
      TEAM_JSON_B64: "<base64(team.json)>"
```

#### 其他平台

大多数支持Docker的平台都可以直接使用镜像名：
```
ghcr.io/nosift/team-dh:latest
```

---

## 🔧 方式三：Docker Compose部署

### 适用场景
- 本地开发环境
- VPS自建服务
- 需要完整环境控制

### 使用方法

#### 1. 完整部署

```bash
# 克隆仓库
git clone https://github.com/nosift/team-dh.git
cd team-dh

# 配置文件（使用模板）
cp config.toml.example config.toml
cp team.json.template team.json

# 编辑配置文件
nano config.toml  # 修改管理密码
nano team.json    # 添加Team凭证

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f
```

#### 2. 仅使用Web服务

```bash
# 启动主服务（不包含Nginx）
docker-compose up -d redemption-web
```

#### 3. 包含Nginx反向代理

```bash
# 启动完整服务栈
docker-compose --profile with-nginx up -d
```

---

## ⚙️ 高级配置

### 环境变量配置

| 变量名 | 默认值 | 说明 | 示例 |
|--------|--------|------|------|
| `PORT` | 5000 | 监听端口 | 8080 |
| `GUNICORN_WORKERS` | 2 | Worker进程数 | 1 |
| `GUNICORN_TIMEOUT` | 120 | 请求超时(秒) | 60 |
| `LOG_LEVEL` | INFO | 日志级别 | WARNING |
| `ADMIN_PASSWORD` | - | 管理员密码 | SecurePass123 |
| `TEAM_JSON_B64` | - | Team 凭证（team.json 的 base64） | ewo... |
| `TEAM_JSON` | - | Team 凭证（原始 JSON，可能需转义） | [{"user":...}] |
| `DATA_DIR` | /data | 数据目录（持久化卷挂载点） | /data |
| `REDEMPTION_DATABASE_FILE` | redemption.db | SQLite 文件路径 | /data/redemption.db |
| `ENABLE_ADMIN` | true | 是否启用管理后台 | true |

### 多版本镜像

```bash
# 使用特定版本
docker pull ghcr.io/nosift/team-dh:v1.0.0

# 使用最新版本
docker pull ghcr.io/nosift/team-dh:latest

# 使用开发版本
docker pull ghcr.io/nosift/team-dh:develop
```

### 自定义构建

```bash
# 从源码构建
git clone https://github.com/nosift/team-dh.git
cd team-dh
docker build -t my-redemption-system .

# 多平台构建
docker buildx build --platform linux/amd64,linux/arm64 -t my-redemption-system .
```

---

## 📊 性能优化建议

### 轻量级平台（Zeabur/Railway）
```
GUNICORN_WORKERS=1
LOG_LEVEL=WARNING
```

### 中等性能VPS
```
GUNICORN_WORKERS=2-4
LOG_LEVEL=INFO
```

### 高性能服务器
```
GUNICORN_WORKERS=8+
LOG_LEVEL=INFO
使用外部数据库（PostgreSQL）
添加Redis缓存
```

---

## 🔐 安全配置

### 1. 配置文件安全

**方式A：私有仓库（当前方式）**
```bash
# 配置文件在Git中，仓库必须私有
git add config.toml team.json
```

**方式B：环境变量**
```bash
# 配置通过环境变量传递，更安全
ADMIN_PASSWORD=xxx
TEAM_0_TOKEN=xxx
```

### 2. 生产环境建议

```toml
[web]
admin_password = "VerySecurePassword!2026"
debug = false

[redemption]
rate_limit_per_hour = 10
enable_ip_check = true
```

### 3. HTTPS配置

大多数云平台自动提供HTTPS。自建服务器可使用：

```bash
# 使用Nginx反向代理
docker-compose --profile with-nginx up -d

# 或配置Let's Encrypt
certbot --nginx -d your-domain.com
```

---

## 🚀 部署命令速查

### 快速开始（Zeabur）
```bash
# 1. 推送代码到GitHub
git push

# 2. 在Zeabur连接仓库
# 访问 zeabur.com → New Project → GitHub

# 3. 自动部署完成
```

### 快速开始（Docker镜像）
```bash
# 1. 准备配置文件
cat > config.toml << 'EOF'
[web]
admin_password = "your-password"
EOF

# 2. 运行容器
docker run -d -p 5000:5000 \
  -v $(pwd)/config.toml:/app/config.toml:ro \
  ghcr.io/nosift/team-dh:latest

# 3. 访问服务
open http://localhost:5000
```

### 快速开始（Docker Compose）
```bash
# 1. 克隆并配置
git clone <repo> && cd <repo>
cp config.toml.example config.toml

# 2. 启动服务
docker-compose up -d

# 3. 查看状态
docker-compose ps
```

---

## 🆘 故障排查

### 常见问题

1. **端口冲突**
   ```bash
   # 修改端口
   docker run -p 8080:5000 ...
   ```

2. **配置文件未找到**
   ```bash
   # 检查挂载
   docker exec -it container ls -la /app/
   ```

3. **内存不足**
   ```bash
   # 减少worker数量
   GUNICORN_WORKERS=1
   ```

4. **数据库权限错误**
   ```bash
   # 修复权限
   sudo chown -R 1000:1000 data/
   ```

---

## 📚 相关文档

- [轻量级平台部署详细指南](./LIGHTWEIGHT_DEPLOYMENT.md)
- [Docker部署完整指南](./DOCKER_DEPLOYMENT.md)
- [配置文件说明](./CONFIG_GUIDE.md)
- [故障排查指南](./TROUBLESHOOTING.md)

---

## 🎯 推荐方案

### 个人使用
- **平台**：Zeabur（简单快速）
- **方式**：仓库源码部署
- **配置**：私有仓库 + 配置文件提交

### 团队使用
- **平台**：Railway/Render（稳定性好）
- **方式**：仓库源码部署 + 环境变量
- **配置**：配置分离，环境变量管理

### 生产环境
- **平台**：自建VPS/云服务器
- **方式**：Docker镜像 + Docker Compose
- **配置**：完整监控、备份、安全配置

---

选择适合您需求的部署方式，开始使用吧！🚀
