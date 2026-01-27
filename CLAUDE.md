# CLAUDE.md - Team-DH 项目工作日志

> 本文档用于记录 Claude 与项目的协作历史、当前任务、决策记录和常见问题

**最后更新**: 2026-01-27 (完成前端用户体验优化)
**项目状态**: 🟢 活跃开发中

---

## 📋 目录

- [项目概览](#项目概览)
- [当前任务](#当前任务)
- [已完成任务](#已完成任务)
- [决策记录](#决策记录)
- [常见问题](#常见问题)
- [技术架构](#技术架构)
- [开发指南](#开发指南)

---

## 🎯 项目概览

### 项目简介
Team-DH 是一个面向 Zeabur/容器部署的 **ChatGPT Team 席位兑换码系统**，集成了：
- 兑换码管理系统（生成、启用/禁用、删除）
- 用户兑换流程（邮箱 + 兑换码）
- 自动到期转移系统（按月自动转移到新 Team）
- 管理后台（Team 管理、兑换记录、统计）
- 原批量注册系统（保留但默认不启用）

### 核心价值
- **席位复用**: 通过自动转移实现席位的循环利用
- **灵活管理**: 支持多 Team 管理、兑换码批量生成
- **安全可靠**: 并发锁、IP 限流、审计日志
- **云原生**: 支持 Docker、Zeabur、Railway 等平台

### 技术栈
- **后端**: Python 3.12+, Flask, SQLite
- **前端**: HTML/CSS/JavaScript (Vanilla)
- **部署**: Docker, Gunicorn, Nginx
- **外部 API**: ChatGPT Team API, Email Service, CRS Service

---

## 📝 当前任务

### 正在进行
> 暂无进行中的任务

### 待办事项

**功能实现** (部分完成，详见 docs/IMPLEMENTATION_STATUS.md):
1. Team 开通时间识别 (后端 100%，前端待完成，约 1-2 小时)
2. 兑换码分组管理 (设计 100%，实现待完成，约 7 小时)
3. 转移服务优化 (审查 100%，实现待完成，约 4-6 小时)

---

## ✅ 已完成任务

### 2026-01-27

- [x] **Team 开通时间识别（后端）** (完成时间: 2026-01-27)
  - ✅ 数据库字段添加
    - `teams_stats.created_at`: Team 创建时间
    - `teams_stats.first_seen_at`: 首次添加时间
    - `teams_stats.created_at_source`: 数据来源标识
  - ✅ 数据库方法实现
    - `update_team_created_at()`: 更新创建时间
    - `get_team_created_at()`: 获取创建时间
    - `get_earliest_redemption()`: 获取最早兑换时间
    - `get_earliest_lease()`: 获取最早加入时间
  - ✅ Team Service 方法
    - `estimate_team_created_time()`: 推断创建时间（3种数据源）
    - `sync_team_created_time()`: 同步创建时间
    - `get_organization_info()`: API 框架
  - ✅ API 接口
    - `POST /api/admin/teams/<index>/sync-created-time`: 同步接口
    - `GET /api/admin/stats`: 返回创建时间和来源

**技术实现**:
- 多数据源推断：最早兑换记录、最早加入时间、首次添加时间
- 数据来源标识：api/estimated_*/first_seen/first_code/unknown
- 准确度等级系统（待前端实现）

**文件修改**:
- `database.py`: 添加字段和方法
- `team_service.py`: 添加推断和同步逻辑
- `web_server.py`: 添加 API 接口

**剩余工作**:
- 前端界面（Team 统计表格、同步按钮、数据来源显示）
- 预计 1-2 小时

- [x] **代码审查和设计文档** (完成时间: 2026-01-27)
  - ✅ 转移服务代码审查
    - 发现 5 个潜在问题（竞态条件、错误处理、重试逻辑、事务保护、Team 选择）
    - 提出 4 个优化建议（健康检查、席位检查、前置检查、错误恢复）
    - 编写测试建议（并发测试、失败恢复、边界条件）
  - ✅ 兑换码分组管理设计
    - 完整的数据库设计（group_name 字段 + code_groups 表）
    - API 设计（创建/更新/删除分组、批量操作、筛选）
    - 前端界面设计（分组管理 Tab、筛选、标签）
    - 使用场景和统计功能
    - 分 4 个 Phase 的实现计划
  - ✅ Team 开通时间识别方案
    - 3 种数据来源（ChatGPT API、本地记录、推断方法）
    - 完整的实现方案（数据库、API、前端）
    - 准确度等级系统（高/中/低）
    - 自动同步和使用场景
    - 分 4 个 Phase 的实现计划

**设计文档**:
```
docs/
├── TRANSFER_REVIEW.md      # 转移服务代码审查报告
├── GROUP_MANAGEMENT.md      # 兑换码分组管理实现方案
└── TEAM_CREATED_TIME.md     # Team 开通时间识别方案
```

**审查发现**:
- 潜在竞态条件（席位检查和邀请之间）
- 错误处理不完整（静默失败）
- 缺少最大重试次数限制
- 缺少事务保护
- Team 选择算法可优化

**设计亮点**:
- 兑换码分组：支持 VIP、活动、渠道等场景
- Team 时间：多数据源 + 准确度等级
- 向后兼容：不影响现有功能
- 分阶段实现：可按优先级逐步完成

- [x] **文档完善** (完成时间: 2026-01-27)
  - ✅ 添加 API 文档
    - 完整的 REST API 文档（用户 API + 管理员 API + 监控 API）
    - 请求/响应示例
    - 错误码说明
    - 限流规则
    - 最佳实践
  - ✅ 添加故障排查指南
    - 启动问题（端口占用、Python 版本、依赖缺失）
    - 兑换问题（兑换码无效、IP 限流、席位不足）
    - 转移问题（转移失败、转移超时、加入时间未同步）
    - 数据库问题（数据库锁定、损坏、过大）
    - 性能问题（响应缓慢、内存占用）
    - 监控告警处理
    - 日志分析
    - 紧急恢复流程
  - ✅ 添加性能优化指南
    - 数据库优化（索引、查询、配置、清理）
    - 应用层优化（连接池、缓存、并发控制、异步处理）
    - 部署优化（Gunicorn、Nginx、Docker）
    - 监控和调优（性能监控、日志分析、压力测试）
    - 性能基准（硬件要求、性能指标、容量规划）
    - 优化检查清单

**文档结构**:
```
docs/
├── API.md              # API 文档（400+ 行）
├── TROUBLESHOOTING.md  # 故障排查指南（500+ 行）
└── PERFORMANCE.md      # 性能优化指南（600+ 行）
```

**文档特点**:
- 详细的代码示例
- 清晰的步骤说明
- 实用的命令和 SQL
- 完整的检查清单
- 性能基准数据

- [x] **增强监控和告警** (完成时间: 2026-01-27)
  - ✅ 添加 Team 席位不足告警
    - 席位使用率 ≥ 95%：严重告警
    - 席位使用率 ≥ 85%：警告告警
    - 自动检测所有配置的 Team
  - ✅ 添加转移失败告警
    - 检测失败状态的租约（24小时内）
    - 检测长时间处于 transferring 状态的租约（超过1小时）
    - 记录详细错误信息
  - ✅ 添加数据库性能监控
    - 数据库文件大小监控（超过500MB告警）
    - 查询性能监控（超过1秒告警）
    - 大表数据量监控（超过10万条记录）
  - ✅ 系统健康检查
    - 兑换活动监控
    - 待处理租约统计
    - 到期租约检测
  - ✅ 管理后台集成
    - 新增"监控告警" Tab
    - 告警统计卡片（严重/错误/警告/信息）
    - 告警列表（支持级别和分类筛选）
    - 手动触发检查功能
    - 标记告警为已解决

**技术实现**:
- 创建 `monitor.py` 模块（AlertManager + Monitor）
- 数据库表：`system_alerts`（告警记录）
- 后台线程：每5分钟自动检查（可配置）
- RESTful API：4个监控接口
- 前端界面：实时告警展示和管理

**配置选项**:
- `MONITOR_ENABLED`: 启用/禁用监控（默认 true）
- `MONITOR_INTERVAL`: 检查间隔秒数（默认 300）

**文件修改**:
- `monitor.py`: 新建监控模块
- `web_server.py`: 集成监控功能 + 添加 API 接口
- `static/admin.html`: 添加监控告警 Tab

- [x] **优化前端用户体验** (完成时间: 2026-01-27)
  - ✅ 添加兑换进度提示
    - 单个兑换页面：4步进度展示（验证兑换码 → 检查席位 → 发送邀请 → 完成）
    - 实时状态更新（进行中、已完成、失败）
    - 动画效果和加载指示器
  - ✅ 优化移动端适配
    - 响应式布局（640px、380px 断点）
    - 移动端字体大小优化（防止 iOS 自动缩放）
    - 导航链接自适应（小屏幕垂直排列）
    - 表单元素和按钮适配
  - ✅ 批量兑换结果展示优化
    - 实时进度条（显示当前兑换进度）
    - 逐个兑换并实时显示结果
    - 结果列表自动滚动到最新
    - 成功/失败统计实时更新
    - 滑入动画效果
  - ✅ **批量兑换功能重构** (新增)
    - 分离式输入：邮箱和兑换码分别填写（两个独立输入框）
    - 自动按行配对：第N行邮箱对应第N行兑换码
    - 实时计数显示：显示邮箱和兑换码数量
    - 数量不匹配警告：自动检测并提示数量不一致
    - 最多支持 20 组批量兑换

**技术亮点**:
- 进度管理：4步状态机（active → completed/error）
- 实时反馈：逐个兑换 + 300ms 延迟防止请求过快
- 移动优先：响应式设计 + 触摸友好
- 用户体验：加载动画 + 自动滚动 + 视觉反馈
- 批量兑换：一对一配对 + 智能解析 + 实时进度

**文件修改**:
- `static/index.html`: 添加进度提示组件 + 移动端适配
- `static/batch.html`: 三种兑换模式 + 实时进度条 + 逐个兑换 + 移动端适配

- [x] **项目分析与文档生成**
  - 完成项目架构深度分析（使用 Explore Agent）
  - 生成 CLAUDE.md 工作日志文档（包含完整架构、决策记录、常见问题）
  - 识别核心模块和数据流（7 个核心服务模块）
  - 整理技术栈和部署架构（Flask + SQLite + Docker）
  - 重写 README.md（添加徽章、功能特性、部署指南、配置说明）
  - 建立工作流程规范（开始工作、完成功能、决策记录、踩坑记录）

**成果**:
- ✅ 创建 CLAUDE.md（约 1000 行，包含完整项目文档）
- ✅ 优化 README.md（从 35 行扩展到 400+ 行）
- ✅ 识别 6 个数据库表和完整状态机
- ✅ 记录 4 个重要技术决策（DR-001 到 DR-004）
- ✅ 整理 5 个常见问题和解决方案

**技术亮点**:
- 并发控制：数据库锁 + 应用层锁
- 自动转移：后台轮询 + 指数退避重试
- 多 worker 支持：固定 SECRET_KEY + 配置自动重载
- 审计日志：完整的 member_lease_events 记录

### 近期提交 (Git Log)
- `1232eab` - fix: align login input and button width with box-sizing
- `6926074` - style: change login button color from blue to black
- `276687b` - Restore CN labels and backfill team added time
- `5187355` - Team tabs: English status labels
- `c835329` - Show team added time (created_at) in stats
- `3659963` - Fix lease delete (route order + DB delete)
- `e89d506` - debug: 添加删除功能调试日志
- `b5e2933` - fix: 增加数据库超时时间,解决删除时 database locked 错误
- `af2408d` - feat: 前端完整实现自动转移权限控制功能
- `5a95ad5` - feat: Team统计添加"添加时间"字段

---

## 🔍 决策记录

### DR-001: 数据库选型 - SQLite
**日期**: 项目初期
**决策**: 使用 SQLite 作为持久化存储
**理由**:
- 无需外部数据库服务，简化部署
- 支持并发读写（通过 WAL 模式）
- 数据量小（< 100GB），性能足够
- 支持事务和锁机制

**权衡**:
- ✅ 部署简单，适合容器化
- ✅ 数据文件可直接备份
- ⚠️ 不适合高并发写入场景（已通过应用层锁解决）
- ⚠️ 不支持分布式（当前不需要）

---

### DR-002: 自动转移架构 - 后台轮询
**日期**: 项目中期
**决策**: 使用后台线程轮询方式实现自动转移
**理由**:
- 简单可靠，无需外部调度器
- 支持多 worker 环境（通过数据库锁协调）
- 可配置轮询间隔（默认 300 秒）

**权衡**:
- ✅ 实现简单，易于调试
- ✅ 无需外部依赖（如 Celery、Redis）
- ⚠️ 精度受限于轮询间隔
- ⚠️ 单进程执行（已通过全局锁保证）

**实现细节**:
- 使用 `threading.Thread` 启动后台 worker
- 通过 `app_locks` 表实现分布式锁
- 支持手动触发（管理后台）

---

### DR-003: Session 管理 - 固定 SECRET_KEY
**日期**: 2026-01-XX
**决策**: 多 worker 环境下必须使用固定 SECRET_KEY
**问题**: Gunicorn 多 worker 场景下，随机 SECRET_KEY 导致登录态在不同 worker 间失效
**解决方案**:
```python
_secret_key = (
    os.getenv("SECRET_KEY")
    or os.getenv("FLASK_SECRET_KEY")
    or config.get("web.secret_key")
)
if not _secret_key:
    _secret_key = secrets.token_hex(32)
    log.warning("未设置 SECRET_KEY，已生成临时 key")
app.secret_key = _secret_key
```

**教训**: 多实例部署时，session 加密密钥必须在所有实例间共享

---

### DR-004: 并发控制 - 数据库锁 + 应用层锁
**日期**: 项目初期
**决策**: 双层锁机制防止超发
**实现**:
1. **数据库锁**: `locked_by`, `locked_until` 字段
2. **应用层锁**: `reserve_code()` 方法原子操作

**流程**:
```python
# 1. 预留兑换码（加锁）
reserve_code(code, lock_id, lock_seconds=120)

# 2. 执行业务逻辑（邀请用户）
invite_to_team(email, team)

# 3. 消费兑换码（解锁）
consume_reserved_code(code, lock_id)
```

**权衡**:
- ✅ 防止并发超发
- ✅ 支持超时自动释放
- ⚠️ 增加复杂度
- ⚠️ 需要处理锁超时场景

---

## ❓ 常见问题

### Q1: 数据库锁定错误 (database is locked)
**问题**: 删除操作时出现 `database is locked` 错误
**原因**: SQLite 默认超时时间过短（5 秒）
**解决方案**:
```python
# database.py
conn = sqlite3.connect(db_path, timeout=30.0)  # 增加到 30 秒
conn.execute("PRAGMA busy_timeout = 30000")    # 30 秒
```

**相关提交**: `b5e2933`

---

### Q2: 前端 JSON 解析错误 (<!DOCTYPE ... is not valid JSON)
**问题**: 管理后台 API 请求返回 HTML 而非 JSON
**原因**: 未登录时被重定向到 `/admin/login`，前端把 HTML 当 JSON 解析
**解决方案**:
```python
@require_admin
def decorated_function(*args, **kwargs):
    if not session.get("admin_logged_in"):
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": "未登录"}), 401
        return redirect(url_for("admin_login"))
```

**教训**: API 接口必须始终返回 JSON，不能重定向到 HTML 页面

---

### Q3: 多 worker 环境下 Team 配置不同步
**问题**: 在一个 worker 中更新 Team 配置，其他 worker 看不到
**原因**: 配置只在启动时加载一次
**解决方案**:
```python
@app.before_request
def _auto_reload_config_if_changed():
    """检查配置文件 mtime，自动 reload"""
    global _last_config_reload_sig
    sig = _config_files_signature()
    if _last_config_reload_sig != sig:
        config.reload_teams()
        _last_config_reload_sig = sig
```

**教训**: 多进程环境下需要主动同步配置变更

---

### Q4: 如何获取用户真实加入时间 (joined_at)?
**问题**: 用户接受邀请后，系统不知道具体时间
**解决方案**: 三种方式
1. **Invites API** (推荐): `GET /api/accounts/{account_id}/invites`
   - 返回 `accepted_at` 时间戳
   - 最准确，但需要 Team 权限

2. **Members API** (备用): `GET /api/accounts/{account_id}/members`
   - 返回 `joined_at` 时间戳
   - 可能有延迟（几分钟）

3. **近似值** (可选): 使用 `invited_at + 5分钟`
   - 配置: `AUTO_TRANSFER_ALLOW_APPROX_JOIN_AT=true`
   - 不准确，仅用于测试

**最佳实践**: 兑换后 60 秒启动后台同步任务

---

### Q5: 如何处理转移失败的席位?
**问题**: 自动转移失败后，席位状态变为 `failed`
**处理方式**:
1. **自动重试**: 指数退避（5m → 10m → 20m → ... → 24h）
2. **手动干预**: 管理后台 → "到期转移" → "强制转移"
3. **查看日志**: `member_lease_events` 表记录详细错误

**预防措施**:
- 确保 Team Token 有效
- 检查 Team 席位是否充足
- 验证网络连接

---

## 🏗️ 技术架构

### 系统架构图
```
┌─────────────────────────────────────────────────────────┐
│         Web Server (Flask) - web_server.py              │
│  - User redemption API (/api/redeem)                    │
│  - Admin dashboard (/admin/*)                           │
│  - Session management & authentication                  │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│    Business Logic Services                              │
│  - RedemptionService (redemption_service.py)            │
│  - TransferService (transfer_service.py)                │
│  - JoinSyncService (join_sync_service.py)               │
│  - TeamService (team_service.py)                        │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│    Data Layer (database.py)                             │
│  - SQLite database management                           │
│  - Redemption codes CRUD                                │
│  - Member leases & events                               │
│  - Team statistics                                      │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│    External APIs                                        │
│  - ChatGPT Team API (invites, members, remove)          │
│  - Email service (batch_create_emails)                  │
│  - CRS service (crs_add_account)                        │
└─────────────────────────────────────────────────────────┘
```

### 核心模块

#### 1. 配置管理 (config.py)
- 加载 `config.toml`, `team.json`, 环境变量
- 管理 Team 凭证（Token, Account ID, Org ID）
- 提供辅助函数：`resolve_team()`, `get_random_email()`

#### 2. 数据库层 (database.py)
**表结构**:
- `redemption_codes`: 兑换码（状态、使用次数、自动转移标志）
- `redemptions`: 兑换记录（邮箱、兑换码、时间戳）
- `teams_stats`: Team 统计（总席位、已用、待定）
- `member_leases`: 成员租约（邮箱、Team、加入时间、到期时间、状态）
- `member_lease_events`: 审计日志（状态变更、转移记录）
- `app_locks`: 全局锁（多 worker 协调）

**关键方法**:
- `reserve_code()` / `consume_reserved_code()`: 并发安全的兑换码预留
- `upsert_member_lease()`: 创建/更新租约
- `list_due_member_leases()`: 获取到期租约
- `update_member_lease_transfer_success()`: 标记转移成功

#### 3. 兑换服务 (redemption_service.py)
**流程**:
1. 验证邮箱格式
2. 检查 IP 限流（默认 10 次/小时）
3. 检查邮箱是否已兑换
4. 预留兑换码（数据库锁）
5. 检查 Team 席位
6. 创建兑换记录
7. 邀请用户到 Team
8. 创建成员租约（如果启用自动转移）
9. 触发后台 join_at 同步

#### 4. 转移服务 (transfer_service.py)
**工作流**:
1. 同步待定租约的 join_at 时间
2. 查找到期租约（`expires_at <= now`）
3. 选择下一个 Team（轮询，避免当前 Team）
4. 从旧 Team 移除成员（如果启用）
5. 邀请到新 Team
6. 更新租约状态为 "pending"（等待接受）

**后台 Worker**:
- 每 300 秒轮询一次（可配置）
- 使用全局锁防止多 worker 重复执行
- 支持手动触发

#### 5. 加入同步服务 (join_sync_service.py)
**目的**: 获取用户实际接受邀请的时间
**方法**:
1. 查询 ChatGPT Invites API
2. 查找邮箱对应的邀请记录
3. 提取 `accepted_at` 时间戳
4. 更新 `lease.joined_at` 和 `expires_at`
5. 状态从 "pending" 变为 "active"

**备用方案**: 如果 Invites API 不可用，使用 Members API

#### 6. Team 服务 (team_service.py)
**功能**:
- `batch_invite_to_team()`: 批量邀请
- `get_invite_status_for_email()`: 检查邀请状态
- `get_member_info_for_email()`: 获取成员信息
- `remove_member_by_email()`: 移除成员
- `get_team_stats()`: 获取 Team 容量信息

**特性**:
- HTTP 会话复用
- 重试逻辑（5 次，指数退避）
- 错误处理和日志记录

#### 7. Web 服务器 (web_server.py)
**用户 API**:
- `POST /api/redeem`: 单次兑换
- `POST /api/redeem/batch`: 批量兑换（最多 20 个）
- `GET /api/verify`: 验证兑换码信息

**管理 API** (需要认证):
- `GET /api/admin/stats`: 仪表板统计
- `GET /api/admin/codes`: 兑换码列表
- `GET /api/admin/redemptions`: 兑换记录
- `GET /api/admin/leases`: 成员租约
- `POST /api/admin/leases/sync`: 同步 join_at
- `POST /api/admin/leases/transfer`: 手动转移
- `POST /api/admin/codes/generate`: 生成兑换码

**特性**:
- Session 认证（固定 SECRET_KEY）
- IP 检测（支持 X-Forwarded-For）
- 配置文件自动重载
- 后台转移 worker 线程

### 数据流图

#### 兑换流程
```
用户提交 (email + code)
    ↓
验证邮箱格式
    ↓
检查 IP 限流
    ↓
检查邮箱是否已兑换
    ↓
预留兑换码（加锁）
    ↓
检查 Team 席位
    ↓
创建兑换记录
    ↓
邀请到 Team
    ↓
创建成员租约
    ↓
后台同步 join_at (60s 后)
    ↓
返回成功
```

#### 自动转移流程
```
后台 Worker (每 300s)
    ↓
获取全局锁
    ↓
同步待定租约的 join_at
    ↓
查找到期租约
    ↓
For each 到期租约:
    ├─ 标记为 "transferring"
    ├─ 选择下一个 Team
    ├─ 从旧 Team 移除
    ├─ 邀请到新 Team
    ├─ 更新租约（team, invited_at, status=pending）
    ├─ 记录事件
    └─ 释放锁
    ↓
等待用户接受邀请
    ↓
后台同步 join_at
    ↓
状态变为 "active"
    ↓
计算新的 expires_at
```

### 状态机

#### 租约状态转换
```
pending (等待接受邀请)
  ↓
active (用户已接受，租约生效)
  ↓
transferring (转移中)
  ↓
pending (新 Team，等待接受)
  ↓
active (循环重复)

OR

failed (转移失败，需要人工干预)
cancelled (用户取消)
```

#### 兑换码状态
```
active (可用)
  ↓
used_up (用尽)

OR

disabled (管理员禁用)
expired (过期)
deleted (删除)
```

---

## 🛠️ 开发指南

### 本地开发环境搭建

#### 1. 克隆项目
```bash
git clone <repository-url>
cd team-dh
```

#### 2. 安装依赖
```bash
# 使用 uv (推荐)
uv sync

# 或使用 pip
pip install -r requirements.txt
```

#### 3. 配置文件
```bash
# 复制示例配置
cp config.toml.example config.toml
cp team.json.example team.json
cp .env.example .env

# 编辑配置文件
vim config.toml  # 配置 Team 信息
vim team.json    # 配置 Team Token
```

#### 4. 初始化数据库
```bash
python init_db.py
```

#### 5. 启动服务
```bash
# 开发模式
python web_server.py

# 生产模式
gunicorn -w 4 -b 0.0.0.0:5000 web_server:app
```

#### 6. 访问
- 兑换页面: http://localhost:5000/
- 管理后台: http://localhost:5000/admin

### 常用命令

#### 生成兑换码
```bash
# 生成 10 个兑换码
python code_generator.py generate --team TeamA --count 10

# 查看所有兑换码
python code_generator.py list

# 启用/禁用兑换码
python code_generator.py enable <code>
python code_generator.py disable <code>

# 删除兑换码
python code_generator.py delete <code>

# 导出统计
python code_generator.py stats --export stats.csv
```

#### 数据库操作
```bash
# 查看数据库
sqlite3 /data/redemption.db

# 查看兑换码
SELECT * FROM redemption_codes;

# 查看租约
SELECT * FROM member_leases;

# 查看事件日志
SELECT * FROM member_lease_events ORDER BY created_at DESC LIMIT 10;
```

#### Docker 部署
```bash
# 构建镜像
docker build -t team-dh:latest .

# 运行容器
docker run -d \
  -p 5000:5000 \
  -v /path/to/data:/data \
  -e ADMIN_PASSWORD=your-password \
  -e SECRET_KEY=your-secret-key \
  team-dh:latest
```

### 代码规范

#### 文件命名
- 模块文件: `snake_case.py`
- 配置文件: `lowercase.toml`, `lowercase.json`
- 文档文件: `UPPERCASE.md`

#### 代码风格
- 遵循 PEP 8
- 使用 4 空格缩进
- 最大行长度 120 字符
- 使用类型注解（Python 3.12+）

#### 提交规范
```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type**:
- `feat`: 新功能
- `fix`: 修复 bug
- `docs`: 文档更新
- `style`: 代码格式（不影响功能）
- `refactor`: 重构
- `test`: 测试
- `chore`: 构建/工具链

**示例**:
```
feat(transfer): add manual transfer API

- Add /api/admin/leases/transfer endpoint
- Support force transfer without expiration check
- Add event logging

Closes #123
```

### 调试技巧

#### 1. 启用详细日志
```python
# logger.py
log.setLevel(logging.DEBUG)
```

#### 2. 查看 SQL 查询
```python
# database.py
conn.set_trace_callback(print)  # 打印所有 SQL
```

#### 3. 测试自动转移
```bash
# 手动触发一次转移
curl -X POST http://localhost:5000/api/admin/leases/transfer \
  -H "Cookie: session=..." \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com"}'
```

#### 4. 模拟到期
```sql
-- 将租约设置为已到期
UPDATE member_leases
SET expires_at = datetime('now', '-1 day')
WHERE email = 'user@example.com';
```

### 测试

#### 单元测试
```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_redemption.py

# 覆盖率报告
pytest --cov=. --cov-report=html
```

#### 集成测试
```bash
# 测试兑换流程
curl -X POST http://localhost:5000/api/redeem \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "code": "TEST-1234-5678-9ABC"}'

# 测试管理后台
curl http://localhost:5000/api/admin/stats \
  -H "Cookie: session=..."
```

### 性能优化

#### 1. 数据库优化
```sql
-- 创建索引
CREATE INDEX idx_leases_status_expires ON member_leases(status, expires_at);
CREATE INDEX idx_codes_status ON redemption_codes(status);
CREATE INDEX idx_events_email ON member_lease_events(email);

-- 启用 WAL 模式
PRAGMA journal_mode=WAL;
```

#### 2. 缓存配置
```python
# config.py
@lru_cache(maxsize=128)
def get_team_config(team_name: str):
    return _load_team_config(team_name)
```

#### 3. 连接池
```python
# team_service.py
session = requests.Session()
adapter = HTTPAdapter(max_retries=5, pool_connections=10, pool_maxsize=20)
session.mount('https://', adapter)
```

---

## 📚 相关文档

### 项目文档
- [README.md](README.md) - 项目概览和快速开始
- [CONFIG_GUIDE.md](CONFIG_GUIDE.md) - 配置指南
- [AUTO_TRANSFER_FLOW.md](AUTO_TRANSFER_FLOW.md) - 自动转移流程
- [REDEMPTION_GUIDE.md](REDEMPTION_GUIDE.md) - 兑换系统指南
- [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) - Docker 部署指南

### API 文档
- ChatGPT Team API: https://platform.openai.com/docs/api-reference/teams
- Flask 文档: https://flask.palletsprojects.com/
- SQLite 文档: https://www.sqlite.org/docs.html

---

## 📞 联系方式

- **项目仓库**: [GitHub](https://github.com/nosift/team-dh)
- **问题反馈**: [Issues](https://github.com/nosift/team-dh/issues)
- **许可证**: MIT License

---

## 📝 工作流程

### 开始工作时
1. 更新 [当前任务](#当前任务) 部分
2. 记录开始时间和目标

### 完成功能时
1. 将任务从 "当前任务" 移到 [已完成任务](#已完成任务)
2. 记录完成时间和相关提交

### 做重要决定时
1. 在 [决策记录](#决策记录) 中添加新条目
2. 使用格式: `DR-XXX: 决策标题`
3. 包含: 日期、决策、理由、权衡

### 踩坑时
1. 在 [常见问题](#常见问题) 中添加新条目
2. 使用格式: `Q-XXX: 问题描述`
3. 包含: 问题、原因、解决方案、教训

### 结束工作时
1. 让 Claude 总结今天的进度
2. 更新 "最后更新" 时间
3. 规划明天的任务

---

**文档版本**: v1.0.0
**生成时间**: 2026-01-27
**生成工具**: Claude Code (Sonnet 4.5)
