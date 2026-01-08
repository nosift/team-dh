# Docker 容器化部署 - 完整实现清单

## ✅ 已完成的Docker文件

### 核心Docker文件 (4个)

1. **Dockerfile** - 多阶段构建镜像
   - 基于 Python 3.12-slim
   - 非root用户运行
   - Gunicorn生产服务器
   - 健康检查

2. **docker-compose.yml** - 容器编排
   - Web服务定义
   - Nginx反向代理(可选)
   - 数据卷挂载
   - 网络配置

3. **.dockerignore** - 构建优化
   - 排除不必要文件
   - 减小镜像体积

4. **.env.example** - 环境变量模板
   - 端口配置
   - 日志级别
   - 时区设置

### Nginx配置 (1个)

5. **nginx/nginx.conf** - 反向代理配置
   - HTTP/HTTPS支持
   - Gzip压缩
   - 静态文件缓存
   - 负载均衡

### 自动化脚本 (4个)

6. **build.sh** - Linux/macOS构建脚本
7. **build.bat** - Windows构建脚本
8. **start.sh** - Linux/macOS启动脚本
9. **start.bat** - Windows启动脚本

### 文档 (1个)

10. **DOCKER_DEPLOYMENT.md** - 完整部署文档
    - 快速开始
    - 配置说明
    - 常用命令
    - 故障排查
    - 性能优化
    - 生产部署

---

## 🚀 Docker部署特性

### ✅ 实现的功能

- [x] **多阶段构建** - 减小镜像体积
- [x] **非root用户** - 提高安全性
- [x] **Gunicorn生产服务器** - 4个worker进程
- [x] **健康检查** - 自动检测服务状态
- [x] **数据持久化** - Volume挂载数据库
- [x] **配置外部化** - 配置文件挂载
- [x] **Nginx反向代理** - 支持HTTPS
- [x] **一键启动** - 自动化脚本
- [x] **跨平台支持** - Linux/macOS/Windows
- [x] **环境变量配置** - .env文件

---

## 📦 镜像信息

### 基础镜像
```
python:3.12-slim
```

### 最终镜像
```
ghcr.io/nosift/team-dh:latest
```

### 镜像大小
- 预计大小: ~200MB (包含Python运行时 + 依赖)

### 端口
- 5000 (Web服务)
- 80/443 (Nginx, 可选)

---

## 🔧 使用方式

### 方式1: Docker Compose (推荐)

```bash
# 1. 准备配置
cp config.toml.example config.toml
nano config.toml team.json

# 2. 启动
docker-compose up -d

# 3. 访问
http://localhost:5000/
```

### 方式2: Docker命令

```bash
# 构建
docker build -t team-dh .

# 运行
docker run -d \
  -p 5000:5000 \
  -v $(pwd)/config.toml:/data/config.toml:ro \
  -v $(pwd)/team.json:/data/team.json:ro \
  -v $(pwd)/data:/data \
  -e DATA_DIR=/data \
  -e REDEMPTION_DATABASE_FILE=/data/redemption.db \
  team-dh
```

### 方式3: 一键脚本

```bash
# Linux/macOS
./start.sh

# Windows
start.bat
```

---

## 📁 目录结构

```
project/
├── Dockerfile              ← Docker镜像定义
├── docker-compose.yml      ← 容器编排配置
├── .dockerignore          ← 构建忽略
├── .env.example           ← 环境变量模板
│
├── nginx/
│   └── nginx.conf         ← Nginx配置
│
├── build.sh / build.bat   ← 构建脚本
├── start.sh / start.bat   ← 启动脚本
│
├── config.toml            ← 应用配置(挂载)
├── team.json              ← Team凭证(挂载)
│
└── data/                  ← 数据目录(持久化)
    └── redemption.db
```

---

## 🎯 部署流程

### 开发环境

```bash
1. cp config.toml.example config.toml
2. nano config.toml team.json
3. docker-compose up -d
4. 访问 http://localhost:5000
```

### 生产环境

```bash
1. 准备配置文件
2. 配置SSL证书(可选)
3. docker-compose --profile with-nginx up -d
4. 配置域名DNS
5. 访问 https://your-domain.com
```

