# Team 开通时间识别方案

## 需求分析

识别每个 Team 的开通时间（创建时间），用于：
1. 统计 Team 使用时长
2. 计算 Team 续费时间
3. 监控 Team 生命周期

## 数据来源

### 1. ChatGPT API

#### Organization API
```
GET https://api.openai.com/v1/organization
```

**响应示例**:
```json
{
  "id": "org-xxx",
  "name": "My Organization",
  "created": 1609459200,  // Unix timestamp
  "role": "owner",
  "personal": false
}
```

**优点**:
- 官方 API，数据准确
- 包含创建时间戳

**缺点**:
- 需要 Organization 权限
- 可能需要不同的 Token

#### Account API
```
GET https://api.openai.com/v1/accounts/{account_id}
```

可能包含账户创建时间。

### 2. 本地记录

#### 方案 A: 首次添加时记录

在 `team.json` 或数据库中记录 Team 首次添加的时间：

```json
{
  "teams": [
    {
      "name": "TeamA",
      "account_id": "xxx",
      "created_at": "2026-01-01T00:00:00",  // 首次添加时间
      "openai_created_at": null  // OpenAI 实际创建时间（如果能获取）
    }
  ]
}
```

#### 方案 B: 数据库记录

在 `teams_stats` 表添加字段：

```sql
ALTER TABLE teams_stats ADD COLUMN created_at DATETIME;
ALTER TABLE teams_stats ADD COLUMN first_seen_at DATETIME;
```

- `created_at`: OpenAI 实际创建时间
- `first_seen_at`: 首次添加到系统的时间

### 3. 推断方法

如果无法获取准确时间，可以通过以下方式推断：

#### 方法 1: 最早的兑换记录

```sql
SELECT MIN(redeemed_at) as estimated_created_at
FROM redemptions
WHERE team_name = 'TeamA'
```

#### 方法 2: 最早的成员加入时间

```sql
SELECT MIN(joined_at) as estimated_created_at
FROM member_leases
WHERE team_name = 'TeamA'
```

#### 方法 3: 配置文件修改时间

检查 `team.json` 的 git 历史：

```bash
git log --follow --format=%aI --reverse -- team.json | head -1
```

## 实现方案

### Phase 1: 数据库支持

```python
# database.py

def init_database(self):
    """初始化数据库"""
    # ... 现有代码 ...

    # 添加 Team 创建时间字段
    cursor.execute("PRAGMA table_info(teams_stats)")
    cols = {row["name"] for row in cursor.fetchall()}

    if "created_at" not in cols:
        cursor.execute("ALTER TABLE teams_stats ADD COLUMN created_at DATETIME")
        log.info("已添加 created_at 字段到 teams_stats 表")

    if "first_seen_at" not in cols:
        cursor.execute("ALTER TABLE teams_stats ADD COLUMN first_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP")
        log.info("已添加 first_seen_at 字段到 teams_stats 表")

def update_team_created_at(self, team_name, created_at):
    """更新 Team 创建时间"""
    with self.get_connection() as conn:
        conn.execute("""
            UPDATE teams_stats
            SET created_at = ?
            WHERE team_name = ?
        """, (created_at, team_name))

def get_team_created_at(self, team_name):
    """获取 Team 创建时间"""
    with self.get_connection() as conn:
        cursor = conn.execute("""
            SELECT created_at, first_seen_at
            FROM teams_stats
            WHERE team_name = ?
        """, (team_name,))
        row = cursor.fetchone()
        return dict(row) if row else None
```

### Phase 2: API 集成

