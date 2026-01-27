# Zeabur 部署指南

## 自动部署流程

### 1. GitHub 推送触发

当代码推送到 GitHub 后，Zeabur 会自动：
1. 检测到仓库更新
2. 拉取最新代码
3. 构建 Docker 镜像
4. 部署新版本

### 2. 检查部署状态

访问 Zeabur 控制台：
```
https://dash.zeabur.com
```

查看：
- **Deployments** 标签：查看部署历史和状态
- **Logs** 标签：查看构建和运行日志
- **Settings** 标签：查看环境变量配置

---

## 部署验证

### 1. 检查构建日志

在 Zeabur 控制台的 **Logs** 中查看：

```
✅ 成功标志：
[INFO] Building Docker image...
[INFO] Successfully built image
[INFO] Deploying new version...
[INFO] Deployment successful

❌ 失败标志：
[ERROR] Build failed
[ERROR] Deployment failed
```

### 2. 检查服务状态

访问你的域名：
```
https://your-domain.zeabur.app/
```

应该看到兑换页面正常显示。

### 3. 检查管理后台

访问管理后台：
```
https://your-domain.zeabur.app/admin
```

验证新功能：
- ✅ "分组管理" 标签页
- ✅ "监控告警" 标签页
- ✅ Team 统计显示创建时间
- ✅ 兑换码表格显示分组列

### 4. 检查 API

测试 API 是否正常：
```bash
# 检查健康状态
curl https://your-domain.zeabur.app/health

# 检查统计 API
curl https://your-domain.zeabur.app/api/admin/stats
```

---

## 如果自动部署失败

### 方案 1: 手动触发部署

1. 进入 Zeabur 控制台
2. 找到你的项目
3. 点击 **Redeploy** 按钮
4. 等待构建完成

### 方案 2: 检查 Webhook

1. 进入 GitHub 仓库设置
2. 点击 **Settings** → **Webhooks**
3. 检查 Zeabur webhook 状态
4. 如果显示错误，点击 **Redeliver** 重新发送

### 方案 3: 重新连接仓库

1. 在 Zeabur 控制台断开 GitHub 连接
2. 重新连接 GitHub 仓库
3. 选择 `nosift/team-dh` 仓库
4. 选择 `main` 分支
5. 保存并等待自动部署

---

## 环境变量配置

确保在 Zeabur 中配置了以下环境变量：

### 必需变量

```bash
# 管理员密码
ADMIN_PASSWORD=your-secure-password

# Session 密钥（多 worker 必须）
SECRET_KEY=your-secret-key-here

# 自动转移配置（可选）
AUTO_TRANSFER_ENABLED=true
AUTO_TRANSFER_POLL_SECONDS=300
AUTO_TRANSFER_TERM_MONTHS=1
MAX_TRANSFER_ATTEMPTS=10
```

### 可选变量

```bash
# Gunicorn 配置
GUNICORN_WORKERS=2
GUNICORN_TIMEOUT=120

# 日志级别
LOG_LEVEL=INFO

# 端口（Zeabur 会自动设置）
PORT=5000
```

---

## 数据持久化

### 1. 检查数据卷

在 Zeabur 控制台：
1. 进入 **Storage** 标签
2. 确认 `/app/data` 目录已挂载
3. 数据库文件 `redemption.db` 应该在这里

### 2. 备份数据库

定期备份数据库：

```bash
# 方法 1: 通过 Zeabur CLI
zeabur exec -- sqlite3 /app/data/redemption.db .dump > backup.sql

# 方法 2: 通过 API 导出
curl https://your-domain.zeabur.app/api/admin/export \
  -H "Cookie: session=..." \
  -o backup.json
```

### 3. 恢复数据库

如果需要恢复：

```bash
# 上传备份文件
zeabur cp backup.sql :/app/data/

# 恢复数据库
zeabur exec -- sqlite3 /app/data/redemption.db < /app/data/backup.sql
```

---

## 性能优化

### 1. Worker 数量

根据 Zeabur 套餐调整：

```bash
# 免费套餐（512MB 内存）
GUNICORN_WORKERS=1

# 基础套餐（1GB 内存）
GUNICORN_WORKERS=2

# 专业套餐（2GB+ 内存）
GUNICORN_WORKERS=4
```