---

## 🔐 安全配置

### 已实现的安全措施

- ✅ 非root用户运行容器
- ✅ 只读挂载配置文件
- ✅ 健康检查机制
- ✅ 资源限制(可配置)
- ✅ Nginx安全头(HTTPS模式)
- ✅ 环境变量隔离

### 建议的额外措施

- [ ] 使用HTTPS (Let's Encrypt)
- [ ] 配置防火墙规则
- [ ] 定期更新基础镜像
- [ ] 设置强管理密码
- [ ] 配置日志轮转

---

## 📊 性能配置

### Gunicorn配置

```dockerfile
--workers 4              # 4个worker进程
--timeout 120            # 120秒超时
--bind 0.0.0.0:5000     # 监听所有接口
```

### 优化建议

1. **增加Worker数** - 根据CPU核心数调整
2. **使用Nginx** - 静态文件缓存
3. **启用Gzip** - 压缩响应
4. **配置连接池** - 数据库连接复用

---

## 🛠️ 常用命令

### 服务管理
```bash
docker-compose up -d        # 启动
docker-compose down         # 停止
docker-compose restart      # 重启
docker-compose logs -f      # 查看日志
docker-compose ps           # 查看状态
```

### 数据管理
```bash
# 备份
docker cp team-dh:/data/redemption.db ./backup/

# 恢复
docker cp ./backup/redemption.db team-dh:/data/

# 生成兑换码
docker-compose exec redemption-web python code_generator.py generate --team TeamA --count 10
```

### 镜像管理
```bash
docker images                              # 查看镜像
docker rmi team-dh        # 删除镜像
docker-compose build --no-cache           # 重新构建
```

---

## 🌐 多实例部署

### 使用Docker Swarm

```bash
# 初始化
docker swarm init

# 部署
docker stack deploy -c docker-compose.yml redemption

# 扩展
docker service scale redemption_redemption-web=3
```

### 使用Kubernetes

(需要额外的k8s配置文件)

---

## 📈 监控和日志

### 查看日志
```bash
# 实时日志
docker-compose logs -f

# 最近100行
docker-compose logs --tail=100

# 导出日志
docker-compose logs > app.log
```

### 资源监控
```bash
# 实时监控
docker stats

# 查看特定容器
docker stats team-dh
```

---

## 🐛 故障排查

### 容器无法启动

```bash
# 查看日志
docker-compose logs

# 检查配置
docker-compose config

# 检查端口
netstat -tuln | grep 5000
```

### 配置文件问题

```bash
# 检查挂载
docker-compose exec redemption-web ls -la /app/

# 验证配置
docker-compose exec redemption-web cat /app/config.toml
```

### 权限问题

```bash
# 修改权限
sudo chown -R 1000:1000 data/

# 或在容器内
docker-compose exec redemption-web chown -R appuser:appuser /app/data
```

---

## 📦 镜像发布

### Docker Hub

```bash
# 登录
docker login

# 标记
docker tag team-dh:latest username/team-dh:latest

# 推送
docker push username/team-dh:latest
```

### 私有Registry

```bash
# 标记
docker tag team-dh:latest registry.example.com/team-dh:latest

# 推送
docker push registry.example.com/team-dh:latest
```

---

## 💡 最佳实践

1. ✅ 使用多阶段构建减小镜像体积
2. ✅ 非root用户运行提高安全性
3. ✅ 配置健康检查确保服务可用
4. ✅ 数据持久化避免数据丢失
5. ✅ 使用.dockerignore优化构建
6. ✅ 环境变量配置便于部署
7. ✅ Nginx反向代理提升性能
8. ✅ 定期备份数据库

---

## 🎯 总结

Docker容器化部署提供了:

- ✅ **一键部署** - 无需手动配置环境
- ✅ **环境隔离** - 不影响宿主机
- ✅ **易于迁移** - 跨平台部署
- ✅ **快速扩展** - 支持多实例
- ✅ **便于维护** - 标准化运维

现在你可以使用Docker轻松部署兑换码系统到任何服务器了！🐳🚀
