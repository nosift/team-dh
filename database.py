"""
SQLite数据库管理模块
管理兑换码、兑换记录和Team统计
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from pathlib import Path
from logger import log


class Database:
    """数据库管理类"""

    def __init__(self, db_file: str | None = None):
        if db_file is None:
            import config

            db_file = config.get("redemption.database_file", str(config.DATA_DIR / "redemption.db"))

        if db_file != ":memory:":
            try:
                db_path = Path(db_file)
                if not db_path.is_absolute():
                    # 相对路径统一落到 DATA_DIR（容器持久化卷通常挂载到 /data）
                    import config

                    db_path = Path(config.DATA_DIR) / db_path
                db_path.parent.mkdir(parents=True, exist_ok=True)
                db_file = str(db_path)
            except Exception:
                pass

        self.db_file = db_file
        self.init_database()

    @contextmanager
    def get_connection(self):
        """获取数据库连接的上下文管理器"""
        conn = sqlite3.connect(self.db_file, timeout=30.0)  # 增加超时到30秒
        conn.row_factory = sqlite3.Row  # 允许通过列名访问
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            log.error(f"数据库操作失败: {e}")
            raise
        finally:
            conn.close()

    def init_database(self):
        """初始化数据库表"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 创建兑换码表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS redemption_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code VARCHAR(32) UNIQUE NOT NULL,
                    team_name VARCHAR(100) NOT NULL,
                    max_uses INTEGER DEFAULT 1,
                    used_count INTEGER DEFAULT 0,
                    expires_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    status VARCHAR(20) DEFAULT 'active',
                    notes TEXT,
                    locked_by TEXT,
                    locked_until DATETIME
                )
            """)

            # 兼容旧库：补齐并发锁字段 + 自动转移控制字段
            cursor.execute("PRAGMA table_info(redemption_codes)")
            cols = {row["name"] for row in cursor.fetchall()}
            if "locked_by" not in cols:
                cursor.execute("ALTER TABLE redemption_codes ADD COLUMN locked_by TEXT")
            if "locked_until" not in cols:
                cursor.execute("ALTER TABLE redemption_codes ADD COLUMN locked_until DATETIME")
            if "auto_transfer_enabled" not in cols:
                # 默认 1 (启用自动转移) - 保持向后兼容
                cursor.execute("ALTER TABLE redemption_codes ADD COLUMN auto_transfer_enabled INTEGER DEFAULT 1")
                log.info("已添加 auto_transfer_enabled 字段到 redemption_codes 表（默认启用）", icon="upgrade")
            if "group_name" not in cols:
                cursor.execute("ALTER TABLE redemption_codes ADD COLUMN group_name VARCHAR(100)")
                log.info("已添加 group_name 字段到 redemption_codes 表", icon="upgrade")

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

            # 创建索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_codes_group ON redemption_codes(group_name)")

            # 创建兑换记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS redemptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code_id INTEGER NOT NULL,
                    email VARCHAR(255) NOT NULL,
                    team_name VARCHAR(100) NOT NULL,
                    redeemed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    invite_status VARCHAR(20) DEFAULT 'pending',
                    error_message TEXT,
                    ip_address VARCHAR(45),
                    FOREIGN KEY (code_id) REFERENCES redemption_codes(id)
                )
            """)

            # 创建Team统计表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS teams_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    team_name VARCHAR(100) UNIQUE NOT NULL,
                    total_seats INTEGER DEFAULT 0,
                    used_seats INTEGER DEFAULT 0,
                    pending_invites INTEGER DEFAULT 0,
                    available_seats INTEGER DEFAULT 0,
                    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 添加 Team 创建时间字段
            cursor.execute("PRAGMA table_info(teams_stats)")
            teams_stats_cols = {row["name"] for row in cursor.fetchall()}
            if "created_at" not in teams_stats_cols:
                cursor.execute("ALTER TABLE teams_stats ADD COLUMN created_at DATETIME")
                log.info("已添加 created_at 字段到 teams_stats 表")
            if "first_seen_at" not in teams_stats_cols:
                # SQLite 不支持 ALTER TABLE 时使用 CURRENT_TIMESTAMP，需要分两步
                cursor.execute("ALTER TABLE teams_stats ADD COLUMN first_seen_at DATETIME")
                # 为现有记录设置默认值
                cursor.execute("UPDATE teams_stats SET first_seen_at = CURRENT_TIMESTAMP WHERE first_seen_at IS NULL")
                log.info("已添加 first_seen_at 字段到 teams_stats 表")
            if "created_at_source" not in teams_stats_cols:
                cursor.execute("ALTER TABLE teams_stats ADD COLUMN created_at_source VARCHAR(20)")
                log.info("已添加 created_at_source 字段到 teams_stats 表")

            # 添加 Team 状态检测字段
            if "is_active" not in teams_stats_cols:
                cursor.execute("ALTER TABLE teams_stats ADD COLUMN is_active INTEGER DEFAULT 1")
                log.info("已添加 is_active 字段到 teams_stats 表")
            if "status_error" not in teams_stats_cols:
                cursor.execute("ALTER TABLE teams_stats ADD COLUMN status_error TEXT")
                log.info("已添加 status_error 字段到 teams_stats 表")
            if "last_checked_at" not in teams_stats_cols:
                cursor.execute("ALTER TABLE teams_stats ADD COLUMN last_checked_at DATETIME")
                log.info("已添加 last_checked_at 字段到 teams_stats 表")

            # 成员租约：用于"按月到期自动转移到新 Team"
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS member_leases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    team_name VARCHAR(100) NOT NULL,
                    team_account_id VARCHAR(128),
                    created_at DATETIME NOT NULL,
                    invited_at DATETIME NOT NULL,
                    joined_at DATETIME,
                    expires_at DATETIME NOT NULL,
                    status VARCHAR(32) DEFAULT 'pending',
                    transfer_count INTEGER DEFAULT 0,
                    attempts INTEGER DEFAULT 0,
                    next_attempt_at DATETIME,
                    last_error TEXT,
                    last_synced_at DATETIME,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS member_lease_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email VARCHAR(255) NOT NULL,
                    from_team VARCHAR(100),
                    to_team VARCHAR(100),
                    action VARCHAR(32) NOT NULL,
                    message TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 全局锁（防止多 worker 重复执行后台任务）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS app_locks (
                    name VARCHAR(64) PRIMARY KEY,
                    locked_by TEXT,
                    locked_until DATETIME
                )
            """)

            # 兼容旧库：补齐 member_leases 新字段 + 迁移旧数据
            cursor.execute("PRAGMA table_info(member_leases)")
            lease_cols = {row["name"] for row in cursor.fetchall()}

            # 迁移：将旧字段 start_at/join_at 改名为 created_at/joined_at
            if "start_at" in lease_cols and "created_at" not in lease_cols:
                cursor.execute("ALTER TABLE member_leases RENAME COLUMN start_at TO created_at")
            if "join_at" in lease_cols and "joined_at" not in lease_cols:
                cursor.execute("ALTER TABLE member_leases RENAME COLUMN join_at TO joined_at")

            # 刷新字段列表
            cursor.execute("PRAGMA table_info(member_leases)")
            lease_cols = {row["name"] for row in cursor.fetchall()}

            # 添加新字段
            if "created_at" not in lease_cols:
                cursor.execute("ALTER TABLE member_leases ADD COLUMN created_at DATETIME")
            if "invited_at" not in lease_cols:
                # 对于旧数据,用 created_at 作为 invited_at 的默认值
                cursor.execute("ALTER TABLE member_leases ADD COLUMN invited_at DATETIME")
                cursor.execute("UPDATE member_leases SET invited_at = created_at WHERE invited_at IS NULL")
            if "joined_at" not in lease_cols:
                cursor.execute("ALTER TABLE member_leases ADD COLUMN joined_at DATETIME")
            if "last_synced_at" not in lease_cols:
                cursor.execute("ALTER TABLE member_leases ADD COLUMN last_synced_at DATETIME")

            # 状态迁移：awaiting_join → pending, active → active
            cursor.execute("UPDATE member_leases SET status = 'pending' WHERE status = 'awaiting_join'")
            cursor.execute("UPDATE member_leases SET status = 'failed' WHERE status = 'awaiting_transfer'")


            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_code ON redemption_codes(code)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_email ON redemptions(email)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_team ON redemption_codes(team_name)
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_member_leases_expires ON member_leases(expires_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_member_leases_next_attempt ON member_leases(next_attempt_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_member_events_email ON member_lease_events(email)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_member_leases_status ON member_leases(status)")

            log.info("数据库初始化完成", icon="success")

    # ==================== 全局锁（后台任务） ====================

    def acquire_lock(self, name: str, *, lock_by: str, lock_seconds: int = 90) -> bool:
        """尝试获取全局锁（SQLite 多进程/多 worker 共享）。"""
        if not name:
            return False
        now = datetime.now()
        now_str = now.isoformat(sep=" ", timespec="seconds")
        until_str = (now + timedelta(seconds=max(5, int(lock_seconds or 90)))).isoformat(
            sep=" ", timespec="seconds"
        )
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO app_locks (name, locked_by, locked_until)
                VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    locked_by = excluded.locked_by,
                    locked_until = excluded.locked_until
                WHERE app_locks.locked_until IS NULL OR app_locks.locked_until <= ?
            """,
                (name, lock_by, until_str, now_str),
            )
            return cursor.rowcount == 1

    def release_lock(self, name: str, *, lock_by: str):
        """释放锁（仅释放自己持有的锁）。"""
        if not name:
            return
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE app_locks SET locked_by = NULL, locked_until = NULL WHERE name = ? AND locked_by = ?",
                (name, lock_by),
            )

    # ==================== 成员租约（按月转移） ====================

    def upsert_member_lease(
        self,
        *,
        email: str,
        team_name: str,
        team_account_id: str | None,
        created_at: datetime,
        invited_at: datetime,
        expires_at: datetime,
        status: str = "pending",
    ):
        """创建或更新租约

        新模型:
        - created_at: 租约创建时间(兑换时间)
        - invited_at: 发送邀请时间
        - joined_at: 用户接受邀请时间(初始为 NULL)
        - expires_at: 到期时间(初始预估,实际以 joined_at + term_months 为准)
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO member_leases (email, team_name, team_account_id, created_at, invited_at, expires_at, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(email) DO UPDATE SET
                    team_name = excluded.team_name,
                    team_account_id = excluded.team_account_id,
                    created_at = excluded.created_at,
                    invited_at = excluded.invited_at,
                    expires_at = excluded.expires_at,
                    status = excluded.status,
                    updated_at = CURRENT_TIMESTAMP
            """,
                (
                    email,
                    team_name,
                    team_account_id,
                    created_at.isoformat(sep=" ", timespec="seconds"),
                    invited_at.isoformat(sep=" ", timespec="seconds"),
                    expires_at.isoformat(sep=" ", timespec="seconds"),
                    status,
                ),
            )

    def add_member_lease_event(
        self,
        *,
        email: str,
        action: str,
        from_team: str | None = None,
        to_team: str | None = None,
        message: str | None = None,
    ):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO member_lease_events (email, from_team, to_team, action, message)
                VALUES (?, ?, ?, ?, ?)
            """,
                (email, from_team, to_team, action, message),
            )

    def list_due_member_leases(self, *, limit: int = 20) -> List[Dict[str, Any]]:
        """获取已到期的租约(只包含 active 状态且 joined_at 不为 NULL 的)"""
        now = datetime.now().isoformat(sep=" ", timespec="seconds")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT *
                FROM member_leases
                WHERE status = 'active'
                  AND joined_at IS NOT NULL
                  AND expires_at <= ?
                  AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                ORDER BY expires_at ASC
                LIMIT ?
            """,
                (now, now, int(limit)),
            )
            return [dict(row) for row in cursor.fetchall()]

    def list_member_leases_pending_join(self, *, limit: int = 50) -> List[Dict[str, Any]]:
        """获取等待用户接受邀请的租约(status=pending 且 joined_at 为 NULL)"""
        return self.list_member_leases_pending_join_with_due(limit=limit, include_not_due=False)

    def list_member_leases_pending_join_with_due(self, *, limit: int = 50, include_not_due: bool = False) -> List[Dict[str, Any]]:
        """获取等待同步的租约"""
        now = datetime.now().isoformat(sep=" ", timespec="seconds")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if include_not_due:
                cursor.execute(
                    """
                    SELECT *
                    FROM member_leases
                    WHERE status = 'pending'
                      AND joined_at IS NULL
                    ORDER BY updated_at DESC
                    LIMIT ?
                """,
                    (int(limit),),
                )
            else:
                cursor.execute(
                    """
                    SELECT *
                    FROM member_leases
                    WHERE status = 'pending'
                      AND joined_at IS NULL
                      AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                    ORDER BY updated_at DESC
                    LIMIT ?
                """,
                    (now, int(limit)),
                )
            return [dict(row) for row in cursor.fetchall()]

    def defer_member_lease_join_sync(self, *, email: str, next_attempt_at: datetime, last_error: str | None = None) -> bool:
        """延迟下次同步尝试(用于 pending 状态)"""
        email = (email or "").strip().lower()
        if not email:
            return False
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE member_leases
                SET next_attempt_at = ?,
                    last_error = ?,
                    last_synced_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE email = ?
                  AND status = 'pending'
            """,
                (
                    next_attempt_at.isoformat(sep=" ", timespec="seconds"),
                    last_error,
                    email,
                ),
            )
            return cursor.rowcount == 1

    def update_member_lease_joined(
        self,
        *,
        email: str,
        joined_at: datetime,
        expires_at: datetime,
        from_team: str | None = None,
        event_action: str = "joined",
        event_message: str | None = None,
    ):
        """更新租约为已加入状态

        注意: 现在只更新 joined_at 和 expires_at, 不再覆盖 created_at
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE member_leases
                SET joined_at = ?,
                    expires_at = ?,
                    status = 'active',
                    attempts = 0,
                    next_attempt_at = NULL,
                    last_error = NULL,
                    last_synced_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE email = ?
            """,
                (
                    joined_at.isoformat(sep=" ", timespec="seconds"),
                    expires_at.isoformat(sep=" ", timespec="seconds"),
                    email,
                ),
            )

        self.add_member_lease_event(
            email=email,
            action=event_action,
            from_team=from_team,
            to_team=None,
            message=event_message or f"检测到加入时间：{joined_at.isoformat(sep=' ', timespec='seconds')}",
        )

    def get_member_lease(self, email: str) -> Optional[Dict[str, Any]]:
        email = (email or "").strip().lower()
        if not email:
            return None
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM member_leases WHERE email = ?", (email,))
            row = cursor.fetchone()
            return dict(row) if row else None


    def mark_member_lease_transferring(self, email: str) -> bool:
        """标记租约为转移中状态"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE member_leases
                SET status = 'transferring', updated_at = CURRENT_TIMESTAMP
                WHERE email = ?
                  AND status = 'active'
            """,
                (email,),
            )
            return cursor.rowcount == 1

    def update_member_lease_transfer_success(
        self,
        *,
        email: str,
        new_team_name: str,
        new_team_account_id: str | None,
        invited_at: datetime,
        expires_at: datetime,
    ):
        """转移成功: 更新为新 Team, 重置为 pending 状态"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE member_leases
                SET team_name = ?,
                    team_account_id = ?,
                    invited_at = ?,
                    joined_at = NULL,
                    expires_at = ?,
                    status = 'pending',
                    transfer_count = transfer_count + 1,
                    attempts = 0,
                    next_attempt_at = NULL,
                    last_error = NULL,
                    last_synced_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE email = ?
            """,
                (
                    new_team_name,
                    new_team_account_id,
                    invited_at.isoformat(sep=" ", timespec="seconds"),
                    expires_at.isoformat(sep=" ", timespec="seconds"),
                    email,
                ),
            )

    def update_member_lease_transfer_failure(
        self,
        *,
        email: str,
        message: str,
        next_attempt_at: datetime,
    ):
        """转移失败: 标记为 failed 状态, 记录重试时间"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE member_leases
                SET status = 'failed',
                    attempts = attempts + 1,
                    next_attempt_at = ?,
                    last_error = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE email = ?
            """,
                (next_attempt_at.isoformat(sep=" ", timespec="seconds"), message, email),
            )

    def update_member_lease_status(self, email: str, status: str):
        """更新租约状态"""
        email = (email or "").strip().lower()
        if not email:
            return
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE member_leases
                SET status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE email = ?
            """,
                (status, email),
            )

    def list_member_leases(self, *, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT *
                FROM member_leases
                ORDER BY updated_at DESC, email ASC
                LIMIT ? OFFSET ?
            """,
                (int(limit), int(offset)),
            )
            return [dict(row) for row in cursor.fetchall()]

    def list_member_lease_events(self, *, email: str | None = None, limit: int = 200, offset: int = 0) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if email:
                cursor.execute(
                    """
                    SELECT *
                    FROM member_lease_events
                    WHERE email = ?
                    ORDER BY created_at DESC, id DESC
                    LIMIT ? OFFSET ?
                """,
                    ((email or "").strip().lower(), int(limit), int(offset)),
                )
            else:
                cursor.execute(
                    """
                    SELECT *
                    FROM member_lease_events
                    ORDER BY created_at DESC, id DESC
                    LIMIT ? OFFSET ?
                """,
                    (int(limit), int(offset)),
                )
            return [dict(row) for row in cursor.fetchall()]

    def upsert_member_lease_manual(
        self,
        *,
        email: str,
        team_name: str,
        team_account_id: str | None,
        join_at: datetime | None,
        expires_at: datetime | None,
    ):
        """
        管理后台手动录入/修正租约。
        - join_at 为空：标记为 awaiting_join，等待后台同步 join_at
        - join_at 非空：直接进入 active（并计算/使用 expires_at）
        """
        email = (email or "").strip().lower()
        team_name = (team_name or "").strip()
        if not email or not team_name:
            raise ValueError("email/team_name 不能为空")

        if join_at and not expires_at:
            raise ValueError("join_at 不为空时必须提供 expires_at")

        status = "active" if join_at else "awaiting_join"
        start_at = join_at or datetime.now()
        exp = expires_at or (datetime.now() + timedelta(days=30))

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO member_leases (email, team_name, team_account_id, start_at, join_at, expires_at, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(email) DO UPDATE SET
                    team_name = excluded.team_name,
                    team_account_id = excluded.team_account_id,
                    start_at = excluded.start_at,
                    join_at = excluded.join_at,
                    expires_at = excluded.expires_at,
                    status = excluded.status,
                    attempts = 0,
                    next_attempt_at = NULL,
                    last_error = NULL,
                    updated_at = CURRENT_TIMESTAMP
            """,
                (
                    email,
                    team_name,
                    team_account_id,
                    start_at.isoformat(sep=" ", timespec="seconds"),
                    (join_at.isoformat(sep=" ", timespec="seconds") if join_at else None),
                    exp.isoformat(sep=" ", timespec="seconds"),
                    status,
                ),
            )

    def delete_member_lease(self, *, email: str, delete_events: bool = True) -> bool:
        """删除某邮箱的租约（可选同时删除其事件记录）。"""
        email = (email or "").strip().lower()
        if not email:
            return False
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM member_leases WHERE email = ?", (email,))
            ok = cursor.rowcount == 1
            if delete_events:
                cursor.execute("DELETE FROM member_lease_events WHERE email = ?", (email,))
        return ok

    def force_expire_member_lease(self, *, email: str):
        """测试用：将租约标记为立即到期（使其进入到期转移队列）。"""
        email = (email or "").strip().lower()
        if not email:
            raise ValueError("email 不能为空")
        now = datetime.now().isoformat(sep=" ", timespec="seconds")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE member_leases
                SET expires_at = ?,
                    status = CASE
                        WHEN status = 'awaiting_join' THEN status
                        ELSE 'active'
                    END,
                    next_attempt_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE email = ?
            """,
                (now, email),
            )
            if cursor.rowcount != 1:
                raise ValueError("租约不存在")

    def _ensure_code_lock_columns(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(redemption_codes)")
            cols = {row["name"] for row in cursor.fetchall()}
            if "locked_by" not in cols:
                cursor.execute("ALTER TABLE redemption_codes ADD COLUMN locked_by TEXT")
            if "locked_until" not in cols:
                cursor.execute("ALTER TABLE redemption_codes ADD COLUMN locked_until DATETIME")

    # ==================== 兑换码管理 ====================

    def create_code(
        self,
        code: str,
        team_name: str,
        max_uses: int = 1,
        expires_at: Optional[datetime] = None,
        notes: Optional[str] = None,
        auto_transfer_enabled: bool = True,
    ) -> int:
        """创建兑换码"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO redemption_codes (code, team_name, max_uses, expires_at, notes, auto_transfer_enabled)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (code, team_name, max_uses, expires_at, notes, 1 if auto_transfer_enabled else 0),
            )
            return cursor.lastrowid

    def get_code(self, code: str) -> Optional[Dict[str, Any]]:
        """获取兑换码信息"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM redemption_codes WHERE code = ?
            """,
                (code,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def verify_code(self, code: str) -> tuple[bool, str]:
        """
        验证兑换码是否有效
        返回: (是否有效, 错误信息)
        """
        code_info = self.get_code(code)

        if not code_info:
            return False, "兑换码不存在"

        status = code_info.get("status")
        if status != "active":
            if status == "used_up":
                return False, "兑换码已用完"
            if status == "expired":
                return False, "兑换码已过期"
            if status == "disabled":
                return False, "兑换码已禁用"
            if status == "deleted":
                return False, "兑换码已删除"
            return False, f"兑换码状态异常: {status}"

        # 检查过期时间
        if code_info["expires_at"]:
            expires_at = datetime.fromisoformat(code_info["expires_at"])
            if datetime.now() > expires_at:
                # 自动标记为过期
                self.update_code_status(code, "expired")
                return False, "兑换码已过期"

        # 检查使用次数
        if code_info["used_count"] >= code_info["max_uses"]:
            # 自动标记为已用完，便于后台展示
            if code_info.get("status") == "active":
                self.update_code_status(code, "used_up")
            return False, "兑换码已用完"

        return True, "有效"

    def reserve_code(self, code: str, *, lock_by: str, lock_seconds: int = 120) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        以数据库级锁的方式预占兑换码，避免并发兑换造成超发。

        - 成功: 返回 (True, "OK", code_info)
        - 失败: 返回 (False, message, None)

        注意：该预占仅用于短时间内串行化兑换流程，需要在兑换结束后调用
        consume_reserved_code/release_reserved_code 清理锁。
        """
        if not code:
            return False, "兑换码不能为空", None

        self._ensure_code_lock_columns()

        now = datetime.now()
        now_str = now.isoformat(sep=" ", timespec="seconds")
        lock_until = (now + timedelta(seconds=max(5, int(lock_seconds or 120)))).isoformat(
            sep=" ", timespec="seconds"
        )

        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE redemption_codes
                SET locked_by = ?, locked_until = ?
                WHERE code = ?
                  AND status = 'active'
                  AND (expires_at IS NULL OR expires_at > ?)
                  AND used_count < max_uses
                  AND (locked_until IS NULL OR locked_until <= ?)
            """,
                (lock_by, lock_until, code, now_str, now_str),
            )

            if cursor.rowcount == 1:
                cursor.execute("SELECT * FROM redemption_codes WHERE code = ?", (code,))
                row = cursor.fetchone()
                return True, "OK", dict(row) if row else None

            cursor.execute("SELECT * FROM redemption_codes WHERE code = ?", (code,))
            row = cursor.fetchone()
            if not row:
                return False, "兑换码不存在", None

            code_info = dict(row)
            status = code_info.get("status")
            if status != "active":
                return False, f"兑换码状态异常: {status}", None

            if code_info.get("expires_at"):
                try:
                    expires_at = datetime.fromisoformat(code_info["expires_at"])
                    if datetime.now() > expires_at:
                        cursor.execute(
                            "UPDATE redemption_codes SET status = 'expired' WHERE code = ?",
                            (code,),
                        )
                        return False, "兑换码已过期", None
                except Exception:
                    pass

            used_count = int(code_info.get("used_count") or 0)
            max_uses = int(code_info.get("max_uses") or 0)
            if used_count >= max_uses:
                cursor.execute(
                    "UPDATE redemption_codes SET status = 'used_up' WHERE code = ? AND status = 'active'",
                    (code,),
                )
                return False, "兑换码已用完", None

            locked_until_val = code_info.get("locked_until")
            if locked_until_val:
                try:
                    locked_until_dt = datetime.fromisoformat(locked_until_val)
                    if locked_until_dt > datetime.now():
                        return False, "兑换码正在被使用，请稍后再试", None
                except Exception:
                    return False, "兑换码正在被使用，请稍后再试", None

            return False, "兑换码暂不可用，请稍后重试", None

    def release_reserved_code(self, code: str, *, lock_by: str):
        """释放预占的兑换码锁"""
        if not code:
            return
        self._ensure_code_lock_columns()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE redemption_codes
                SET locked_by = NULL, locked_until = NULL
                WHERE code = ? AND locked_by = ?
            """,
                (code, lock_by),
            )

    def consume_reserved_code(self, code: str, *, lock_by: str) -> bool:
        """
        消费已预占的兑换码：增加 used_count 并释放锁。
        仅当 locked_by 匹配时生效，返回是否成功。
        """
        if not code:
            return False
        self._ensure_code_lock_columns()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE redemption_codes
                SET used_count = used_count + 1,
                    status = CASE
                        WHEN (used_count + 1) >= max_uses THEN 'used_up'
                        ELSE status
                    END,
                    locked_by = NULL,
                    locked_until = NULL
                WHERE code = ? AND locked_by = ?
            """,
                (code, lock_by),
            )
            return cursor.rowcount == 1

    def update_code_status(self, code: str, status: str):
        """更新兑换码状态"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE redemption_codes SET status = ? WHERE code = ?
            """,
                (status, code),
            )

    def increment_code_usage(self, code: str):
        """增加兑换码使用次数"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE redemption_codes
                SET used_count = used_count + 1
                WHERE code = ?
            """,
                (code,),
            )

            # 达到上限后自动标记为已用完（仅影响展示与后续校验）
            cursor.execute(
                "SELECT used_count, max_uses, status FROM redemption_codes WHERE code = ?",
                (code,),
            )
            row = cursor.fetchone()
            if row:
                used_count = row["used_count"]
                max_uses = row["max_uses"]
                status = row["status"]
                if status == "active" and used_count >= max_uses:
                    cursor.execute(
                        "UPDATE redemption_codes SET status = 'used_up' WHERE code = ?",
                        (code,),
                    )

    def list_codes(
        self,
        team_name: Optional[str] = None,
        status: Optional[str] = None,
        include_deleted: bool = False,
    ) -> List[Dict[str, Any]]:
        """列出兑换码"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM redemption_codes WHERE 1=1"
            params = []

            if team_name:
                query += " AND team_name = ?"
                params.append(team_name)

            if status:
                query += " AND status = ?"
                params.append(status)
            elif not include_deleted:
                query += " AND status != 'deleted'"

            query += " ORDER BY created_at DESC"

            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def delete_code(self, code: str, hard: bool = False) -> bool:
        """
        删除兑换码。

        - hard=False: 软删除（将 status 标记为 deleted）
        - hard=True: 物理删除（同时删除关联兑换记录）
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT id FROM redemption_codes WHERE code = ?", (code,))
            row = cursor.fetchone()
            if not row:
                return False

            code_id = row["id"] if isinstance(row, sqlite3.Row) else row[0]

            if hard:
                cursor.execute("DELETE FROM redemptions WHERE code_id = ?", (code_id,))
                cursor.execute("DELETE FROM redemption_codes WHERE id = ?", (code_id,))
            else:
                cursor.execute("UPDATE redemption_codes SET status = 'deleted' WHERE id = ?", (code_id,))

            return True

    def soft_delete_codes_by_team_names(self, team_names: List[str]) -> int:
        """按 team_name 批量软删除兑换码（status=deleted），返回影响行数。"""
        names = [n for n in (team_names or []) if n]
        if not names:
            return 0
        with self.get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ",".join(["?"] * len(names))
            cursor.execute(
                f"""
                UPDATE redemption_codes
                SET status = 'deleted'
                WHERE status != 'deleted' AND team_name IN ({placeholders})
            """,
                names,
            )
            return cursor.rowcount or 0

    def delete_team_stats_by_names(self, team_names: List[str]) -> int:
        """按 team_name 批量删除 Team 统计行，返回影响行数。"""
        names = [n for n in (team_names or []) if n]
        if not names:
            return 0
        with self.get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ",".join(["?"] * len(names))
            cursor.execute(f"DELETE FROM teams_stats WHERE team_name IN ({placeholders})", names)
            return cursor.rowcount or 0

    # ==================== 兑换记录管理 ====================

    def create_redemption(
        self,
        code_id: int,
        email: str,
        team_name: str,
        ip_address: Optional[str] = None,
    ) -> int:
        """创建兑换记录"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO redemptions (code_id, email, team_name, ip_address)
                VALUES (?, ?, ?, ?)
            """,
                (code_id, email, team_name, ip_address),
            )
            return cursor.lastrowid

    def update_redemption_status(
        self,
        redemption_id: int,
        status: str,
        error_message: Optional[str] = None,
    ):
        """更新兑换状态"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE redemptions
                SET invite_status = ?, error_message = ?
                WHERE id = ?
            """,
                (status, error_message, redemption_id),
            )

    def check_email_redeemed(self, email: str) -> bool:
        """检查邮箱是否已兑换过"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*) as count FROM redemptions
                WHERE email = ? AND invite_status = 'success'
            """,
                (email,),
            )
            result = cursor.fetchone()
            return result["count"] > 0

    def count_ip_redemptions(self, ip_address: str, hours: int = 1) -> int:
        """统计IP在指定小时内的兑换次数"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            time_threshold = datetime.now() - timedelta(hours=hours)
            cursor.execute(
                """
                SELECT COUNT(*) as count FROM redemptions
                WHERE ip_address = ? AND redeemed_at > ?
            """,
                (ip_address, time_threshold),
            )
            result = cursor.fetchone()
            return result["count"]

    def list_redemptions(
        self, limit: int = 100, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """列出兑换记录"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    r.*,
                    rc.code,
                    rc.team_name
                FROM redemptions r
                JOIN redemption_codes rc ON r.code_id = rc.id
                ORDER BY r.redeemed_at DESC
                LIMIT ? OFFSET ?
            """,
                (limit, offset),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_redemptions_by_email(self, email: str, limit: int = 20) -> List[Dict[str, Any]]:
        """根据邮箱查询兑换记录"""
        email = (email or "").strip().lower()
        if not email:
            return []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    r.*,
                    rc.code,
                    rc.team_name
                FROM redemptions r
                JOIN redemption_codes rc ON r.code_id = rc.id
                WHERE LOWER(r.email) = ?
                ORDER BY r.redeemed_at DESC
                LIMIT ?
            """,
                (email, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    def bulk_delete_redemptions(self, *, team_names: Optional[List[str]] = None) -> int:
        """批量删除兑换记录，返回删除条数。"""
        names = [n for n in (team_names or []) if n]
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if names:
                placeholders = ",".join(["?"] * len(names))
                cursor.execute(f"DELETE FROM redemptions WHERE team_name IN ({placeholders})", names)
            else:
                cursor.execute("DELETE FROM redemptions")
            return cursor.rowcount or 0

    def delete_redemption(self, redemption_id: int) -> bool:
        """删除单条兑换记录"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM redemptions WHERE id = ?", (int(redemption_id),))
            return (cursor.rowcount or 0) > 0

    # ==================== Team统计管理 ====================

    def update_team_stats(
        self,
        team_name: str,
        total_seats: int,
        used_seats: int,
        pending_invites: int,
    ):
        """更新Team统计信息"""
        available_seats = total_seats - used_seats - pending_invites

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO teams_stats (team_name, total_seats, used_seats, pending_invites, available_seats)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(team_name) DO UPDATE SET
                    total_seats = ?,
                    used_seats = ?,
                    pending_invites = ?,
                    available_seats = ?,
                    last_updated = CURRENT_TIMESTAMP
            """,
                (
                    team_name,
                    total_seats,
                    used_seats,
                    pending_invites,
                    available_seats,
                    total_seats,
                    used_seats,
                    pending_invites,
                    available_seats,
                ),
            )

    def get_team_stats(self, team_name: str) -> Optional[Dict[str, Any]]:
        """获取Team统计信息"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM teams_stats WHERE team_name = ?
            """,
                (team_name,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_team_stats(self) -> List[Dict[str, Any]]:
        """列出所有Team统计"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM teams_stats ORDER BY team_name
            """
            )
            return [dict(row) for row in cursor.fetchall()]

    # ==================== 统计查询 ====================

    def get_dashboard_stats(self) -> Dict[str, Any]:
        """获取仪表盘统计数据"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 总兑换码数
            cursor.execute("SELECT COUNT(*) as count FROM redemption_codes WHERE status != 'deleted'")
            total_codes = cursor.fetchone()["count"]

            # 激活的兑换码数
            cursor.execute(
                "SELECT COUNT(*) as count FROM redemption_codes WHERE status = 'active'"
            )
            active_codes = cursor.fetchone()["count"]

            # 兑换码状态细分
            cursor.execute("SELECT COUNT(*) as count FROM redemption_codes WHERE status = 'used_up'")
            used_up_codes = cursor.fetchone()["count"]
            cursor.execute("SELECT COUNT(*) as count FROM redemption_codes WHERE status = 'disabled'")
            disabled_codes = cursor.fetchone()["count"]
            cursor.execute("SELECT COUNT(*) as count FROM redemption_codes WHERE status = 'expired'")
            expired_codes = cursor.fetchone()["count"]

            # 总兑换次数
            cursor.execute("SELECT COUNT(*) as count FROM redemptions")
            total_redemptions = cursor.fetchone()["count"]

            # 成功兑换次数
            cursor.execute(
                "SELECT COUNT(*) as count FROM redemptions WHERE invite_status = 'success'"
            )
            successful_redemptions = cursor.fetchone()["count"]

            # 失败兑换次数
            cursor.execute(
                "SELECT COUNT(*) as count FROM redemptions WHERE invite_status = 'failed'"
            )
            failed_redemptions = cursor.fetchone()["count"]

            # 今日兑换次数
            cursor.execute(
                """
                SELECT COUNT(*) as count FROM redemptions
                WHERE DATE(redeemed_at, 'localtime') = DATE('now', 'localtime')
            """
            )
            today_redemptions = cursor.fetchone()["count"]

            cursor.execute(
                """
                SELECT COUNT(*) as count FROM redemptions
                WHERE invite_status = 'success'
                  AND DATE(redeemed_at, 'localtime') = DATE('now', 'localtime')
            """
            )
            today_successful_redemptions = cursor.fetchone()["count"]

            cursor.execute(
                """
                SELECT COUNT(*) as count FROM redemptions
                WHERE invite_status = 'failed'
                  AND DATE(redeemed_at, 'localtime') = DATE('now', 'localtime')
            """
            )
            today_failed_redemptions = cursor.fetchone()["count"]

            return {
                "total_codes": total_codes,
                "active_codes": active_codes,
                "used_up_codes": used_up_codes,
                "disabled_codes": disabled_codes,
                "expired_codes": expired_codes,
                "total_redemptions": total_redemptions,
                "successful_redemptions": successful_redemptions,
                "failed_redemptions": failed_redemptions,
                "today_redemptions": today_redemptions,
                "today_successful_redemptions": today_successful_redemptions,
                "today_failed_redemptions": today_failed_redemptions,
            }

    # ==================== Team 创建时间管理 ====================

    def update_team_created_at(self, team_name: str, created_at: datetime, source: str = "api"):
        """更新 Team 创建时间

        Args:
            team_name: Team 名称
            created_at: 创建时间
            source: 数据来源 (api/estimated/manual)
        """
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE teams_stats
                SET created_at = ?, created_at_source = ?
                WHERE team_name = ?
            """, (created_at, source, team_name))

    def get_team_created_at(self, team_name: str) -> Optional[Dict[str, Any]]:
        """获取 Team 创建时间"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT created_at, first_seen_at, created_at_source
                FROM teams_stats
                WHERE team_name = ?
            """, (team_name,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_earliest_redemption(self, team_name: str) -> Optional[datetime]:
        """获取最早的兑换记录时间"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT MIN(redeemed_at) as earliest
                FROM redemptions
                WHERE team_name = ?
            """, (team_name,))
            row = cursor.fetchone()
            if row and row["earliest"]:
                return datetime.fromisoformat(row["earliest"])
            return None

    def get_earliest_lease(self, team_name: str) -> Optional[datetime]:
        """获取最早的成员加入时间"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT MIN(joined_at) as earliest
                FROM member_leases
                WHERE team_name = ? AND joined_at IS NOT NULL
            """, (team_name,))
            row = cursor.fetchone()
            if row and row["earliest"]:
                return datetime.fromisoformat(row["earliest"])
            return None

    def update_team_status(
        self,
        team_name: str,
        is_active: bool,
        status_error: Optional[str] = None,
        last_checked_at: Optional[datetime] = None
    ):
        """更新 Team 状态"""
        if last_checked_at is None:
            last_checked_at = datetime.now()

        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO teams_stats (team_name, is_active, status_error, last_checked_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(team_name) DO UPDATE SET
                    is_active = ?,
                    status_error = ?,
                    last_checked_at = ?
            """, (
                team_name,
                1 if is_active else 0,
                status_error,
                last_checked_at.isoformat() if isinstance(last_checked_at, datetime) else last_checked_at,
                1 if is_active else 0,
                status_error,
                last_checked_at.isoformat() if isinstance(last_checked_at, datetime) else last_checked_at
            ))

    def get_team_status(self, team_name: str) -> Optional[Dict[str, Any]]:
        """获取 Team 状态"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT is_active, status_error, last_checked_at
                FROM teams_stats
                WHERE team_name = ?
            """, (team_name,))
            row = cursor.fetchone()
            return dict(row) if row else None

    # ==================== 兑换码分组管理 ====================

    def list_code_groups(self) -> List[Dict[str, Any]]:
        """获取所有分组及其兑换码数量"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT
                    g.id,
                    g.name,
                    g.description,
                    g.color,
                    g.created_at,
                    COUNT(c.id) as code_count,
                    SUM(CASE WHEN c.status = 'active' THEN 1 ELSE 0 END) as active_count,
                    SUM(CASE WHEN c.status = 'used_up' THEN 1 ELSE 0 END) as used_up_count
                FROM code_groups g
                LEFT JOIN redemption_codes c ON c.group_name = g.name AND c.status != 'deleted'
                GROUP BY g.id, g.name, g.description, g.color, g.created_at
                ORDER BY g.created_at DESC
            """)
            return [dict(row) for row in cursor.fetchall()]

    def get_code_group(self, group_id: int) -> Optional[Dict[str, Any]]:
        """获取单个分组信息"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM code_groups WHERE id = ?
            """, (group_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_code_group_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """根据名称获取分组"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM code_groups WHERE name = ?
            """, (name,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def create_code_group(self, name: str, description: str = "", color: str = "#000000") -> int:
        """创建兑换码分组

        Args:
            name: 分组名称（唯一）
            description: 分组描述
            color: 分组颜色（十六进制）

        Returns:
            分组 ID

        Raises:
            sqlite3.IntegrityError: 如果分组名称已存在
        """
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO code_groups (name, description, color)
                VALUES (?, ?, ?)
            """, (name, description, color))
            return cursor.lastrowid

    def update_code_group(self, group_id: int, name: str = None, description: str = None, color: str = None) -> bool:
        """更新分组信息

        Args:
            group_id: 分组 ID
            name: 新名称（可选）
            description: 新描述（可选）
            color: 新颜色（可选）

        Returns:
            是否更新成功
        """
        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if color is not None:
            updates.append("color = ?")
            params.append(color)

        if not updates:
            return False

        params.append(group_id)

        with self.get_connection() as conn:
            cursor = conn.execute(f"""
                UPDATE code_groups
                SET {', '.join(updates)}
                WHERE id = ?
            """, params)
            return cursor.rowcount > 0

    def delete_code_group(self, group_id: int, clear_codes: bool = False) -> bool:
        """删除分组

        Args:
            group_id: 分组 ID
            clear_codes: 是否同时清除该分组下所有兑换码的分组标记

        Returns:
            是否删除成功
        """
        with self.get_connection() as conn:
            # 获取分组名称
            cursor = conn.execute("SELECT name FROM code_groups WHERE id = ?", (group_id,))
            row = cursor.fetchone()
            if not row:
                return False

            group_name = row["name"]

            # 清除或保留兑换码的分组标记
            if clear_codes:
                conn.execute("""
                    UPDATE redemption_codes
                    SET group_name = NULL
                    WHERE group_name = ?
                """, (group_name,))

            # 删除分组
            cursor = conn.execute("DELETE FROM code_groups WHERE id = ?", (group_id,))
            return cursor.rowcount > 0

    def batch_update_code_group(self, code_ids: List[int], group_name: Optional[str]) -> int:
        """批量更新兑换码的分组

        Args:
            code_ids: 兑换码 ID 列表
            group_name: 分组名称（None 表示移除分组）

        Returns:
            更新的兑换码数量
        """
        if not code_ids:
            return 0

        with self.get_connection() as conn:
            placeholders = ','.join('?' * len(code_ids))
            cursor = conn.execute(f"""
                UPDATE redemption_codes
                SET group_name = ?
                WHERE id IN ({placeholders})
            """, [group_name] + code_ids)
            return cursor.rowcount

    def list_codes_with_group(
        self,
        team_name: Optional[str] = None,
        status: Optional[str] = None,
        group_name: Optional[str] = None,
        include_deleted: bool = False,
    ) -> List[Dict[str, Any]]:
        """列出兑换码（支持分组筛选）

        Args:
            team_name: Team 名称筛选
            status: 状态筛选
            group_name: 分组名称筛选（None 表示不筛选，"" 表示未分组）
            include_deleted: 是否包含已删除的兑换码

        Returns:
            兑换码列表
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM redemption_codes WHERE 1=1"
            params = []

            if team_name:
                query += " AND team_name = ?"
                params.append(team_name)

            if status:
                query += " AND status = ?"
                params.append(status)
            elif not include_deleted:
                query += " AND status != 'deleted'"

            if group_name is not None:
                if group_name == "":
                    query += " AND (group_name IS NULL OR group_name = '')"
                else:
                    query += " AND group_name = ?"
                    params.append(group_name)

            query += " ORDER BY created_at DESC"

            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]


# 单例实例
db = Database()


if __name__ == "__main__":
    # 测试数据库初始化
    print("正在初始化数据库...")
    test_db = Database("test_redemption.db")
    print("✅ 数据库初始化成功！")

    # 测试创建兑换码
    print("\n测试创建兑换码...")
    code_id = test_db.create_code(
        code="TEST-DEMO-1234",
        team_name="TestTeam",
        max_uses=5,
        expires_at=datetime.now() + timedelta(days=30),
        notes="测试兑换码",
    )
    print(f"✅ 创建兑换码成功, ID: {code_id}")

    # 测试验证兑换码
    print("\n测试验证兑换码...")
    valid, message = test_db.verify_code("TEST-DEMO-1234")
    print(f"验证结果: {valid}, 信息: {message}")

    # 测试获取统计
    print("\n测试获取统计...")
    stats = test_db.get_dashboard_stats()
    print(f"统计数据: {stats}")

    print("\n✅ 所有测试通过!")