### 2. 超时时间

如果有大量转移操作：

```bash
GUNICORN_TIMEOUT=180  # 增加到 3 分钟
```

### 3. 数据库优化

在管理后台执行：
```sql
-- 优化数据库
VACUUM;
ANALYZE;

-- 重建索引
REINDEX;
```

---

## 监控和日志

### 1. 查看实时日志

在 Zeabur 控制台：
```
Logs → Real-time logs
```

### 2. 查看错误日志

筛选错误：
```
Logs → Filter: ERROR
```

### 3. 监控告警

访问管理后台：
```
https://your-domain.zeabur.app/admin
→ 监控告警标签页
```

查看：
- Team 容量告警
- 转移失败告警
- 数据库性能告警

---

## 故障排查

### 问题 1: 部署失败

**症状**: 构建失败或部署失败

**排查步骤**:
1. 查看 Zeabur 构建日志
2. 检查 Dockerfile 语法
3. 验证 requirements.txt

**解决方案**:
```bash
# 本地测试构建
docker build -t team-dh:test .
docker run -p 5000:5000 team-dh:test
```

### 问题 2: 服务无法访问

**症状**: 域名无法访问或 502 错误

**排查步骤**:
1. 检查服务是否运行
2. 查看运行日志
3. 检查端口配置

**解决方案**:
- 确认 `PORT` 环境变量正确
- 检查健康检查是否通过
- 重启服务

### 问题 3: 数据库错误

**症状**: "database is locked" 或其他数据库错误

**排查步骤**:
1. 检查数据卷是否正常挂载
2. 查看数据库文件权限
3. 检查并发连接数

**解决方案**:
```bash
# 检查数据库
zeabur exec -- sqlite3 /app/data/redemption.db "PRAGMA integrity_check;"

# 优化数据库
zeabur exec -- sqlite3 /app/data/redemption.db "VACUUM;"
```

### 问题 4: 新功能不显示

**症状**: 推送代码后新功能没有出现

**排查步骤**:
1. 确认代码已推送到 GitHub
2. 检查 Zeabur 是否自动部署
3. 清除浏览器缓存

**解决方案**:
```bash
# 1. 确认 GitHub 最新提交
git log -1

# 2. 手动触发部署
# 在 Zeabur 控制台点击 Redeploy

# 3. 清除浏览器缓存
# Ctrl+Shift+R (Windows/Linux)
# Cmd+Shift+R (Mac)
```

---

## 版本回滚

如果新版本有问题，可以回滚：

### 方法 1: 通过 Zeabur 控制台

1. 进入 **Deployments** 标签
2. 找到之前的稳定版本
3. 点击 **Rollback** 按钮

### 方法 2: 通过 Git

```bash
# 1. 回滚到上一个提交
git revert HEAD

# 2. 推送到 GitHub
git push origin main

# 3. Zeabur 会自动部署回滚版本
```

---

## 更新检查清单

每次更新后检查：

- [ ] GitHub 代码已推送
- [ ] Zeabur 自动部署成功
- [ ] 服务可以正常访问
- [ ] 管理后台可以登录
- [ ] 新功能正常显示
- [ ] 数据库迁移成功
- [ ] 日志没有错误
- [ ] 监控告警正常

---

## 本次更新内容

### 新增功能
- ✅ Team 开通时间识别
- ✅ 兑换码分组管理
- ✅ 转移服务优化
- ✅ 监控告警系统
- ✅ 前端用户体验优化

### 数据库变更
- 自动迁移，无需手动操作
- 新增 `code_groups` 表
- 新增多个字段到现有表

### 环境变量
- 新增 `MAX_TRANSFER_ATTEMPTS`（可选）
- 支持 `PORT` 环境变量

### 破坏性变更
- 无

---

## 联系支持

如果遇到问题：

1. **查看文档**: `docs/TROUBLESHOOTING.md`
2. **查看日志**: Zeabur 控制台 → Logs
3. **GitHub Issues**: https://github.com/nosift/team-dh/issues

---

**部署时间**: 2026-01-27
**版本**: e202197
**状态**: ✅ 已推送到 GitHub，等待 Zeabur 自动部署
