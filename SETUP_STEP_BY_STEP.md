# 本地部署完整步骤详解（图文版）

## 📋 准备工作

### 你需要的东西

```
✓ Python 3.12+ (已安装)
✓ ChatGPT Team管理员账号
✓ 10分钟时间
```

---

## 🎯 步骤流程图

```
开始
  ↓
① 安装依赖 (pip install)
  ↓
② 获取Team凭证 (访问ChatGPT网页)
  ↓
③ 创建team.json (复制粘贴)
  ↓
④ 创建config.toml (复制+修改密码)
  ↓
⑤ 初始化数据库 (python database.py)
  ↓
⑥ 生成兑换码 (python code_generator.py)
  ↓
⑦ 启动服务 (python start_redemption.py)
  ↓
✅ 完成！访问 http://localhost:5000
```

---

## 📝 详细步骤

### 步骤① 安装依赖

打开命令行/终端，进入项目目录：

```bash
# Windows命令提示符
cd d:\vscode_所有项目\team-dh

# 然后安装
pip install flask gunicorn
```

**看到这个就成功了：**
```
Successfully installed flask-3.0.0 gunicorn-21.2.0
```

---

### 步骤② 获取Team凭证

#### 2.1 登录ChatGPT

```
浏览器访问: https://chatgpt.com
使用你的Team管理员账号登录
```

#### 2.2 获取凭证JSON

```
在新标签页访问: https://chatgpt.com/api/auth/session
```

会看到这样的JSON数据（简化版）：

```json
{
  "user": {
    "id": "user-abc123",
    "email": "admin@company.com"
  },
  "account": {
    "id": "def456-ghi789",
    "organizationId": "org-xyz987"
  },
  "accessToken": "eyJhbGci...（很长）"
}
```

**全选并复制这段JSON** (Ctrl+A, Ctrl+C)

---

### 步骤③ 创建team.json

#### 3.1 创建新文件

在项目根目录创建文件: `team.json`

#### 3.2 填入内容

把刚才复制的JSON改成这个格式：

```json
[
  {
    "user": {
      "id": "粘贴你的user.id",
      "email": "粘贴你的email"
    },
    "account": {
      "id": "粘贴你的account.id",
      "organizationId": "粘贴你的organizationId"
    },
    "accessToken": "粘贴你的accessToken（整个很长的字符串）"
  }
]
```

**示例：**

```json
[
  {
    "user": {
      "id": "user-abc123",
      "email": "admin@company.com"
    },
    "account": {
      "id": "def456-ghi789",
      "organizationId": "org-xyz987"
    },
    "accessToken": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6Ik1UaEV..."
  }
]
```

**⚠️ 注意：**
- 外面要用 `[ ]` 包起来
- 只需要这5个字段: `user.id`, `user.email`, `account.id`, `account.organizationId`, `accessToken`
- 保持JSON格式（引号、逗号、括号）

---

### 步骤④ 创建config.toml

#### 4.1 复制模板

```bash
# Windows
copy config.toml.example config.toml

# Linux/macOS
cp config.toml.example config.toml
```

#### 4.2 修改管理密码

用记事本/文本编辑器打开 `config.toml`

找到第71行（或搜索 `admin_password`）：

```toml
admin_password = "change-me-to-secure-password"
```

改成你自己的密码：

```toml
admin_password = "MyPassword123!"
```

保存文件。

**其他配置暂时不用改！**

---

### 步骤⑤ 初始化数据库

运行初始化命令：

```bash
python database.py
```

**成功的话会看到：**

```
✅ 数据库初始化完成
```

这会在项目目录创建 `redemption.db` 文件。

---

### 步骤⑥ 生成兑换码

#### 6.1 确定Team名称

**Team名称 = 你的邮箱@前面的部分**

示例：
```
邮箱: admin@company.com
Team名: admin

邮箱: zhang@example.org
Team名: zhang
```

或者随便取一个名字也行，比如 `MyTeam`

#### 6.2 生成兑换码

```bash
# 生成10个兑换码
python code_generator.py generate --team admin --count 10

# 把 "admin" 替换成你的Team名
```

**成功的话会看到：**

```
开始生成 10 个兑换码...
已生成: 10/10
✅ 成功生成 10 个兑换码

生成的兑换码:
==================================================
1. TEAM-ABCD-1234-EFGH
2. TEAM-WXYZ-5678-IJKL
3. TEAM-MNOP-9012-QRST
...
==================================================
```

