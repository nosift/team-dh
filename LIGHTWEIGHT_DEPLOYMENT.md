# 轻量级平台部署指南

## 🚀 适用平台

本指南适用于以下轻量级容器部署平台：

- ✅ **Zeabur** - 推荐，支持Docker部署，自动域名
- ✅ **爪云 (Claws Cloud)** - 国内平台，速度快
- ✅ **Railway** - 国外平台，免费额度
- ✅ **Render** - 免费层可用
- ✅ **Fly.io** - 轻量级部署

---

## 📋 部署前准备

### 1. 必需文件

确保项目根目录有以下文件：

```
team-dh/
├── Dockerfile              ✅ 已优化为轻量级版本
├── docker-compose.yml      ✅ 已优化环境变量支持
├── .dockerignore          ✅ 已配置排除规则
├── config.toml            ⚠️ 需要配置
├── team.json              ⚠️ 需要配置
└── requirements.txt        ✅ 依赖已精简
```

### 2. 配置文件准备

**config.toml** - 必须修改管理密码：
```toml
[web]
admin_password = "your-secure-password"  # ⚠️ 必须修改
```

**team.json** - 从ChatGPT获取Team凭证：
1. 访问 https://chatgpt.com/api/auth/session
2. 复制返回的JSON中的以下字段：
   - `user.id`
   - `user.email`
   - `account.id`
   - `account.organizationId`
   - `accessToken`

---

## 🌟 Zeabur 部署 (推荐)

### 特点
- ✅ 支持Docker部署
- ✅ 自动分配域名
- ✅ 免费额度充足
- ✅ 中国大陆访问速度快

### 部署步骤

#### 方法1: 通过GitHub (推荐)

**1. 准备Git仓库**
```bash
# 初始化git (如果还没有)
git init
git add .
git commit -m "Initial commit"

# 推送到GitHub
git remote add origin https://github.com/your-username/your-repo.git
git push -u origin main
```

**2. 在Zeabur创建项目**
1. 访问 https://zeabur.com/
2. 登录/注册账号
3. 点击 "New Project"
4. 选择 "Deploy from GitHub"
5. 选择你的仓库

**3. 配置环境变量**

在Zeabur项目设置中添加：
```
GUNICORN_WORKERS=1
GUNICORN_TIMEOUT=120
LOG_LEVEL=INFO
```

**4. 配置注入（推荐）**

Zeabur 不支持挂载本地文件，建议使用环境变量/Secrets 注入敏感配置（无需把 `config.toml`/`team.json` 提交到仓库）：

```
ADMIN_PASSWORD=your-secure-password
TEAM_JSON_B64=<base64(team.json)>

# 可选
ENABLE_ADMIN=true
DATA_DIR=/data
REDEMPTION_DATABASE_FILE=/data/redemption.db
```

**5. 部署完成**

Zeabur会自动：
- 检测Dockerfile
- 构建Docker镜像
- 部署容器
- 分配域名 (如: `your-app.zeabur.app`)

#### 方法2: 使用Zeabur CLI

```bash
# 安装Zeabur CLI
npm i -g @zeabur/cli

# 登录
zeabur auth login

# 部署
zeabur deploy
```

### 数据持久化

Zeabur 默认不保证容器文件持久化；请在 **Volumes** 挂载一个持久化卷到 `/data`，并设置 `DATA_DIR=/data`、`REDEMPTION_DATABASE_FILE=/data/redemption.db`，避免更新镜像/重启后兑换码与 Team 信息丢失。

### 查看日志

```bash
# 在Zeabur控制台查看日志
# 或使用CLI:
zeabur logs
```

---

## 🐾 爪云 (Claws Cloud) 部署

### 特点
- ✅ 国内平台，速度快
- ✅ 简单易用
- ✅ 支持Docker

### 部署步骤

1. 访问 https://clawscloud.com/ (或对应域名)
2. 创建新应用
3. 选择 "Docker部署"
4. 上传项目文件或连接Git仓库
5. 配置环境变量 (同Zeabur)
6. 部署

---

## 🚂 Railway 部署

### 特点
- ✅ 国外平台，全球CDN
- ✅ 每月500小时免费
- ✅ 自动HTTPS

### 部署步骤

**1. 连接GitHub**
1. 访问 https://railway.app/
2. 使用GitHub登录
3. 点击 "New Project"
4. 选择 "Deploy from GitHub repo"

**2. 配置环境变量**

在Railway项目设置中添加：
```
GUNICORN_WORKERS=1
GUNICORN_TIMEOUT=120
LOG_LEVEL=INFO
PORT=5000
```

