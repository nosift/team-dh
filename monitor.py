"""
监控和告警模块

功能：
1. Team 席位不足告警
2. 转移失败告警
3. 数据库性能监控
4. 系统健康检查
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

from database import db
from logger import log
import config


@dataclass
class Alert:
    """告警数据结构"""
    level: str  # info, warning, error, critical
    category: str  # team_capacity, transfer_failure, database, system
    title: str
    message: str
    timestamp: datetime
    metadata: Dict = None

    def to_dict(self):
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


class AlertManager:
    """告警管理器"""

    def __init__(self):
        self.alerts: List[Alert] = []
        self.max_alerts = 100  # 最多保留 100 条告警
        self._init_alert_table()

    def _init_alert_table(self):
        """初始化告警表"""
        with db.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS system_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level TEXT NOT NULL,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    resolved_at TIMESTAMP,
                    resolved_by TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_alerts_created
                ON system_alerts(created_at DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_alerts_level_category
                ON system_alerts(level, category)
            """)
            conn.commit()

    def add_alert(self, level: str, category: str, title: str, message: str, metadata: Dict = None):
        """添加告警"""
        alert = Alert(
            level=level,
            category=category,
            title=title,
            message=message,
            timestamp=datetime.now(),
            metadata=metadata or {}
        )

        # 保存到数据库
        import json
        with db.get_connection() as conn:
            conn.execute("""
                INSERT INTO system_alerts (level, category, title, message, metadata)
                VALUES (?, ?, ?, ?, ?)
            """, (level, category, title, message, json.dumps(metadata or {})))
            conn.commit()

        # 保存到内存（用于快速访问）
        self.alerts.append(alert)
        if len(self.alerts) > self.max_alerts:
            self.alerts.pop(0)

        # 记录日志
        log_method = {
            'info': log.info,
            'warning': log.warning,
            'error': log.error,
            'critical': log.error
        }.get(level, log.info)

        log_method(f"[{category.upper()}] {title}: {message}", icon="alert")

    def get_recent_alerts(self, limit: int = 50, level: str = None, category: str = None) -> List[Dict]:
        """获取最近的告警"""
        with db.get_connection() as conn:
            query = "SELECT * FROM system_alerts WHERE 1=1"
            params = []

            if level:
                query += " AND level = ?"
                params.append(level)

            if category:
                query += " AND category = ?"
                params.append(category)

            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

            import json
            alerts = []
            for row in rows:
                alerts.append({
                    'id': row[0],
                    'level': row[1],
                    'category': row[2],
                    'title': row[3],
                    'message': row[4],
                    'metadata': json.loads(row[5]) if row[5] else {},
                    'created_at': row[6],
                    'resolved_at': row[7],
                    'resolved_by': row[8]
                })

            return alerts

    def resolve_alert(self, alert_id: int, resolved_by: str = "system"):
        """标记告警为已解决"""
        with db.get_connection() as conn:
            conn.execute("""
                UPDATE system_alerts
                SET resolved_at = CURRENT_TIMESTAMP, resolved_by = ?
                WHERE id = ?
            """, (resolved_by, alert_id))
            conn.commit()

    def get_alert_stats(self) -> Dict:
        """获取告警统计"""
        with db.get_connection() as conn:
            cursor = conn.execute("""
                SELECT
                    level,
                    COUNT(*) as count
                FROM system_alerts
                WHERE created_at >= datetime('now', '-24 hours')
                AND resolved_at IS NULL
                GROUP BY level
            """)

            stats = {'info': 0, 'warning': 0, 'error': 0, 'critical': 0}
            for row in cursor.fetchall():
                stats[row[0]] = row[1]

            return stats


