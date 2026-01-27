# API 文档

Team-DH 项目的完整 API 接口文档。

## 目录

- [用户 API](#用户-api)
- [管理员 API](#管理员-api)
- [监控 API](#监控-api)
- [错误码](#错误码)

---

## 用户 API

### 1. 单个兑换

**接口**: `POST /api/redeem`

**描述**: 使用兑换码兑换 ChatGPT Team 席位

**请求头**:
```
Content-Type: application/json
```

**请求体**:
```json
{
  "email": "user@example.com",
  "code": "TEAM-XXXX-XXXX-XXXX"
}
```

**响应**:

成功 (200):
```json
{
  "success": true,
  "message": "兑换成功！邀请邮件已发送到 user@example.com"
}
```

失败 (400/500):
```json
{
  "success": false,
  "error": "兑换码无效或已过期"
}
```

**错误情况**:
- 邮箱格式错误
- 兑换码不存在或已禁用
- 兑换码已用尽
- IP 限流（默认 10 次/小时）
- 邮箱已兑换过
- Team 席位不足

---

### 2. 批量兑换

**接口**: `POST /api/redeem/batch`

**描述**: 批量兑换多个兑换码（最多 20 个）

**请求头**:
```
Content-Type: application/json
```

**请求体**:
```json
{
  "email": "user@example.com",
  "codes": [
    "TEAM-XXXX-XXXX-XXXX",
    "TEAM-YYYY-YYYY-YYYY"
  ]
}
```

**响应**:

成功 (200):
```json
{
  "success": true,
  "success_count": 2,
  "fail_count": 0,
  "results": [
    {
      "code": "TEAM-XXXX-XXXX-XXXX",
      "success": true,
      "message": "兑换成功"
    },
    {
      "code": "TEAM-YYYY-YYYY-YYYY",
      "success": true,
      "message": "兑换成功"
    }
  ]
}
```

**限制**:
- 单次最多 20 个兑换码
- 受 IP 限流限制

---

### 3. 验证兑换码

**接口**: `GET /api/verify`

**描述**: 验证兑换码是否有效

**请求参数**:
```
code: 兑换码（必填）
```

**示例**:
```
GET /api/verify?code=TEAM-XXXX-XXXX-XXXX
```

**响应**:

有效:
```json
{
  "valid": true,
  "team": "TeamA",
  "remaining_uses": 5,
  "expires_at": "2026-12-31T23:59:59"
}
```

无效:
```json
{
  "valid": false,
  "error": "兑换码不存在"
}
```

---

## 管理员 API

所有管理员 API 都需要登录认证。未登录时返回 401 错误。

### 认证

**登录**: `POST /admin/login`

**请求体**:
```json
{
  "password": "admin123"
}
```

**响应**:
```json
{
  "success": true,
  "message": "登录成功"
}
```

登录后会设置 session cookie，后续请求自动携带。

**登出**: `GET /admin/logout`

---

### 1. 获取统计信息

**接口**: `GET /api/admin/stats`

**描述**: 获取仪表板统计数据

**响应**:
```json
{
  "success": true,
  "stats": {
    "total_codes": 100,
    "active_codes": 80,
    "used_codes": 15,
    "total_redemptions": 50,
    "unique_users": 45,
    "pending_invites": 5
  },
  "teams": [
    {
      "team_name": "TeamA",
      "total_seats": 100,
      "used_seats": 45,
      "pending_seats": 5,
      "available_seats": 50,
      "created_at": "2026-01-01T00:00:00"
    }
  ]
}
```

---

### 2. 兑换码管理

#### 2.1 获取兑换码列表

**接口**: `GET /api/admin/codes`

**请求参数**:
- `team`: Team 名称（可选）
- `status`: 状态筛选（可选）

**响应**:
```json
{
  "success": true,
  "codes": [
    {
      "id": 1,
      "code": "TEAM-XXXX-XXXX-XXXX",
      "team_name": "TeamA",
      "max_uses": 10,
      "used_count": 5,
      "status": "active",
      "created_at": "2026-01-01T00:00:00",
      "expires_at": null,
      "auto_transfer": true
    }
  ]
}
```

#### 2.2 生成兑换码

**接口**: `POST /api/admin/codes/generate`

**请求体**:
```json
{
  "team_name": "TeamA",
  "count": 10,
  "max_uses": 1,
  "expires_days": 30,
  "auto_transfer": true
}
```

**响应**:
```json
{
  "success": true,
  "message": "成功生成 10 个兑换码",
  "codes": [
    "TEAM-XXXX-XXXX-XXXX",
    "TEAM-YYYY-YYYY-YYYY"
  ]
}
```

#### 2.3 启用/禁用兑换码

**接口**: `POST /api/admin/codes/{code_id}/toggle`

**响应**:
```json
{
  "success": true,
  "message": "兑换码已禁用",
  "status": "disabled"
}
```

#### 2.4 删除兑换码

**接口**: `DELETE /api/admin/codes/{code_id}`

**响应**:
```json
{
  "success": true,
  "message": "兑换码已删除"
}
```

---

### 3. 兑换记录

**接口**: `GET /api/admin/redemptions`

**请求参数**:
- `limit`: 返回数量（默认 100）

**响应**:
```json
{
  "success": true,
  "redemptions": [
    {
      "id": 1,
      "email": "user@example.com",
      "code": "TEAM-XXXX-XXXX-XXXX",
      "team_name": "TeamA",
      "redeemed_at": "2026-01-27T12:00:00",
      "invite_status": "accepted",
      "ip_address": "192.168.1.1"
    }
  ]
}
```

---

### 4. Team 管理

#### 4.1 获取 Team 列表

**接口**: `GET /api/admin/teams`

**响应**:
```json
{
  "success": true,
  "teams": [
    {
      "index": 0,
      "name": "TeamA",
      "email": "team@example.com",
      "user_id": "user-xxx",
      "account_id": "xxx-xxx-xxx",
      "org_id": "org-xxx",
      "has_token": true,
      "created_at": "2026-01-01T00:00:00"
    }
  ]
}
```

#### 4.2 添加 Team

**接口**: `POST /api/admin/teams`

**请求体**:
```json
{
  "name": "TeamB",
  "email": "teamb@example.com",
  "user_id": "user-xxx",
  "account_id": "xxx-xxx-xxx",
  "org_id": "org-xxx",
  "access_token": "eyJhbGci..."
}
```

#### 4.3 更新 Team

**接口**: `PUT /api/admin/teams/{index}`

**请求体**: 同添加 Team

#### 4.4 删除 Team

**接口**: `DELETE /api/admin/teams/{index}`

---

### 5. 成员租约管理

#### 5.1 获取租约列表

**接口**: `GET /api/admin/leases`

**请求参数**:
- `email`: 邮箱筛选（可选）

**响应**:
```json
{
  "success": true,
  "leases": [
    {
      "id": 1,
      "email": "user@example.com",
      "team_name": "TeamA",
      "status": "active",
      "invited_at": "2026-01-01T00:00:00",
      "joined_at": "2026-01-01T00:05:00",
      "expires_at": "2026-02-01T00:05:00",
      "transfer_count": 0
    }
  ]
}
```

#### 5.2 同步加入时间

**接口**: `POST /api/admin/leases/sync`

**请求体**:
```json
{
  "email": "user@example.com"
}
```

#### 5.3 手动转移

**接口**: `POST /api/admin/leases/transfer`

**请求体**:
```json
{
  "email": "user@example.com",
  "force": false
}
```

---

## 监控 API

### 1. 获取监控仪表板

**接口**: `GET /api/admin/monitor/dashboard`

**响应**:
```json
{
  "success": true,
  "data": {
    "alert_stats": {
      "critical": 0,
      "error": 2,
      "warning": 5,
      "info": 10
    },
    "recent_alerts": [...],
    "timestamp": "2026-01-27T12:00:00"
  }
}
```

---

### 2. 获取告警列表

**接口**: `GET /api/admin/monitor/alerts`

**请求参数**:
- `limit`: 返回数量（默认 50）
- `level`: 告警级别（info/warning/error/critical）
- `category`: 分类（team_capacity/transfer_failure/database/system）

**响应**:
```json
{
  "success": true,
  "alerts": [
    {
      "id": 1,
      "level": "warning",
      "category": "team_capacity",
      "title": "Team TeamA 席位不足",
      "message": "席位使用率 87.5%，剩余 12 个席位",
      "metadata": {
        "team": "TeamA",
        "total": 100,
        "used": 88,
        "available": 12
      },
      "created_at": "2026-01-27T12:00:00",
      "resolved_at": null,
      "resolved_by": null
    }
  ]
}
```

---

### 3. 标记告警已解决

**接口**: `POST /api/admin/monitor/alerts/{alert_id}/resolve`

**请求体**:
```json
{
  "resolved_by": "admin"
}
```

**响应**:
```json
{
  "success": true,
  "message": "告警已标记为已解决"
}
```

---

### 4. 手动触发监控检查

**接口**: `POST /api/admin/monitor/check`

**响应**:
```json
{
  "success": true,
  "message": "监控检查已完成"
}
```

---

## 错误码

### HTTP 状态码

- `200`: 成功
- `400`: 请求参数错误
- `401`: 未授权（需要登录）
- `403`: 禁止访问
- `404`: 资源不存在
- `429`: 请求过于频繁（限流）
- `500`: 服务器内部错误

### 业务错误码

所有错误响应格式：
```json
{
  "success": false,
  "error": "错误描述"
}
```

常见错误：
- `邮箱格式错误`
- `兑换码不存在`
- `兑换码已禁用`
- `兑换码已用尽`
- `IP 请求过于频繁`
- `邮箱已兑换过`
- `Team 席位不足`
- `未登录`
- `密码错误`

---

## 限流规则

### IP 限流

- **兑换接口**: 10 次/小时/IP
- **验证接口**: 无限制
- **管理接口**: 需要登录，无 IP 限流

### 并发控制

- 兑换码预留锁定时间: 120 秒
- 数据库锁超时: 30 秒

---

## 最佳实践

### 1. 错误处理

始终检查 `success` 字段：
```javascript
const response = await fetch('/api/redeem', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email, code })
});

const result = await response.json();

if (result.success) {
  // 处理成功
  console.log(result.message);
} else {
  // 处理错误
  console.error(result.error);
}
```

### 2. 批量操作

批量兑换时，逐个处理结果：
```javascript
const result = await fetch('/api/redeem/batch', {
  method: 'POST',
  body: JSON.stringify({ email, codes })
}).then(r => r.json());

result.results.forEach(r => {
  if (r.success) {
    console.log(`${r.code}: 成功`);
  } else {
    console.error(`${r.code}: ${r.message}`);
  }
});
```

### 3. 管理员认证

登录后保持 session：
```javascript
// 登录
await fetch('/admin/login', {
  method: 'POST',
  credentials: 'include', // 重要：携带 cookie
  body: JSON.stringify({ password })
});

// 后续请求自动携带 session
await fetch('/api/admin/stats', {
  credentials: 'include'
});
```

---

## 更新日志

### v1.0.0 (2026-01-27)
- 初始版本
- 用户兑换 API
- 管理员 API
- 监控 API