```python
# team_service.py

def get_organization_info(team_cfg):
    """获取 Organization 信息（包含创建时间）"""
    org_id = team_cfg.get("org_id")
    token = team_cfg.get("auth_token")

    if not org_id or not token:
        return None

    try:
        response = http_session.get(
            f"https://api.openai.com/v1/organization",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            timeout=REQUEST_TIMEOUT
        )

        if response.status_code == 200:
            data = response.json()
            created_timestamp = data.get("created")

            if created_timestamp:
                from datetime import datetime
                created_at = datetime.fromtimestamp(created_timestamp)
                return {
                    "created_at": created_at,
                    "org_id": data.get("id"),
                    "name": data.get("name")
                }
    except Exception as e:
        log.warning(f"获取 Organization 信息失败: {e}")

    return None

def sync_team_created_time(team_name):
    """同步 Team 创建时间"""
    team_cfg = config.resolve_team(team_name)
    if not team_cfg:
        return False

    # 尝试从 API 获取
    org_info = get_organization_info(team_cfg)

    if org_info and org_info.get("created_at"):
        db.update_team_created_at(team_name, org_info["created_at"])
        log.info(f"已同步 Team {team_name} 的创建时间: {org_info['created_at']}")
        return True

    # 如果 API 失败，尝试推断
    estimated = estimate_team_created_time(team_name)
    if estimated:
        db.update_team_created_at(team_name, estimated)
        log.info(f"已推断 Team {team_name} 的创建时间: {estimated}")
        return True

    return False

def estimate_team_created_time(team_name):
    """推断 Team 创建时间"""
    # 方法 1: 最早的兑换记录
    earliest_redemption = db.get_earliest_redemption(team_name)

    # 方法 2: 最早的成员加入时间
    earliest_lease = db.get_earliest_lease(team_name)

    # 方法 3: first_seen_at
    team_stats = db.get_team_stats(team_name)
    first_seen = team_stats.get("first_seen_at") if team_stats else None

    # 取最早的时间
    times = []
    if earliest_redemption:
        times.append(earliest_redemption)
    if earliest_lease:
        times.append(earliest_lease)
    if first_seen:
        times.append(first_seen)

    return min(times) if times else None
```

### Phase 3: 管理后台

```python
# web_server.py

@app.route("/api/admin/teams/<int:team_index>/sync-created-time", methods=["POST"])
@require_admin
def sync_team_created_time_api(team_index):
    """同步 Team 创建时间"""
    from team_manager import team_manager
    teams = team_manager.get_team_list()

    if team_index < 0 or team_index >= len(teams):
        return jsonify({"success": False, "error": "Team 不存在"}), 404

    team = teams[team_index]
    team_name = team.get("name")

    try:
        from team_service import sync_team_created_time
        success = sync_team_created_time(team_name)

        if success:
            return jsonify({
                "success": True,
                "message": "已同步 Team 创建时间"
            })
        else:
            return jsonify({
                "success": False,
                "error": "无法获取或推断创建时间"
            })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
```

### Phase 4: 前端界面

```html
<!-- Team 统计表格添加创建时间列 -->
<table class="data-table">
    <thead>
        <tr>
            <th>Team</th>
            <th>总席位</th>
            <th>已用</th>
            <th>可用</th>
            <th>创建时间</th>
            <th>使用时长</th>
            <th>操作</th>
        </tr>
    </thead>
    <tbody>
        <!-- 动态渲染 -->
    </tbody>
</table>
```

```javascript
// 渲染 Team 统计
function renderTeamStats(teams) {
    teams.forEach(team => {
        const createdAt = team.created_at ? new Date(team.created_at) : null;
        const usageDays = createdAt ? Math.floor((Date.now() - createdAt.getTime()) / (1000 * 60 * 60 * 24)) : '-';

        html += `<tr>`;
        html += `<td>${team.team_name}</td>`;
        html += `<td>${team.total_seats}</td>`;
        html += `<td>${team.used_seats}</td>`;
        html += `<td>${team.available_seats}</td>`;
        html += `<td>${createdAt ? formatDate(createdAt) : '未知'}</td>`;
        html += `<td>${usageDays !== '-' ? usageDays + ' 天' : '-'}</td>`;
        html += `<td>
            <button onclick="syncTeamCreatedTime(${team.index})">同步时间</button>
        </td>`;
        html += `</tr>`;
    });
}

// 同步 Team 创建时间
async function syncTeamCreatedTime(teamIndex) {
    const response = await fetch(`/api/admin/teams/${teamIndex}/sync-created-time`, {
        method: 'POST'
    });

    const result = await response.json();

    if (result.success) {
        showMessage('已同步 Team 创建时间', 'success');
        loadTeamStats();
    } else {
        showMessage(result.error, 'error');
    }
}
```