class Monitor:
    """监控器"""

    def __init__(self):
        self.alert_manager = AlertManager()

    def check_team_capacity(self):
        """检查 Team 席位容量"""
        from team_service import get_team_stats

        for team in config.TEAMS or []:
            team_name = team.get("name")
            if not team_name:
                continue

            try:
                stats = get_team_stats(team_name)
                if not stats:
                    continue

                total = stats.get("total_seats", 0)
                used = stats.get("used_seats", 0)
                available = total - used

                # 计算使用率
                usage_rate = (used / total * 100) if total > 0 else 0

                # 告警阈值
                if usage_rate >= 95:
                    self.alert_manager.add_alert(
                        level='critical',
                        category='team_capacity',
                        title=f'Team {team_name} 席位严重不足',
                        message=f'席位使用率 {usage_rate:.1f}%，仅剩 {available} 个席位',
                        metadata={'team': team_name, 'total': total, 'used': used, 'available': available}
                    )
                elif usage_rate >= 85:
                    self.alert_manager.add_alert(
                        level='warning',
                        category='team_capacity',
                        title=f'Team {team_name} 席位不足',
                        message=f'席位使用率 {usage_rate:.1f}%，剩余 {available} 个席位',
                        metadata={'team': team_name, 'total': total, 'used': used, 'available': available}
                    )

            except Exception as e:
                log.error(f"检查 Team {team_name} 容量失败: {e}")

    def check_transfer_failures(self):
        """检查转移失败的租约"""
        with db.get_connection() as conn:
            # 查找失败的租约
            cursor = conn.execute("""
                SELECT email, team_name, status, last_error, updated_at
                FROM member_leases
                WHERE status = 'failed'
                AND updated_at >= datetime('now', '-24 hours')
            """)

            failures = cursor.fetchall()

            if failures:
                for failure in failures:
                    email, team_name, status, last_error, updated_at = failure

                    self.alert_manager.add_alert(
                        level='error',
                        category='transfer_failure',
                        title=f'用户 {email} 转移失败',
                        message=f'从 Team {team_name} 转移失败: {last_error or "未知错误"}',
                        metadata={
                            'email': email,
                            'team': team_name,
                            'error': last_error,
                            'updated_at': updated_at
                        }
                    )

            # 查找长时间处于 transferring 状态的租约
            cursor = conn.execute("""
                SELECT email, team_name, status, updated_at
                FROM member_leases
                WHERE status = 'transferring'
                AND updated_at < datetime('now', '-1 hour')
            """)

            stuck_transfers = cursor.fetchall()

            if stuck_transfers:
                for transfer in stuck_transfers:
                    email, team_name, status, updated_at = transfer

                    self.alert_manager.add_alert(
                        level='warning',
                        category='transfer_failure',
                        title=f'用户 {email} 转移超时',
                        message=f'转移操作已超过 1 小时仍未完成',
                        metadata={
                            'email': email,
                            'team': team_name,
                            'status': status,
                            'updated_at': updated_at
                        }
                    )

    def check_database_performance(self):
        """检查数据库性能"""
        with db.get_connection() as conn:
            try:
                # 检查数据库大小
                cursor = conn.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
                db_size = cursor.fetchone()[0]
                db_size_mb = db_size / (1024 * 1024)

                if db_size_mb > 500:  # 超过 500MB
                    self.alert_manager.add_alert(
                        level='warning',
                        category='database',
                        title='数据库文件过大',
                        message=f'数据库大小: {db_size_mb:.2f} MB',
                        metadata={'size_mb': db_size_mb}
                    )

                # 检查慢查询（通过查询计划分析）
                start_time = time.time()
                conn.execute("SELECT COUNT(*) FROM member_leases").fetchone()
                query_time = time.time() - start_time

                if query_time > 1.0:  # 超过 1 秒
                    self.alert_manager.add_alert(
                        level='warning',
                        category='database',
                        title='数据库查询缓慢',
                        message=f'简单查询耗时 {query_time:.2f} 秒',
                        metadata={'query_time': query_time}
                    )

                # 检查表大小
                cursor = conn.execute("""
                    SELECT name,
                           (SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=m.name) as count
                    FROM sqlite_master m
                    WHERE type='table'
                """)

                tables = cursor.fetchall()
                for table_name, _ in tables:
                    if table_name.startswith('sqlite_'):
                        continue

                    cursor = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
                    row_count = cursor.fetchone()[0]

                    # 记录大表
                    if row_count > 100000:
                        self.alert_manager.add_alert(
                            level='info',
                            category='database',
                            title=f'表 {table_name} 数据量较大',
                            message=f'当前有 {row_count:,} 条记录',
                            metadata={'table': table_name, 'row_count': row_count}
                        )

            except Exception as e:
                log.error(f"检查数据库性能失败: {e}")

    def check_system_health(self):
        """系统健康检查"""
        with db.get_connection() as conn:
            # 检查最近的兑换活动
            cursor = conn.execute("""
                SELECT COUNT(*)
                FROM redemptions
                WHERE redeemed_at >= datetime('now', '-1 hour')
            """)
            recent_redemptions = cursor.fetchone()[0]

            # 检查待处理的租约
            cursor = conn.execute("""
                SELECT COUNT(*)
                FROM member_leases
                WHERE status = 'pending'
            """)
            pending_leases = cursor.fetchone()[0]

            # 检查到期的租约
            cursor = conn.execute("""
                SELECT COUNT(*)
                FROM member_leases
                WHERE status = 'active'
                AND expires_at <= datetime('now')
            """)
            expired_leases = cursor.fetchone()[0]

            if expired_leases > 10:
                self.alert_manager.add_alert(
                    level='warning',
                    category='system',
                    title='大量租约已到期',
                    message=f'有 {expired_leases} 个租约已到期但未转移',
                    metadata={'expired_count': expired_leases}
                )

            # 检查失败的兑换码
            cursor = conn.execute("""
                SELECT COUNT(*)
                FROM redemption_codes
                WHERE status = 'disabled'
            """)
            disabled_codes = cursor.fetchone()[0]

            log.info(f"系统健康检查: 最近1小时兑换 {recent_redemptions} 次, "
                    f"待处理租约 {pending_leases} 个, "
                    f"已到期租约 {expired_leases} 个, "
                    f"禁用兑换码 {disabled_codes} 个")

    def run_all_checks(self):
        """运行所有检查"""
        log.info("开始运行监控检查...", icon="check")

        try:
            self.check_team_capacity()
            self.check_transfer_failures()
            self.check_database_performance()
            self.check_system_health()

            log.info("监控检查完成", icon="check")
        except Exception as e:
            log.error(f"监控检查失败: {e}")

    def get_dashboard_data(self) -> Dict:
        """获取监控仪表板数据"""
        return {
            'alert_stats': self.alert_manager.get_alert_stats(),
            'recent_alerts': self.alert_manager.get_recent_alerts(limit=20),
            'timestamp': datetime.now().isoformat()
        }


# 全局监控实例
monitor = Monitor()


def run_monitor_loop(interval: int = 300):
    """运行监控循环（每 5 分钟检查一次）"""
    import threading

    def _loop():
        while True:
            try:
                monitor.run_all_checks()
            except Exception as e:
                log.error(f"监控循环出错: {e}")

            time.sleep(interval)

    thread = threading.Thread(target=_loop, daemon=True, name="MonitorThread")
    thread.start()
    log.info(f"监控线程已启动，检查间隔: {interval} 秒", icon="start")


if __name__ == "__main__":
    # 测试监控功能
    monitor.run_all_checks()
    print("\n最近的告警:")
    for alert in monitor.alert_manager.get_recent_alerts(limit=10):
        print(f"[{alert['level'].upper()}] {alert['title']}: {alert['message']}")
