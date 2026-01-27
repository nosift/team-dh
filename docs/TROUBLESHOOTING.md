# 故障排查指南

Team-DH 项目常见问题和解决方案。

## 目录

- [启动问题](#启动问题)
- [兑换问题](#兑换问题)
- [转移问题](#转移问题)
- [数据库问题](#数据库问题)
- [性能问题](#性能问题)
- [监控告警](#监控告警)

---

## 启动问题

### 1. 服务无法启动

**症状**: 运行 `python web_server.py` 后报错

**可能原因**:

#### 1.1 端口被占用

```
Address already in use
Port 5000 is in use by another program
```

**解决方案**:
```bash
# 查看占用端口的进程
lsof -i :5000

# 杀掉进程
kill -9 <PID>

# 或者使用其他端口
PORT=5001 python web_server.py
```

#### 1.2 Python 版本过低

```
TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'
```

**解决方案**:
- 项目需要 Python 3.10+
- 检查版本: `python --version`
- 使用正确的 Python: `python3.11 web_server.py`

#### 1.3 依赖缺失

```
ModuleNotFoundError: No module named 'flask'
```

**解决方案**:
```bash
# 安装依赖
pip install -r requirements.txt

# 或使用 uv
uv sync
```

---

### 2. 数据库初始化失败

**症状**: 启动时报数据库错误

**解决方案**:
```bash
# 删除旧数据库
rm redemption.db

# 重新初始化
python init_db.py

# 或让程序自动初始化
python web_server.py
```

---

## 兑换问题

### 1. 兑换码无效

**症状**: 用户提示"兑换码不存在"

**排查步骤**:

1. 检查兑换码是否存在:
```bash
sqlite3 redemption.db "SELECT * FROM redemption_codes WHERE code = 'TEAM-XXXX-XXXX-XXXX';"
```

2. 检查兑换码状态:
```sql
SELECT code, status, used_count, max_uses, expires_at
FROM redemption_codes
WHERE code = 'TEAM-XXXX-XXXX-XXXX';
```

**可能原因**:
- 兑换码不存在
- 状态为 `disabled`
- 已用尽 (`used_count >= max_uses`)
- 已过期 (`expires_at < now`)

**解决方案**:
```bash
# 启用兑换码
python code_generator.py enable TEAM-XXXX-XXXX-XXXX

# 增加使用次数
sqlite3 redemption.db "UPDATE redemption_codes SET max_uses = 10 WHERE code = 'TEAM-XXXX-XXXX-XXXX';"
```

---

### 2. IP 限流

**症状**: 提示"IP 请求过于频繁"

**原因**: 同一 IP 1小时内兑换超过 10 次

**解决方案**:

1. 临时解决 - 清除限流记录:
```bash
sqlite3 redemption.db "DELETE FROM ip_rate_limits WHERE ip_address = '192.168.1.1';"
```

2. 永久解决 - 调整限流配置:
```python
# config.py
RATE_LIMIT_PER_HOUR = 20  # 增加到 20 次
```

---

### 3. 邮箱已兑换

**症状**: 提示"该邮箱已兑换过"

**排查**:
```sql
SELECT * FROM redemptions WHERE email = 'user@example.com';
```

**解决方案**:

如果是误兑换，可以删除记录：
```bash
sqlite3 redemption.db "DELETE FROM redemptions WHERE email = 'user@example.com';"
```

**注意**: 删除后需要手动从 Team 中移除该用户。

---

### 4. Team 席位不足

**症状**: 提示"Team 席位不足"

**排查**:
```bash
# 查看 Team 统计
sqlite3 redemption.db "SELECT * FROM teams_stats WHERE team_name = 'TeamA';"
```

**解决方案**:

1. 检查实际席位:
   - 登录管理后台
   - 查看 "Team统计" Tab
   - 确认 `available_seats` 数量

2. 如果统计不准确，手动刷新:
   - 点击 "Team管理" Tab
   - 点击 "刷新统计"

3. 如果席位确实不足:
   - 购买更多席位
   - 或移除不活跃用户

---

## 转移问题

### 1. 转移失败

**症状**: 租约状态变为 `failed`

**排查步骤**:

1. 查看错误信息:
```sql
SELECT email, team_name, status, last_error, updated_at
FROM member_leases
WHERE status = 'failed';
```

2. 查看事件日志:
```sql
SELECT * FROM member_lease_events
WHERE email = 'user@example.com'
ORDER BY created_at DESC
LIMIT 10;
```

**常见原因**:

#### 1.1 Token 失效

**错误**: `401 Unauthorized`

**解决方案**:
```bash
# 更新 Team Token
# 1. 访问 https://chatgpt.com/api/auth/session
# 2. 复制 accessToken
# 3. 在管理后台更新 Team 配置
```

#### 1.2 用户不在 Team 中

**错误**: `Member not found`

**解决方案**:
- 用户可能已经被手动移除
- 标记租约为已取消:
```sql
UPDATE member_leases
SET status = 'cancelled'
WHERE email = 'user@example.com';
```

#### 1.3 目标 Team 席位不足

**错误**: `Team capacity exceeded`

**解决方案**:
- 检查所有 Team 的席位情况
- 确保至少有一个 Team 有可用席位
- 或暂时禁用自动转移

---

### 2. 转移超时

**症状**: 租约长时间处于 `transferring` 状态

**排查**:
```sql
SELECT email, team_name, status, updated_at
FROM member_leases
WHERE status = 'transferring'
AND updated_at < datetime('now', '-1 hour');
```

**解决方案**:

1. 手动重试转移:
   - 登录管理后台
   - 进入 "到期/转移" Tab
   - 找到对应租约
   - 点击 "强制转移"

2. 或重置状态:
```sql
UPDATE member_leases
SET status = 'active', attempts = 0
WHERE email = 'user@example.com';
```

---

### 3. 加入时间未同步

**症状**: 租约状态为 `pending`，`joined_at` 为空

**原因**: 用户还未接受邀请，或同步失败

**解决方案**:

1. 手动同步:
   - 登录管理后台
   - 进入 "到期/转移" Tab
   - 输入邮箱
   - 点击 "同步加入时间"

2. 检查邀请状态:
```bash
# 查看 Invites API
curl -H "Authorization: Bearer $TOKEN" \
  "https://api.openai.com/v1/organization/invites"
```

3. 如果用户确实已加入，但同步失败:
```sql
-- 手动设置加入时间
UPDATE member_leases
SET joined_at = datetime('now'),
    expires_at = datetime('now', '+1 month'),
    status = 'active'
WHERE email = 'user@example.com';
```

---

## 数据库问题

### 1. 数据库锁定

**症状**: `database is locked`

**原因**: 多个进程同时访问数据库

**解决方案**:

1. 增加超时时间（已在代码中设置为 30 秒）

2. 检查是否有僵尸进程:
```bash
ps aux | grep python
kill -9 <PID>
```

3. 启用 WAL 模式（已默认启用）:
```bash
sqlite3 redemption.db "PRAGMA journal_mode=WAL;"
```

---

### 2. 数据库损坏

**症状**: `database disk image is malformed`

**解决方案**:

1. 尝试修复:
```bash
sqlite3 redemption.db "PRAGMA integrity_check;"
```

2. 如果无法修复，从备份恢复:
```bash
cp redemption.db.backup redemption.db
```

3. 如果没有备份，导出数据:
```bash
sqlite3 redemption.db .dump > backup.sql
rm redemption.db
sqlite3 redemption.db < backup.sql
```

---

### 3. 数据库过大

**症状**: 数据库文件超过 500MB

**解决方案**:

1. 清理旧数据:
```sql
-- 删除 3 个月前的兑换记录
DELETE FROM redemptions
WHERE redeemed_at < datetime('now', '-3 months');

-- 删除已解决的告警
DELETE FROM system_alerts
WHERE resolved_at IS NOT NULL
AND resolved_at < datetime('now', '-1 month');

-- 删除旧的事件日志
DELETE FROM member_lease_events
WHERE created_at < datetime('now', '-6 months');
```

2. 压缩数据库:
```bash
sqlite3 redemption.db "VACUUM;"
```

---

## 性能问题

### 1. 响应缓慢

**症状**: API 请求响应时间超过 2 秒

**排查步骤**:

1. 检查数据库性能:
```sql
-- 查看表大小
SELECT name, COUNT(*) as count
FROM sqlite_master m, pragma_table_info(m.name)
WHERE m.type='table'
GROUP BY name;

-- 分析慢查询
EXPLAIN QUERY PLAN
SELECT * FROM member_leases WHERE status = 'active';
```

2. 检查索引:
```sql
-- 查看所有索引
SELECT * FROM sqlite_master WHERE type='index';
```

**解决方案**:

1. 添加缺失的索引:
```sql
CREATE INDEX IF NOT EXISTS idx_redemptions_email
ON redemptions(email);

CREATE INDEX IF NOT EXISTS idx_leases_status_expires
ON member_leases(status, expires_at);
```

2. 清理旧数据（见上文）

3. 增加 worker 数量:
```bash
gunicorn -w 4 -b 0.0.0.0:5000 web_server:app
```

---

### 2. 内存占用过高

**症状**: 进程内存占用超过 500MB

**排查**:
```bash
ps aux | grep python
```

**解决方案**:

1. 减少 worker 数量
2. 重启服务释放内存
3. 检查是否有内存泄漏

---

## 监控告警

### 1. 席位不足告警

**告警**: "Team TeamA 席位不足"

**处理**:

1. 确认告警准确性:
   - 登录管理后台
   - 查看 Team 统计

2. 如果确实不足:
   - 购买更多席位
   - 或移除不活跃用户

3. 如果是误报:
   - 刷新 Team 统计
   - 标记告警为已解决

---

### 2. 转移失败告警

**告警**: "用户 xxx 转移失败"

**处理**:

1. 查看错误详情:
   - 点击告警查看 metadata
   - 查看 last_error 字段

2. 根据错误类型处理（见上文"转移问题"）

3. 处理完成后标记告警为已解决

---

### 3. 数据库性能告警

**告警**: "数据库查询缓慢"

**处理**:

1. 检查数据库大小和表数据量
2. 清理旧数据
3. 优化索引
4. 考虑升级硬件

---

## 日志分析

### 查看日志

```bash
# 实时查看日志
tail -f /var/log/team-dh/app.log

# 搜索错误
grep "ERROR" /var/log/team-dh/app.log

# 搜索特定用户
grep "user@example.com" /var/log/team-dh/app.log
```

### 日志级别

- `INFO`: 正常操作
- `WARNING`: 警告信息
- `ERROR`: 错误信息
- `CRITICAL`: 严重错误

---

## 紧急恢复

### 1. 服务完全不可用

```bash
# 1. 停止服务
pkill -f web_server.py

# 2. 检查数据库
sqlite3 redemption.db "PRAGMA integrity_check;"

# 3. 重启服务
python web_server.py

# 4. 检查日志
tail -f /var/log/team-dh/app.log
```

### 2. 数据丢失

```bash
# 从备份恢复
cp /backup/redemption.db.$(date +%Y%m%d) redemption.db

# 重启服务
systemctl restart team-dh
```

---

## 预防措施

### 1. 定期备份

```bash
# 每天备份数据库
0 2 * * * cp /data/redemption.db /backup/redemption.db.$(date +\%Y\%m\%d)

# 保留最近 30 天的备份
find /backup -name "redemption.db.*" -mtime +30 -delete
```

### 2. 监控告警

- 启用监控功能（默认已启用）
- 定期查看告警
- 及时处理问题

### 3. 日志轮转

```bash
# /etc/logrotate.d/team-dh
/var/log/team-dh/*.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    create 0640 www-data www-data
}
```

---

## 获取帮助

如果以上方法都无法解决问题：

1. 查看项目文档: `docs/`
2. 查看 GitHub Issues
3. 联系技术支持

---

## 更新日志

### v1.0.0 (2026-01-27)
- 初始版本
- 涵盖常见问题和解决方案
