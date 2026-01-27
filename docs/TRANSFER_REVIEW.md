# 转移服务代码审查报告

## 发现的问题

### 1. 潜在的竞态条件

**位置**: `_process_transfer_for_lease` 函数 (line 632-732)

**问题**:
- 在检查席位可用性 (line 696) 和实际邀请 (line 701) 之间存在时间窗口
- 如果多个转移同时进行，可能导致席位超发

**建议**:
- 在邀请前再次检查席位
- 或者使用更细粒度的锁

### 2. 错误处理不完整

**位置**: `_sync_joined_leases` 函数 (line 121-294)

**问题**:
- 多个 try-except 块捕获异常但只记录，不返回错误状态
- 可能导致静默失败

**建议**:
- 增加错误计数器
- 在监控中添加同步失败告警

### 3. 重试逻辑可能过于激进

**位置**: `_next_attempt_time` 函数 (line 64-68)

**问题**:
- 指数退避最大值是 24 小时
- 对于持续失败的情况，可能会一直重试

**建议**:
- 添加最大重试次数限制
- 超过限制后标记为 "需要人工干预"

### 4. 缺少事务保护

**位置**: 多处数据库操作

**问题**:
- 转移过程中的多个数据库操作没有事务保护
- 如果中间步骤失败，可能导致数据不一致

**建议**:
- 使用数据库事务包装关键操作
- 确保原子性

### 5. Team 选择逻辑可能不够智能

**位置**: `_pick_next_team` 函数 (line 31-61)

**问题**:
- 只是简单的轮询，不考虑 Team 的实际负载
- 可能导致某些 Team 过载

**建议**:
- 考虑 Team 的可用席位数
- 优先选择席位充足的 Team

## 优化建议

### 1. 添加健康检查

```python
def check_transfer_health():
    """检查转移系统健康状态"""
    # 检查长时间处于 transferring 状态的租约
    # 检查重试次数过多的租约
    # 检查 Team 席位情况
```

### 2. 改进席位检查

```python
def _pick_next_team_with_capacity(current_team, email):
    """选择有足够席位的 Team"""
    candidates = _pick_next_team(...)

    # 按可用席位数排序
    candidates_with_capacity = []
    for team in candidates:
        capacity = get_team_available_seats(team)
        if capacity > 0:
            candidates_with_capacity.append((team, capacity))

    # 优先选择席位最多的
    candidates_with_capacity.sort(key=lambda x: x[1], reverse=True)
    return [t[0] for t in candidates_with_capacity]
```

### 3. 添加转移前置检查

```python
def _pre_transfer_check(lease):
    """转移前的完整检查"""
    checks = {
        'has_joined': lease.get('joined_at') is not None,
        'is_expired': is_expired(lease),
        'has_available_team': len(_pick_next_team(...)) > 0,
        'not_transferring': lease.get('status') != 'transferring',
    }

    return all(checks.values()), checks
```

### 4. 改进错误恢复

```python
def recover_stuck_transfers():
    """恢复卡住的转移"""
    # 查找长时间处于 transferring 状态的租约
    stuck = db.get_stuck_transfers(hours=2)

    for lease in stuck:
        # 重置状态，允许重试
        db.reset_transfer_status(lease['email'])
```

## 测试建议

### 1. 并发测试

测试多个用户同时到期转移的情况

### 2. 失败恢复测试

模拟各种失败场景：
- 网络超时
- API 错误
- 席位不足
- Token 失效

### 3. 边界条件测试

- 只有 1 个 Team
- 所有 Team 都满了
- 用户不在旧 Team 中

## 总体评价

代码整体质量良好，逻辑清晰，但在以下方面可以改进：

✅ **优点**:
- 完善的事件日志
- 详细的错误信息
- 灵活的配置选项
- 指数退避重试机制

⚠️ **需要改进**:
- 并发控制
- 错误处理
- 事务保护
- 智能 Team 选择

## 优先级

**高优先级**:
1. 添加事务保护
2. 改进席位检查逻辑
3. 添加最大重试次数限制

**中优先级**:
4. 优化 Team 选择算法
5. 添加健康检查
6. 改进错误恢复

**低优先级**:
7. 性能优化
8. 代码重构
