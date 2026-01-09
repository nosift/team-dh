# 到期自动退 Team & 转移（按 join_at 计时）

这份文档说明：
- 功能逻辑是什么
- 需要哪些环境变量
- 如何把某个邮箱“纳入系统”
- 如何在管理后台**可复现**地测试“到期自动退 + 转移”是否有效

适用版本：`team-dh`（管理后台包含「到期转移」页签）。

---

## 1. 这套功能到底做了什么

目标：让某个邮箱加入 Team 后，**从实际入车时间开始计 1 个月**，到期时：
1) 自动退出旧 Team（服务端用 Team 管理员 token 移除该成员）
2) 自动邀请到新的 Team（从你配置的其它 Team 中自动挑选有空位的）
3) 新 Team 需要用户**点击邮件接受邀请**才能真正加入

> 说明：真正“用户自己点退出”无法由服务端替代完成；系统实现“自动退”必须使用管理员权限把成员移除。

---

## 2. join_at / expires_at 的定义（你最关心的）

- `join_at`：系统检测到该邮箱在当前 Team 的邀请状态变成 `accepted/completed` 的时间（来自 ChatGPT invites 列表）。
- 如果 invites 接口无法返回 `accepted/completed`（有些情况下邀请被“转成成员”后不再出现在 invites 列表），系统会退而求其次查询 **members 成员列表**：只要邮箱已经在成员列表中，就认为已加入，并尽量读取成员记录里的 `joined_at/created_at`；若成员记录不提供时间字段，则用“当前时间”近似并在事件里标注为 `joined_fallback`。
- `expires_at`：用 `join_at` 计算的“下个月同日同时间”。
  - 例：`2026-01-07 12:00` → `2026-02-07 12:00`
  - 若目标月无该日：取当月最后一天（如 `1/31 → 2/28 或 2/29`）

如果你在「到期转移」看到：
- `status=awaiting_join` 且 `join_at=-`：表示用户还没接受邀请，或系统还没同步到 invites 的 accepted 状态。
- `expires_at=待同步`：表示等待 join_at 确认后再以 join_at 为准。

重要提醒（非常容易误解）：
- “邀请成功/拉入 Team”通常只代表**邀请已发送**，并不等于用户已点击邮件接受加入。
- 只有在用户确实成为成员后，系统才能有可靠的 `join_at`，从而开始按月计时。

---

## 3. 必要前提

1) 至少配置 **2 个 Team**（否则无法“转移到新 Team”）
2) Team 的 `accessToken` 必须是管理员可用 token（能邀请、能查询 invites；要自动退还需要能移除成员）
3) 数据必须持久化（否则重启后历史租约会丢）
   - 推荐 Zeabur 挂载 Volume 到 `/data`
   - `REDEMPTION_DATABASE_FILE=/data/redemption.db`

---

## 4. Zeabur 环境变量（建议这样填）

核心（你截图里大部分已经有）：

```env
REDEMPTION_DATABASE_FILE=/data/redemption.db
TRUST_PROXY=true
REDEMPTION_CODE_LOCK_SECONDS=120

AUTO_TRANSFER_ENABLED=true
AUTO_TRANSFER_POLL_SECONDS=300
AUTO_TRANSFER_TERM_MONTHS=1
AUTO_TRANSFER_AUTO_LEAVE_OLD_TEAM=true

TZ=Asia/Shanghai
SECRET_KEY=<固定值，必须设置>
```

注意：
- Zeabur Raw Variables 必须使用 `KEY=value`，不要写 `KEY = value`（有空格会导致不生效）
- `SECRET_KEY` 必须固定（多 worker / 重启否则 session 和行为会乱）

---

## 5. 如何把某个邮箱“纳入系统”

方式 A（推荐）：走正常兑换
1) 在后台为某 Team 生成兑换码
2) 用户用邮箱兑换
3) 用户点击邮件接受邀请
4) 到后台「到期转移」查看该邮箱租约：应出现该邮箱，且 join_at 会被同步出来

方式 B：后台手动录入（适合“老用户补录”）
1) 后台 → 「到期转移」→ `录入邮箱`
2) 输入邮箱 + 选择当前 Team
3) `join_at`：
   - 不知道就留空（状态会是 `awaiting_join`）
   - 知道就填 ISO：`2026-01-07T12:00:00`（会立刻计算到期日）
4) 点保存

---

## 6. 如何复现/测试“自动退 + 转移”是否有效（不看日志也能确认）

推荐用「到期转移」页签做可控测试：

### 6.1 同步 join_at（确保到期起点正确）
1) 打开后台 → 「到期转移」
2) 点 `同步加入时间`
3) 找到目标邮箱：
   - 若用户已经接受邀请：`join_at` 应出现，`status` 变为 `active`
   - 若未接受邀请：仍为 `awaiting_join`（此时不应进行到期转移）

### 6.2 强制到期（测试按钮）
1) 在目标邮箱行点 `强制到期`（会要求输入口令 `DELLT`）
2) 这会把该邮箱租约立即变为“到期状态”（仅用于测试）

### 6.3 执行转移（测试按钮）
1) 在目标邮箱行点 `执行转移`
2) 预期结果：
   - 如果开启了 `AUTO_TRANSFER_AUTO_LEAVE_OLD_TEAM=true`：
     - 事件里会出现 `left_old_team`（退出旧 Team 成功）或 `leave_old_failed`（失败原因）
   - 然后尝试邀请到新 Team：
     - 成功会出现 `transferred`
     - 失败会出现 `transfer_failed`（原因：无空位 / 邀请失败 / 旧 Team 退出失败等）

### 6.4 查看事件流水（最直观的“证据”）
1) 点该邮箱行 `查看`
2) 看事件表：
   - `joined`：已同步 join_at
   - `left_old_team`：已退出旧 Team（自动退生效）
   - `transferred`：已发送新 Team 邀请
   - `transfer_failed`：失败原因（用于排障）

---

## 7. 常见问题排查

### 7.1 “按钮没反应”
- 先确认你部署的镜像版本包含「到期转移」页签和行内按钮
- 若还有问题，看事件是否有刷新；通常是浏览器缓存旧页面导致（强刷 / 清缓存）

### 7.2 join_at 一直是 “-”
- 用户还没点击邮件接受邀请
- 或 token 无法拉取 invites（会在事件/最后错误里体现）

### 7.3 自动退失败（leave_old_failed）
- 多数是 ChatGPT 后端“成员列表/移除成员”接口权限或路径不匹配
- 需要你提供日志中的 HTTP 状态码/返回片段以便对齐接口