**3. 配置文件处理**

Railway不支持文件挂载，需要将配置文件提交到仓库。

**4. 生成域名**

Railway会自动分配域名，也可以绑定自定义域名。

---

## 🎨 Render 部署

### 特点
- ✅ 免费层可用
- ✅ 自动SSL
- ✅ 支持Docker

### 部署步骤

**1. 创建Web Service**
1. 访问 https://render.com/
2. 点击 "New +" → "Web Service"
3. 连接GitHub仓库

**2. 配置构建设置**
- Build Command: `docker build -t app .`
- Start Command: `gunicorn --workers 1 --bind 0.0.0.0:$PORT --timeout 120 --access-logfile - --error-logfile - web_server:app`

**3. 环境变量**
```
GUNICORN_WORKERS=1
GUNICORN_TIMEOUT=120
LOG_LEVEL=INFO
```

**4. 健康检查路径**
```
/health
```

---

## 🪰 Fly.io 部署

### 特点
- ✅ 边缘计算平台
- ✅ 全球部署
- ✅ 免费额度

### 部署步骤

**1. 安装Fly CLI**
```bash
# macOS/Linux
curl -L https://fly.io/install.sh | sh

# Windows (PowerShell)
iwr https://fly.io/install.ps1 -useb | iex
```

**2. 登录**
```bash
fly auth login
```

**3. 初始化项目**
```bash
fly launch
```

按照提示选择：
- App name: your-app-name
- Region: 选择离你最近的区域
- PostgreSQL: No (我们使用SQLite)
- Redis: No

**4. 配置环境变量**
```bash
fly secrets set GUNICORN_WORKERS=1
fly secrets set GUNICORN_TIMEOUT=120
fly secrets set LOG_LEVEL=INFO
```

**5. 部署**
```bash
fly deploy
```

**6. 查看日志**
```bash
fly logs
```

---

## ⚙️ 优化配置说明

### Dockerfile 优化要点

```dockerfile
# 1. 使用轻量级基础镜像
FROM python:3.12-slim

# 2. 多阶段构建减小体积
FROM python:3.12-slim as base
# ... build
FROM python:3.12-slim
# ... copy from base

# 3. 环境变量控制workers数量
ENV GUNICORN_WORKERS=2  # 轻量级平台建议1-2个worker

# 4. 优化健康检查 (不依赖requests库)
HEALTHCHECK CMD python -c "import urllib.request; ..."
```

### 环境变量说明

| 变量名 | 默认值 | 说明 | 推荐值 (轻量级平台) |
|--------|--------|------|---------------------|
| `GUNICORN_WORKERS` | 2 | Worker进程数量 | 1-2 |
| `GUNICORN_TIMEOUT` | 120 | 请求超时时间(秒) | 120 |
| `LOG_LEVEL` | INFO | 日志级别 | INFO |
| `PORT` | 5000 | 监听端口 | 平台自动分配 |
| `ADMIN_PASSWORD` | - | 管理后台密码 | 必填 |
| `TEAM_JSON_B64` | - | Team 凭证（team.json 的 base64） | 必填 |
| `TEAM_JSON` | - | Team 凭证（原始 JSON，可能需转义） | 可选 |
| `DATA_DIR` | /data | 数据目录（持久化卷挂载点） | /data |
| `REDEMPTION_DATABASE_FILE` | redemption.db | SQLite 路径 | /data/redemption.db |
| `ENABLE_ADMIN` | true | 是否启用后台 | true |

### 资源占用估算

- **内存**: ~150-200MB (1 worker)
- **CPU**: 0.1-0.5 core
- **存储**: ~100MB (镜像) + SQLite数据库

---

## 🔧 配置文件管理

### 方法1: 使用环境变量/Secrets（推荐）

项目已内置支持从环境变量读取 `ADMIN_PASSWORD` / `TEAM_JSON(_B64)`，更适合 Zeabur/Railway 等云平台。

### 方法2: 提交到私有仓库（不推荐）

如果你坚持使用文件方式，请确保 `config.toml` / `team.json` 会进入镜像构建上下文（检查 `.dockerignore`），并务必使用私有仓库。

### 方法3: 使用平台Secret管理 (高级)

某些平台支持Secret文件，查阅平台文档。

---

## 📊 部署后检查

### 1. 健康检查

访问：`https://your-app.example.com/health`

应该返回：
```json
{
  "status": "ok",
  "timestamp": "2026-01-05T..."
}
```

### 2. 访问管理后台

访问：`https://your-app.example.com/admin`

使用config.toml中配置的密码登录。

### 3. 测试兑换功能