## 显示格式

### 1. 绝对时间

```
创建时间: 2026-01-01 00:00:00
```

### 2. 相对时间

```
使用时长: 27 天
```

### 3. 详细信息

```
创建时间: 2026-01-01 00:00:00
首次添加: 2026-01-05 10:30:00
使用时长: 27 天
数据来源: OpenAI API / 推断 / 手动设置
```

## 数据准确性

### 准确度等级

1. **高准确度**: 从 OpenAI API 获取
   - 标记: ✓ 已验证
   - 颜色: 绿色

2. **中准确度**: 从本地记录推断
   - 标记: ~ 推断
   - 颜色: 黄色

3. **低准确度**: 无法确定
   - 标记: ? 未知
   - 颜色: 灰色

### 显示示例

```
TeamA: 2026-01-01 ✓ (已验证)
TeamB: 2026-01-05 ~ (推断)
TeamC: 未知 ? (无数据)
```

## 自动同步

### 定时任务

```python
def sync_all_teams_created_time():
    """同步所有 Team 的创建时间"""
    from team_manager import team_manager
    teams = team_manager.get_team_list()

    for team in teams:
        team_name = team.get("name")
        try:
            sync_team_created_time(team_name)
        except Exception as e:
            log.warning(f"同步 Team {team_name} 创建时间失败: {e}")

# 在监控循环中添加
def monitor_loop():
    while True:
        # ... 现有监控 ...

        # 每天同步一次 Team 创建时间
        if should_sync_team_times():
            sync_all_teams_created_time()

        time.sleep(300)
```

## 使用场景

### 场景 1: 续费提醒

```python
def check_team_renewal():
    """检查 Team 是否需要续费"""
    teams = db.list_teams_with_created_time()

    for team in teams:
        created_at = team.get("created_at")
        if not created_at:
            continue

        # 计算使用时长
        usage_days = (datetime.now() - created_at).days

        # 如果接近 30 天，发送续费提醒
        if usage_days >= 25 and usage_days < 30:
            send_renewal_reminder(team)
```

### 场景 2: 使用统计

```python
def get_team_usage_stats():
    """获取 Team 使用统计"""
    teams = db.list_teams_with_created_time()

    stats = {
        "total_teams": len(teams),
        "avg_usage_days": 0,
        "oldest_team": None,
        "newest_team": None
    }

    # 计算平均使用时长
    usage_days = []
    for team in teams:
        if team.get("created_at"):
            days = (datetime.now() - team["created_at"]).days
            usage_days.append(days)

    if usage_days:
        stats["avg_usage_days"] = sum(usage_days) / len(usage_days)
        stats["oldest_team"] = max(usage_days)
        stats["newest_team"] = min(usage_days)

    return stats
```

## 优先级

**高优先级**:
1. 数据库字段添加
2. 本地记录（first_seen_at）
3. 推断方法实现

**中优先级**:
4. API 集成（Organization API）
5. 前端显示
6. 手动同步功能

**低优先级**:
7. 自动同步
8. 续费提醒
9. 高级统计

## 实现时间估算

- Phase 1 (数据库): 30 分钟
- Phase 2 (API 集成): 2 小时
- Phase 3 (后端 API): 1 小时
- Phase 4 (前端界面): 2 小时

**总计**: 约 5.5 小时

## 注意事项

1. **隐私**: 不要在日志中记录敏感的 Token
2. **性能**: API 调用可能较慢，考虑异步处理
3. **容错**: API 失败时使用推断方法
4. **兼容性**: 向后兼容，现有 Team 的创建时间可能为空
