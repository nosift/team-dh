# 配置文件填写指南

## 📋 需要配置的文件

你需要配置2个文件：
1. ✅ **config.toml** - 已创建，只需修改1处
2. ⭐ **team.json** - 需要你手动创建

---

## 📝 步骤1: 修改 config.toml

### 必须修改的地方（只有1处）

打开 `config.toml`，找到第**71行**：

```toml
admin_password = "change-me-to-secure-password"
```

**改成你自己的密码**，比如：

```toml
admin_password = "MySecure@Pass2024!"
```

✅ **就这样！其他都不用改！**

---

### 可选修改的地方

#### 如果5000端口被占用

找到第**66行**：

```toml
port = 5000
```

改成其他端口，比如：

```toml
port = 5001
```

然后访问时用 http://localhost:5001

#### 如果只想本机访问

找到第**61行**：

```toml
host = "0.0.0.0"
```

改成：

```toml
host = "127.0.0.1"
```

#### 调整IP限流次数

找到第**53行**：

```toml
rate_limit_per_hour = 10
```

改成你想要的次数，比如：

```toml
rate_limit_per_hour = 20  # 每小时最多20次
```

---

## ⭐ 步骤2: 创建 team.json

### 2.1 获取Team凭证

#### ① 登录ChatGPT

浏览器访问: https://chatgpt.com

使用你的**Team管理员账号**登录

#### ② 获取凭证数据

在浏览器**新标签页**访问:

```
https://chatgpt.com/api/auth/session
```

你会看到这样的JSON数据：

```json
{
  "user": {
    "id": "user-abc123xyz",
    "name": "Your Name",
    "email": "admin@company.com",
    "image": "...",
    "picture": "...",
    "idp": "...",
    "iat": 123456,
    "mfa": false,
    "groups": [],
    "intercom_hash": "..."
  },
  "expires": "2024-03-15T10:00:00.000Z",
  "account": {
    "id": "def456-ghi789-jkl012",
    "name": "My Company",
    "account_user_role": "owner",
    "account_user_id": "...",
    "processor": {...},
    "account_type": "team",
    "is_most_recent_expired_subscription_gratis": false,
    "has_previously_paid_subscription": true,
    "organizationId": "org-xyz987abc654"
  },
  "accessToken": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6Ik1UaEVOVUpHTkVNMVFURTRNMEZCTWpkQ05UZzVNRFUxUlRVd1FVSkRNRU13UmtGRVFrRXpSZyJ9.eyJodHRwczovL2FwaS5vcGVuYWkuY29tL3Byb2ZpbGUiOnsiZW1haWwiOiJhZG1pbkBjb21wYW55LmNvbSIsImVtYWlsX3ZlcmlmaWVkIjp0cnVlfSwiaHR0cHM6Ly9hcGkub3BlbmFpLmNvbS9hdXRoIjp7InBvaWQiOiJvcmcteHl6OTg3YWJjNjU0IiwidXNlcl9pZCI6InVzZXItYWJjMTIzeHl6In0sImlzcyI6Imh0dHBzOi8vYXV0aDAub3BlbmFpLmNvbS8iLCJzdWIiOiJhdXRoMHw2NWVkNjNhMGQ5NzQzYjhmNzRhYmNkZWYiLCJhdWQiOlsiaHR0cHM6Ly9hcGkub3BlbmFpLmNvbS92MSIsImh0dHBzOi8vb3BlbmFpLm9wZW5haS5hdXRoMGFwcC5jb20vdXNlcmluZm8iXSwiaWF0IjoxNzEwNDg2MTIzLCJleHAiOjE3MTE2OTU3MjMsInNjb3BlIjoib3BlbmlkIHByb2ZpbGUgZW1haWwgb2ZmbGluZV9hY2Nlc3MiLCJhenAiOiJURGpYOGtCRUt4dk9iS0tHRktROXpORTdPYjhFUXRWdCJ9...."
}
```

#### ③ 提取需要的信息

**只需要这5个字段：**

| 字段 | 在JSON中的位置 | 示例值 |
|------|---------------|--------|
| **user.id** | `user.id` | `"user-abc123xyz"` |
| **user.email** | `user.email` | `"admin@company.com"` |
| **account.id** | `account.id` | `"def456-ghi789-jkl012"` |
| **account.organizationId** | `account.organizationId` | `"org-xyz987abc654"` |
| **accessToken** | `accessToken` | `"eyJhbGci...（很长）"` |

### 2.2 创建team.json文件

在项目根目录创建 `team.json` 文件，内容如下：

```json
[
  {
    "user": {
      "id": "把你的user.id粘贴到这里",
      "email": "把你的user.email粘贴到这里"
    },
    "account": {
      "id": "把你的account.id粘贴到这里",
      "organizationId": "把你的account.organizationId粘贴到这里"
    },
    "accessToken": "把你的accessToken粘贴到这里（整个很长的字符串）"
  }
]
```

### 2.3 填写示例

假设从网页获取的数据是：