1. 生成测试兑换码
2. 访问首页测试兑换流程
3. 检查数据库记录

---

## 🐛 常见问题

### 1. 容器启动失败

**原因**: 配置文件缺失或格式错误

**解决**:
```bash
# 检查config.toml格式
cat config.toml

# 检查team.json格式
cat team.json | python -m json.tool
```

### 2. 数据库权限错误

**原因**: SQLite文件权限问题

**解决**: Dockerfile已配置非root用户，确保使用最新版本。

### 3. 内存溢出

**原因**: Worker数量过多

**解决**: 设置环境变量
```
GUNICORN_WORKERS=1
```

### 4. 健康检查失败

**原因**: 启动时间过长

**解决**: 增加start_period
```dockerfile
HEALTHCHECK --start-period=10s
```

### 5. 无法访问

**原因**: 端口配置错误

**解决**: 某些平台(如Render)需要使用环境变量$PORT
```bash
--bind 0.0.0.0:${PORT:-5000}
```

---

## 🔐 安全建议

### 1. 强密码

```toml
[web]
admin_password = "VerySecureP@ssw0rd!2026"
```

### 2. HTTPS

大部分平台自动提供HTTPS，无需额外配置。

### 3. IP限流

```toml
[redemption]
rate_limit_per_hour = 10
enable_ip_check = true
```

### 4. 私有仓库

配置文件包含敏感信息，建议使用私有Git仓库。

### 5. 定期备份

```bash
# 定期导出数据库
# 通过平台CLI或API下载redemption.db文件
```

---

## 📈 性能优化

### 1. 减少Worker数量

轻量级平台资源有限，建议：
```
GUNICORN_WORKERS=1  # 单worker足够
```

### 2. 启用日志级别

生产环境使用WARNING级别：
```
LOG_LEVEL=WARNING
```

### 3. 优化镜像大小

已通过以下方式优化：
- ✅ 使用slim基础镜像
- ✅ 多阶段构建
- ✅ .dockerignore排除无用文件
- ✅ 清理pip缓存

当前镜像大小：~150MB

---

## 🚀 快速部署命令

### Zeabur (GitHub)
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/your-username/your-repo.git
git push -u origin main
# 然后在Zeabur网页选择仓库部署
```

### Railway (GitHub)
```bash
# 同Zeabur，在Railway网页选择仓库
```

### Fly.io (CLI)
```bash
fly auth login
fly launch
fly secrets set GUNICORN_WORKERS=1
fly deploy
```

### Render (GitHub)
```bash
# 推送到GitHub后在Render网页配置
```

---

## 📋 平台对比

| 平台 | 免费额度 | 国内速度 | 部署难度 | 推荐指数 |
|------|----------|----------|----------|----------|
| Zeabur | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 爪云 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Railway | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Render | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| Fly.io | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |

---

## ✅ 部署检查清单

部署前确认：

- [ ] config.toml已配置管理密码
- [ ] team.json包含有效Team凭证
- [ ] 环境变量已设置 (GUNICORN_WORKERS=1)
- [ ] Dockerfile存在且为最新版本
- [ ] .dockerignore已配置
- [ ] Git仓库已推送 (如使用GitHub部署)

部署后确认：

- [ ] /health 端点返回正常
- [ ] 可以访问管理后台
- [ ] 可以生成兑换码
- [ ] 兑换功能正常工作
- [ ] 数据持久化正常

---

## 🎯 推荐部署方案

**个人/测试使用**:
- 平台: Zeabur / Railway
- Workers: 1
- 配置: 提交到私有仓库

**小规模生产**:
- 平台: Zeabur / Railway
- Workers: 1-2
- 配置: 使用平台Secrets

**中大规模生产**:
- 建议使用VPS + Docker Compose
- 参考 DOCKER_DEPLOYMENT.md

---

## 💡 提示

1. **首次部署建议使用Zeabur** - 最简单，中文支持好
2. **配置文件使用私有仓库** - 保护敏感信息
3. **Worker数量设为1** - 轻量级平台足够
4. **定期备份数据库** - 下载redemption.db文件
5. **监控资源使用** - 查看平台控制台

---

## 📚 相关文档

- [Docker部署完整指南](./DOCKER_DEPLOYMENT.md)
- [配置文件说明](./CONFIG_GUIDE.md)
- [快速开始](./QUICK_START.md)

---

## 🆘 需要帮助？

如遇到问题：

1. 检查平台日志
2. 查看本文档"常见问题"部分
3. 参考平台官方文档
4. 提交Issue到GitHub仓库

---

**祝部署顺利！🎉**
