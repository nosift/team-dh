# 本地快速开始指南

## 🎯 目标

从零开始在本地运行ChatGPT Team兑换码系统，让用户可以通过网页兑换Team席位。

---

## 📋 前置准备

### 需要准备的内容

1. **ChatGPT Team管理员账号** - 用于邀请用户
2. **Python 3.12+** - 运行环境
3. **文本编辑器** - 用于编辑配置文件

---

## 🚀 完整步骤

### 步骤1: 安装Python依赖

打开终端/命令提示符，进入项目目录：

```bash
# Windows
cd d:\vscode_所有项目\team-dh

# Linux/macOS
cd /path/to/team-dh
```

安装依赖：

```bash
pip install flask gunicorn
```

或者一次性安装所有依赖：

```bash
pip install -r requirements.txt
```

---

### 步骤2: 获取Team凭证

这是**最关键的一步**！

#### 2.1 登录ChatGPT Team

1. 打开浏览器
2. 访问 https://chatgpt.com
3. 使用你的Team**管理员账号**登录

#### 2.2 获取凭证信息

登录后，在浏览器新标签页访问：

```
https://chatgpt.com/api/auth/session
```

你会看到类似这样的JSON数据：

```json
{
  "user": {
    "id": "user-xxxxxxxxxx",
    "email": "your-admin@example.com",
    "name": "Your Name",
    ...
  },
  "account": {
    "id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "organizationId": "org-xxxxxxxxxxxxxxxxxxxxxxxx",
    ...
  },
  "accessToken": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIs...(很长一串)"
}
```

#### 2.3 创建team.json文件

在项目根目录创建 `team.json` 文件，内容如下：

```json
[
  {
    "user": {
      "id": "user-xxxxxxxxxx",
      "email": "your-admin@example.com"
    },
    "account": {
      "id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
      "organizationId": "org-xxxxxxxxxxxxxxxxxxxxxxxx"
    },
    "accessToken": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIs..."
  }
]
```

**重要提示：**
- 只需要复制 `user`、`account` 和 `accessToken` 这三个字段
- 把上面的示例值替换成你自己的
- 注意保持JSON格式正确（逗号、引号、括号）

---

### 步骤3: 创建配置文件

#### 3.1 复制配置模板

```bash
# Windows
copy config.toml.example config.toml

# Linux/macOS
cp config.toml.example config.toml
```

#### 3.2 编辑config.toml

用文本编辑器打开 `config.toml`，**至少要修改管理密码**：

找到这一段：

```toml
[web]
# 监听地址 (0.0.0.0 表示接受所有来源的连接)
host = "0.0.0.0"
# 监听端口
port = 5000
# 调试模式 (生产环境请设置为 false)
debug = false
# 管理后台密码 (请务必修改!)
admin_password = "change-me-to-secure-password"  # ← 改成你自己的密码
# 是否启用管理后台
enable_admin = true
```

把 `admin_password` 改成你自己的密码，比如：

```toml
admin_password = "MySecurePassword123!"
```

**其他配置暂时不用改**（邮箱服务、CRS服务等是用于自动注册的，兑换系统不需要）

---

### 步骤4: 初始化数据库

运行初始化脚本：

```bash
python database.py
```

你会看到：

```
✅ 数据库初始化完成
```

这会创建 `redemption.db` 文件。

---

### 步骤5: 生成兑换码

现在生成一些测试兑换码：

```bash
# 生成10个兑换码，绑定到你的Team
# 注意：TeamA 要改成你在team.json中配置的team名称
python code_generator.py generate --team TeamA --count 10
```

**如何知道Team名称？**

Team名称就是你在 `team.json` 中的邮箱@前面的部分。

比如你的邮箱是 `admin@company.com`，Team名称就是 `admin`。

或者可以随便取一个名字，只要后面使用时保持一致即可。

你会看到生成的兑换码：

```
生成的兑换码:
==================================================
1. TEAM-ABCD-1234-EFGH
2. TEAM-WXYZ-5678-IJKL
...
==================================================
✅ 成功生成 10 个兑换码
```

**把这些兑换码复制保存下来**，等下测试要用！

---

### 步骤6: 启动Web服务

#### 方式1: 使用快速启动脚本（推荐）

```bash
python start_redemption.py
```

#### 方式2: 直接启动

```bash
python web_server.py
```

你会看到：

```
🚀 启动Web服务器: http://0.0.0.0:5000
📝 用户兑换页面: http://0.0.0.0:5000/
🔧 管理后台: http://0.0.0.0:5000/admin
🔑 管理密码: MySecurePassword123!
```

---

### 步骤7: 测试兑换功能

#### 7.1 打开用户兑换页面

浏览器访问：

```
http://localhost:5000/
```

你会看到一个漂亮的兑换界面。

#### 7.2 测试兑换

1. **邮箱地址**: 输入你要邀请的邮箱（可以是你的其他邮箱）
2. **兑换码**: 输入刚才生成的兑换码（比如 `TEAM-ABCD-1234-EFGH`）
3. 点击"**立即兑换**"