```json
{
  "user": {
    "id": "user-abc123xyz",
    "email": "admin@company.com"
  },
  "account": {
    "id": "def456-ghi789-jkl012",
    "organizationId": "org-xyz987abc654"
  },
  "accessToken": "eyJhbGciOiJSUzI1NiIsInR5cCI6..."
}
```

那么你的 `team.json` 应该是：

```json
[
  {
    "user": {
      "id": "user-abc123xyz",
      "email": "admin@company.com"
    },
    "account": {
      "id": "def456-ghi789-jkl012",
      "organizationId": "org-xyz987abc654"
    },
    "accessToken": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6Ik1UaEVOVUpHTkVNMVFURTRNMEZCTWpkQ05UZzVNRFUxUlRVd1FVSkRNRU13UmtGRVFrRXpSZyJ9.eyJodHRwczovL2FwaS5vcGVuYWkuY29tL3Byb2ZpbGUiOnsiZW1haWwiOiJhZG1pbkBjb21wYW55LmNvbSIsImVtYWlsX3ZlcmlmaWVkIjp0cnVlfSwiaHR0cHM6Ly9hcGkub3BlbmFpLmNvbS9hdXRoIjp7InBvaWQiOiJvcmcteHl6OTg3YWJjNjU0IiwidXNlcl9pZCI6InVzZXItYWJjMTIzeHl6In0sImlzcyI6Imh0dHBzOi8vYXV0aDAub3BlbmFpLmNvbS8iLCJzdWIiOiJhdXRoMHw2NWVkNjNhMGQ5NzQzYjhmNzRhYmNkZWYiLCJhdWQiOlsiaHR0cHM6Ly9hcGkub3BlbmFpLmNvbS92MSIsImh0dHBzOi8vb3BlbmFpLm9wZW5haS5hdXRoMGFwcC5jb20vdXNlcmluZm8iXSwiaWF0IjoxNzEwNDg2MTIzLCJleHAiOjE3MTE2OTU3MjMsInNjb3BlIjoib3BlbmlkIHByb2ZpbGUgZW1haWwgb2ZmbGluZV9hY2Nlc3MiLCJhenAiOiJURGpYOGtCRUt4dk9iS0tHRktROXpORTdPYjhFUXRWdCJ9...."
  }
]
```

### 2.4 注意事项

⚠️ **重要提示：**

1. **外面要用 `[ ]` 包起来**（方括号）
2. **只需要5个字段**，其他字段不用复制
3. **accessToken很长**，要完整复制整个字符串
4. **保持JSON格式**，注意引号、逗号、括号
5. **文件名必须是 `team.json`**，不能是 `team.json.txt`

### 2.5 验证JSON格式

可以使用在线工具验证JSON格式是否正确：

- https://jsonlint.com/
- https://www.json.cn/

把你的 `team.json` 内容粘贴进去，点击验证。

---

## 📁 最终文件位置

配置完成后，你的项目目录应该是这样的：

```
team-dh/
├── config.toml          ✅ 已创建，已修改密码
├── team.json            ⭐ 你需要创建这个
│
├── database.py          (已有)
├── web_server.py        (已有)
└── ...其他文件
```

---

## ✅ 配置完成检查

- [ ] `config.toml` 已存在
- [ ] `config.toml` 中的 `admin_password` 已修改
- [ ] `team.json` 已创建
- [ ] `team.json` 包含5个必需字段
- [ ] JSON格式正确（可用在线工具验证）

---

## 🚀 下一步

配置完成后，继续执行：

```bash
# 1. 初始化数据库
python database.py

# 2. 生成兑换码（Team名 = 邮箱@前面的部分）
python code_generator.py generate --team admin --count 10

# 3. 启动服务
python start_redemption.py
```

---

## ❓ 常见问题

### Q: 如何确定Team名称？

**A:** Team名称就是你的邮箱@前面的部分

示例：
```
邮箱: admin@company.com
Team名: admin

邮箱: zhang@example.org
Team名: zhang
```

或者随便取一个名字也行，只要生成兑换码时保持一致即可。

### Q: accessToken在哪里？

**A:** 在网页返回的JSON中，是最长的那个字段，通常以 `eyJ` 开头。

### Q: team.json格式错误怎么办？

**A:**
1. 确保外面有 `[ ]`
2. 确保所有字段都有引号 `""`
3. 确保字段之间有逗号 `,`
4. 用在线JSON验证工具检查

### Q: 找不到user.id怎么办？

**A:** 在网页JSON中搜索 `"user":`，它下面的 `"id":` 就是user.id

### Q: 我有多个Team怎么办？

**A:** 可以在 `team.json` 中添加多个Team：

```json
[
  {
    "user": {"id": "user-1", "email": "admin1@xx.com"},
    "account": {"id": "xxx", "organizationId": "org-1"},
    "accessToken": "token1..."
  },
  {
    "user": {"id": "user-2", "email": "admin2@xx.com"},
    "account": {"id": "yyy", "organizationId": "org-2"},
    "accessToken": "token2..."
  }
]
```

---

## 📞 需要帮助？

参考详细文档：
- [本地启动指南](LOCAL_SETUP_GUIDE.md)
- [分步教程](SETUP_STEP_BY_STEP.md)
- [快速开始](START_HERE.md)
