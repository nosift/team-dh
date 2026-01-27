# 数据库迁移错误修复

## 问题描述

在 Zeabur 部署时遇到以下错误：

```
sqlite3.OperationalError: Cannot add a column with non-constant default
```

## 原因分析

SQLite 在使用 `ALTER TABLE ADD COLUMN` 时有以下限制：

1. **不支持非常量默认值**
   - ❌ `DEFAULT CURRENT_TIMESTAMP`
   - ❌ `DEFAULT (datetime('now'))`
   - ✅ `DEFAULT 'fixed_value'`
   - ✅ `DEFAULT 0`
   - ✅ `DEFAULT NULL`

2. **CREATE TABLE 时可以使用**
   - ✅ 创建新表时可以使用 `DEFAULT CURRENT_TIMESTAMP`
   - ❌ 修改现有表时不能使用

## 错误代码

```python
# ❌ 错误的写法
cursor.execute("ALTER TABLE teams_stats ADD COLUMN first_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP")
```

## 修复方案

分两步操作：

```python
# ✅ 正确的写法
# 步骤 1: 添加列（无默认值）
cursor.execute("ALTER TABLE teams_stats ADD COLUMN first_seen_at DATETIME")

# 步骤 2: 为现有记录设置默认值
cursor.execute("UPDATE teams_stats SET first_seen_at = CURRENT_TIMESTAMP WHERE first_seen_at IS NULL")
```

## 修复位置

**文件**: `database.py`
**行号**: 140

**修改前**:
```python
if "first_seen_at" not in teams_stats_cols:
    cursor.execute("ALTER TABLE teams_stats ADD COLUMN first_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP")
    log.info("已添加 first_seen_at 字段到 teams_stats 表")
```

**修改后**:
```python
if "first_seen_at" not in teams_stats_cols:
    # SQLite 不支持 ALTER TABLE 时使用 CURRENT_TIMESTAMP，需要分两步
    cursor.execute("ALTER TABLE teams_stats ADD COLUMN first_seen_at DATETIME")
    # 为现有记录设置默认值
    cursor.execute("UPDATE teams_stats SET first_seen_at = CURRENT_TIMESTAMP WHERE first_seen_at IS NULL")
    log.info("已添加 first_seen_at 字段到 teams_stats 表")
```

## 验证修复

### 本地测试

```bash
python3 -c "from database import db; print('✅ 数据库初始化成功')"
```

**预期输出**:
```
✅ 数据库初始化完成
✅ 数据库初始化成功
```

### Zeabur 部署

推送修复后，Zeabur 会自动重新部署：

```bash
git add database.py
git commit -m "fix: 修复 SQLite ALTER TABLE 不支持 CURRENT_TIMESTAMP 默认值的问题"
git push origin main
```

## SQLite 限制总结

### ALTER TABLE 限制

| 操作 | 支持 | 说明 |
|------|------|------|
| ADD COLUMN | ✅ | 支持 |
| ADD COLUMN with constant DEFAULT | ✅ | 支持常量默认值 |
| ADD COLUMN with CURRENT_TIMESTAMP | ❌ | 不支持 |
| ADD COLUMN with expression | ❌ | 不支持表达式 |
| DROP COLUMN | ✅ | SQLite 3.35.0+ 支持 |
| RENAME COLUMN | ✅ | SQLite 3.25.0+ 支持 |
| ALTER COLUMN | ❌ | 不支持 |

### 解决方案

对于需要非常量默认值的情况：

1. **方案 A: 分两步操作**（推荐）
   ```python
   cursor.execute("ALTER TABLE t ADD COLUMN c DATETIME")
   cursor.execute("UPDATE t SET c = CURRENT_TIMESTAMP WHERE c IS NULL")
   ```

2. **方案 B: 重建表**
   ```python
   cursor.execute("CREATE TABLE t_new (..., c DATETIME DEFAULT CURRENT_TIMESTAMP)")
   cursor.execute("INSERT INTO t_new SELECT *, CURRENT_TIMESTAMP FROM t")
   cursor.execute("DROP TABLE t")
   cursor.execute("ALTER TABLE t_new RENAME TO t")
   ```

3. **方案 C: 使用触发器**
   ```python
   cursor.execute("ALTER TABLE t ADD COLUMN c DATETIME")
   cursor.execute("""
       CREATE TRIGGER set_default_c
       AFTER INSERT ON t
       WHEN NEW.c IS NULL
       BEGIN
           UPDATE t SET c = CURRENT_TIMESTAMP WHERE rowid = NEW.rowid;
       END
   """)
   ```

## 相关资源

- [SQLite ALTER TABLE 文档](https://www.sqlite.org/lang_altertable.html)
- [SQLite 限制说明](https://www.sqlite.org/limits.html)
- [SQLite 数据类型](https://www.sqlite.org/datatype3.html)

## 其他注意事项

### 1. 数据库版本

确保使用的 SQLite 版本支持所需功能：

```python
import sqlite3
print(sqlite3.sqlite_version)  # 应该 >= 3.35.0
```

### 2. 迁移策略

对于生产环境，建议：

1. **备份数据库**
   ```bash
   sqlite3 /data/redemption.db .dump > backup.sql
   ```

2. **测试迁移**
   ```bash
   # 在测试环境先测试
   python -c "from database import db"
   ```

3. **监控日志**
   ```bash
   # 查看迁移日志
   tail -f /var/log/app.log
   ```

### 3. 回滚计划

如果迁移失败：

```bash
# 恢复备份
sqlite3 /data/redemption.db < backup.sql

# 或回滚代码
git revert HEAD
git push origin main
```

## 总结

- ✅ 问题已修复
- ✅ 本地测试通过
- ✅ 代码已推送到 GitHub
- ⏳ 等待 Zeabur 自动部署

**修复时间**: 2026-01-27 22:47
**Commit ID**: 40ddccd