成功后会显示：

```
✅ 兑换成功！邀请邮件已发送到 your@email.com
```

#### 7.3 查收邮件

到你输入的邮箱查收来自ChatGPT的邀请邮件，点击链接完成注册。

---

### 步骤8: 访问管理后台

#### 8.1 登录

浏览器访问：

```
http://localhost:5000/admin
```

输入你在 `config.toml` 中设置的管理密码。

#### 8.2 查看统计

登录后可以看到：

- **仪表盘** - 总兑换码数、总兑换次数等
- **兑换码管理** - 查看、启用、禁用兑换码
- **兑换记录** - 查看所有用户的兑换历史
- **Team统计** - 查看Team席位使用情况

---

## 📁 最终目录结构

完成后，你的项目目录应该是这样的：

```
team-dh/
├── config.toml              ← 你创建的配置文件
├── team.json                ← 你创建的Team凭证
├── redemption.db            ← 自动生成的数据库
│
├── database.py              ← 已有的代码文件
├── web_server.py            ← 已有的代码文件
├── code_generator.py        ← 已有的代码文件
├── start_redemption.py      ← 已有的代码文件
│
├── static/
│   ├── index.html          ← 用户兑换页面
│   └── admin.html          ← 管理后台
│
└── ...其他文件
```

---

## ✅ 检查清单

启动前确认：

- [ ] 已安装 Python 3.12+
- [ ] 已安装 flask 和 gunicorn
- [ ] 已创建 `team.json` 文件（包含Team凭证）
- [ ] 已创建 `config.toml` 文件（已修改管理密码）
- [ ] 已运行 `python database.py` 初始化数据库
- [ ] 已生成兑换码

启动后确认：

- [ ] 可以访问 http://localhost:5000/
- [ ] 可以访问 http://localhost:5000/admin
- [ ] 可以成功兑换（测试一个邮箱）
- [ ] 邮箱收到ChatGPT邀请邮件

---

## 🎯 完整命令速查

```bash
# 1. 安装依赖
pip install flask gunicorn

# 2. 创建配置
cp config.toml.example config.toml
# 然后编辑 config.toml 修改密码

# 3. 创建team.json
# 访问 https://chatgpt.com/api/auth/session 获取内容

# 4. 初始化数据库
python database.py

# 5. 生成兑换码
python code_generator.py generate --team 你的Team名 --count 10

# 6. 启动服务
python start_redemption.py

# 7. 访问
# 用户页面: http://localhost:5000/
# 管理后台: http://localhost:5000/admin
```

---

## ❓ 常见问题

### Q1: 如何确定Team名称？

有两种方式：

**方式1**: 使用邮箱@前面的部分
```
邮箱: admin@company.com
Team名: admin
```

**方式2**: 随便取一个名字
```
Team名: MyTeam
```

然后在生成兑换码和配置时都用这个名字即可。

### Q2: 找不到team.json怎么办？

确保：
1. `team.json` 文件在项目**根目录**（和 `web_server.py` 同级）
2. 文件名完全是 `team.json`（不是 `team.json.txt`）
3. JSON格式正确（可以用在线JSON验证工具检查）

### Q3: 提示"Team不存在"怎么办？

确保：
1. 生成兑换码时的 `--team` 参数和 `team.json` 中的Team名一致
2. `team.json` 中的 `user.email` 前面的部分就是Team名

比如：
```json
"email": "admin@company.com"  → Team名是 "admin"
```

生成时就要用：
```bash
python code_generator.py generate --team admin --count 10
```

### Q4: 兑换后没收到邮件怎么办？

检查：
1. 邮箱地址是否正确
2. 检查垃圾邮件文件夹
3. 到管理后台查看兑换记录的状态
4. 确认Team还有可用席位

### Q5: 如何查看Team席位？

访问管理后台 → Team统计 标签页，可以看到：
- 总席位数
- 已使用席位
- 待接受邀请
- 可用席位

---

## 🎉 成功了！

如果你看到：

✅ 用户兑换页面可以访问
✅ 输入邮箱和兑换码后显示"兑换成功"
✅ 邮箱收到了ChatGPT邀请邮件
✅ 管理后台可以查看记录

**恭喜！系统已经成功运行了！** 🎊

现在你可以：
1. 生成更多兑换码分发给用户
2. 通过管理后台监控兑换情况
3. 管理Team席位

---

## 📝 下一步

- 阅读 [REDEMPTION_GUIDE.md](REDEMPTION_GUIDE.md) 了解更多功能
- 查看 [QUICK_START.md](QUICK_START.md) 快速命令参考
- 如需Docker部署，参考 [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md)

---

## 💡 小提示

1. **每次重启电脑后**，只需运行 `python start_redemption.py` 即可
2. **数据不会丢失**，都保存在 `redemption.db` 中
3. **兑换码可以随时生成**，运行 `code_generator.py` 即可
4. **查看日志**，终端会显示所有操作记录

祝使用愉快！🚀
