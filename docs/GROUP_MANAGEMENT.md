# 兑换码分组管理实现方案

## 功能概述

为兑换码添加分组管理功能，方便批量管理和统计。

## 数据库设计

### 1. 添加分组字段

在 `redemption_codes` 表添加 `group_name` 字段：

```sql
ALTER TABLE redemption_codes ADD COLUMN group_name VARCHAR(100);
CREATE INDEX IF NOT EXISTS idx_codes_group ON redemption_codes(group_name);
```

### 2. 创建分组表（可选）

```sql
CREATE TABLE IF NOT EXISTS code_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    color VARCHAR(20) DEFAULT '#000000'
);
```

## API 设计

### 1. 分组管理 API

#### 创建分组
```
POST /api/admin/groups
{
  "name": "VIP用户",
  "description": "VIP用户专用兑换码",
  "color": "#ff0000"
}
```

#### 获取分组列表
```
GET /api/admin/groups
```

#### 更新分组
```
PUT /api/admin/groups/{group_id}
```

#### 删除分组
```
DELETE /api/admin/groups/{group_id}
```

### 2. 兑换码分组 API

#### 生成带分组的兑换码
```
POST /api/admin/codes/generate
{
  "team_name": "TeamA",
  "count": 10,
  "group_name": "VIP用户"
}
```

#### 批量设置分组
```
POST /api/admin/codes/batch-group
{
  "code_ids": [1, 2, 3],
  "group_name": "VIP用户"
}
```

#### 按分组筛选
```
GET /api/admin/codes?group=VIP用户
```

## 前端设计

### 1. 分组管理界面

在管理后台添加"分组管理" Tab：

- 分组列表（名称、描述、兑换码数量、颜色标签）
- 添加/编辑/删除分组
- 分组统计（总数、已用、剩余）

### 2. 兑换码列表增强

- 添加分组筛选下拉框
- 显示分组标签（带颜色）
- 批量操作：设置分组

### 3. 生成兑换码增强

- 添加分组选择下拉框
- 支持创建新分组

## 实现步骤

### Phase 1: 数据库迁移

```python
# database.py
def migrate_add_group_support(self):
    """添加分组支持"""
    with self.get_connection() as conn:
        cursor = conn.cursor()

        # 检查是否已有 group_name 字段
        cursor.execute("PRAGMA table_info(redemption_codes)")
        cols = {row["name"] for row in cursor.fetchall()}

        if "group_name" not in cols:
            cursor.execute("ALTER TABLE redemption_codes ADD COLUMN group_name VARCHAR(100)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_codes_group ON redemption_codes(group_name)")
            log.info("已添加 group_name 字段到 redemption_codes 表")

        # 创建分组表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS code_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) UNIQUE NOT NULL,
                description TEXT,
                color VARCHAR(20) DEFAULT '#000000',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
```

### Phase 2: 后端 API

```python
# web_server.py

@app.route("/api/admin/groups", methods=["GET"])
@require_admin
def get_groups():
    """获取分组列表"""
    groups = db.list_code_groups()
    return jsonify({"success": True, "groups": groups})

@app.route("/api/admin/groups", methods=["POST"])
@require_admin
def create_group():
    """创建分组"""
    data = request.json
    name = data.get("name")
    description = data.get("description", "")
    color = data.get("color", "#000000")

    if not name:
        return jsonify({"success": False, "error": "分组名称不能为空"}), 400

    try:
        group_id = db.create_code_group(name, description, color)
        return jsonify({"success": True, "group_id": group_id})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/admin/codes/batch-group", methods=["POST"])
@require_admin
def batch_set_group():
    """批量设置分组"""
    data = request.json
    code_ids = data.get("code_ids", [])
    group_name = data.get("group_name")

    if not code_ids:
        return jsonify({"success": False, "error": "请选择兑换码"}), 400

    try:
        db.batch_update_code_group(code_ids, group_name)
        return jsonify({"success": True, "message": f"已更新 {len(code_ids)} 个兑换码的分组"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
```

### Phase 3: 数据库方法

```python
# database.py

def list_code_groups(self):
    """获取所有分组"""
    with self.get_connection() as conn:
        cursor = conn.execute("""
            SELECT
                g.*,
                COUNT(c.id) as code_count,
                SUM(CASE WHEN c.status = 'active' THEN 1 ELSE 0 END) as active_count
            FROM code_groups g
            LEFT JOIN redemption_codes c ON c.group_name = g.name
            GROUP BY g.id
            ORDER BY g.created_at DESC
        """)
        return [dict(row) for row in cursor.fetchall()]

def create_code_group(self, name, description="", color="#000000"):
    """创建分组"""
    with self.get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO code_groups (name, description, color)
            VALUES (?, ?, ?)
        """, (name, description, color))
        return cursor.lastrowid

def batch_update_code_group(self, code_ids, group_name):
    """批量更新兑换码分组"""
    with self.get_connection() as conn:
        placeholders = ','.join('?' * len(code_ids))
        conn.execute(f"""
            UPDATE redemption_codes
            SET group_name = ?
            WHERE id IN ({placeholders})
        """, [group_name] + code_ids)
```

### Phase 4: 前端界面

