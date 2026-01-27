# 性能优化指南

Team-DH 项目的性能优化建议和最佳实践。

## 目录

- [数据库优化](#数据库优化)
- [应用层优化](#应用层优化)
- [部署优化](#部署优化)
- [监控和调优](#监控和调优)
- [性能基准](#性能基准)

---

## 数据库优化

### 1. 索引优化

#### 1.1 必要索引

确保以下索引存在：

```sql
-- 兑换码查询
CREATE INDEX IF NOT EXISTS idx_codes_code ON redemption_codes(code);
CREATE INDEX IF NOT EXISTS idx_codes_status ON redemption_codes(status);
CREATE INDEX IF NOT EXISTS idx_codes_team ON redemption_codes(team_name);

-- 兑换记录查询
CREATE INDEX IF NOT EXISTS idx_redemptions_email ON redemptions(email);
CREATE INDEX IF NOT EXISTS idx_redemptions_code_id ON redemptions(code_id);

-- 租约查询
CREATE INDEX IF NOT EXISTS idx_leases_email ON member_leases(email);
CREATE INDEX IF NOT EXISTS idx_leases_status ON member_leases(status);
CREATE INDEX IF NOT EXISTS idx_leases_expires ON member_leases(expires_at);
CREATE INDEX IF NOT EXISTS idx_leases_status_expires ON member_leases(status, expires_at);

-- 告警查询
CREATE INDEX IF NOT EXISTS idx_alerts_created ON system_alerts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_level_category ON system_alerts(level, category);

-- IP 限流
CREATE INDEX IF NOT EXISTS idx_rate_limits_ip ON ip_rate_limits(ip_address);
```

#### 1.2 复合索引

对于常见的组合查询，使用复合索引：

```sql
-- 状态 + 到期时间（用于转移查询）
CREATE INDEX IF NOT EXISTS idx_leases_status_expires
ON member_leases(status, expires_at);

-- 级别 + 分类（用于告警筛选）
CREATE INDEX IF NOT EXISTS idx_alerts_level_category
ON system_alerts(level, category);
```

#### 1.3 检查索引使用情况

```sql
-- 查看查询计划
EXPLAIN QUERY PLAN
SELECT * FROM member_leases
WHERE status = 'active' AND expires_at <= datetime('now');

-- 应该看到 "USING INDEX idx_leases_status_expires"
```

---

### 2. 查询优化

#### 2.1 避免全表扫描

❌ 不好的查询：
```sql
SELECT * FROM redemptions;  -- 全表扫描
```

✅ 优化后：
```sql
SELECT * FROM redemptions
WHERE redeemed_at >= datetime('now', '-7 days')
LIMIT 100;
```

#### 2.2 使用 LIMIT

始终限制返回数量：
```sql
SELECT * FROM member_leases
ORDER BY created_at DESC
LIMIT 100;
```

#### 2.3 避免 SELECT *

只查询需要的字段：
```sql
-- 不好
SELECT * FROM redemption_codes;

-- 好
SELECT id, code, status, used_count FROM redemption_codes;
```

---

### 3. 数据库配置

#### 3.1 WAL 模式

启用 Write-Ahead Logging（已默认启用）：

```sql
PRAGMA journal_mode=WAL;
```

**优点**:
- 提高并发性能
- 读写不互相阻塞
- 更好的崩溃恢复

#### 3.2 缓存大小

增加缓存大小：

```sql
PRAGMA cache_size = -64000;  -- 64MB
```

#### 3.3 同步模式

根据需求调整：

```sql
-- 最安全（默认）
PRAGMA synchronous = FULL;

-- 平衡性能和安全
PRAGMA synchronous = NORMAL;

-- 最快（不推荐生产环境）
PRAGMA synchronous = OFF;
```

#### 3.4 超时设置

```python
# database.py
conn = sqlite3.connect(db_path, timeout=30.0)
conn.execute("PRAGMA busy_timeout = 30000")
```

---

### 4. 数据清理

#### 4.1 定期清理旧数据

```sql
-- 清理 3 个月前的兑换记录
DELETE FROM redemptions
WHERE redeemed_at < datetime('now', '-3 months');

-- 清理已解决的旧告警
DELETE FROM system_alerts
WHERE resolved_at IS NOT NULL
AND resolved_at < datetime('now', '-1 month');

-- 清理旧的事件日志
DELETE FROM member_lease_events
WHERE created_at < datetime('now', '-6 months');
```

#### 4.2 数据归档

对于重要数据，先归档再删除：

```bash
# 导出旧数据
sqlite3 redemption.db <<EOF
.mode csv
.output archive_$(date +%Y%m%d).csv
SELECT * FROM redemptions WHERE redeemed_at < datetime('now', '-3 months');
.quit
EOF

# 删除旧数据
sqlite3 redemption.db "DELETE FROM redemptions WHERE redeemed_at < datetime('now', '-3 months');"
```

#### 4.3 VACUUM

定期压缩数据库：

```bash
# 手动执行
sqlite3 redemption.db "VACUUM;"

# 或设置定时任务
0 3 * * 0 sqlite3 /data/redemption.db "VACUUM;"
```

---

## 应用层优化

### 1. 连接池

使用连接池减少数据库连接开销：

```python
# database.py
from contextlib import contextmanager

@contextmanager
def get_connection():
    conn = sqlite3.connect(db_path, timeout=30.0)
    try:
        yield conn
    finally:
        conn.close()
```

---

### 2. 缓存策略

#### 2.1 配置缓存

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def get_team_config(team_name: str):
    return _load_team_config(team_name)
```

#### 2.2 统计缓存

```python
# 缓存 Team 统计 15 秒
CACHE_TTL_MS = {
    'stats': 15000,
    'teams': 15000,
}
```

#### 2.3 清除缓存

配置文件变更时自动清除：

```python
@app.before_request
def _auto_reload_config_if_changed():
    global _last_config_reload_sig
    sig = _config_files_signature()
    if _last_config_reload_sig != sig:
        config.reload_teams()
        _last_config_reload_sig = sig
```

---

### 3. 并发控制

#### 3.1 数据库锁

使用应用层锁防止超发：

```python
def reserve_code(code, lock_id, lock_seconds=120):
    """预留兑换码（加锁）"""
    with db.get_connection() as conn:
        conn.execute("""
            UPDATE redemption_codes
            SET locked_by = ?, locked_until = datetime('now', '+{} seconds')
            WHERE code = ? AND (locked_until IS NULL OR locked_until < datetime('now'))
        """.format(lock_seconds), (lock_id, code))
        conn.commit()
```

#### 3.2 全局锁

多 worker 环境下使用全局锁：

```python
def acquire_global_lock(lock_name, timeout=300):
    """获取全局锁"""
    with db.get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO app_locks (lock_name, locked_until)
            VALUES (?, datetime('now', '+{} seconds'))
        """.format(timeout), (lock_name,))
        conn.commit()
```

---

### 4. 异步处理

#### 4.1 后台任务

使用后台线程处理耗时任务：

```python
def start_background_worker():
    thread = threading.Thread(target=worker_loop, daemon=True)
    thread.start()
```

#### 4.2 批量处理

批量操作减少数据库往返：

```python
# 不好：逐个插入
for code in codes:
    conn.execute("INSERT INTO redemption_codes (...) VALUES (?)", (code,))

# 好：批量插入
conn.executemany("INSERT INTO redemption_codes (...) VALUES (?)", codes)
```

---

## 部署优化

### 1. Gunicorn 配置

#### 1.1 Worker 数量

```bash
# CPU 密集型：worker = CPU 核心数
gunicorn -w 4 -b 0.0.0.0:5000 web_server:app

# IO 密集型：worker = 2 * CPU 核心数 + 1
gunicorn -w 9 -b 0.0.0.0:5000 web_server:app
```

#### 1.2 Worker 类型

```bash
# 同步 worker（默认）
gunicorn -w 4 --worker-class sync web_server:app

# 异步 worker（处理更多并发）
gunicorn -w 4 --worker-class gevent web_server:app
```

#### 1.3 超时设置

```bash
gunicorn -w 4 --timeout 120 web_server:app
```

#### 1.4 完整配置

```bash
gunicorn \
  -w 4 \
  -b 0.0.0.0:5000 \
  --worker-class sync \
  --timeout 120 \
  --max-requests 1000 \
  --max-requests-jitter 50 \
  --access-logfile /var/log/gunicorn/access.log \
  --error-logfile /var/log/gunicorn/error.log \
  web_server:app
```

---

### 2. Nginx 反向代理

#### 2.1 基本配置

```nginx
upstream team_dh {
    server 127.0.0.1:5000;
    server 127.0.0.1:5001;
    server 127.0.0.1:5002;
    server 127.0.0.1:5003;
}

server {
    listen 80;
    server_name team-dh.example.com;

    location / {
        proxy_pass http://team_dh;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### 2.2 缓存静态文件

```nginx
location /static/ {
    alias /path/to/static/;
    expires 1d;
    add_header Cache-Control "public, immutable";
}
```

#### 2.3 Gzip 压缩

```nginx
gzip on;
gzip_vary on;
gzip_min_length 1024;
gzip_types text/plain text/css text/xml text/javascript application/json application/javascript;
```

#### 2.4 限流

```nginx
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;

location /api/ {
    limit_req zone=api burst=20 nodelay;
    proxy_pass http://team_dh;
}
```

---

### 3. Docker 优化

#### 3.1 多阶段构建

```dockerfile
# 构建阶段
FROM python:3.12-slim as builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user -r requirements.txt

# 运行阶段
FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .
ENV PATH=/root/.local/bin:$PATH
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "web_server:app"]
```

#### 3.2 资源限制

```yaml
# docker-compose.yml
services:
  team-dh:
    image: team-dh:latest
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 1G
        reservations:
          cpus: '1'
          memory: 512M
```

---

## 监控和调优

### 1. 性能监控

#### 1.1 启用监控

```bash
# 默认已启用
MONITOR_ENABLED=true
MONITOR_INTERVAL=300  # 5 分钟检查一次
```

#### 1.2 关键指标

监控以下指标：
- 数据库大小
- 查询响应时间
- API 响应时间
- 内存使用
- CPU 使用
- 并发连接数

#### 1.3 告警阈值

```python
# monitor.py
DB_SIZE_THRESHOLD = 500  # MB
QUERY_TIME_THRESHOLD = 1.0  # 秒
TABLE_SIZE_THRESHOLD = 100000  # 行
```

---

### 2. 日志分析

#### 2.1 慢查询日志

```python
# 记录慢查询
import time

start = time.time()
result = conn.execute(query).fetchall()
duration = time.time() - start

if duration > 1.0:
    log.warning(f"慢查询: {query} ({duration:.2f}s)")
```

#### 2.2 访问日志分析

```bash
# 统计最慢的 API
awk '{print $7, $10}' access.log | sort -k2 -rn | head -10

# 统计最频繁的 API
awk '{print $7}' access.log | sort | uniq -c | sort -rn | head -10
```

---

### 3. 压力测试

#### 3.1 使用 Apache Bench

```bash
# 测试兑换接口
ab -n 1000 -c 10 -p redeem.json -T application/json \
  http://localhost:5000/api/redeem

# redeem.json
{
  "email": "test@example.com",
  "code": "TEAM-XXXX-XXXX-XXXX"
}
```

#### 3.2 使用 wrk

```bash
# 测试并发性能
wrk -t4 -c100 -d30s http://localhost:5000/

# 测试 API
wrk -t4 -c100 -d30s -s post.lua http://localhost:5000/api/redeem
```

---

## 性能基准

### 1. 硬件要求

#### 最低配置
- CPU: 1 核
- 内存: 512MB
- 磁盘: 10GB
- 并发: 10 用户

#### 推荐配置
- CPU: 2 核
- 内存: 2GB
- 磁盘: 50GB SSD
- 并发: 100 用户

#### 高性能配置
- CPU: 4 核
- 内存: 4GB
- 磁盘: 100GB SSD
- 并发: 500+ 用户

---

### 2. 性能指标

#### 2.1 API 响应时间

| 接口 | 平均响应时间 | P95 | P99 |
|------|-------------|-----|-----|
| GET /api/verify | 50ms | 100ms | 200ms |
| POST /api/redeem | 500ms | 1s | 2s |
| POST /api/redeem/batch | 5s | 10s | 15s |
| GET /api/admin/stats | 100ms | 200ms | 500ms |

#### 2.2 数据库性能

| 操作 | 平均时间 | 备注 |
|------|---------|------|
| 简单查询 | <10ms | 带索引 |
| 复杂查询 | <100ms | 多表 JOIN |
| 插入操作 | <5ms | 单条 |
| 批量插入 | <50ms | 100 条 |

#### 2.3 并发能力

| Worker 数 | 并发用户 | QPS | 响应时间 |
|----------|---------|-----|---------|
| 1 | 10 | 20 | 500ms |
| 2 | 50 | 80 | 600ms |
| 4 | 100 | 150 | 700ms |
| 8 | 200 | 250 | 800ms |

---

### 3. 容量规划

#### 3.1 数据增长

| 数据类型 | 每月增长 | 1年总量 | 存储空间 |
|---------|---------|--------|---------|
| 兑换码 | 1000 | 12000 | 1MB |
| 兑换记录 | 5000 | 60000 | 10MB |
| 租约记录 | 5000 | 60000 | 15MB |
| 事件日志 | 20000 | 240000 | 50MB |
| 告警记录 | 1000 | 12000 | 5MB |
| **总计** | - | - | **~100MB** |

#### 3.2 扩展建议

**用户数 < 1000**:
- 单机部署
- 1-2 个 worker
- SQLite 数据库

**用户数 1000-10000**:
- 单机部署
- 4-8 个 worker
- SQLite + 定期清理

**用户数 > 10000**:
- 考虑迁移到 PostgreSQL/MySQL
- 负载均衡
- 读写分离
- 缓存层（Redis）

---

## 优化检查清单

### 启动前

- [ ] 确认 Python 版本 ≥ 3.10
- [ ] 安装所有依赖
- [ ] 配置环境变量
- [ ] 初始化数据库
- [ ] 创建必要索引

### 部署时

- [ ] 使用 Gunicorn 多 worker
- [ ] 配置 Nginx 反向代理
- [ ] 启用 Gzip 压缩
- [ ] 配置静态文件缓存
- [ ] 设置日志轮转

### 运行中

- [ ] 监控数据库大小
- [ ] 定期清理旧数据
- [ ] 检查慢查询
- [ ] 查看告警信息
- [ ] 分析访问日志

### 定期维护

- [ ] 每周：检查告警
- [ ] 每月：清理旧数据
- [ ] 每季度：VACUUM 数据库
- [ ] 每半年：性能测试
- [ ] 每年：容量规划

---

## 更新日志

### v1.0.0 (2026-01-27)
- 初始版本
- 数据库优化建议
- 应用层优化
- 部署优化
- 性能基准