**把这些兑换码复制保存下来！**

---

### 步骤⑦ 启动服务

运行启动命令：

```bash
python start_redemption.py
```

**成功的话会看到：**

```
🔍 检查系统环境...

✅ 配置文件检查通过
✅ 数据库初始化完成
✅ 当前有 10 个兑换码

============================================================
🚀 启动 ChatGPT Team 兑换码系统
============================================================

📝 用户兑换页面: http://0.0.0.0:5000/
🔧 管理后台: http://0.0.0.0:5000/admin
🔑 管理密码: MyPassword123!

按 Ctrl+C 停止服务

============================================================
```

**不要关闭这个窗口！** 服务正在运行。

---

## 🎉 测试使用

### 1. 打开用户兑换页面

浏览器访问: http://localhost:5000/

### 2. 测试兑换

```
邮箱地址: your@email.com  (要邀请的邮箱)
兑换码: TEAM-ABCD-1234-EFGH  (刚才生成的)
```

点击 "立即兑换"

### 3. 查看结果

**成功会显示：**
```
✅ 兑换成功！邀请邮件已发送到 your@email.com
```

**然后到邮箱查收ChatGPT的邀请邮件！**

### 4. 打开管理后台

浏览器访问: http://localhost:5000/admin

输入密码: `MyPassword123!` (你设置的)

可以看到：
- 兑换码列表
- 兑换记录
- 统计数据

---

## 📁 检查文件

完成后，你的目录应该有这些文件：

```
team-dh/
│
├── config.toml          ✓ 你创建的
├── team.json            ✓ 你创建的
├── redemption.db        ✓ 自动生成
│
├── database.py          (已有)
├── web_server.py        (已有)
├── code_generator.py    (已有)
├── start_redemption.py  (已有)
│
└── static/
    ├── index.html       (已有)
    └── admin.html       (已有)
```

---

## ❓ 常见问题排查

### ❌ "找不到模块 flask"

**解决：**
```bash
pip install flask gunicorn
```

### ❌ "找不到 team.json"

**检查：**
1. 文件在项目根目录？
2. 文件名是 `team.json` 不是 `team.json.txt`？
3. 用记事本打开能看到JSON内容？

### ❌ "Team 不存在"

**解决：**

确保生成兑换码时的Team名和team.json中的邮箱匹配

```
team.json中: "email": "admin@company.com"
生成时用:    --team admin
```

### ❌ "兑换后没收到邮件"

**检查：**
1. 垃圾邮件文件夹
2. 管理后台 → 兑换记录 → 查看状态
3. Team统计 → 检查是否还有空位

### ❌ "端口5000被占用"

**解决：**

修改 `config.toml`:
```toml
port = 5001  # 改成其他端口
```

然后访问: http://localhost:5001/

---

## 🎯 成功标志

✅ 运行 `python start_redemption.py` 没有报错
✅ 可以访问 http://localhost:5000/
✅ 可以访问 http://localhost:5000/admin
✅ 输入邮箱+兑换码后显示"兑换成功"
✅ 邮箱收到ChatGPT邀请邮件

**如果以上都✅，恭喜你成功了！** 🎊

---

## 💡 使用提示

### 日常使用

**每次启动电脑后：**
```bash
cd 项目目录
python start_redemption.py
```

**生成更多兑换码：**
```bash
python code_generator.py generate --team admin --count 100
```

**查看统计：**
```bash
python code_generator.py stats
```

**停止服务：**
```
在运行窗口按 Ctrl+C
```

### 数据备份

**重要文件：**
```
redemption.db     ← 所有数据都在这里
config.toml       ← 你的配置
team.json         ← Team凭证
```

**备份方法：**
```bash
# 直接复制这三个文件到安全的地方
copy redemption.db backup/
copy config.toml backup/
copy team.json backup/
```

---

## 📚 下一步

- 📖 查看 [START_HERE.md](START_HERE.md) - 5分钟快速指南
- 📘 查看 [REDEMPTION_GUIDE.md](REDEMPTION_GUIDE.md) - 完整功能文档
- 🐳 查看 [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) - Docker部署

---

## 🆘 需要帮助？

- 查看 [常见问题](#-常见问题排查)
- 阅读详细文档
- 检查终端的错误信息

---

祝你使用愉快！🚀
