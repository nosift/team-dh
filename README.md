# Team-DH

<div align="center">

**ChatGPT Team 席位兑换码管理系统**

一个面向容器部署的 ChatGPT Team 席位分发与自动转移系统

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-brightgreen.svg)](https://www.docker.com/)

[功能特性](#-功能特性) • [快速开始](#-快速开始) • [部署指南](#-部署指南) • [配置说明](#-配置说明) • [文档](#-文档)

</div>

---

## 📖 项目简介

Team-DH 是一个功能完整的 **ChatGPT Team 席位管理系统**，提供：

- 🎫 **兑换码系统**: 生成、分发、管理兑换码，用户通过"邮箱 + 兑换码"兑换席位
- 🔄 **自动转移**: 按月自动将到期成员转移到新 Team，实现席位循环利用
- 📊 **管理后台**: 实时监控 Team 状态、兑换记录、成员租约
- 🔒 **安全可靠**: 并发锁、IP 限流、审计日志、防重复兑换
- 🐳 **云原生**: 支持 Docker、Zeabur、Railway 等容器平台

### 核心价值

- **席位复用**: 通过自动转移机制，一个席位可以服务多个用户（按月轮换）
- **三层保护**: Team 状态检测 + 异常转移 + 到期转移，确保用户始终可用 ⭐
- **灵活管理**: 支持多 Team 管理、批量生成兑换码、手动干预
- **智能监控**: 实时监控 Team 状态、席位使用率、转移失败等
- **成本优化**: 最大化 Team 席位利用率，降低运营成本
- **用户友好**: 简单的兑换流程，自动化的席位续期，无感切换

---

## ✨ 功能特性

### 兑换码管理
- ✅ 批量生成兑换码（支持自定义前缀、数量、有效期）
- ✅ 启用/禁用/删除兑换码
- ✅ 自动标记用尽状态（`used_up`）
- ✅ 支持单次/多次使用（可配置 `max_uses`）
- ✅ 兑换码锁定机制（防止并发超发）

### 兑换流程
- ✅ 邮箱格式验证
- ✅ 防重复兑换（一个邮箱只能兑换一次）
- ✅ Team 席位检查（避免超额邀请）
- ✅ IP 限流（默认 10 次/小时，可配置）
- ✅ 并发安全（数据库锁 + 应用层锁）
- ✅ 批量兑换支持（最多 20 个兑换码）

### 自动转移系统
- ✅ 按月自动转移到期成员（到期转移）
- ✅ Team 不可用时立即转移（异常转移）⭐
- ✅ 智能 Team 选择（优先最早创建的 Team）
- ✅ 自动同步用户加入时间（`joined_at`）
- ✅ 失败重试机制（指数退避）
- ✅ 手动转移/强制转移（管理后台）
- ✅ 完整审计日志（`member_lease_events`）

### 监控和告警系统 ⭐
- ✅ Team 状态定期检测（每 3 小时）
- ✅ 异常转移检测（每 30 分钟）
- ✅ Team 席位使用率监控（≥85% 警告，≥95% 严重）
- ✅ 转移失败检测和告警
- ✅ 数据库性能监控
- ✅ 系统健康检查
- ✅ 告警管理界面（查看、筛选、标记已解决）

### 管理后台
- ✅ 实时仪表板（Team 统计、兑换记录、成员租约）
- ✅ Team 管理（添加/编辑/删除 Team、状态显示）
- ✅ 兑换记录查询（支持邮箱/兑换码搜索）
- ✅ 成员租约管理（查看状态、手动转移、解绑、查看事件）
- ✅ 监控告警（实时告警、级别筛选、标记已解决）⭐
- ✅ 批量操作（删除兑换码/记录）
- ✅ 权限控制（密码认证、Session 管理）

### 数据持久化
- ✅ SQLite 数据库（无需外部数据库）
- ✅ 支持数据卷挂载（`/data`）
- ✅ 镜像更新不丢数据
- ✅ 支持数据备份/恢复

### 部署友好
- ✅ Docker 镜像（`ghcr.io/nosift/team-dh:latest`）
- ✅ 多 worker 支持（Gunicorn）
- ✅ 真实 IP 检测（支持 `Forwarded` / `X-Forwarded-For` / `X-Real-IP`）
- ✅ 配置文件自动重载（多 worker 环境）
- ✅ 健康检查端点

---

## 🚀 快速开始

### 方式一: Docker 部署（推荐）

```bash
# 1. 拉取镜像
docker pull ghcr.io/nosift/team-dh:latest

# 2. 创建数据目录
mkdir -p /path/to/data

# 3. 运行容器
docker run -d \
  --name team-dh \
  -p 5000:5000 \
  -v /path/to/data:/data \
  -e ADMIN_PASSWORD=your-secure-password \
  -e SECRET_KEY=$(openssl rand -hex 32) \
  -e DATA_DIR=/data \
  -e REDEMPTION_DATABASE_FILE=/data/redemption.db \
  -e TRUST_PROXY=true \
  ghcr.io/nosift/team-dh:latest

# 4. 访问
# 兑换页面: http://localhost:5000/
# 管理后台: http://localhost:5000/admin
```

### 方式二: 本地开发

```bash
# 1. 克隆项目
git clone https://github.com/nosift/team-dh.git
cd team-dh

# 2. 安装依赖
pip install -r requirements.txt
# 或使用 uv (推荐)
uv sync

# 3. 配置文件
cp config.toml.example config.toml
cp team.json.example team.json
# 编辑 config.toml 和 team.json，填入 Team 信息

# 4. 初始化数据库
python init_db.py

# 5. 启动服务
python web_server.py
# 或使用 Gunicorn (生产环境)
gunicorn -w 4 -b 0.0.0.0:5000 web_server:app
```

---

## 🐳 部署指南

### Zeabur 部署（推荐）

1. **创建服务**
   - 选择 "Deploy from GitHub"
   - 选择本仓库

2. **配置 Volumes**
   - 挂载路径: `/data`
   - 大小: 1GB+（根据需求调整）

3. **配置环境变量**
   ```env
   ADMIN_PASSWORD=your-secure-password
   SECRET_KEY=<random-64-hex>
   DATA_DIR=/data
   REDEMPTION_DATABASE_FILE=/data/redemption.db
   TRUST_PROXY=true
   REDEMPTION_CODE_LOCK_SECONDS=120
   AUTO_TRANSFER_ENABLED=true
   AUTO_TRANSFER_POLL_SECONDS=300
   AUTO_TRANSFER_TERM_MONTHS=1
   ```

4. **配置 Team 信息**（两种方式）

   **方式 A: 环境变量**
   ```env
   TEAM_0_TOKEN=Bearer sk-proj-...
   TEAM_0_ACCOUNT_ID=account-...
   TEAM_0_ORG_ID=org-...
   TEAM_0_NAME=TeamA

   TEAM_1_TOKEN=Bearer sk-proj-...
   TEAM_1_ACCOUNT_ID=account-...
   TEAM_1_ORG_ID=org-...
   TEAM_1_NAME=TeamB
   ```

   **方式 B: Base64 编码的 team.json**
   ```env
   TEAM_JSON_BASE64=<base64-encoded-team.json>
   ```

   生成 Base64:
   ```bash
   cat team.json | base64 -w 0
   ```

5. **部署**
   - 点击 "Deploy"
   - 等待构建完成

### Railway 部署

1. **创建项目**
   - 选择 "Deploy from GitHub repo"
   - 选择本仓库

2. **添加 Volume**
   - 挂载路径: `/data`

3. **配置环境变量**（同 Zeabur）

4. **部署**
   - Railway 会自动检测 Dockerfile 并构建

### Docker Compose 部署

```yaml
version: '3.8'

services:
  team-dh:
    image: ghcr.io/nosift/team-dh:latest
    container_name: team-dh
    ports:
      - "5000:5000"
    volumes:
      - ./data:/data
    environment:
      # 基础配置
      - ADMIN_PASSWORD=your-secure-password
      - SECRET_KEY=${SECRET_KEY}
      - DATA_DIR=/data
      - REDEMPTION_DATABASE_FILE=/data/redemption.db
      - TRUST_PROXY=true

      # 自动转移配置
      - AUTO_TRANSFER_ENABLED=true
      - AUTO_TRANSFER_TERM_MONTHS=1
      - AUTO_TRANSFER_POLL_SECONDS=300
      - AUTO_TRANSFER_AUTO_LEAVE_OLD_TEAM=true

      # 监控和保护配置（推荐启用）
      - TEAM_STATUS_CHECK_ENABLED=true
      - TEAM_STATUS_CHECK_INTERVAL=7200
      - ABNORMAL_TRANSFER_CHECK_ENABLED=true
      - ABNORMAL_TRANSFER_CHECK_INTERVAL=1800
      - MONITOR_ENABLED=true
      - MONITOR_INTERVAL=300
    restart: unless-stopped
```

启动:
```bash
docker-compose up -d
```

---

## ⚙️ 配置说明

### 核心配置

| 环境变量 | 说明 | 默认值 | 必填 |
|---------|------|--------|------|
| `ADMIN_PASSWORD` | 管理后台密码 | `admin123` | ✅ |
| `SECRET_KEY` | Session 加密密钥 | 自动生成 | ✅ (多 worker) |
| `DATA_DIR` | 数据目录 | `/data` | ❌ |
| `REDEMPTION_DATABASE_FILE` | 数据库文件路径 | `/data/redemption.db` | ❌ |
| `TRUST_PROXY` | 信任代理头（获取真实 IP） | `false` | ❌ |

### 兑换系统配置

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `REDEMPTION_CODE_LOCK_SECONDS` | 兑换码锁定时长（秒） | `120` |
| `REDEMPTION_RATE_LIMIT_PER_HOUR` | IP 限流（次/小时） | `10` |
| `REDEMPTION_CODE_PREFIX` | 兑换码前缀 | `TEAM` |

### 自动转移配置

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `AUTO_TRANSFER_ENABLED` | 启用到期转移 | `false` |
| `AUTO_TRANSFER_POLL_SECONDS` | 到期转移轮询间隔（秒） | `300` |
| `AUTO_TRANSFER_TERM_MONTHS` | 租约期限（月） | `1` |
| `AUTO_TRANSFER_AUTO_LEAVE_OLD_TEAM` | 自动离开旧 Team | `true` |
| `AUTO_TRANSFER_ALLOW_APPROX_JOIN_AT` | 允许近似加入时间 | `false` |

### 监控和保护配置 ⭐

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `TEAM_STATUS_CHECK_ENABLED` | 启用 Team 状态检测 | `true` |
| `TEAM_STATUS_CHECK_INTERVAL` | Team 状态检测间隔（秒） | `10800` (3小时) |
| `ABNORMAL_TRANSFER_CHECK_ENABLED` | 启用异常转移检测 | `true` |
| `ABNORMAL_TRANSFER_CHECK_INTERVAL` | 异常转移检测间隔（秒） | `1800` (30分钟) |
| `MONITOR_ENABLED` | 启用监控和告警 | `true` |
| `MONITOR_INTERVAL` | 监控检测间隔（秒） | `300` (5分钟) |

**三层保护机制**:
- **第一层**: Team 状态检测（每 3 小时）- 提前发现问题
- **第二层**: 异常转移（每 30 分钟）- 快速响应，确保可用
- **第三层**: 到期转移（每 5 分钟）- 周期管理，席位复用

### Team 配置

**方式 A: 环境变量**
```env
TEAM_0_TOKEN=Bearer sk-proj-...
TEAM_0_ACCOUNT_ID=account-...
TEAM_0_ORG_ID=org-...
TEAM_0_NAME=TeamA
```

**方式 B: team.json 文件**
```json
{
  "teams": [
    {
      "name": "TeamA",
      "token": "Bearer sk-proj-...",
      "account_id": "account-...",
      "org_id": "org-..."
    }
  ]
}
```

**方式 C: Base64 编码**
```env
TEAM_JSON_BASE64=<base64-encoded-team.json>
```

---

## 📚 文档

### 用户指南
- [快速开始](QUICK_START.md) - 5 分钟上手指南
- [配置指南](CONFIG_GUIDE.md) - 详细配置说明
- [兑换系统指南](REDEMPTION_GUIDE.md) - 兑换流程和 API

### 管理员指南
- [自动转移流程](AUTO_TRANSFER_FLOW.md) - 自动转移机制详解
- [Docker 部署指南](DOCKER_DEPLOYMENT.md) - Docker 部署最佳实践
- [多实例部署](MULTI_DEPLOYMENT_GUIDE.md) - 多实例/负载均衡

### 开发者指南
- [CLAUDE.md](CLAUDE.md) - 项目架构和开发日志
- [实现总结](IMPLEMENTATION_SUMMARY.md) - 技术实现细节
- [重构总结](REFACTORING_SUMMARY.md) - 代码重构记录

---

## 🔧 常用命令

### 生成兑换码
```bash
# 生成 10 个兑换码
python code_generator.py generate --team TeamA --count 10

# 查看所有兑换码
python code_generator.py list

# 启用/禁用兑换码
python code_generator.py enable <code>
python code_generator.py disable <code>

# 导出统计
python code_generator.py stats --export stats.csv
```

### 数据库操作
```bash
# 进入数据库
sqlite3 /data/redemption.db

# 查看兑换码
SELECT * FROM redemption_codes;

# 查看租约
SELECT * FROM member_leases;

# 查看事件日志
SELECT * FROM member_lease_events ORDER BY created_at DESC LIMIT 10;
```

### 手动触发转移
```bash
# 同步所有待定租约的 join_at
curl -X POST http://localhost:5000/api/admin/leases/sync \
  -H "Cookie: session=..."

# 手动转移特定邮箱
curl -X POST http://localhost:5000/api/admin/leases/transfer \
  -H "Cookie: session=..." \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com"}'
```

---

## 🛡️ 安全特性

- ✅ **并发控制**: 数据库锁 + 应用层锁，防止超发
- ✅ **IP 限流**: 防止恶意刷兑换
- ✅ **邮箱验证**: 格式校验 + 防重复兑换
- ✅ **Session 认证**: 管理后台密码保护
- ✅ **审计日志**: 完整的操作记录
- ✅ **输入验证**: 防止 SQL 注入、XSS 攻击

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

### 开发流程
1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'feat: Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request

### 提交规范
遵循 [Conventional Commits](https://www.conventionalcommits.org/):
- `feat`: 新功能
- `fix`: 修复 bug
- `docs`: 文档更新
- `style`: 代码格式
- `refactor`: 重构
- `test`: 测试
- `chore`: 构建/工具链

---

## 📝 关于"批量注册/CRS"

本仓库早期来自上游项目，代码中仍保留了一些"批量注册/CRS"等脚本文件，但 **镜像默认入口只启动兑换码系统**（`web_server:app`）。

这些旧脚本包括:
- `run.py` - 批量注册主程序
- `browser_automation.py` - Selenium 自动化
- `email_service.py` - 邮箱创建服务
- `crs_service.py` - CRS 集成

如果你不需要这些功能，可以安全地忽略它们。如果希望彻底移除，可以提交 Issue。

---

## 📄 License

本项目采用 [MIT License](LICENSE) 开源协议。

---

## 🙏 致谢

- [Flask](https://flask.palletsprojects.com/) - Web 框架
- [SQLite](https://www.sqlite.org/) - 数据库
- [OpenAI](https://openai.com/) - ChatGPT Team API

---

<div align="center">

**如果这个项目对你有帮助，请给个 ⭐️ Star！**

Made with ❤️ by Team-DH Contributors

</div>