```html
<!-- 分组管理 Tab -->
<div id="groups" class="tab-pane" style="display: none;">
    <div class="filter-bar">
        <div class="filter-left">
            <h3>分组管理</h3>
        </div>
        <div class="filter-right">
            <button class="btn" onclick="showCreateGroupModal()">创建分组</button>
        </div>
    </div>

    <div id="groupsTable">
        <div class="loading">加载中...</div>
    </div>
</div>

<!-- 兑换码列表添加分组筛选 -->
<div class="filter-bar">
    <select id="groupFilter" onchange="loadCodes()">
        <option value="">全部分组</option>
        <!-- 动态加载分组选项 -->
    </select>
</div>
```

```javascript
// 加载分组列表
async function loadGroups() {
    const response = await fetch('/api/admin/groups');
    const result = await response.json();

    if (result.success) {
        renderGroupsTable(result.groups);
        updateGroupFilter(result.groups);
    }
}

// 渲染分组表格
function renderGroupsTable(groups) {
    let html = '<table class="data-table"><thead><tr>';
    html += '<th>分组名称</th>';
    html += '<th>描述</th>';
    html += '<th>兑换码数量</th>';
    html += '<th>活跃数量</th>';
    html += '<th>操作</th>';
    html += '</tr></thead><tbody>';

    groups.forEach(group => {
        html += '<tr>';
        html += `<td><span class="group-tag" style="background: ${group.color}">${group.name}</span></td>`;
        html += `<td>${group.description || '-'}</td>`;
        html += `<td>${group.code_count}</td>`;
        html += `<td>${group.active_count}</td>`;
        html += `<td>
            <button onclick="editGroup(${group.id})">编辑</button>
            <button onclick="deleteGroup(${group.id})">删除</button>
        </td>`;
        html += '</tr>';
    });

    html += '</tbody></table>';
    document.getElementById('groupsTable').innerHTML = html;
}

// 批量设置分组
async function batchSetGroup() {
    const selectedCodes = getSelectedCodes(); // 获取选中的兑换码
    const groupName = document.getElementById('batchGroupSelect').value;

    if (selectedCodes.length === 0) {
        alert('请选择兑换码');
        return;
    }

    const response = await fetch('/api/admin/codes/batch-group', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            code_ids: selectedCodes,
            group_name: groupName
        })
    });

    const result = await response.json();

    if (result.success) {
        showMessage(result.message, 'success');
        loadCodes();
    } else {
        showMessage(result.error, 'error');
    }
}
```

## 使用场景

### 场景 1: VIP 用户专属码

```
1. 创建分组 "VIP用户"
2. 生成 100 个兑换码，分组设为 "VIP用户"
3. 在分组列表中查看使用情况
4. 导出该分组的兑换码
```

### 场景 2: 活动兑换码

```
1. 创建分组 "双十一活动"
2. 生成 1000 个兑换码
3. 活动结束后，批量禁用该分组的所有兑换码
```

### 场景 3: 渠道管理

```
1. 创建分组 "渠道A", "渠道B", "渠道C"
2. 为每个渠道生成专属兑换码
3. 统计各渠道的兑换情况
```

## 统计功能

### 分组统计

```sql
SELECT
    group_name,
    COUNT(*) as total_codes,
    SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active_codes,
    SUM(used_count) as total_uses,
    SUM(max_uses) as max_uses
FROM redemption_codes
WHERE group_name IS NOT NULL
GROUP BY group_name
```

### 分组兑换趋势

```sql
SELECT
    c.group_name,
    DATE(r.redeemed_at) as date,
    COUNT(*) as redemptions
FROM redemptions r
JOIN redemption_codes c ON r.code_id = c.id
WHERE c.group_name IS NOT NULL
GROUP BY c.group_name, DATE(r.redeemed_at)
ORDER BY date DESC
```

## 导出功能

支持按分组导出兑换码：

```python
@app.route("/api/admin/codes/export")
@require_admin
def export_codes():
    group_name = request.args.get("group")
    format = request.args.get("format", "csv")  # csv, json, txt

    codes = db.list_codes(group_name=group_name)

    if format == "csv":
        # 生成 CSV
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Code', 'Group', 'Team', 'Status', 'Used', 'Max Uses'])
        for code in codes:
            writer.writerow([code['code'], code['group_name'], ...])
        return output.getvalue(), 200, {'Content-Type': 'text/csv'}
```

## 优先级

**高优先级**:
1. 数据库迁移（添加 group_name 字段）
2. 基本 API（创建分组、设置分组、筛选）
3. 前端界面（分组筛选、显示）

**中优先级**:
4. 分组管理界面
5. 批量操作
6. 统计功能

**低优先级**:
7. 导出功能
8. 分组颜色标签
9. 高级统计

## 实现时间估算

- Phase 1 (数据库): 1 小时
- Phase 2 (后端 API): 2 小时
- Phase 3 (前端界面): 3 小时
- Phase 4 (测试优化): 1 小时

**总计**: 约 7 小时

## 兼容性

- 向后兼容：现有兑换码的 `group_name` 为 NULL
- 不影响现有功能
- 可选功能，不使用分组也能正常工作
